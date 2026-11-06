#!/usr/bin/env python3
"""Reference expectations for the EFloud Lab indicator's display-only zone layers.

Mirrors pine/lab/tail_indicator.pine rules (spec docs/superpowers/specs/2026-11-06-lab-indicator-visuals-design.md):
OB/FVG/liquidity straight from lx.analyze(); BB/MB (two-scale sweep rule) and the fixed-range OTE as pure functions.
Used by `pine_lab_parity.py visuals` to produce expected.json for TradingView comparisons.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.smc_v2 import luxalgo as lx  # noqa: E402


def swept_pivots(pivots: list, is_high: bool, h: np.ndarray, l: np.ndarray, swing_len: int) -> list:
    """core.pine: swept when a bar after `bar + swing_len` trades through the level (wick)."""
    out = []
    for bar, price in pivots:
        start = bar + swing_len + 1
        seg = h[start:] if is_high else l[start:]
        out.append(bool(seg.size and ((seg > price).any() if is_high else (seg < price).any())))
    return out


def swept_equals(equals: list, h: np.ndarray, l: np.ndarray, eq_len: int) -> list:
    out = []
    for e in equals:
        is_high = e.kind == "EQH"
        start = e.idx_b + eq_len + 1
        seg = h[start:] if is_high else l[start:]
        out.append(bool(seg.size and ((seg > e.price_b).any() if is_high else (seg < e.price_b).any())))
    return out


def volume_confirmed(idx: int, is_high: bool, h: np.ndarray, l: np.ndarray, v: np.ndarray, vma: np.ndarray) -> bool:
    """3 bars ending at idx: rising highs (falling lows), rising volume, last volume above its 60-bar SMA."""
    if idx < 2 or idx >= len(v) or np.isnan(vma[idx]):
        return False
    p = h if is_high else l
    mono = (p[idx - 2] < p[idx - 1] < p[idx]) if is_high else (p[idx - 2] > p[idx - 1] > p[idx])
    return bool(mono and v[idx - 2] < v[idx - 1] < v[idx] and v[idx] > vma[idx])


def _last_pivot_before(pivots: list, bar: int) -> Optional[float]:
    px = None
    for b, p in pivots:
        if b < bar:
            px = p
    return px


def classify_flips(result, h: np.ndarray, l: np.ndarray, c: np.ndarray, swing_len: int, window: int) -> list:
    """Two-scale rule (spec §3.2). A pivot is known to the tail only once confirmed (bar + swing_len <= created)."""
    n = len(c)
    out = []
    seen = set()
    for b in result.breaks:
        ob = b.order_block
        if ob is None or id(ob) in seen:
            continue
        seen.add(id(ob))
        bear = ob.bias == "BEAR"
        top, bot = max(ob.bar_high, ob.bar_low), min(ob.bar_high, ob.bar_low)
        piv = [(pb, pp) for pb, pp in (result.swing_low_pivots if bear else result.swing_high_pivots) if pb + swing_len <= ob.created_idx]
        ref = _last_pivot_before(piv, ob.idx)
        rec = {"top": float(top), "bot": float(bot), "idx": int(ob.idx), "created": int(ob.created_idx),
               "flip": -1, "cls": "NONE", "dead": False, "dir": 1 if bear else -1}
        if ref is None:
            out.append(rec)
            continue
        leg = l[ob.idx + 1:ob.created_idx + 1].min() if bear else h[ob.idx + 1:ob.created_idx + 1].max()
        for t in range(ob.created_idx + 1, min(n, ob.created_idx + 1 + window)):
            if (c[t] > top) if bear else (c[t] < bot):
                rec["flip"] = t
                rec["cls"] = "BB" if ((leg < ref) if bear else (leg > ref)) else "MB"
                after = c[t + 1:]
                rec["dead"] = bool(after.size and ((after < bot).any() if bear else (after > top).any()))
                break
            leg = min(leg, l[t]) if bear else max(leg, h[t])
        out.append(rec)
    return out


def ote_range(result, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> Optional[dict]:
    """Fixed swing range (spec §3.5) evaluated bar by bar up to the last bar."""
    n = len(c)
    swing = {}
    for b in result.breaks:
        if not b.internal:
            swing.setdefault(b.idx, []).append(b)
    H = L = None
    hb = lb = -1
    d = 0
    for t in range(n):
        for b in swing.get(t, []):                       # last swing break on the bar wins (core order)
            ob = b.order_block
            if ob is None:
                continue
            lo_seg = l[b.pivot_idx:t + 1]
            hi_seg = h[b.pivot_idx:t + 1]
            L, H = float(lo_seg.min()), float(hi_seg.max())
            lb = b.pivot_idx + int(np.flatnonzero(lo_seg == L)[-1])
            hb = b.pivot_idx + int(np.flatnonzero(hi_seg == H)[-1])
        if H is None:
            continue
        if h[t] > H:
            H, hb = float(h[t]), t
        if l[t] < L:
            L, lb = float(l[t]), t
        d = 1 if hb > lb else -1 if hb < lb else d
    if H is None or d == 0:
        return None
    r = H - L
    long_ = d == 1
    return {"h": H, "l": L, "hBar": hb, "lBar": lb, "dir": d,
            "b618": H - 0.618 * r if long_ else L + 0.618 * r,
            "b786": H - 0.786 * r if long_ else L + 0.786 * r,
            "p705": H - 0.705 * r if long_ else L + 0.705 * r,
            "eq": L + 0.5 * r}


def expected_visuals(df: pd.DataFrame, cfg: dict, warmup: int = 100) -> dict:
    lux_cfg = cfg.get("smc_v2", {}).get("luxalgo", {}) or {}
    lc = lx.LuxConfig.from_dict(lux_cfg)
    res = lx.analyze(df, lc)
    h, l, c = df.high.to_numpy(float), df.low.to_numpy(float), df.close.to_numpy(float)
    v = df["volume"].to_numpy(float) if "volume" in df else np.zeros(len(df))
    vma = pd.Series(v).rolling(60).mean().to_numpy()
    sw, eqn = int(lux_cfg.get("swing_length", 50)), int(lux_cfg.get("eq_length", 3))

    def box(o):
        return {"top": float(max(o.bar_high, o.bar_low)), "bot": float(min(o.bar_high, o.bar_low)), "idx": int(o.idx)}

    liq = []
    for is_high, pivs in ((True, res.swing_high_pivots), (False, res.swing_low_pivots)):
        for (bar, price), swept in zip(pivs, swept_pivots(pivs, is_high, h, l, sw)):
            if bar >= warmup:
                liq.append({"kind": "BSL" if is_high else "SSL", "price": float(price), "bar": int(bar), "swept": swept,
                            "vol": volume_confirmed(bar, is_high, h, l, v, vma)})
    for e, swept in zip(res.equals, swept_equals(res.equals, h, l, eqn)):
        if e.idx_b >= warmup:
            liq.append({"kind": e.kind, "price": float(e.price_b), "bar": int(e.idx_b), "swept": swept,
                        "vol": volume_confirmed(e.idx_b, e.kind == "EQH", h, l, v, vma)})
    return {
        "meta": {"bars": len(df), "warmup": warmup, "swing_len": sw},
        "ob_swing": [box(o) for o in res.active_obs(internal=False) if o.idx >= warmup],
        "ob_internal": [box(o) for o in res.active_obs(internal=True) if o.idx >= warmup],
        "fvg": [{"top": float(f.top), "bot": float(f.bot), "idx": int(f.idx)} for f in res.active_fvgs() if f.idx >= warmup],
        "liquidity": liq,
        "flips": [f for f in classify_flips(res, h, l, c, sw, 750) if f["idx"] >= warmup and f["flip"] >= 0 and not f["dead"]],
        "ote": ote_range(res, h, l, c),
    }


def cmd_visuals(a) -> int:
    from scripts.pine_lab_parity import load_config, load_ohlcv_csv
    df = load_ohlcv_csv(a.ohlcv).tail(a.window)
    out = expected_visuals(df, load_config(a.config), warmup=a.warmup)
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"visuals: ob {len(out['ob_swing'])}/{len(out['ob_internal'])} fvg {len(out['fvg'])} liq {len(out['liquidity'])} "
          f"flips {len(out['flips'])} ote {'-' if out['ote'] is None else out['ote']['dir']} -> {a.out}")
    return 0
