#!/usr/bin/env python3
"""Pine lab parity harness — replay / compare / score (spec §7.1).

READ-ONLY against the engine: it imports engine.safe_orchestrator and engine.smc_v2 and
drives the real v2 glue bar by bar. Nothing here edits trading code.

  replay  : OHLCV CSV → python_setups.csv (what the live engine would have set up)
  compare : python_setups.csv + TradingView "List of trades" CSV → match report (gate ≥ 95 %)
  score   : TradingView trade CSVs → NET R metrics; WIN/NO vs a baseline (spec §6.3)
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.safe_orchestrator import SafeOrchestrator  # noqa: E402
from engine.smc_v2 import luxalgo as lx  # noqa: E402
from engine.smc_v2.atr import wilder_atr  # noqa: E402,F401  (re-exported for tests)
from engine.smc_v2.exceptions import InsufficientTPDistanceError, SLTooFarError  # noqa: E402
from engine.smc_v2.setup_state import SetupStateStore  # noqa: E402
from engine.smc_v2.sl_calc import calc_sl  # noqa: E402

logging.getLogger("engine").setLevel(logging.WARNING)

BAR_MS = 900_000
TF_MS = {"4h": 14_400_000, "12h": 43_200_000, "1d": 86_400_000}
HTF_RULE = {"4h": "4h", "12h": "12h", "1d": "1D"}
ROW_FIELDS = ["symbol", "direction", "trigger_bar_ts", "trigger_price", "scope", "kind", "zone_low", "zone_high",
              "tags", "confluence_score", "confirmed_ts", "entry", "sl", "tp1", "tp2", "tp1_source", "tp2_source",
              "atr_source", "drop_reason", "python_guard_rejected"]
NUMERIC = {"trigger_bar_ts": int, "confirmed_ts": int, "confluence_score": int, "trigger_price": float,
           "zone_low": float, "zone_high": float, "entry": float, "sl": float, "tp1": float, "tp2": float}


# ───────────────────────────── data ─────────────────────────────
def load_config(path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_ohlcv_csv(path) -> pd.DataFrame:
    """TradingView 'Export chart data' (time in s) or Binance-style (timestamp in ms) CSV → OHLCV frame."""
    raw = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in raw.columns}
    tcol = cols.get("time") or cols.get("timestamp") or cols.get("date")
    if tcol is None:
        raise ValueError("no time/timestamp column")
    t = pd.to_numeric(raw[tcol], errors="coerce")
    unit = "ms" if t.dropna().abs().max() > 1e12 else "s"
    idx = pd.to_datetime(t, unit=unit)
    out = pd.DataFrame({k: pd.to_numeric(raw[cols[k]], errors="coerce").astype(float)
                        for k in ("open", "high", "low", "close")}, index=idx)
    vcol = cols.get("volume")
    out["volume"] = pd.to_numeric(raw[vcol], errors="coerce").astype(float) if vcol else 0.0
    out.index.name = "timestamp"
    return out.sort_index()


def resample_htf(df15: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Exact HTF bars from 15m bars on UTC-epoch bins (Binance 4h/12h/1d open at 00:00 UTC multiples)."""
    if tf not in TF_MS:
        raise ValueError(f"unsupported htf {tf!r}")
    ms = df15.index.as_unit("ns").asi8 // 1_000_000
    if (ms % BAR_MS != 0).any():
        raise ValueError("15m index is not aligned to 15-minute UTC boundaries")
    agg = df15.resample(HTF_RULE[tf], origin="epoch", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
    last_end = df15.index[-1] + pd.Timedelta(milliseconds=BAR_MS)
    complete = (agg.index + pd.Timedelta(milliseconds=TF_MS[tf])) <= last_end
    return agg[complete]


# ───────────────────────────── replay ─────────────────────────────
def new_store(config: dict, state_dir) -> SetupStateStore:
    cap = int(config.get("smc_v2", {}).get("max_pending_per_symbol", 3))
    return SetupStateStore(path=Path(state_dir) / "lab_candidates.json", max_pending_per_symbol=cap)


class LabOrchestrator(SafeOrchestrator):
    """The real v2 glue (_emit_setup_candidates, _advance_setup_state_tick, confirm_entry, Po3);
    only order placement is replaced by SL/TP recording (mirrors safe_orchestrator._place_v2_entry_order)."""

    def __init__(self, config: dict, store: SetupStateStore, state_dir):
        super().__init__(config=config, state_dir=str(state_dir), order_manager=None,
                         setup_state_store=store, persist=False, freshness_check=False)
        self.records: list[dict] = []
        self.current_bar_ts: int = 0

    def _place_v2_entry_order(self, cand, current_price: float, entry_price: float, df_entry=None):
        engine_cfg = self.config.get("engine", {})
        safety_cfg = self.config.get("safety", {})
        risk_cfg = self.config.get("risk", {})
        lux_cfg = self.config.get("smc_v2", {}).get("luxalgo", {}) or {}
        row = {k: "" for k in ROW_FIELDS}
        reasons = list(cand.reasons) + ["", "", ""]
        m = re.match(r"LUX (\w+) (\w+) (\w+)", reasons[0])
        row.update(symbol=cand.symbol, direction=cand.direction, trigger_bar_ts=int(cand.trigger_bar_ts),
                   trigger_price=float(cand.trigger_price), scope=m.group(1) if m else "", kind=m.group(2) if m else "",
                   zone_low=float(cand.target_zone.low), zone_high=float(cand.target_zone.high),
                   tags=reasons[2].replace("confluence=", ""), confluence_score=int(cand.confluence_score),
                   confirmed_ts=int(self.current_bar_ts), entry=float(entry_price), python_guard_rejected=False)
        atr_15m = None
        if bool(engine_cfg.get("v2_use_real_atr", False)) and df_entry is not None:
            atr_15m = wilder_atr(df_entry, period=14)
        if atr_15m is None:
            floor_pct = float(engine_cfg.get("v2_atr_proxy_floor_pct", 1.0))
            atr_15m = max(entry_price * floor_pct / 100.0, abs(cand.target_zone.high - cand.target_zone.low))
            row["atr_source"] = "PROXY"
        else:
            row["atr_source"] = "WILDER14"
        min_sl_atr = float(safety_cfg.get("min_sl_atr", 0.5))
        try:
            sl = calc_sl(direction=cand.direction, entry_price=entry_price, zone=cand.target_zone,
                         htf_swing_anchor=cand.htf_swing_anchor, atr_15m=atr_15m,
                         config=SimpleNamespace(
                             sl_atr_buffer=safety_cfg.get("sl_atr_buffer", risk_cfg.get("sl_atr_buffer", 0.5)),
                             min_sl_atr=min_sl_atr, max_sl_atr=safety_cfg.get("max_sl_atr", 5.0)))
        except SLTooFarError:
            row["drop_reason"] = "SL_TOO_FAR"
            self.records.append(row)
            return None
        row["sl"] = float(sl)
        row["python_guard_rejected"] = bool(atr_15m > 0 and abs(entry_price - sl) / atr_15m < min_sl_atr)
        lux_now = lx.analyze(df_entry, lx.LuxConfig.from_dict(lux_cfg))
        try:
            tp1, tp2, tags = lx.tp_targets(cand.direction, entry_price, sl, lux_now,
                                           float(risk_cfg.get("min_rr", 1.8)),
                                           wick_buffer_r=float(lux_cfg.get("tp_wick_buffer_r", 0.0)))
        except InsufficientTPDistanceError:
            row["drop_reason"] = "TP_INSUFFICIENT"
            self.records.append(row)
            return None
        row.update(tp1=float(tp1), tp2="" if tp2 is None else float(tp2),
                   tp1_source=tags.get("tp1_source", ""), tp2_source=tags.get("tp2_source", ""))
        self.records.append(row)
        return None


def _snapshot(store: SetupStateStore) -> dict:
    return {(c.direction, c.trigger_bar_ts): c.state for c in store.candidates}


def recency_bars(config: dict) -> int:
    """Same source as the live orchestrator (safe_orchestrator.py: config["risk"]["recency_bars"], default 40)."""
    return int(config.get("risk", {}).get("recency_bars", 40))


def replay(df15: pd.DataFrame, config: dict, *, htf_tf: str = "12h", window: int = 750, ticks_per_bar: int = 3,
           symbol: str = "LAB/USDT", htf_bias_override: Optional[str] = None) -> tuple[list[dict], dict]:
    """Walk closed 15m bars exactly as the live orchestrator sees them (rolling `window` bars, HTF closed bars only)."""
    smc = config.get("smc_v2", {})
    lux_cfg = smc.get("luxalgo", {}) or {}
    cfg_ltf = lx.LuxConfig.from_dict(lux_cfg)
    cfg_htf = lx.LuxConfig.from_dict({**lux_cfg, **(lux_cfg.get("htf") or {})})
    recency = recency_bars(config)
    htf = resample_htf(df15, htf_tf) if htf_bias_override is None else None
    htf_end = None if htf is None else htf.index + pd.Timedelta(milliseconds=TF_MS[htf_tf])
    stats = {"bars": 0, "emitted": 0, "confirmed": 0, "expired": 0}
    with tempfile.TemporaryDirectory() as tmp:
        store = new_store(config, tmp)
        orch = LabOrchestrator(config, store, tmp)
        expired_rows: list[dict] = []
        for t in range(window - 1, len(df15)):
            df_entry = df15.iloc[t - window + 1:t + 1]
            price = float(df_entry["close"].iloc[-1])
            ts = int(df_entry.index[-1].as_unit("ns").value // 1_000_000)
            orch.current_bar_ts = ts
            if htf_bias_override is not None:
                bias = htf_bias_override
            else:
                bar_end = df15.index[t] + pd.Timedelta(milliseconds=BAR_MS)
                df_htf = htf[htf_end <= bar_end].iloc[-window:]
                bias = lx.analyze(df_htf, cfg_htf).swing_trend if len(df_htf) else "UNDEF"
            lux_ltf = lx.analyze(df_entry, cfg_ltf)
            trig_min = max(0, len(df_entry) - 1 - recency)
            stats["bars"] += 1
            for _tick in range(ticks_per_bar):
                before = _snapshot(store)
                orch._advance_setup_state_tick(symbol=symbol, current_price=price, current_bar_ts=ts, df_15m=df_entry)
                for c in store.candidates:
                    if c.state == "EXPIRED" and before.get((c.direction, c.trigger_bar_ts)) != "EXPIRED":
                        row = {k: "" for k in ROW_FIELDS}
                        row.update(symbol=symbol, direction=c.direction, trigger_bar_ts=int(c.trigger_bar_ts),
                                   trigger_price=float(c.trigger_price), zone_low=float(c.target_zone.low),
                                   zone_high=float(c.target_zone.high), confluence_score=int(c.confluence_score),
                                   confirmed_ts=ts, drop_reason="EXPIRED", python_guard_rejected=False)
                        expired_rows.append(row)
                        stats["expired"] += 1
                store.prune()
                cands = lx.generate_candidates(
                    symbol=symbol, lux=lux_ltf, htf_bias=bias, trigger_idx_min=trig_min,
                    use_internal=bool(lux_cfg.get("use_internal", True)), use_swing=bool(lux_cfg.get("use_swing", True)),
                    require_premium_discount=bool(lux_cfg.get("require_premium_discount", True)),
                    allowed_kinds=tuple(lux_cfg.get("kinds", ["CHoCH", "BOS"])),
                    min_confluence=int(lux_cfg.get("min_confluence", 0)))
                n_before = len(store.candidates)
                orch._emit_setup_candidates(
                    symbol=symbol, htf_bias=bias, precomputed_candidates=cands, ltf_structure_breaks=[],
                    htf_swings={"swing_highs": [], "swing_lows": []}, htf_bars=[], htf_fvgs=[], ote_band=(0.0, 0.0),
                    ltf_trigger_idx_min=trig_min, current_price=price, df_entry=df_entry)
                stats["emitted"] += len(store.candidates) - n_before
        rows = orch.records + expired_rows
    stats["confirmed"] = sum(1 for r in orch.records if r["drop_reason"] == "")
    rows.sort(key=lambda r: (r["confirmed_ts"], r["trigger_bar_ts"]))
    return rows, stats


def write_rows(rows: list[dict], path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ROW_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in ROW_FIELDS})


def read_rows(path) -> list[dict]:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            for k, typ in NUMERIC.items():
                r[k] = typ(float(r[k])) if r.get(k, "") != "" else ""
            r["python_guard_rejected"] = str(r.get("python_guard_rejected", "")).lower() == "true"
            out.append(r)
    return out


# ───────────────────────────── compare ─────────────────────────────
def _col(df: pd.DataFrame, *prefixes: str, exclude_pct: bool = False) -> str:
    for p in prefixes:
        for c in df.columns:
            if c.strip().lower().startswith(p.lower()) and not (exclude_pct and c.strip().endswith("%")):
                return c
    raise ValueError(f"column starting with one of {prefixes} not found in {list(df.columns)}")


def load_tv_trades(path) -> pd.DataFrame:
    """TradingView Strategy Tester 'List of trades' export → trade, type, time, signal, price, qty, pnl."""
    raw = pd.read_csv(path)
    return pd.DataFrame({
        "trade": pd.to_numeric(raw[_col(raw, "Trade #", "Trade")], errors="coerce").astype(int),
        "type": raw[_col(raw, "Type")].astype(str).str.strip(),
        "time": pd.to_datetime(raw[_col(raw, "Date")]),
        "signal": raw[_col(raw, "Signal")].astype(str).str.strip(),
        "price": pd.to_numeric(raw[_col(raw, "Price")], errors="coerce").astype(float),
        "qty": pd.to_numeric(raw[_col(raw, "Position size (qty)", "Contracts", "Quantity")], errors="coerce").astype(float),
        "pnl": pd.to_numeric(raw[_col(raw, "Net P&L", "Profit", exclude_pct=True)], errors="coerce"),
    })


def parse_signal(s: str) -> dict:
    parts = str(s).split("|")
    d = {"variant": parts[0] if parts else ""}
    for kv in parts[1:]:
        if "=" in kv:
            k, v = kv.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _num(v) -> Optional[float]:
    try:
        return None if v in (None, "", "na") else float(v)
    except ValueError:
        return None


def tv_entries(trades: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in trades[trades["type"].str.startswith("Entry")].iterrows():
        sig = parse_signal(r["signal"])
        trig = _num(sig.get("trig"))
        out.append({"direction": "LONG" if "long" in r["type"].lower() else "SHORT",
                    "trig": int(trig) if trig is not None else None, "entry": float(r["price"]),
                    "sl": _num(sig.get("sl")), "tp1": _num(sig.get("tp1")), "tp2": _num(sig.get("tp2")),
                    "time": r["time"], "variant": sig["variant"]})
    return out


def _close(a, b, tol: float) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    if a in (None, "") or b in (None, ""):
        return False
    return abs(float(a) - float(b)) <= tol * max(abs(float(a)), 1e-12)


def _key(direction, trig) -> tuple:
    return (direction, None if trig is None else int(trig))


def compare(py_rows: list[dict], entries: list[dict], *, entry_tol: float = 0.0005, level_tol: float = 0.001,
            gate: float = 0.95) -> dict:
    """Pair intended Python entries (drop_reason == '') with TradingView entries on (direction, trig).

    Duplicate keys (the engine re-emits a break after its candidate expired; the strategy can reopen on the
    same trig) pair in time order: i-th Python row (by confirmed_ts) with i-th TV entry (by time).
    """
    py_entries = [r for r in py_rows if r.get("drop_reason", "") == ""]
    py_groups: dict = {}
    for r in py_entries:
        py_groups.setdefault(_key(r["direction"], r["trigger_bar_ts"]), []).append(r)
    tv_groups: dict = {}
    for e in entries:
        tv_groups.setdefault(_key(e["direction"], e["trig"]), []).append(e)
    matched, python_only, pine_only, mismatches = 0, [], [], []
    for key in list(py_groups) + [k for k in tv_groups if k not in py_groups]:
        prs = sorted(py_groups.get(key, []), key=lambda r: r["confirmed_ts"] if r.get("confirmed_ts", "") != "" else 0)
        tes = sorted(tv_groups.get(key, []), key=lambda e: e["time"])
        for r, e in zip(prs, tes):
            matched += 1
            bad = [] if _close(r["entry"], e["entry"], entry_tol) else ["entry"]
            bad += [lvl for lvl in ("sl", "tp1", "tp2") if not _close(r.get(lvl, ""), e.get(lvl), level_tol)]
            if bad:
                mismatches.append({"trig": key[1], "direction": key[0], "levels": bad,
                                   "python": {k: r.get(k) for k in bad}, "pine": {k: e.get(k) for k in bad}})
        python_only.extend(prs[len(tes):])
        pine_only.extend(tes[len(prs):])
    rate = matched / len(py_entries) if py_entries else 0.0
    return {"python_entries": len(py_entries), "matched": matched, "python_only": python_only, "pine_only": pine_only,
            "level_mismatch": mismatches, "guard_rejected": sum(1 for r in py_entries if r.get("python_guard_rejected")),
            "match_rate": rate, "passed": bool(py_entries) and rate >= gate and not mismatches
            and len(pine_only) <= (1.0 - gate) * max(1, len(entries))}


def format_compare(res: dict) -> str:
    lines = [f"python entries : {res['python_entries']}",
             f"matched        : {res['matched']}  (match rate {res['match_rate']:.1%})",
             f"python-only    : {len(res['python_only'])}",
             f"pine-only      : {len(res['pine_only'])}",
             f"level mismatch : {len(res['level_mismatch'])}",
             f"guard-rejected : {res['guard_rejected']}  (B2 float flag — live would have dropped these)",
             f"GATE           : {'PASS' if res['passed'] else 'FAIL'}"]
    for r in res["python_only"][:20]:
        lines.append(f"  py-only  {r['direction']} trig={r['trigger_bar_ts']} entry={r['entry']}")
    for e in res["pine_only"][:20]:
        lines.append(f"  pine-only {e['direction']} trig={e['trig']} entry={e['entry']} at {e['time']}")
    for m in res["level_mismatch"][:20]:
        lines.append(f"  levels   {m['direction']} trig={m['trig']} {m['levels']} py={m['python']} pine={m['pine']}")
    return "\n".join(lines)


def _cmd_compare(a) -> int:
    try:
        py = read_rows(a.python)
        entries = tv_entries(load_tv_trades(a.tv))
    except ValueError as exc:
        print(f"compare: {exc}", file=sys.stderr)
        return 2
    stamps = [r["confirmed_ts"] for r in py if r["confirmed_ts"] != ""]
    if stamps:
        first = pd.Timestamp(min(stamps), unit="ms")
        entries = [e for e in entries if e["time"] >= first]
    res = compare(py, entries, entry_tol=a.entry_tol, level_tol=a.level_tol, gate=a.gate)
    print(format_compare(res))
    return 0 if res["passed"] else 1


# ───────────────────────────── score ─────────────────────────────
def score_trades(trades: pd.DataFrame) -> dict:
    """NET R per trade from the TradingView list: R = Σ exit P&L / (|entry − initial SL| × qty at entry).
    The initial SL comes from the entry signal (`sl=`), or from the first exit signal when the entry
    was a limit order placed before the SL was known (T3: exit comment `TP1/SL|sl=…`)."""
    rs, variants = [], {}
    for _trade_id, grp in trades.groupby("trade", sort=True):
        ent = grp[grp["type"].str.startswith("Entry")]
        ex = grp[grp["type"].str.startswith("Exit")]
        if ent.empty or ex.empty:
            continue
        e = ent.iloc[0]
        sig = parse_signal(e["signal"])
        sl = _num(sig.get("sl"))
        if sl is None:
            sl = _num(parse_signal(ex.iloc[0]["signal"]).get("sl"))
        risk = abs(float(e["price"]) - sl) * float(e["qty"]) if sl is not None else 0.0
        if risk <= 0:
            continue
        r = float(ex["pnl"].fillna(0.0).sum()) / risk
        rs.append(r)
        variants.setdefault(sig.get("variant", ""), []).append(r)
    if not rs:
        return {"n": 0, "total_r": 0.0, "avg_r": 0.0, "pf": 0.0, "max_dd_r": 0.0, "win_rate": 0.0, "by_variant": {}}
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)
    peak, dd, cum = 0.0, 0.0, 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {"n": len(rs), "total_r": sum(rs), "avg_r": sum(rs) / len(rs),
            "pf": (gains / losses) if losses > 0 else float("inf"), "max_dd_r": dd,
            "win_rate": sum(1 for r in rs if r > 0) / len(rs),
            "by_variant": {k: {"n": len(v), "total_r": sum(v)} for k, v in variants.items()}}


def decide(baseline: dict, variant: dict) -> tuple[bool, list[str]]:
    """Spec §6.3: n ≥ 50, total NET R > baseline, avg NET R > baseline, max DD(R) ≤ 1.2 × baseline."""
    why = []
    if variant["n"] < 50:
        why.append(f"n={variant['n']} < 50")
    if not variant["total_r"] > baseline["total_r"]:
        why.append(f"total R {variant['total_r']:.2f} ≤ baseline {baseline['total_r']:.2f}")
    if not variant["avg_r"] > baseline["avg_r"]:
        why.append(f"avg R {variant['avg_r']:.3f} ≤ baseline {baseline['avg_r']:.3f}")
    if variant["max_dd_r"] > 1.2 * baseline["max_dd_r"]:
        why.append(f"max drawdown {variant['max_dd_r']:.2f}R > 1.2 × baseline {baseline['max_dd_r']:.2f}R")
    return (not why), why


def format_score(name: str, s: dict) -> str:
    return (f"{name:<28} n={s['n']:<4} totalR={s['total_r']:+8.2f} avgR={s['avg_r']:+.3f} "
            f"PF={s['pf']:.2f} maxDD={s['max_dd_r']:.2f}R win={s['win_rate']:.0%}")


def _cmd_score(a) -> int:
    base = score_trades(load_tv_trades(a.baseline))
    print(format_score("baseline", base))
    rc = 0
    for v in a.variant:
        s = score_trades(load_tv_trades(v))
        ok, why = decide(base, s)
        print(format_score(Path(v).stem, s) + ("  WIN" if ok else "  NO: " + "; ".join(why)))
        rc = rc or (0 if ok else 2)
    return rc


# ───────────────────────────── cli ─────────────────────────────
def _cmd_replay(a) -> int:
    cfg = load_config(a.config)
    df = load_ohlcv_csv(a.ohlcv)
    rows, stats = replay(df, cfg, htf_tf=a.htf, window=a.window, ticks_per_bar=a.ticks, symbol=a.symbol)
    write_rows(rows, a.out)
    print(f"replay: {stats} → {a.out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="python_setups.csv from a 15m OHLCV CSV")
    r.add_argument("--ohlcv", required=True)
    r.add_argument("--config", default=str(ROOT / "configs" / "config.phase2_1k.yaml"))
    r.add_argument("--htf", default="12h", choices=sorted(TF_MS))
    r.add_argument("--window", type=int, default=750)
    r.add_argument("--ticks", type=int, default=3)
    r.add_argument("--symbol", default="LAB/USDT")
    r.add_argument("--out", default="python_setups.csv")
    r.set_defaults(fn=_cmd_replay)
    c = sub.add_parser("compare", help="python_setups.csv vs TradingView trade list")
    c.add_argument("--python", required=True)
    c.add_argument("--tv", required=True)
    c.add_argument("--entry-tol", type=float, default=0.0005)
    c.add_argument("--level-tol", type=float, default=0.001)
    c.add_argument("--gate", type=float, default=0.95)
    c.set_defaults(fn=_cmd_compare)
    s = sub.add_parser("score", help="NET R metrics + WIN/NO vs baseline (spec §6.3)")
    s.add_argument("--baseline", required=True)
    s.add_argument("--variant", action="append", default=[])
    s.set_defaults(fn=_cmd_score)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
