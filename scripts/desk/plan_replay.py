#!/usr/bin/env python3
"""Plan replay — Monte Carlo odds for an entry/stop/target plan on 24/7 crypto bars.

Adapted from day-trader-skill's `trader-timemachine/timemachine.py`
(https://github.com/Jakeschincariol/day-trader-skill, MIT License,
Copyright (c) 2026 Jake Schincariol; see THIRD_PARTY_NOTICES.md). Changes for
Binance USDT-M perpetuals: UTC time-of-day slots instead of NYSE sessions, a
fixed horizon in bars instead of the session close, shorts supported, and the
round-trip fee folded into R (efloud's NET-cost rule).

Research tool only. It never places orders and is not imported by the engine.

How it works:
  1. Pool: every closed bar becomes (o, h, l, c) / previous close, filed under its
     UTC slot of the day (minute_of_day // tf). Only consecutive bars count.
  2. Replay: start at the entry; for each of `horizon` bars draw a past bar from the
     same slot (+/- `window` slots, wrapping midnight), scale it to the current
     price, check the stop first, then the target. A bar touching both = stop.
  3. Odds: target first, stop first, neither (still open at the horizon), plus
     average NET R. Break-even share of the replays that hit a side is
     (1 + cost_R) / (1 + R_target).
  4. History: the same plan geometry (stop/target as % of entry) entered at the
     same slot on every past day, walked forward on the real bars.

Usage:
  python scripts/desk/plan_replay.py --symbol BTC/USDT --tf 15m --side long \
      --entry 68000 --stop 67300 --target 69400 --horizon 96 [--days 60] [--json]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

import pandas as pd

KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
MIN_DAYS = 20
MIN_RISK_FRAC = 0.0005      # risk under 0.05 % of price is too tight to survive the spread
COIN_FLIP = 0.05
STRONG = 0.15
DEFAULT_FEE_PCT = 0.04      # per side, matches configs backtest.commission_pct


class PlanError(ValueError):
    pass


@dataclass
class Plan:
    side: str       # "long" | "short"
    entry: float
    stop: float
    target: float

    @property
    def long(self) -> bool:
        return self.side == "long"

    @property
    def risk(self) -> float:
        return (self.entry - self.stop) if self.long else (self.stop - self.entry)

    @property
    def r_target(self) -> float:
        reward = (self.target - self.entry) if self.long else (self.entry - self.target)
        return reward / self.risk


def validate(plan: Plan) -> None:
    if plan.side not in ("long", "short"):
        raise PlanError(f"side must be long or short, got {plan.side!r}")
    if plan.risk <= 0:
        raise PlanError("stop is on the wrong side of the entry")
    if plan.r_target <= 0:
        raise PlanError("target is on the wrong side of the entry")
    if plan.risk < plan.entry * MIN_RISK_FRAC:
        raise PlanError("stop too tight: risk under 0.05 % of the entry")


def _tf_minutes(tf: str) -> int:
    units = {"m": 1, "h": 60, "d": 1440}
    try:
        return int(tf[:-1]) * units[tf[-1]]
    except (KeyError, ValueError):
        raise PlanError(f"unsupported timeframe {tf!r}") from None


def _slot(ts: pd.Timestamp, tf_minutes: int) -> int:
    return (ts.hour * 60 + ts.minute) // tf_minutes


def build_pool(df: pd.DataFrame, tf_minutes: int) -> list[list[tuple]]:
    """pool[slot] = (o, h, l, c) / previous close for every consecutive pair of bars."""
    n_slots = 1440 // tf_minutes
    pool: list[list[tuple]] = [[] for _ in range(n_slots)]
    step = pd.Timedelta(minutes=tf_minutes)
    idx, o, h, l, c = df.index, df["open"].values, df["high"].values, df["low"].values, df["close"].values
    for i in range(1, len(df)):
        if idx[i] - idx[i - 1] != step:
            continue
        pc = c[i - 1]
        pool[_slot(idx[i], tf_minutes)].append((o[i] / pc, h[i] / pc, l[i] / pc, c[i] / pc))
    return pool


def _pct(sorted_vals, q):
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def simulate(pool, plan: Plan, start_slot: int, horizon: int, replays: int = 10000,
             seed: int = 19, window: int = 2, fee_pct: float = 0.0) -> dict:
    """Monte Carlo replays of `horizon` bars starting at `start_slot`."""
    validate(plan)
    n_slots = len(pool)
    long = plan.long
    risk = plan.risk
    r_target = plan.r_target
    cost_r = (2 * fee_pct / 100.0 * plan.entry) / risk
    rng = random.Random(seed)

    def draw(base):
        s = base if window == 0 else (base + rng.randint(-window, window)) % n_slots
        bucket = pool[s] or pool[base]
        if not bucket:
            raise PlanError(f"no history for slot {base}")
        return rng.choice(bucket)

    outcomes, closes = [], []
    for _ in range(replays):
        p = plan.entry
        outcome = None
        for j in range(horizon):
            _, h, lo, c = draw((start_slot + j) % n_slots)
            hi, low, cl = p * h, p * lo, p * c
            if long:
                if low <= plan.stop:
                    outcome = "stop"
                elif hi >= plan.target:
                    outcome = "target"
            else:
                if hi >= plan.stop:
                    outcome = "stop"
                elif low <= plan.target:
                    outcome = "target"
            p = cl
            if outcome:
                break
        outcomes.append(outcome or "neither")
        closes.append(p)

    def r_of(o, p):
        if o == "target":
            return r_target - cost_r
        if o == "stop":
            return -1.0 - cost_r
        return ((p - plan.entry) if long else (plan.entry - p)) / risk - cost_r

    srt = sorted(closes)
    return {
        "replays": replays, "seed": seed, "window": window, "horizon": horizon,
        "p_target": outcomes.count("target") / replays,
        "p_stop": outcomes.count("stop") / replays,
        "p_neither": outcomes.count("neither") / replays,
        "avg_r": round(statistics.mean(r_of(o, p) for o, p in zip(outcomes, closes)), 6),
        "r_at_target": round(r_target, 4), "cost_r": round(cost_r, 6),
        "p5_close": _pct(srt, 0.05), "median_close": _pct(srt, 0.5), "p95_close": _pct(srt, 0.95),
    }


def history(df: pd.DataFrame, plan: Plan, tf_minutes: int, horizon: int) -> dict:
    """Real record: the plan's % geometry entered at the entry bar's slot on every past day."""
    validate(plan)
    slot0 = _slot(df.index[-1], tf_minutes)
    step = pd.Timedelta(minutes=tf_minutes)
    stop_k, target_k = plan.stop / plan.entry, plan.target / plan.entry
    idx, h, l, c = df.index, df["high"].values, df["low"].values, df["close"].values
    counts = {"target": 0, "stop": 0, "neither": 0}
    for i in range(len(df) - 1 - horizon):
        if _slot(idx[i], tf_minutes) != slot0:
            continue
        if idx[i + horizon] - idx[i] != step * horizon:
            continue  # gap inside the window
        e = c[i]
        stop, target = e * stop_k, e * target_k
        outcome = "neither"
        for j in range(i + 1, i + horizon + 1):
            if plan.long:
                if l[j] <= stop:
                    outcome = "stop"
                elif h[j] >= target:
                    outcome = "target"
            else:
                if h[j] >= stop:
                    outcome = "stop"
                elif l[j] <= target:
                    outcome = "target"
            if outcome != "neither":
                break
        counts[outcome] += 1
    n = sum(counts.values())
    return {"n": n, **{f"p_{k}": (v / n if n else 0.0) for k, v in counts.items()}}


def verdict(mc: dict) -> str:
    pt, ps = mc["p_target"], mc["p_stop"]
    if pt + ps <= 0:
        return (f"No replay reached the target or the stop within {mc.get('horizon')} bars: "
                "the price at the horizon decides every one.")
    r = mc.get("r_at_target") or 1.0
    cost = mc.get("cost_r") or 0.0
    share, even = pt / (pt + ps), (1.0 + cost) / (1.0 + r)
    d = share - even
    one_r = abs(r - 1.0) < 0.005 and cost == 0
    if abs(d) < COIN_FLIP:
        head = "Close to a coin flip" if one_r else "Close to break-even"
    elif abs(d) < STRONG:
        head = "Leans toward the target" if d > 0 else "Leans toward the stop"
    else:
        head = "Strongly toward the target" if d > 0 else "Strongly toward the stop"
    return (f"{head}: at {r:g}R (fees {cost:.2f}R) the target must come first in "
            f"{100 * even:.0f} % of the replays that hit a side; it did in {100 * share:.0f} % "
            f"(target first {100 * pt:.1f} % vs stop first {100 * ps:.1f} %).")


def run(df: pd.DataFrame, plan: Plan, tf_minutes: int, horizon: int, replays: int = 10000,
        seed: int = 19, window: int = 2, fee_pct: float = DEFAULT_FEE_PCT) -> dict:
    validate(plan)
    days = (df.index[-1] - df.index[0]).days if len(df) else 0
    if days < MIN_DAYS:
        raise PlanError(f"need at least {MIN_DAYS} days of bars, got {days} days")
    pool = build_pool(df, tf_minutes)
    start_slot = (_slot(df.index[-1], tf_minutes) + 1) % len(pool)
    mc = simulate(pool, plan, start_slot, horizon, replays, seed, window, fee_pct)
    return {"mc": mc, "history": history(df, plan, tf_minutes, horizon), "verdict": verdict(mc),
            "last_closed_bar_utc": df.index[-1].isoformat()}


def _frame(rows) -> pd.DataFrame:
    df = pd.DataFrame([r[:6] for r in rows], columns=["ts", "open", "high", "low", "close", "volume"])
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    df.index = pd.to_datetime(df.pop("ts").astype("int64"), unit="ms", utc=True)
    return df[~df.index.duplicated()].sort_index()


def fetch_klines(symbol: str, tf: str, days: int) -> pd.DataFrame:
    """Public Binance USDT-M klines (no key). Drops the still-forming bar."""
    sym = symbol.replace("/", "").split(":")[0]
    end = int(time.time() * 1000)
    start = end - days * 86_400_000
    rows: list = []
    cursor = start
    while cursor < end:
        q = urllib.parse.urlencode({"symbol": sym, "interval": tf, "startTime": cursor, "limit": 1500})
        with urllib.request.urlopen(f"{KLINES_URL}?{q}", timeout=20) as resp:
            batch = json.loads(resp.read())
        if not batch:
            break
        rows += batch
        cursor = batch[-1][0] + 1
    now_ms = int(time.time() * 1000)
    rows = [r for r in rows if int(r[6]) < now_ms]  # close time in the past = closed bar
    return _frame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--side", required=True, choices=["long", "short"])
    ap.add_argument("--entry", type=float, required=True)
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--horizon", type=int, default=96, help="bars to hold before 'neither'")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--replays", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=19)
    ap.add_argument("--window", type=int, default=2)
    ap.add_argument("--fee-pct", type=float, default=DEFAULT_FEE_PCT, help="per side, percent")
    ap.add_argument("--offline", help="JSON file of Binance kline rows instead of fetching")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    plan = Plan(a.side, a.entry, a.stop, a.target)
    tf_min = _tf_minutes(a.tf)
    try:
        if a.offline:
            with open(a.offline, encoding="utf-8") as fh:
                df = _frame(json.load(fh))
        else:
            df = fetch_klines(a.symbol, a.tf, a.days)
        doc = run(df, plan, tf_min, a.horizon, a.replays, a.seed, a.window, a.fee_pct)
    except PlanError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    doc["plan"] = {"symbol": a.symbol, "tf": a.tf, **asdict(plan)}
    if a.json:
        print(json.dumps(doc, default=float))
    else:
        mc, hist = doc["mc"], doc["history"]
        print(f"{a.symbol} {a.tf} {a.side} entry {a.entry} stop {a.stop} target {a.target} "
              f"| last closed bar {doc['last_closed_bar_utc']} | seed {mc['seed']}")
        print(f"replays {mc['replays']}: target {mc['p_target']:.1%} stop {mc['p_stop']:.1%} "
              f"neither {mc['p_neither']:.1%} avg NET R {mc['avg_r']:+.3f}")
        print(f"history (same slot, real bars, n={hist['n']}): target {hist['p_target']:.1%} "
              f"stop {hist['p_stop']:.1%} neither {hist['p_neither']:.1%}")
        print(doc["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
