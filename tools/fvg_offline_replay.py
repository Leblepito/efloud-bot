"""FVG offline replay — ADR-0011 offline gate for the target model (2026-11-14).

Walk-forward replay of the SHADOW code (`engine.smc_v2.fvg_entry.shadow_step`, the same body
`SafeOrchestrator._fvg_shadow_step` runs) over cached history. No orders, no live state.

    python -m scripts.prefetch_data --config configs/config.phase2_1k.yaml --days 400
    python tools/fvg_offline_replay.py run --symbols BTC/USDT --days 180 --end 2026-11-13 \\
        --out C:/tmp/fvg/btc
    python tools/fvg_offline_replay.py merge --inputs C:/tmp/fvg/btc.json C:/tmp/fvg/eth.json \\
        --out C:/tmp/fvg/all

``--out PREFIX`` writes PREFIX.json (meta + trades + results) and PREFIX.md. A date-only
``--end`` means the END of that UTC day (exclusive bound = next midnight). The exit line carries
no timestamp, so a trade's exit time is the closed entry bar at which the book emitted it.
Spec: docs/superpowers/specs/2026-11-14-fvg-offline-replay-design.md.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data.timeframes import resolve_timeframes, tf_to_minutes  # noqa: E402
from engine.smc_v2 import fvg_entry as fe  # noqa: E402
from engine.smc_v2 import luxalgo as lx  # noqa: E402

# ADR-0011 offline criteria
MIN_TRADES = 100
MIN_OOS_PF = 1.30
MIN_SYMBOL_SHARE = 0.60
MIN_WINDOW_DAYS = 180
PASS_VERDICT = "PASS (absolute criteria; baseline comparison not run)"
DEFAULT_IS_FRAC = 0.67
MS_DAY = 86_400_000

_EXIT_RE = re.compile(
    r"\[fvg shadow\] exit (?P<sym>\S+) (?P<dir>LONG|SHORT)(?: v=(?P<v>\w+))? "
    r"reason=(?P<reason>\S+) gross_r=(?P<g>[-+]?\d+\.\d+) net_r=(?P<n>[-+]?\d+\.\d+) "
    r"cost_r=(?P<c>[-+]?\d+\.\d+)")


class HistoryError(RuntimeError):
    """Not enough cached history for a faithful replay."""


class MergeError(ValueError):
    """Inputs to `merge` are not parts of the same run."""


@dataclass
class ReplayResult:
    symbol: str
    lines: List[Tuple[int, str]] = field(default_factory=list)   # (entry-bar open ms, line)
    trades: List[dict] = field(default_factory=list)


# ---- pure helpers ----------------------------------------------------------

def parse_exit_line(line: str, exit_ts: int) -> Optional[dict]:
    m = _EXIT_RE.search(line)
    if not m:
        return None
    return {"variant": m["v"] or "A", "symbol": m["sym"], "direction": m["dir"],
            "reason": m["reason"], "gross_r": float(m["g"]), "net_r": float(m["n"]),
            "cost_r": float(m["c"]), "exit_ts": int(exit_ts)}


def usable_mtf_count(mtf_open_ms: np.ndarray, mtf_tf_ms: int, entry_close_ms: int) -> int:
    """Number of MTF bars (sorted by open) whose CLOSE <= the entry bar's close (look-ahead guard)."""
    return int(np.searchsorted(mtf_open_ms + mtf_tf_ms, entry_close_ms, side="right"))


def compute_metrics(trades: Sequence[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "avg_gross_r": 0.0, "avg_net_r": 0.0,
                "pf_net": 0.0, "max_dd_r": 0.0, "avg_cost_r": 0.0}
    nets = [t["net_r"] for t in sorted(trades, key=lambda t: t["exit_ts"])]
    wins = sum(x for x in nets if x > 0)
    losses = -sum(x for x in nets if x < 0)
    peak = cum = dd = 0.0
    for x in nets:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {"n": n,
            "win_rate": sum(1 for x in nets if x > 0) / n,
            "avg_gross_r": sum(t["gross_r"] for t in trades) / n,
            "avg_net_r": sum(nets) / n,
            "pf_net": wins / losses if losses > 0 else (math.inf if wins > 0 else 0.0),
            "max_dd_r": dd,
            "avg_cost_r": sum(t["cost_r"] for t in trades) / n}


def split_is_oos(trades: Sequence[dict], start_ms: int, end_ms: int,
                 is_frac: float) -> Tuple[List[dict], List[dict]]:
    cut = start_ms + is_frac * (end_ms - start_ms)
    return ([t for t in trades if t["exit_ts"] < cut], [t for t in trades if t["exit_ts"] >= cut])


def symbol_positive_share(trades: Sequence[dict], symbols: Optional[Sequence[str]] = None) -> float:
    """Share of evaluated symbols with NET R > 0; zero-trade symbols count as not positive."""
    per: Dict[str, float] = defaultdict(float)
    for t in trades:
        per[t["symbol"]] += t["net_r"]
    universe = set(symbols) if symbols is not None else set(per)
    return sum(1 for s in universe if per.get(s, 0.0) > 0) / len(universe) if universe else 0.0


def evaluate(trades: Sequence[dict], start_ms: int, end_ms: int, is_frac: float,
             symbols: Optional[Sequence[str]] = None,
             live_symbols: Optional[Sequence[str]] = None) -> dict:
    """Metrics + ADR-0011 offline verdict for ONE variant's trades.

    `symbols` = every evaluated symbol (zero-trade ones included); `live_symbols` = config
    `engine.smc_v2_symbols`. An unknown live set fails closed. No baseline arm is run, so a
    passing verdict is only ever the absolute-criteria one."""
    is_t, oos_t = split_is_oos(trades, start_ms, end_ms, is_frac)
    m_all, m_is, m_oos = compute_metrics(trades), compute_metrics(is_t), compute_metrics(oos_t)
    syms = sorted({t["symbol"] for t in trades}) if symbols is None else sorted(set(symbols))
    share = symbol_positive_share(trades, syms)
    reasons = []
    if end_ms - start_ms < MIN_WINDOW_DAYS * MS_DAY:
        reasons.append(f"window<{MIN_WINDOW_DAYS}d")
    if live_symbols is None or set(syms) != set(live_symbols):
        reasons.append("symbols != live set")
    if m_all["n"] < MIN_TRADES:
        reasons.append(f"n={m_all['n']} < {MIN_TRADES}")
    if not m_is["avg_net_r"] > 0:
        reasons.append(f"IS avg NET R {m_is['avg_net_r']:+.3f} <= 0")
    if not m_oos["avg_net_r"] > 0:
        reasons.append(f"OOS avg NET R {m_oos['avg_net_r']:+.3f} <= 0")
    if not m_oos["pf_net"] >= MIN_OOS_PF:
        reasons.append(f"OOS PF {m_oos['pf_net']:.2f} < {MIN_OOS_PF:.2f}")
    if share < MIN_SYMBOL_SHARE:
        reasons.append(f"symbols NET-positive {share:.0%} < {MIN_SYMBOL_SHARE:.0%}")
    return {"all": m_all, "is": m_is, "oos": m_oos, "symbol_positive_share": share,
            "verdict": "FAIL" if reasons else PASS_VERDICT, "reasons": reasons}


def evaluate_all(trades: Sequence[dict], start_ms: int, end_ms: int, is_frac: float,
                 symbols: Optional[Sequence[str]] = None,
                 live_symbols: Optional[Sequence[str]] = None) -> Dict[str, dict]:
    by_v: Dict[str, List[dict]] = defaultdict(list)
    for t in trades:
        by_v[t["variant"]].append(t)
    return {v: evaluate(ts, start_ms, end_ms, is_frac, symbols, live_symbols)
            for v, ts in sorted(by_v.items())}


# ---- walk-forward ----------------------------------------------------------

def _utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is None:
        df = df.copy()
        df.index = df.index.tz_localize("UTC")
    return df


def _ms(index: pd.DatetimeIndex) -> np.ndarray:
    return index.as_unit("ms").asi8.astype("int64")


def replay_symbol(symbol: str, df_entry: pd.DataFrame, df_mtf: pd.DataFrame, config: dict,
                  start_ms: int, end_ms: int) -> ReplayResult:
    """Replay every entry bar that opens in [start_ms, end_ms) and closes by end_ms."""
    tf = resolve_timeframes(json.loads(json.dumps(config)))
    # live fetch_ohlcv(limit=kline_limit) drops the forming bar -> live sees kline_limit-1 closed bars
    k, e_tf, m_tf = tf["kline_limit"] - 1, tf["entry"], tf["mtf"]
    e_ms, m_ms = tf_to_minutes(e_tf) * 60_000, tf_to_minutes(m_tf) * 60_000
    df_entry, df_mtf = _utc_index(df_entry), _utc_index(df_mtf)
    e_open, m_open = _ms(df_entry.index), _ms(df_mtf.index)

    first = int(np.searchsorted(e_open, start_ms, side="left"))
    if first + 1 < k:
        raise HistoryError(f"{symbol} {e_tf}: {first} bars before window start, need {k} "
                           f"(kline_limit-1); prefetch more history")
    n_mtf_before = usable_mtf_count(m_open, m_ms, start_ms)
    if n_mtf_before < k:
        raise HistoryError(f"{symbol} {m_tf}: {n_mtf_before} closed bars before window "
                           f"start, need {k} (kline_limit-1); prefetch more history")
    last_close = int(e_open[-1]) + e_ms
    if last_close < end_ms:
        raise HistoryError(f"{symbol} {e_tf}: cache ends at {_iso(last_close)} UTC, before the "
                           f"window end {_iso(end_ms)}; prefetch newer data")

    lux_cfg = (config.get("smc_v2", {}) or {}).get("luxalgo", {}) or {}
    lux_conf = lx.LuxConfig.from_dict(lux_cfg)
    book = fe.book_from_config(config, lux_cfg)
    res = ReplayResult(symbol=symbol)
    for i in range(first, len(df_entry)):
        close_ms = int(e_open[i]) + e_ms
        if close_ms > end_ms:
            break
        n_m = usable_mtf_count(m_open, m_ms, close_ms)
        if n_m == 0 or close_ms - (int(m_open[n_m - 1]) + m_ms) > m_ms:
            raise HistoryError(f"{symbol} {m_tf}: MTF data lag at entry bar closing "
                               f"{_iso(close_ms)} UTC (last usable close lags by more than one "
                               f"{m_tf} bar); prefetch newer data")
        de = df_entry.iloc[i + 1 - k: i + 1]
        dm = df_mtf.iloc[n_m - k: n_m]
        lux_ltf = lx.analyze(de, lux_conf)
        # shadow_step recomputes MTF bias itself; unchanged MTF window -> same value, so the
        # book is stepped through the shared code path exactly as the live shadow does.
        lines = fe.shadow_step(book, config, lux_cfg, symbol, de, dm, lux_ltf)
        for ln in lines:
            res.lines.append((int(e_open[i]), ln))
            t = parse_exit_line(ln, exit_ts=close_ms)
            if t:
                res.trades.append(t)
    return res


# ---- report ----------------------------------------------------------------

def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _cost_line(config: dict) -> str:
    bt = config.get("backtest", {}) or {}
    return (f"commission {float(bt.get('commission_pct', fe.DEFAULT_COMMISSION_PCT))}%/leg, "
            f"funding {float(bt.get('funding_pct_per_8h', fe.DEFAULT_FUNDING_PCT_PER_8H))}%/8h, "
            f"SL/BE slip {fe.DEFAULT_SL_SLIP_PCT}%, TP slip {fe.DEFAULT_EXIT_SLIP_PCT}%")


def build_report(meta: dict, trades: List[dict]) -> dict:
    res = evaluate_all(trades, meta["start_ms"], meta["end_ms"], meta["is_frac"],
                       meta["symbols"], meta.get("live_symbols"))
    return {"meta": meta, "trades": trades, "results": res}


def _iso(ms: int) -> str:
    return pd.Timestamp(ms, unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M")


def render_markdown(rep: dict) -> str:
    m = rep["meta"]
    out = ["# FVG offline replay (ADR-0011 offline gate)", "",
           f"- window: {_iso(m['start_ms'])} .. {_iso(m['end_ms'])} UTC, IS fraction {m['is_frac']}",
           f"- symbols: {', '.join(m['symbols'])}",
           f"- git SHA: {m['git_sha']}", f"- config: {m.get('config', '?')}",
           f"- cost: {m.get('cost', '?')}",
           f"- SL variants tried: {m.get('variants_tried', '?')} (multiple-testing: judge accordingly)",
           ""]
    for v, r in rep["results"].items():
        a, i, o = r["all"], r["is"], r["oos"]
        out += [f"## Variant {v}: {r['verdict']}", ""]
        out += [f"- {x}" for x in r["reasons"]] or ["- all ADR-0011 offline criteria met"]
        out += ["", "| set | n | win | avg gross R | avg NET R | NET PF | max DD R | avg cost R |",
                "|---|---|---|---|---|---|---|---|"]
        for name, s in (("all", a), ("IS", i), ("OOS", o)):
            out.append(f"| {name} | {s['n']} | {s['win_rate']:.0%} | {s['avg_gross_r']:+.3f} | "
                       f"{s['avg_net_r']:+.3f} | {s['pf_net']:.2f} | {s['max_dd_r']:.2f} | "
                       f"{s['avg_cost_r']:.3f} |")
        out += ["", f"symbols NET-positive: {r['symbol_positive_share']:.0%}", ""]
    if not rep["results"]:
        out.append("No closed shadow trades in the window.")
    return "\n".join(out) + "\n"


def write_report(rep: dict, prefix: Path) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(json.dumps(rep, indent=1, sort_keys=True, default=str))
    prefix.with_suffix(".md").write_text(render_markdown(rep), encoding="utf-8")


def summary_lines(rep: dict) -> List[str]:
    out = []
    for v, r in rep["results"].items():
        a = r["all"]
        out.append(f"variant {v}: {r['verdict']} n={a['n']} avgNET={a['avg_net_r']:+.3f}R "
                   f"PF={a['pf_net']:.2f} OOS avgNET={r['oos']['avg_net_r']:+.3f}R "
                   f"{'; '.join(r['reasons'])}")
    return out or ["no closed shadow trades"]


_MERGE_SAME = ("start_ms", "end_ms", "is_frac", "cost", "config", "profile", "variants_tried",
               "live_symbols")


def merge_reports(paths: Sequence[Path]) -> dict:
    reps = [json.loads(Path(p).read_text()) for p in paths]
    metas = [r["meta"] for r in reps]
    for f in _MERGE_SAME:
        vals = {json.dumps(m.get(f), sort_keys=True) for m in metas}
        if len(vals) > 1:
            raise MergeError(f"inputs differ in {f}: {sorted(vals)}")
    seen: Dict[str, int] = defaultdict(int)
    for m in metas:
        for s_ in m["symbols"]:
            seen[s_] += 1
    dups = sorted(s_ for s_, c in seen.items() if c > 1)
    if dups:
        raise MergeError(f"symbol(s) appear in more than one input: {', '.join(dups)}")
    meta = dict(metas[0])
    meta.update(symbols=sorted(seen),
                git_sha=metas[0]["git_sha"] if len({m["git_sha"] for m in metas}) == 1
                else "mixed: " + ",".join(sorted({m["git_sha"] for m in metas})))
    return build_report(meta, [t for r in reps for t in r["trades"]])


# ---- CLI -------------------------------------------------------------------

def _end_ms(end: str) -> int:
    ts = pd.Timestamp(end)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    if len(end) <= 10:                 # date-only -> end of that day
        ts += pd.Timedelta(days=1)
    return int(ts.timestamp() * 1000)


def cmd_run(args) -> int:
    import yaml

    from data.cache import OHLCVCache

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    tf = resolve_timeframes(config)
    symbols = args.symbols or list((config.get("engine", {}) or {}).get("smc_v2_symbols", []))
    cache = OHLCVCache(Path(args.cache_dir))
    trades: List[dict] = []
    start_ms = end_ms = 0
    for sym in symbols:
        frames = {}
        for role in ("entry", "mtf"):
            df = cache.get(sym, tf[role])
            if df is None or df.empty:
                raise HistoryError(f"{sym} {tf[role]}: no cached data in {args.cache_dir}; run "
                                   f"scripts.prefetch_data first")
            frames[role] = df
        end_ms = _end_ms(args.end)
        start_ms = end_ms - args.days * MS_DAY
        r = replay_symbol(sym, frames["entry"], frames["mtf"], config, start_ms, end_ms)
        trades += r.trades
        print(f"{sym}: {len(r.trades)} closed trades "
              f"({sum(1 for _, ln in r.lines if ' setup+ ' in ln)} setups)", flush=True)
    meta = {"git_sha": git_sha(), "config": args.config, "cost": _cost_line(config),
            "start_ms": start_ms, "end_ms": end_ms, "days": args.days, "is_frac": args.is_frac,
            "symbols": sorted(symbols),
            "live_symbols": sorted((config.get("engine", {}) or {}).get("smc_v2_symbols", [])),
            "profile": tf["profile"],
            "variants_tried": len(fe.sl_modes_from_config(config))}
    rep = build_report(meta, trades)
    write_report(rep, Path(args.out))
    print("\n".join(summary_lines(rep)))
    return 0


def cmd_merge(args) -> int:
    try:
        rep = merge_reports([Path(p) for p in args.inputs])
    except MergeError as e:
        print(f"merge refused: {e}", file=sys.stderr)
        return 2
    write_report(rep, Path(args.out))
    print("\n".join(summary_lines(rep)))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="replay the FVG shadow over cached history")
    r.add_argument("--config", default="configs/config.phase2_1k.yaml")
    r.add_argument("--symbols", nargs="*", help="default: engine.smc_v2_symbols")
    r.add_argument("--days", type=int, default=180)
    r.add_argument("--end", required=True,
                   help="ISO date/time (UTC); date-only = end of that day; required (fixed gate window)")
    r.add_argument("--cache-dir", default="cache/ohlcv", help="OHLCVCache root")
    r.add_argument("--out", required=True, help="output prefix (writes .json and .md)")
    r.add_argument("--is-frac", type=float, default=DEFAULT_IS_FRAC)
    r.set_defaults(fn=cmd_run)
    m = sub.add_parser("merge", help="combine per-symbol JSON outputs")
    m.add_argument("--inputs", nargs="+", required=True)
    m.add_argument("--out", required=True)
    m.set_defaults(fn=cmd_merge)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
