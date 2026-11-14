"""FVG pullback entry — SHADOW only (T-20261114-01, operator 2026-11-14).

Operator setup: 15m entry with a 4h bias. After a CHoCH/BOS, enter on the
pullback into the FVG the break left; SL a little beyond the order block that
made the break; TP1 the next opposite OB/BB; TP2 the liquidity in the trade
direction. Spec: docs/superpowers/specs/2026-11-14-fvg-entry-shadow-design.md.

This module places NO orders and touches no live state: `build_plans` is pure,
`FvgShadowBook` only simulates fills/exits on closed bars and logs
`[fvg shadow] ...` lines for tools/fvg_shadow_report.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from engine.smc_v2 import luxalgo as lx
from engine.smc_v2.exceptions import SLTooFarError
from engine.smc_v2.sl_calc import calc_sl
from engine.smc_v2.zones import ZoneSpec

log = logging.getLogger("efloud.safe_orch")

# Canonical NET cost (ADR-0011), percent units like config `backtest:`. Slippage
# defaults are copied from backtest/slippage.py SlippageConfig (importing the
# backtest package from engine is heavy); tests/engine/test_fvg_entry.py pins parity.
DEFAULT_COMMISSION_PCT = 0.04      # per leg, entry counted as taker (conservative)
DEFAULT_FUNDING_PCT_PER_8H = 0.01
DEFAULT_SL_SLIP_PCT = 0.10         # SL and BE fills
DEFAULT_EXIT_SLIP_PCT = 0.05       # TP1 / TP2 fills; limit entry has no slippage
# SL modes -> variant tag: A = calc_sl (OB anchor +- ATR band), B = operator SL
# (breaking OB far wick +- sl_pct, STRATEGY_INTENT step 6).
SL_VARIANTS = {"atr": "A", "ob_pct": "B"}
# The FVG must come from the displacement that made the break.
FVG_AFTER_BREAK_BARS = 2
# TP2 must sit at least this many R beyond TP1, else it is a second TP1.
TP2_MIN_GAP_R = 0.5

Bar = Tuple[int, float, float, float, float]  # (open_ts_ms, open, high, low, close)


@dataclass(frozen=True)
class FvgPlan:
    symbol: str
    direction: str            # LONG | SHORT
    break_ts: int
    fvg_ts: int
    known_ts: int             # open ts of the bar on which the plan became known
    entry: float
    sl: float
    tp1: float
    tp2: Optional[float]
    tp1_src: str
    tp2_src: str
    fvg: Tuple[float, float]  # (low, high)
    ob: Tuple[float, float]
    bias: str
    trigger: str              # e.g. "internal-BOS"
    variant: str = "A"        # A = atr SL, B = ob_pct SL

    @property
    def key(self) -> tuple:
        return (self.symbol, self.direction, self.break_ts, self.fvg_ts, self.variant)


def _pick_fvg(lux: lx.LuxResult, brk: lx.LuxBreak) -> Optional[lx.LuxFVG]:
    ob = brk.order_block
    cands = [f for f in lux.fvgs
             if f.bias == brk.direction and f.mitigated_idx < 0
             and ob.idx < f.idx <= brk.idx + FVG_AFTER_BREAK_BARS]
    return max(cands, key=lambda f: f.idx) if cands else None


def _tp1(direction: str, entry: float, risk: float, lux: lx.LuxResult,
         min_rr: float) -> Optional[Tuple[float, str]]:
    """Nearest opposite OB or breaker block at >= min_rr * risk."""
    obs = lux.swing_obs + lux.internal_obs
    if direction == "LONG":
        c = [(o.bot, "LUX_OB") for o in obs if o.bias == lx.BEAR and not o.mitigated]
        c += [(o.bot, "LUX_BB") for o in obs if o.bias == lx.BULL and o.mitigated]
        ok = sorted(x for x in c if x[0] - entry >= min_rr * risk)
    else:
        c = [(o.top, "LUX_OB") for o in obs if o.bias == lx.BULL and not o.mitigated]
        c += [(o.top, "LUX_BB") for o in obs if o.bias == lx.BEAR and o.mitigated]
        ok = sorted((x for x in c if entry - x[0] >= min_rr * risk), reverse=True)
    return ok[0] if ok else None


def _tp2(direction: str, tp1: float, risk: float, lux: lx.LuxResult,
         wick_buffer_r: float) -> Tuple[Optional[float], str]:
    """Nearest liquidity (equal highs/lows, swing pivots) beyond TP1."""
    buf = max(0.0, wick_buffer_r) * risk
    gap = TP2_MIN_GAP_R * risk
    if direction == "LONG":
        c = [(e.price_b - buf, "LUX_EQH") for e in lux.equals if e.kind == "EQH"]
        c += [(p - buf, "LUX_LIQ_HIGH") for _, p in lux.swing_high_pivots]
        ok = sorted(x for x in c if x[0] >= tp1 + gap)
    else:
        c = [(e.price_b + buf, "LUX_EQL") for e in lux.equals if e.kind == "EQL"]
        c += [(p + buf, "LUX_LIQ_LOW") for _, p in lux.swing_low_pivots]
        ok = sorted((x for x in c if x[0] <= tp1 - gap), reverse=True)
    return ok[0] if ok else (None, "NONE")


def build_plans(symbol: str, lux: lx.LuxResult, bias: str, bar_ts: Sequence[int],
                atr: float, safety, min_rr: float, wick_buffer_r: float = 0.0,
                slack_bars: int = 1, sl_mode: str = "atr",
                sl_pct: float = 0.002) -> List[FvgPlan]:
    """Plans that became known on the newest closed bar(s) of ``bar_ts``.

    Only fresh plans are returned, so a later FVG mitigation cannot filter the
    history (no survivorship) and a restart does not backfill old setups.
    ``sl_mode`` "atr" = calc_sl (variant A); "ob_pct" = OB far wick -/+ ``sl_pct`` (variant B).
    """
    if sl_mode not in SL_VARIANTS:
        raise ValueError(f"unknown sl_mode {sl_mode!r}")
    if bias not in (lx.BULL, lx.BEAR) or not bar_ts:
        return []
    newest = len(bar_ts) - 1
    out: List[FvgPlan] = []
    for brk in lux.breaks:
        if brk.direction != bias or brk.order_block is None:
            continue
        fvg = _pick_fvg(lux, brk)
        if fvg is None:
            continue
        known = max(brk.idx, fvg.idx + 1)
        if known < newest - slack_bars or known > newest:
            continue
        ob = brk.order_block
        direction = "LONG" if bias == lx.BULL else "SHORT"
        entry = fvg.top if direction == "LONG" else fvg.bot
        anchor = ob.bot if direction == "LONG" else ob.top
        if sl_mode == "ob_pct":
            sl = anchor * (1 - sl_pct) if direction == "LONG" else anchor * (1 + sl_pct)
            risk = (entry - sl) if direction == "LONG" else (sl - entry)
        else:
            try:
                sl = calc_sl(direction, entry, ZoneSpec(low=fvg.bot, high=fvg.top, source="HTF_FVG"),
                             anchor, atr, safety)
            except SLTooFarError:
                continue
            risk = abs(entry - sl)
        if risk <= 0:
            continue
        t1 = _tp1(direction, entry, risk, lux, min_rr)
        if t1 is None:
            continue
        tp2, tp2_src = _tp2(direction, t1[0], risk, lux, wick_buffer_r)
        out.append(FvgPlan(
            symbol=symbol, direction=direction, break_ts=int(bar_ts[brk.idx]),
            fvg_ts=int(bar_ts[fvg.idx]), known_ts=int(bar_ts[known]),
            entry=float(entry), sl=float(sl), tp1=float(t1[0]),
            tp2=None if tp2 is None else float(tp2), tp1_src=t1[1], tp2_src=tp2_src,
            fvg=(float(fvg.bot), float(fvg.top)), ob=(float(ob.bot), float(ob.top)),
            bias=bias, trigger=f"{'internal' if brk.internal else 'swing'}-{brk.kind}",
            variant=SL_VARIANTS[sl_mode],
        ))
    return out


@dataclass
class _Track:
    plan: FvgPlan
    last_ts: int
    state: str = "pending"    # pending | filled | tp1
    bars_waited: int = 0
    realized_r: float = 0.0   # R already booked by the TP1 half
    fill_ts: int = 0          # open ts of the fill bar (funding clock start)


@dataclass
class FvgShadowBook:
    """Simulates the plans on closed bars. In memory; one open plan per (symbol, direction, variant)."""
    timeout_bars: int = 48
    commission_pct: float = DEFAULT_COMMISSION_PCT
    funding_pct_per_8h: float = DEFAULT_FUNDING_PCT_PER_8H
    sl_slip_pct: float = DEFAULT_SL_SLIP_PCT
    exit_slip_pct: float = DEFAULT_EXIT_SLIP_PCT
    _open: Dict[tuple, _Track] = field(default_factory=dict)
    _seen: set = field(default_factory=set)

    def step(self, symbol: str, plans: Sequence[FvgPlan], bars: Sequence[Bar]) -> List[str]:
        lines: List[str] = []
        for p in plans:
            if p.key in self._seen:
                continue
            if len(self._seen) >= 4096:
                # plans are only ever fresh (newest bar +- slack), so keys a day
                # older than this one can never come back
                self._seen = {k for k in self._seen if k[2] >= p.break_ts - 86_400_000}
            self._seen.add(p.key)        # a plan skipped for a busy key stays skipped
            if (p.symbol, p.direction, p.variant) in self._open:
                continue
            self._open[(p.symbol, p.direction, p.variant)] = _Track(plan=p, last_ts=p.known_ts)
            lines.append(self._fmt("setup+", p,
                                   f"entry={p.entry:.8g} sl={p.sl:.8g} tp1={p.tp1:.8g}({p.tp1_src}) "
                                   f"tp2={p.tp2 if p.tp2 is None else f'{p.tp2:.8g}'}({p.tp2_src}) "
                                   f"fvg=[{p.fvg[0]:.8g}-{p.fvg[1]:.8g}] ob=[{p.ob[0]:.8g}-{p.ob[1]:.8g}] "
                                   f"bias4h={p.bias} break={p.trigger}"))
        for k in [k for k in self._open if k[0] == symbol]:
            tr = self._open[k]
            for bar in bars:
                if bar[0] <= tr.last_ts:
                    continue
                tr.last_ts = bar[0]
                done = self._walk(tr, bar, lines)
                if done:
                    del self._open[k]
                    break
        for ln in lines:
            log.info(ln)
        return lines

    @staticmethod
    def _fmt(event: str, p: FvgPlan, rest: str) -> str:
        return f"[fvg shadow] {event} {p.symbol} {p.direction} v={p.variant} {rest}"

    def _cost_pct(self, tr: _Track, reason: str, exit_ts: int) -> float:
        """Canonical round-trip cost in percent of entry notional (ADR-0011): commission both legs
        (entry counted as taker), per-exit slippage (TP1→stop split 0.5/0.5), whole 8h funding periods."""
        stop_slip = self.sl_slip_pct if reason in ("SL", "BE") else self.exit_slip_pct
        # after TP1 half the position left at a TP; only the other half takes `reason`
        slip = (0.5 * self.exit_slip_pct + 0.5 * stop_slip) if tr.state == "tp1" else stop_slip
        # whole 8h funding periods, like backtest/metrics.py (floor) — one cost model for shadow + offline
        periods = max(0, exit_ts - tr.fill_ts) // (8 * 3_600_000)
        return 2 * self.commission_pct + slip + self.funding_pct_per_8h * periods

    def _exit(self, tr: _Track, reason: str, gross_r: float, exit_ts: int, lines: List[str]) -> bool:
        p = tr.plan
        cost_r = self._cost_pct(tr, reason, exit_ts) / 100.0 * p.entry / abs(p.entry - p.sl)
        lines.append(self._fmt("exit", p, f"reason={reason} gross_r={gross_r:+.2f} "
                                          f"net_r={gross_r - cost_r:+.2f} cost_r={cost_r:.2f} "
                                          f"entry={p.entry:.8g}"))
        return True

    def _walk(self, tr: _Track, bar: Bar, lines: List[str]) -> bool:
        p = tr.plan
        _, _o, h, l, _c = bar
        long_ = p.direction == "LONG"
        risk = abs(p.entry - p.sl)

        def reached(level: float, favourable: bool) -> bool:
            # favourable: price moving in the trade direction (TP); else adverse (entry/SL)
            return (h >= level) if long_ == favourable else (l <= level)

        def r_at(level: float) -> float:
            return ((level - p.entry) if long_ else (p.entry - level)) / risk

        if tr.state == "pending":
            if reached(p.entry, favourable=False):
                tr.state = "filled"
                tr.fill_ts = bar[0]
                lines.append(self._fmt("filled", p, f"entry={p.entry:.8g} bar_ts={bar[0]}"))
                # fill bar: intrabar order unknown -> only the stop counts
                if reached(p.sl, favourable=False):
                    return self._exit(tr, "SL", -1.0, bar[0], lines)
                return False
            if reached(p.tp1, favourable=True):
                lines.append(self._fmt("cancelled", p, f"entry={p.entry:.8g} reason=ran_away"))
                return True
            tr.bars_waited += 1
            if tr.bars_waited >= self.timeout_bars:
                lines.append(self._fmt("expired", p, f"entry={p.entry:.8g} bars={tr.bars_waited}"))
                return True
            return False

        if tr.state == "filled":
            if reached(p.sl, favourable=False):
                return self._exit(tr, "SL", -1.0, bar[0], lines)
            if not reached(p.tp1, favourable=True):
                return False
            if p.tp2 is None:
                return self._exit(tr, "TP1", r_at(p.tp1), bar[0], lines)
            tr.state = "tp1"
            tr.realized_r = 0.5 * r_at(p.tp1)
            # same bar: intrabar order unknown -> the break-even stop counts first
            if reached(p.entry, favourable=False):
                return self._exit(tr, "BE", tr.realized_r, bar[0], lines)
            if reached(p.tp2, favourable=True):
                return self._exit(tr, "TP2", tr.realized_r + 0.5 * r_at(p.tp2), bar[0], lines)
            return False

        # tp1: half closed, stop at break-even (mirrors lifecycle.py partial close)
        if reached(p.entry, favourable=False):
            return self._exit(tr, "BE", tr.realized_r, bar[0], lines)
        if reached(p.tp2, favourable=True):
            return self._exit(tr, "TP2", tr.realized_r + 0.5 * r_at(p.tp2), bar[0], lines)
        return False


# ── Shadow step shared by SafeOrchestrator._fvg_shadow_step and tools/fvg_offline_replay.py ──
# One code path so the offline replay and the live shadow cannot drift apart.

def sl_modes_from_config(config: dict) -> List[str]:
    """`smc_v2.fvg_entry_sl_variants` -> build_plans sl_modes; absent -> ["atr"]; unknown ignored."""
    raw = (config.get("smc_v2", {}) or {}).get("fvg_entry_sl_variants")
    if raw is None:
        return ["atr"]
    if isinstance(raw, str):  # YAML scalar typo (`atr` instead of `[atr]`) = one variant
        raw = [raw.strip()]
    modes = []
    for m in raw:
        if m in SL_VARIANTS:
            modes.append(m)
        else:
            log.warning(f"[fvg shadow] unknown sl variant {m!r} ignored")
    return modes


def book_from_config(config: dict, lux_cfg: dict) -> FvgShadowBook:
    bt = config.get("backtest", {}) or {}
    return FvgShadowBook(
        timeout_bars=int(lux_cfg.get("pullback_timeout_bars", 48)),
        commission_pct=float(bt.get("commission_pct", DEFAULT_COMMISSION_PCT)),
        funding_pct_per_8h=float(bt.get("funding_pct_per_8h", DEFAULT_FUNDING_PCT_PER_8H)))


def shadow_step(book: FvgShadowBook, config: dict, lux_cfg: dict, symbol: str,
                df_entry, df_mtf, lux_ltf) -> List[str]:
    """Build the plans for every configured SL variant on the newest closed entry bar and step ``book``."""
    from types import SimpleNamespace

    from engine.smc_v2.atr import wilder_atr

    safety_cfg = config.get("safety", {}) or {}
    risk_cfg = config.get("risk", {}) or {}
    safety = SimpleNamespace(
        sl_atr_buffer=safety_cfg.get("sl_atr_buffer", risk_cfg.get("sl_atr_buffer", 0.5)),
        min_sl_atr=safety_cfg.get("min_sl_atr", 0.5),
        max_sl_atr=safety_cfg.get("max_sl_atr", 5.0),
    )
    bias = lx.analyze(df_mtf, lx.LuxConfig.from_dict(lux_cfg)).swing_trend
    ts = [int(t.timestamp() * 1000) for t in df_entry.index]
    atr = wilder_atr(df_entry, period=14)
    min_rr = float(risk_cfg.get("min_rr", 1.8))
    wick = float(lux_cfg.get("tp_wick_buffer_r", 0.0))
    plans: List[FvgPlan] = []
    if atr:
        for mode in sl_modes_from_config(config):
            extra = {} if mode == "atr" else {"sl_mode": mode}
            plans += build_plans(symbol, lux_ltf, bias, ts, atr, safety, min_rr,
                                 wick_buffer_r=wick, **extra)
    bars = list(zip(ts, df_entry["open"].astype(float), df_entry["high"].astype(float),
                    df_entry["low"].astype(float), df_entry["close"].astype(float)))
    return book.step(symbol, plans, bars[-(book.timeout_bars + 200):])
