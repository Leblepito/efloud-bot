"""
Efloud SMC Core Engine — Tüm detection algoritmaları.
Swing, CHoCH/BOS, FVG, Order Block, Breaker, IC, SFP, Range, OTE.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Tuple
import logging

log = logging.getLogger("efloud.engine")


# ═══════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════

@dataclass
class Swing:
    price: float
    idx: int
    ts: str = ""
    is_high: bool = True


@dataclass
class StructBreak:
    kind: str           # "CHoCH" | "BOS"
    direction: str      # "BULL" | "BEAR"
    price: float
    idx: int
    ts: str = ""
    broken_level: float = 0.0


@dataclass
class FVG:
    top: float
    bot: float
    idx: int
    ts: str = ""
    direction: str = "BULL"
    mitigated: bool = False


@dataclass
class OrderBlock:
    top: float
    bot: float
    eq: float               # İç EQ (Efloud: OB range kullanır)
    idx: int
    ts: str = ""
    direction: str = "BULL"
    count: int = 1          # Ardışık mum sayısı
    near_swing: bool = False
    mitigated: bool = False
    became_breaker: bool = False


@dataclass
class SFP:
    price: float
    sweep_level: float
    idx: int
    ts: str = ""
    direction: str = "BULL"


@dataclass
class RangeInfo:
    hi: float
    lo: float
    eq: float
    premium: bool
    discount: bool
    dev_bull: bool = False
    dev_bear: bool = False


@dataclass
class OTE:
    top: float
    bot: float
    ext_1272: float = 0.0
    ext_1618: float = 0.0
    direction: str = "BULL"


@dataclass
class EqLevel:
    """Clustered equal high / low (liquidity pool).

    Used by smc_v2.tp_calc.calc_tp_targets as the primary TP1 source.
    Created by SMCEngine.liquidity_pools() (v2) — distinct from the
    dict-based output of equal_levels() which is kept for v1 callers.
    """
    price: float
    kind: str          # "EQH" (equal highs) | "EQL" (equal lows)
    touches: int = 2   # number of swings clustered (minimum 2)


# ═══════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════

class SMCEngine:

    def __init__(self, swing_lb: int = 5, ob_seq: int = 5,
                 body_mode: bool = True, eq_thr: float = 0.001,
                 range_lb: int = 50, ote_lo: float = 0.618,
                 ote_hi: float = 0.786):
        self.swing_lb = swing_lb
        self.ob_seq = ob_seq
        self.body_mode = body_mode
        self.eq_thr = eq_thr
        self.range_lb = range_lb
        self.ote_lo = ote_lo
        self.ote_hi = ote_hi

    @staticmethod
    def _ts(df: pd.DataFrame) -> list:
        try:
            return df.index.astype(str).tolist()
        except Exception:
            return [""] * len(df)

    # ── Swings ──

    def swings(self, df: pd.DataFrame) -> Tuple[List[Swing], List[Swing]]:
        h, l = df["high"].values, df["low"].values
        n, lb = len(df), self.swing_lb
        ts = self._ts(df)
        sh, sl = [], []
        for i in range(lb, n - lb):
            if all(h[i] > h[i - j] and h[i] > h[i + j] for j in range(1, lb + 1)):
                sh.append(Swing(float(h[i]), i, ts[i] if i < len(ts) else "", True))
            if all(l[i] < l[i - j] and l[i] < l[i + j] for j in range(1, lb + 1)):
                sl.append(Swing(float(l[i]), i, ts[i] if i < len(ts) else "", False))
        return sh, sl

    # ── Structure (CHoCH / BOS) ──

    def structure(self, df: pd.DataFrame, sh: list, sl: list) -> List[StructBreak]:
        c = df["close"].values
        ts = self._ts(df)
        out, trend = [], "UNDEF"
        last_sh, last_sl = None, None
        si, li = 0, 0
        for bar in range(len(c)):
            while si < len(sh) and sh[si].idx <= bar:
                last_sh = sh[si]; si += 1
            while li < len(sl) and sl[li].idx <= bar:
                last_sl = sl[li]; li += 1
            if last_sh and c[bar] > last_sh.price:
                k = "CHoCH" if trend in ("BEAR", "UNDEF") else "BOS"
                out.append(StructBreak(k, "BULL", float(c[bar]), bar,
                           ts[bar] if bar < len(ts) else "", last_sh.price))
                trend = "BULL"; last_sh = None
            if last_sl and c[bar] < last_sl.price:
                k = "CHoCH" if trend in ("BULL", "UNDEF") else "BOS"
                out.append(StructBreak(k, "BEAR", float(c[bar]), bar,
                           ts[bar] if bar < len(ts) else "", last_sl.price))
                trend = "BEAR"; last_sl = None
        return out

    # ── FVG ──

    def fvgs(self, df: pd.DataFrame) -> List[FVG]:
        h, l = df["high"].values, df["low"].values
        ts = self._ts(df)
        out = []
        for i in range(2, len(df)):
            if l[i] > h[i - 2]:
                out.append(FVG(float(l[i]), float(h[i - 2]), i - 1,
                           ts[i - 1] if (i - 1) < len(ts) else "", "BULL"))
            if h[i] < l[i - 2]:
                out.append(FVG(float(l[i - 2]), float(h[i]), i - 1,
                           ts[i - 1] if (i - 1) < len(ts) else "", "BEAR"))
        # Mitigation
        for f in out:
            for j in range(f.idx + 2, len(df)):
                if f.direction == "BULL" and l[j] <= f.bot:
                    f.mitigated = True; break
                elif f.direction == "BEAR" and h[j] >= f.top:
                    f.mitigated = True; break
        return out

    # ── Order Block (Efloud Extended) ──

    def order_blocks(self, df: pd.DataFrame, sh: list, sl: list,
                     trend: str = "UNDEF") -> List[OrderBlock]:
        o, c, h, l = df["open"].values, df["close"].values, df["high"].values, df["low"].values
        ts = self._ts(df)
        atr = pd.Series(h - l).rolling(14).mean().values
        out = []
        bm = self.body_mode

        for i in range(self.ob_seq + 1, len(df)):
            av = atr[i] if not np.isnan(atr[i]) else 0
            body = abs(c[i] - o[i])

            # Bullish OB: ardışık bearish + bullish breakout
            if c[i] > o[i] and body > 1.5 * av:
                cnt, ot, ob = 0, 0.0, float("inf")
                for k in range(1, self.ob_seq + 1):
                    ix = i - k
                    if ix < 0: break
                    if c[ix] < o[ix]:
                        ct = float(o[ix]) if bm else float(h[ix])
                        cb = float(c[ix]) if bm else float(l[ix])
                        if cnt == 0: ot, ob = ct, cb
                        else: ot, ob = max(ot, ct), min(ob, cb)
                        cnt += 1
                    elif cnt > 0: break
                if cnt >= 1 and ot > ob:
                    ns = any(abs(ob - s.price) / s.price < 0.015
                             for s in sl if abs(s.idx - i) < 30)
                    out.append(OrderBlock(
                        round(ot, 8), round(ob, 8), round((ot + ob) / 2, 8),
                        i - cnt, ts[i - cnt] if (i - cnt) < len(ts) else "",
                        "BULL", cnt, ns))

            # Bearish OB: ardışık bullish + bearish breakout
            if c[i] < o[i] and body > 1.5 * av:
                cnt, ot, ob = 0, 0.0, float("inf")
                for k in range(1, self.ob_seq + 1):
                    ix = i - k
                    if ix < 0: break
                    if c[ix] > o[ix]:
                        ct = float(c[ix]) if bm else float(h[ix])
                        cb = float(o[ix]) if bm else float(l[ix])
                        if cnt == 0: ot, ob = ct, cb
                        else: ot, ob = max(ot, ct), min(ob, cb)
                        cnt += 1
                    elif cnt > 0: break
                if cnt >= 1 and ot > ob:
                    ns = any(abs(ot - s.price) / s.price < 0.015
                             for s in sh if abs(s.idx - i) < 30)
                    out.append(OrderBlock(
                        round(ot, 8), round(ob, 8), round((ot + ob) / 2, 8),
                        i - cnt, ts[i - cnt] if (i - cnt) < len(ts) else "",
                        "BEAR", cnt, ns))

        # Mitigation → breaker
        for ob in out:
            for j in range(ob.idx + 2, len(df)):
                if ob.direction == "BULL" and c[j] < ob.bot:
                    ob.mitigated = ob.became_breaker = True; break
                elif ob.direction == "BEAR" and c[j] > ob.top:
                    ob.mitigated = ob.became_breaker = True; break
        return out

    # ── SFP ──

    def sfps(self, df: pd.DataFrame, sh: list, sl: list) -> List[SFP]:
        h, l, c = df["high"].values, df["low"].values, df["close"].values
        ts = self._ts(df)
        out = []
        for i in range(1, len(df)):
            for s in sl:
                if 1 < i - s.idx < 50 and l[i] < s.price and c[i] > s.price:
                    out.append(SFP(float(c[i]), s.price, i,
                               ts[i] if i < len(ts) else "", "BULL"))
                    break
            for s in sh:
                if 1 < i - s.idx < 50 and h[i] > s.price and c[i] < s.price:
                    out.append(SFP(float(c[i]), s.price, i,
                               ts[i] if i < len(ts) else "", "BEAR"))
                    break
        return out

    # ── Range ──

    def range_info(self, df: pd.DataFrame) -> RangeInfo:
        lb = min(self.range_lb, len(df))
        r = df.iloc[-lb:]
        hi, lo = float(r["high"].max()), float(r["low"].min())
        eq = (hi + lo) / 2
        lc, ll, lh = float(df["close"].iloc[-1]), float(df["low"].iloc[-1]), float(df["high"].iloc[-1])
        return RangeInfo(hi, lo, eq, lc > eq, lc < eq,
                         ll < lo and lc > lo, lh > hi and lc < hi)

    # ── OTE ──

    def ote(self, sh: list, sl: list, trend: str) -> Optional[OTE]:
        if not sh or not sl: return None
        d = sh[-1].price - sl[-1].price
        if d <= 0: return None
        if trend == "BULL":
            return OTE(sh[-1].price - d * self.ote_lo, sh[-1].price - d * self.ote_hi,
                       sl[-1].price + d * 1.272, sl[-1].price + d * 1.618, "BULL")
        return OTE(sl[-1].price + d * self.ote_hi, sl[-1].price + d * self.ote_lo,
                   sh[-1].price - d * 1.272, sh[-1].price - d * 1.618, "BEAR")

    # ── Equal Levels ──

    def equal_levels(self, swings: list) -> list:
        out = []
        for i in range(len(swings)):
            for j in range(i + 1, min(i + 5, len(swings))):
                if swings[i].is_high != swings[j].is_high: continue
                if abs(swings[i].price - swings[j].price) / max(swings[i].price, 1e-10) <= self.eq_thr:
                    out.append({"price": (swings[i].price + swings[j].price) / 2,
                                "type": "EQH" if swings[i].is_high else "EQL"})
        return out

    # ── Full Single-TF Analysis ──

    def analyze(self, df: pd.DataFrame) -> dict:
        sh, sl = self.swings(df)
        brks = self.structure(df, sh, sl)
        trend = brks[-1].direction if brks else "UNDEF"
        fvg_list = self.fvgs(df)
        ob_list = self.order_blocks(df, sh, sl, trend)
        sfp_list = self.sfps(df, sh, sl)
        rng = self.range_info(df)
        ote_zone = self.ote(sh, sl, trend)
        eq_h = self.equal_levels(sh)
        eq_l = self.equal_levels(sl)
        a_fvg = [f for f in fvg_list if not f.mitigated]
        a_ob = [o for o in ob_list if not o.mitigated]

        return {
            "trend": trend,
            "last_break": asdict(brks[-1]) if brks else None,
            "swing_highs": sh,
            "swing_lows": sl,
            "breaks": brks,
            "active_fvgs": a_fvg,
            "active_obs": a_ob,
            "sfps": sfp_list[-10:],
            "range": rng,
            "ote": ote_zone,
            "eq_highs": eq_h,
            "eq_lows": eq_l,
        }
