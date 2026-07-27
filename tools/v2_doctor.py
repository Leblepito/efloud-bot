#!/usr/bin/env python3
"""v2_doctor — SMC v2 setup-emit funnel diagnostic. READ-ONLY.

WHY THIS EXISTS
---------------
When `state_1k/setup_candidates.json` is empty and no `[v2 gate]` lines appear
in the logs, there is no way from the outside to tell WHICH of the six
early-return paths in `generate_setup_candidates()` is eating every CHoCH.
This tool replays exactly the inputs `SafeOrchestrator.run_cycle` builds for
the v2 trigger (same config, same timeframes, same recency window, same SMC
engine parameters) and reports, per symbol, how many breaks survive each
stage of the funnel.

The funnel mirrors engine/smc_v2/triggers.py:120-200 one-for-one:

    breaks                                    SMCEngine.structure(df_entry)
      -> CHoCH        drop: brk.kind != "CHoCH"
      -> aligned      drop: brk.direction != htf_bias
      -> recent       drop: brk.idx < ltf_trigger_idx_min
      -> anchor       drop: select_htf_swing_anchor(...) is None
      -> zone         drop: zone.source == "OTE" and zone.low == zone.high
      -> EMIT
      -> gate         drop: near-edge distance > smc_v2.max_entry_dist_atr

Whole-symbol short circuit: htf_bias == "UNDEF" returns [] before the loop.

SAFETY
------
- Unauthenticated ccxt client. Public market-data endpoints only.
- No API keys are read. No .env file is touched.
- No orders, no cancels, no position changes.
- Writes nothing to disk. Output goes to stdout.

USAGE
-----
    # inside the running container (config is baked into the image at /app)
    docker compose -f docker-compose.prod.yml exec -T efloud-bot \
        python tools/v2_doctor.py

    # against another bot's config
    python tools/v2_doctor.py --config configs/config.phase2_long_1k.yaml

    # narrow to a few symbols while iterating
    python tools/v2_doctor.py --symbols BTC/USDT,ETH/USDT
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Repo root = parent of tools/. Works from any cwd and inside the container,
# where the repo is copied to /app (Dockerfile:48 `COPY . ./`).
# Fallback to /app covers the case where this file was `docker cp`'d somewhere
# outside the tree (e.g. /tmp) to probe an older image that predates tools/.
REPO_ROOT = Path(__file__).resolve().parents[1]
if not (REPO_ROOT / "engine").is_dir() and Path("/app/engine").is_dir():
    REPO_ROOT = Path("/app")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from engine.smc import SMCEngine  # noqa: E402
from engine.smc_v2.atr import wilder_atr  # noqa: E402
from engine.smc_v2.swing_anchor import select_htf_swing_anchor  # noqa: E402
from engine.smc_v2.triggers import (  # noqa: E402
    HtfBar,
    _bar_ts_to_ms,
    generate_setup_candidates,
)
from engine.smc_v2.zones import build_pullback_zones  # noqa: E402

DEFAULT_CONFIG = "configs/config.phase2_1k.yaml"

# Fallback only. The real resolver in data/timeframes.py is preferred and the
# tool prints which one it used, so a drift between the two is visible instead
# of silently reporting the wrong timeframes.
_FALLBACK_PROFILES = {
    "scalp": ("5m", "1h", "4h"),
    "mid": ("15m", "4h", "12h"),
    "long": ("1h", "8h", "1d"),
}


def resolve_tfs(cfg: dict) -> tuple[dict, str]:
    """Return ({entry, mtf, htf, kline_limit, profile}, source_label)."""
    try:
        from data.timeframes import resolve_timeframes

        return resolve_timeframes(cfg), "data.timeframes.resolve_timeframes"
    except Exception as exc:  # ImportError, or config the resolver rejects
        tf = cfg.get("timeframes", {}) or {}
        prof = tf.get("profile")
        if prof in _FALLBACK_PROFILES:
            entry, mtf, htf = _FALLBACK_PROFILES[prof]
        else:
            entry, mtf, htf = tf.get("entry"), tf.get("mtf"), tf.get("htf")
            prof = "custom"
        if not (entry and mtf and htf):
            raise SystemExit(f"cannot resolve timeframes: {exc!r}")
        return (
            {
                "entry": entry,
                "mtf": mtf,
                "htf": htf,
                "kline_limit": tf.get("kline_limit", 500),
                "profile": prof,
            },
            f"builtin fallback ({exc.__class__.__name__})",
        )


def build_smc(cfg: dict) -> SMCEngine:
    """Same construction as SafeOrchestrator.__init__ (safe_orchestrator.py:219)."""
    sc = cfg["structure"]
    fib = cfg["fibonacci"]
    return SMCEngine(
        swing_lb=sc["swing_lookback"],
        ob_seq=sc["ob_sequential"],
        body_mode=sc["body_mode"],
        eq_thr=sc["eq_threshold_pct"] / 100,
        range_lb=sc["range_lookback"],
        ote_lo=fib["ote_lower"],
        ote_hi=fib["ote_upper"],
    )


def symbols_of(cfg: dict) -> list[str]:
    syms = cfg.get("symbols", {}) or {}
    return list(syms.get("fixed_core") or [])


def fetch(ex, symbol: str, tf: str, limit: int) -> pd.DataFrame:
    raw = ex.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df[["open", "high", "low", "close", "volume"]]


def probe(smc: SMCEngine, symbol: str, df_entry, df_htf, recency: int,
          max_dist_atr: float, anchor_time_axis: bool) -> dict:
    """Count survivors at every funnel stage for one symbol."""
    analysis = smc.analyze(df_htf)
    bias = analysis.get("trend", "UNDEF")
    swing_h, swing_l = smc.swings(df_entry)
    breaks = smc.structure(df_entry, swing_h, swing_l)

    idx_min = max(0, len(df_entry) - 1 - recency)
    htf_bars = [
        HtfBar(ordinal=i, high=float(row["high"]), low=float(row["low"]),
               ts_ms=_bar_ts_to_ms(ts))
        for i, (ts, row) in enumerate(df_htf.iterrows())
    ]
    ote = analysis.get("ote")
    ote_band = ((min(ote.bot, ote.top), max(ote.bot, ote.top))
                if ote is not None else (0.0, 0.0))
    htf_swings = {
        "swing_highs": analysis.get("swing_highs", []),
        "swing_lows": analysis.get("swing_lows", []),
    }
    fvgs = analysis.get("active_fvgs", []) or []

    n = dict(choch=0, aligned=0, recent=0, anchor=0, zone=0)
    for brk in breaks:
        if brk.kind != "CHoCH":
            continue
        n["choch"] += 1
        if brk.direction != bias:
            continue
        n["aligned"] += 1
        if brk.idx < idx_min:
            continue
        n["recent"] += 1
        direction = "LONG" if brk.direction == "BULL" else "SHORT"
        anchor = select_htf_swing_anchor(
            htf_swings=htf_swings, direction=direction,
            trigger_idx=brk.idx, htf_bars=htf_bars,
        )
        if anchor is None:
            continue
        n["anchor"] += 1
        zone = build_pullback_zones(
            htf_fvgs=fvgs, ote_band=ote_band,
            direction=direction, trigger_price=brk.price,
        )
        if zone.source == "OTE" and zone.low == zone.high:
            continue
        n["zone"] += 1

    # The real thing, so a divergence between the hand-counted funnel above and
    # the production function is itself a finding.
    emitted = generate_setup_candidates(
        symbol=symbol, htf_bias=bias, ltf_structure_breaks=breaks,
        htf_swings=htf_swings, htf_bars=htf_bars, htf_fvgs=fvgs,
        ote_band=ote_band, ltf_trigger_idx_min=idx_min,
        anchor_time_axis=anchor_time_axis,
    )

    price = float(df_entry["close"].iloc[-1])
    atr = wilder_atr(df_entry, period=14)
    dists = []
    for cand in emitted:
        zl = min(cand.target_zone.low, cand.target_zone.high)
        zh = max(cand.target_zone.low, cand.target_zone.high)
        near = (price - zh) if cand.direction == "LONG" else (zl - price)
        dists.append(near / atr if atr else float("nan"))
    gated = sum(1 for d in dists if max_dist_atr > 0 and d > max_dist_atr)

    print(
        f"{symbol:10} bias={bias:5} brks={len(breaks):3d} CHoCH={n['choch']:3d} "
        f"aligned={n['aligned']:3d} recent={n['recent']:2d} anchor={n['anchor']:2d} "
        f"zone={n['zone']:2d} EMIT={len(emitted):2d} gate_drop={gated:2d} "
        f"ote={'Y' if ote is not None else 'N'} fvg={len(fvgs)} "
        f"atr={atr} dist_atr={[round(d, 1) for d in dists]}",
        flush=True,
    )
    return dict(symbol=symbol, bias=bias, breaks=len(breaks),
                emit=len(emitted), gated=gated, **n)


def verdict(rows: list[dict], max_dist_atr: float) -> None:
    """Name the dominant bottleneck instead of leaving the operator to eyeball."""
    if not rows:
        print("\nno symbols probed — nothing to diagnose")
        return

    undef = sum(1 for r in rows if r["bias"] == "UNDEF")
    tot = {k: sum(r[k] for r in rows)
           for k in ("breaks", "choch", "aligned", "recent", "anchor", "zone",
                     "emit", "gated")}

    print("\n" + "-" * 78)
    print(f"TOTAL  breaks={tot['breaks']} CHoCH={tot['choch']} "
          f"aligned={tot['aligned']} recent={tot['recent']} "
          f"anchor={tot['anchor']} zone={tot['zone']} EMIT={tot['emit']} "
          f"gate_drop={tot['gated']}  (bias=UNDEF symbols: {undef}/{len(rows)})")

    # BOS breaks are not a defect — they are simply not the v2 trigger, so that
    # row is printed for context but excluded from the "dominant" pick.
    stages = [
        ("bias", "direction != htf_bias", tot["choch"] - tot["aligned"]),
        ("recency", "outside recency window", tot["aligned"] - tot["recent"]),
        ("anchor", "no unbroken HTF swing anchor", tot["recent"] - tot["anchor"]),
        ("zone", "degenerate OTE zone (ote_band=0,0)", tot["anchor"] - tot["zone"]),
        ("gate", f"entry too far (> {max_dist_atr} ATR)", tot["gated"]),
    ]
    worst_key, _, worst_n = max(stages, key=lambda s: s[2])

    print("drops per stage:")
    print(f"   {tot['breaks'] - tot['choch']:5d}  kind != CHoCH  (BOS — expected, "
          f"not a bottleneck)")
    for key, name, count in stages:
        mark = "  <-- dominant" if key == worst_key and count > 0 else ""
        print(f"   {count:5d}  {name}{mark}")

    if tot["emit"] > 0:
        print(f"\nVERDICT: emit works — {tot['emit']} candidate(s) this instant. "
              f"{tot['gated']} would be dropped by the max_entry_dist_atr gate.")
        return

    print("\nVERDICT: nothing emitted right now.")
    if tot["breaks"] == 0:
        print("  No structure breaks at all. Either the fetch returned too few\n"
              "  bars or swing_lookback is too wide for this data. Check the\n"
              "  brks column per symbol above.")
    elif undef == len(rows):
        print("  Every symbol's HTF bias is UNDEF, so the trigger short-circuits\n"
              "  before the loop. Bias comes from SMCEngine.analyze(df_htf) — the\n"
              "  HTF fetch or the range_lookback window is the thing to look at.")
    elif worst_n == 0:
        print("  Funnel is clean but nothing survived. Re-run — this is a\n"
              "  snapshot of one instant, not a rate.")
    elif worst_key == "bias":
        print("  CHoCHs exist but none agree with the HTF bias.\n"
              "  Bias is the bottleneck, not the trigger.")
    elif worst_key == "recency":
        print("  Aligned CHoCHs exist but all sit outside the recency window.\n"
              "  This is the EXPECTED idle state — a fresh CHoCH has to land\n"
              "  inside the last `risk.recency_bars` bars. Re-run later; only if\n"
              "  many runs in a row show this is recency_bars actually too tight.")
    elif worst_key == "anchor":
        print("  Setups die at the SL anchor: no unbroken HTF swing on the\n"
              "  trade's wrong side. Look at select_htf_swing_anchor and the\n"
              "  number of HTF bars fetched.")
    elif worst_key == "zone":
        print("  Setups die at the zone guard: HTF analyze() returned no OTE\n"
              "  (ote_band = 0,0) and no usable FVG, so build_pullback_zones\n"
              "  produced a degenerate zone. This is a REAL second bottleneck.")
    elif worst_key == "gate":
        print("  Setups are emitted but every one is beyond max_entry_dist_atr.\n"
              "  The gate is doing its job; nothing is broken upstream.")


def main() -> int:
    ap = argparse.ArgumentParser(description="SMC v2 emit funnel diagnostic (read-only)")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--symbols", default="", help="comma-separated override")
    ap.add_argument("--limit", type=int, default=0, help="override kline_limit")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = REPO_ROOT / cfg_path
    if not cfg_path.exists():
        print(f"config not found: {cfg_path}", file=sys.stderr)
        return 2
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    tfs, tf_source = resolve_tfs(cfg)
    limit = args.limit or tfs["kline_limit"]
    recency = (cfg.get("risk", {}) or {}).get("recency_bars", 40)
    v2 = cfg.get("smc_v2", {}) or {}
    max_dist_atr = float(v2.get("max_entry_dist_atr", 0.0) or 0.0)
    anchor_time_axis = bool(v2.get("anchor_time_axis", False))
    syms = ([s.strip() for s in args.symbols.split(",") if s.strip()]
            or symbols_of(cfg))

    print(f"config          {cfg_path}")
    print(f"timeframes      entry={tfs['entry']} mtf={tfs['mtf']} htf={tfs['htf']} "
          f"profile={tfs['profile']}  (via {tf_source})")
    print(f"kline_limit     {limit}")
    print(f"recency_bars    {recency}   -> trigger must land in the last {recency} "
          f"{tfs['entry']} bars")
    print(f"max_entry_dist  {max_dist_atr} ATR   anchor_time_axis={anchor_time_axis}")
    print(f"symbols         {len(syms)}\n")

    import ccxt  # imported late so --help works without the dep

    ex = ccxt.binanceusdm({"enableRateLimit": True})  # NO keys: public data only
    smc = build_smc(cfg)

    rows = []
    for sym in syms:
        try:
            df_entry = fetch(ex, sym, tfs["entry"], limit)
            df_htf = fetch(ex, sym, tfs["htf"], limit)
            rows.append(probe(smc, sym, df_entry, df_htf, recency,
                              max_dist_atr, anchor_time_axis))
        except Exception as exc:
            print(f"{sym:10} ERROR {exc!r}", flush=True)

    verdict(rows, max_dist_atr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
