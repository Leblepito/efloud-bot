"""LuxAlgo "Smart Money Concepts" port — bar-by-bar, repaint-free.

Kaynak: TradingView "Smart Money Concepts (SMC) [LuxAlgo]" (CnB3fSph,
open-source, CC BY-NC-SA 4.0 — LuxAlgo). Bu modül Pine kodunun MANTIĞINI
Python'a taşır; Pine'daki her `bar` adımı burada aynı sırayla işlenir:

    deleteOrderBlocks(internal) → deleteOrderBlocks(swing)
    getCurrentStructure(swing_len) → getCurrentStructure(5, internal)
    getCurrentStructure(eq_len, equal) → displayStructure(internal)
    displayStructure(swing) → updateTrailingExtremes → FVG

Tanımlar (Pine ile birebir):
  * Pivot: leg(size) — bar[t-size].high > highest(high, size) (t-size+1..t)
    → bearish leg (pivot HIGH), bar[t-size].low < lowest(...) → bullish leg
    (pivot LOW). Pivot yalnız bacak DEĞİŞİNCE kaydedilir (high/low alternatif).
    Pivot `size` bar sonra onaylanır → lookahead YOK.
  * BOS/CHoCH: close, pivot seviyesini crossover/crossunder eder ve pivot
    daha önce kırılmamışsa. Trend bias tersse CHoCH, değilse BOS.
    Internal kırılım, internal pivot == swing pivot ise sayılmaz.
  * Order Block: kırılım anında [pivot.bar, kırılım-1] aralığında
    BULL → en düşük parsedLow mumu, BEAR → en yüksek parsedHigh mumu.
    parsedHigh/Low: yüksek volatilite mumunda (range >= 2×ATR(200)) high/low
    yer değiştirir (LuxAlgo "Order Block Filter").
  * OB mitigation: HIGHLOW (default) → BULL OB low < OB.barLow ile silinir,
    BEAR OB high > OB.barHigh ile silinir. CLOSE modu close kullanır.
  * EQH/EQL: leg(eq_len) pivotları, |önceki - yeni| < eq_threshold × ATR(200).
  * FVG: low > high[2] ve close[1] > high[2] ve barDelta% > auto-threshold.
  * Premium/Discount: trailing top/bottom (swing pivot + running extreme);
    premium = [0.95t+0.05b, t], eq = [0.475.., 0.525..], discount = [b, 0.95b+0.05t].
  * Strong/Weak: swing trend BEAR → top "Strong High"; BULL → bottom "Strong Low".

Saf fonksiyonlar — I/O yok, log yok.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

BULL = "BULL"
BEAR = "BEAR"


# ═══════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════

@dataclass
class LuxPivot:
    current_level: float = math.nan
    last_level: float = math.nan
    crossed: bool = False
    bar_index: int = -1


@dataclass
class LuxBreak:
    kind: str           # "CHoCH" | "BOS"
    direction: str      # "BULL" | "BEAR"
    level: float        # kırılan pivot seviyesi
    pivot_idx: int      # kırılan pivotun bar indeksi
    idx: int            # kırılım barı
    ts: str
    internal: bool
    order_block: Optional["LuxOrderBlock"] = None


@dataclass
class LuxOrderBlock:
    bar_high: float     # Pine parsedHigh (yüksek-vol mumda aslında low)
    bar_low: float      # Pine parsedLow
    idx: int            # OB mumu indeksi
    ts: str
    bias: str           # BULL | BEAR
    internal: bool
    created_idx: int    # kırılım barı (OB'nin bilindiği an)
    mitigated_idx: int = -1

    @property
    def top(self) -> float:
        return max(self.bar_high, self.bar_low)

    @property
    def bot(self) -> float:
        return min(self.bar_high, self.bar_low)

    @property
    def mitigated(self) -> bool:
        return self.mitigated_idx >= 0


@dataclass
class LuxFVG:
    top: float
    bot: float
    idx: int            # orta mum (bar t-1)
    bias: str
    mitigated_idx: int = -1


@dataclass
class LuxEqual:
    kind: str           # "EQH" | "EQL"
    price_a: float
    price_b: float
    idx_a: int
    idx_b: int


@dataclass
class LuxZones:
    top: float
    bottom: float

    @property
    def premium_low(self) -> float:
        return 0.95 * self.top + 0.05 * self.bottom

    @property
    def discount_high(self) -> float:
        return 0.95 * self.bottom + 0.05 * self.top

    @property
    def equilibrium(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def eq_low(self) -> float:
        return 0.525 * self.bottom + 0.475 * self.top

    @property
    def eq_high(self) -> float:
        return 0.525 * self.top + 0.475 * self.bottom


@dataclass
class LuxResult:
    swing_trend: str                      # BULL | BEAR | UNDEF
    internal_trend: str
    breaks: List[LuxBreak]
    swing_obs: List[LuxOrderBlock]        # tümü (mitigated dahil), oluşum sırası
    internal_obs: List[LuxOrderBlock]
    fvgs: List[LuxFVG]
    equals: List[LuxEqual]
    zones: Optional[LuxZones]
    strong_high: Optional[float]          # swing trend BEAR iken top
    strong_low: Optional[float]           # swing trend BULL iken bottom
    swing_high_pivots: List[tuple] = field(default_factory=list)  # (idx, price)
    swing_low_pivots: List[tuple] = field(default_factory=list)

    def active_obs(self, internal: Optional[bool] = None) -> List[LuxOrderBlock]:
        pools = []
        if internal in (None, False):
            pools += self.swing_obs
        if internal in (None, True):
            pools += self.internal_obs
        return [o for o in pools if not o.mitigated]

    def active_fvgs(self) -> List[LuxFVG]:
        return [f for f in self.fvgs if f.mitigated_idx < 0]


@dataclass
class LuxConfig:
    swing_length: int = 50
    internal_length: int = 5
    eq_length: int = 3
    eq_threshold: float = 0.1
    ob_filter: str = "ATR"            # "ATR" | "RANGE" (cumulative mean range)
    ob_mitigation: str = "HIGHLOW"    # "HIGHLOW" | "CLOSE"
    internal_confluence_filter: bool = False
    fvg_auto_threshold: bool = True
    atr_length: int = 200

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "LuxConfig":
        d = d or {}
        c = cls()
        for k in c.__dataclass_fields__:
            if k in d and d[k] is not None:
                setattr(c, k, type(getattr(c, k))(d[k]))
        return c


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def _rma_atr(h, l, c, length: int) -> np.ndarray:
    """Pine ta.atr(length) — RMA of true range; ilk length-1 bar NaN."""
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.full(n, np.nan)
    if n < length:
        return out
    out[length - 1] = tr[:length].mean()
    a = 1.0 / length
    for i in range(length, n):
        out[i] = a * tr[i] + (1 - a) * out[i - 1]
    return out


def _true_range(h, l, c) -> np.ndarray:
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


class _Leg:
    """Pine leg(size) + ta.change state."""
    __slots__ = ("size", "leg", "prev")

    def __init__(self, size: int):
        self.size = size
        self.leg = 0          # Pine: var leg = 0 (BEARISH_LEG)
        self.prev = 0

    def step(self, t: int, h, l) -> int:
        """Return +1 (new pivot LOW / bullish leg), -1 (new pivot HIGH), 0."""
        s = self.size
        self.prev = self.leg
        if t >= s:
            win_h = h[t - s + 1: t + 1]
            win_l = l[t - s + 1: t + 1]
            if h[t - s] > win_h.max():
                self.leg = 0
            elif l[t - s] < win_l.min():
                self.leg = 1
        return self.leg - self.prev


# ═══════════════════════════════════════════════
# Core
# ═══════════════════════════════════════════════

def analyze(df: pd.DataFrame, cfg: Optional[LuxConfig] = None) -> LuxResult:
    """Run the LuxAlgo SMC state machine over ``df`` (closed bars only)."""
    cfg = cfg or LuxConfig()
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    n = len(df)
    try:
        ts = df.index.astype(str).tolist()
    except Exception:  # pragma: no cover
        ts = [""] * n

    atr = _rma_atr(h, l, c, cfg.atr_length)
    if cfg.ob_filter.upper() == "ATR":
        vol = atr
    else:
        tr = _true_range(h, l, c)
        vol = np.full(n, np.nan)
        cum = np.cumsum(tr)
        for i in range(1, n):
            vol[i] = cum[i] / i          # Pine: ta.cum(ta.tr) / bar_index
    high_vol = np.where(np.isnan(vol), False, (h - l) >= 2 * np.nan_to_num(vol, nan=np.inf))
    parsed_high = np.where(high_vol, l, h)
    parsed_low = np.where(high_vol, h, l)

    swing_high, swing_low = LuxPivot(), LuxPivot()
    int_high, int_low = LuxPivot(), LuxPivot()
    eq_high, eq_low = LuxPivot(), LuxPivot()
    swing_bias, int_bias = 0, 0          # 0 undef, +1 bull, -1 bear
    trail_top, trail_bot = math.nan, math.nan

    leg_swing = _Leg(cfg.swing_length)
    leg_int = _Leg(cfg.internal_length)
    leg_eq = _Leg(cfg.eq_length)

    breaks: List[LuxBreak] = []
    swing_obs: List[LuxOrderBlock] = []
    int_obs: List[LuxOrderBlock] = []
    fvgs: List[LuxFVG] = []
    equals: List[LuxEqual] = []
    sh_piv: List[tuple] = []
    sl_piv: List[tuple] = []

    fvg_cum = 0.0
    hi_mit = c if cfg.ob_mitigation.upper() == "CLOSE" else h
    lo_mit = c if cfg.ob_mitigation.upper() == "CLOSE" else l

    def _mitigate(pool: List[LuxOrderBlock], t: int) -> None:
        for ob in pool:
            if ob.mitigated_idx >= 0:
                continue
            if ob.bias == BEAR and hi_mit[t] > ob.bar_high:
                ob.mitigated_idx = t
            elif ob.bias == BULL and lo_mit[t] < ob.bar_low:
                ob.mitigated_idx = t

    def _pivot_update(leg: _Leg, kind: str, t: int) -> None:
        nonlocal trail_top, trail_bot
        ch = leg.step(t, h, l)
        if ch == 0:
            return
        s = leg.size
        pi = t - s
        if ch == 1:      # bullish leg starts → pivot LOW at t-s
            p = {"swing": swing_low, "internal": int_low, "equal": eq_low}[kind]
            if kind == "equal" and not math.isnan(p.current_level) \
                    and not math.isnan(atr[t]) \
                    and abs(p.current_level - l[pi]) < cfg.eq_threshold * atr[t]:
                equals.append(LuxEqual("EQL", p.current_level, float(l[pi]),
                                       p.bar_index, pi))
            p.last_level = p.current_level
            p.current_level = float(l[pi])
            p.crossed = False
            p.bar_index = pi
            if kind == "swing":
                trail_bot = p.current_level
                sl_piv.append((pi, p.current_level))
        else:            # bearish leg starts → pivot HIGH at t-s
            p = {"swing": swing_high, "internal": int_high, "equal": eq_high}[kind]
            if kind == "equal" and not math.isnan(p.current_level) \
                    and not math.isnan(atr[t]) \
                    and abs(p.current_level - h[pi]) < cfg.eq_threshold * atr[t]:
                equals.append(LuxEqual("EQH", p.current_level, float(h[pi]),
                                       p.bar_index, pi))
            p.last_level = p.current_level
            p.current_level = float(h[pi])
            p.crossed = False
            p.bar_index = pi
            if kind == "swing":
                trail_top = p.current_level
                sh_piv.append((pi, p.current_level))

    def _store_ob(p: LuxPivot, internal: bool, bias: str, t: int) -> Optional[LuxOrderBlock]:
        a, b = p.bar_index, t           # Pine slice(barIndex, bar_index) — exclusive
        if a < 0 or b <= a:
            return None
        if bias == BEAR:
            seg = parsed_high[a:b]
            k = a + int(np.argmax(seg))
        else:
            seg = parsed_low[a:b]
            k = a + int(np.argmin(seg))
        ob = LuxOrderBlock(float(parsed_high[k]), float(parsed_low[k]), k,
                           ts[k], bias, internal, t)
        (int_obs if internal else swing_obs).append(ob)
        return ob

    def _structure(internal: bool, t: int) -> None:
        nonlocal swing_bias, int_bias
        bull_bar = bear_bar = True
        if internal and cfg.internal_confluence_filter:
            # Pine (birebir, operatör önceliği dahil):
            # high - max(close, open) > min(close, open - low)
            bull_bar = h[t] - max(c[t], o[t]) > min(c[t], o[t] - l[t])
            bear_bar = h[t] - max(c[t], o[t]) < min(c[t], o[t] - l[t])
        prev_c = c[t - 1] if t > 0 else math.nan

        # Bullish break
        p = int_high if internal else swing_high
        bias = int_bias if internal else swing_bias
        extra = (int_high.current_level != swing_high.current_level and bull_bar) if internal else True
        lvl = p.current_level
        if (not math.isnan(lvl) and c[t] > lvl and not (prev_c > lvl)
                and not p.crossed and extra):
            kind = "CHoCH" if bias == -1 else "BOS"
            p.crossed = True
            ob = _store_ob(p, internal, BULL, t)
            breaks.append(LuxBreak(kind, BULL, lvl, p.bar_index, t, ts[t], internal, ob))
            if internal:
                int_bias = 1
            else:
                swing_bias = 1

        # Bearish break
        p = int_low if internal else swing_low
        bias = int_bias if internal else swing_bias
        extra = (int_low.current_level != swing_low.current_level and bear_bar) if internal else True
        lvl = p.current_level
        if (not math.isnan(lvl) and c[t] < lvl and not (prev_c < lvl)
                and not p.crossed and extra):
            kind = "CHoCH" if bias == 1 else "BOS"
            p.crossed = True
            ob = _store_ob(p, internal, BEAR, t)
            breaks.append(LuxBreak(kind, BEAR, lvl, p.bar_index, t, ts[t], internal, ob))
            if internal:
                int_bias = -1
            else:
                swing_bias = -1

    for t in range(n):
        _mitigate(int_obs, t)
        _mitigate(swing_obs, t)
        _pivot_update(leg_swing, "swing", t)
        _pivot_update(leg_int, "internal", t)
        _pivot_update(leg_eq, "equal", t)
        _structure(True, t)
        _structure(False, t)

        # updateTrailingExtremes
        trail_top = h[t] if math.isnan(trail_top) else max(h[t], trail_top)
        trail_bot = l[t] if math.isnan(trail_bot) else min(l[t], trail_bot)

        # FVG (chart timeframe; newTimeframe her bar True)
        for f in fvgs:
            if f.mitigated_idx >= 0:
                continue
            if f.bias == BULL and l[t] < f.bot:
                f.mitigated_idx = t
            elif f.bias == BEAR and h[t] > f.top:
                f.mitigated_idx = t
        if t >= 2:
            delta = (c[t - 1] - o[t - 1]) / (o[t - 1] * 100) if o[t - 1] else 0.0
            fvg_cum += abs(delta)
            thr = (fvg_cum / t * 2) if cfg.fvg_auto_threshold else 0.0
            if l[t] > h[t - 2] and c[t - 1] > h[t - 2] and delta > thr:
                fvgs.append(LuxFVG(float(l[t]), float(h[t - 2]), t - 1, BULL))
            if h[t] < l[t - 2] and c[t - 1] < l[t - 2] and -delta > thr:
                fvgs.append(LuxFVG(float(l[t - 2]), float(h[t]), t - 1, BEAR))

    def _b(x: int) -> str:
        return BULL if x == 1 else BEAR if x == -1 else "UNDEF"

    zones = None
    if n and not (math.isnan(trail_top) or math.isnan(trail_bot)) and trail_top > trail_bot:
        zones = LuxZones(trail_top, trail_bot)

    return LuxResult(
        swing_trend=_b(swing_bias),
        internal_trend=_b(int_bias),
        breaks=breaks,
        swing_obs=swing_obs,
        internal_obs=int_obs,
        fvgs=fvgs,
        equals=equals,
        zones=zones,
        strong_high=trail_top if swing_bias == -1 else None,
        strong_low=trail_bot if swing_bias == 1 else None,
        swing_high_pivots=sh_piv,
        swing_low_pivots=sl_piv,
    )


# ═══════════════════════════════════════════════
# Trade model (LuxAlgo yayın görselleri)
# ═══════════════════════════════════════════════
#   LONG : bullish kırılımın yarattığı BULL OB'ye geri çekilmede giriş
#          (discount tarafı), SL OB kenarı (+ATR payı calc_sl'de),
#          TP = karşı FVG / karşı (BEAR) OB / equilibrium / likidite (EQH, trailing top).
#   SHORT: ayna — "Entry at Premium", SL "Above Strong Highs & Swing OB",
#          TP "50% level ... at the Equilibrium" ya da karşı BULL OB.

OTE_BAND = (0.618, 0.786)
FIB_EXT_RATIOS = (1.272, 1.618, 2.618)


def _overlaps(lo1: float, hi1: float, lo2: float, hi2: float) -> bool:
    return lo1 <= hi2 and lo2 <= hi1


def zone_confluence(direction: str, brk: "LuxBreak", ob: "LuxOrderBlock",
                    lux: "LuxResult") -> List[str]:
    """Efloud notları: "PA konseptleri çoklu değerlendirilmek zorunda".

    OB'nin yanında hangi ek konseptler aynı bölgede çakışıyor:
      SWING_OB — swing high/low bölgesindeki OB (ara bölge OB'sinden güçlü)
      OTE      — OB, dealing range'in 0.618-0.786 retracement bandıyla çakışıyor
      EQ       — OB, range ortalaması (equilibrium) alanıyla çakışıyor
      FVG      — OB'den sonra oluşan, doldurulmamış aynı yönlü imbalance bölgeyle çakışıyor
      SWEEP    — OB, kendinden önceki swing pivotunun likiditesini süpürmüş (SFP)
    """
    tags: List[str] = []
    if not brk.internal:
        tags.append("SWING_OB")
    z = lux.zones
    long_ = direction == "LONG"
    if z is not None:
        rng = z.top - z.bottom
        if long_:
            band = (z.top - rng * OTE_BAND[1], z.top - rng * OTE_BAND[0])
        else:
            band = (z.bottom + rng * OTE_BAND[0], z.bottom + rng * OTE_BAND[1])
        if _overlaps(ob.bot, ob.top, band[0], band[1]):
            tags.append("OTE")
        if _overlaps(ob.bot, ob.top, z.eq_low, z.eq_high):
            tags.append("EQ")
    want = BULL if long_ else BEAR
    for f in lux.active_fvgs():
        if f.bias == want and f.idx >= ob.idx and _overlaps(ob.bot, ob.top, f.bot, f.top):
            tags.append("FVG")
            break
    piv = lux.swing_low_pivots if long_ else lux.swing_high_pivots
    prior = [p for p in piv if p[0] < ob.idx]
    if prior:
        price = prior[-1][1]
        if (long_ and ob.bot < price) or (not long_ and ob.top > price):
            tags.append("SWEEP")
    return tags


def generate_candidates(
    symbol: str,
    lux: LuxResult,
    htf_bias: str,
    trigger_idx_min: int,
    use_internal: bool = True,
    use_swing: bool = True,
    require_premium_discount: bool = True,
    allowed_kinds=("CHoCH", "BOS"),
    min_confluence: int = 0,
):
    """Kırılım → OB retest SetupCandidate'leri (state=AWAITING_PULLBACK).

    target_zone = kırılımın yarattığı OB (source="OB"), htf_swing_anchor =
    OB'nin uç fiyatı; swing OB'de Strong Low/High ile birleştirilir.
    """
    from engine.smc_v2.setup_state import SetupCandidate
    from engine.smc_v2.zones import ZoneSpec

    if htf_bias not in (BULL, BEAR):
        return []
    out = []
    for brk in lux.breaks:
        if brk.idx < trigger_idx_min or brk.direction != htf_bias:
            continue
        if brk.kind not in allowed_kinds:
            continue
        if brk.internal and not use_internal:
            continue
        if not brk.internal and not use_swing:
            continue
        ob = brk.order_block
        if ob is None or ob.mitigated:
            continue
        direction = "LONG" if brk.direction == BULL else "SHORT"
        z = lux.zones
        if require_premium_discount and z is not None:
            # LONG yalnız equilibrium ALTINDAKİ OB'den (discount yarısı),
            # SHORT yalnız ÜSTÜNDEKİ OB'den (premium yarısı).
            if direction == "LONG" and ob.top > z.equilibrium:
                continue
            if direction == "SHORT" and ob.bot < z.equilibrium:
                continue
        anchor = ob.bot if direction == "LONG" else ob.top
        conf = zone_confluence(direction, brk, ob, lux)
        if len(conf) < min_confluence:
            continue
        try:
            trig_ms = int(pd.Timestamp(brk.ts).timestamp() * 1000)
        except (ValueError, TypeError):
            trig_ms = 0
        scope = "internal" if brk.internal else "swing"
        out.append(SetupCandidate(
            symbol=symbol,
            direction=direction,
            trigger_bar_ts=trig_ms,
            trigger_price=float(brk.level),
            htf_bias=htf_bias,
            target_zone=ZoneSpec(low=ob.bot, high=ob.top, source="OB"),
            htf_swing_anchor=float(anchor),
            bars_waited=0,
            state="AWAITING_PULLBACK",
            confluence_score=(10 if not brk.internal else 0) + len(conf),
            reasons=[f"LUX {scope} {brk.kind} {brk.direction} aligned with HTF {htf_bias}",
                     f"entry from LUX {scope} OB [{ob.bot:.8g}-{ob.top:.8g}] (bar {ob.idx})",
                     f"confluence={'+'.join(conf) if conf else 'NONE'}"],
        ))
    return out


def tp_targets(direction: str, entry: float, sl: float, lux: LuxResult,
               min_rr: float, wick_buffer_r: float = 0.0):
    """TP1/TP2 — karşı OB yakın kenarı, equilibrium, EQH/EQL, trailing extreme.

    TP1 = min_rr×risk'i karşılayan EN YAKIN aday; TP2 = TP1'in ötesindeki
    sonraki aday. Aday var ama hiçbiri min_rr'yi karşılamıyorsa
    InsufficientTPDistanceError; hiç aday yoksa RR projeksiyonu.
    """
    from engine.smc_v2.exceptions import InsufficientTPDistanceError

    risk = abs(entry - sl)
    min_dist = min_rr * risk
    buf = max(0.0, wick_buffer_r) * risk
    cands = []
    z = lux.zones
    obs = lux.active_obs()
    if direction == "LONG":
        cands += [(ob.bot, "LUX_OB") for ob in obs if ob.bias == BEAR and ob.bot > entry]
        cands += [(f.bot, "LUX_FVG") for f in lux.active_fvgs() if f.bias == BEAR and f.bot > entry]
        cands += [(e.price_b - buf, "LUX_EQH") for e in lux.equals if e.kind == "EQH" and e.price_b - buf > entry]
        cands += [(p - buf, "LUX_LIQ_HIGH") for _, p in lux.swing_high_pivots if p - buf > entry]
        if z is not None:
            if z.equilibrium > entry:
                cands.append((z.equilibrium, "LUX_EQUILIBRIUM"))
            if z.top - buf > entry:
                cands.append((z.top - buf, "LUX_TRAIL_TOP"))
        cands.sort(key=lambda x: x[0])
        ok = [x for x in cands if x[0] - entry >= min_dist]
    else:
        cands += [(ob.top, "LUX_OB") for ob in obs if ob.bias == BULL and ob.top < entry]
        cands += [(f.top, "LUX_FVG") for f in lux.active_fvgs() if f.bias == BULL and f.top < entry]
        cands += [(e.price_b + buf, "LUX_EQL") for e in lux.equals if e.kind == "EQL" and e.price_b + buf < entry]
        cands += [(p + buf, "LUX_LIQ_LOW") for _, p in lux.swing_low_pivots if p + buf < entry]
        if z is not None:
            if z.equilibrium < entry:
                cands.append((z.equilibrium, "LUX_EQUILIBRIUM"))
            if z.bottom + buf < entry:
                cands.append((z.bottom + buf, "LUX_TRAIL_BOTTOM"))
        cands.sort(key=lambda x: x[0], reverse=True)
        ok = [x for x in cands if entry - x[0] >= min_dist]

    if not cands:
        tp1 = entry + min_dist if direction == "LONG" else entry - min_dist
        return tp1, None, {"tp1_source": "RR_PROJECTION", "tp2_source": "NONE"}
    if not ok:
        raise InsufficientTPDistanceError(nearest=cands[0][0], required=min_dist)
    tp1, s1 = ok[0]
    # TP2 = TP1'in KESİN ötesindeki ilk aday (aynı fiyattaki çakışan kaynak
    # — ör. OB kenarı == equilibrium — ikinci hedef sayılmaz).
    beyond = [x for x in ok[1:] if (x[0] > tp1 if direction == "LONG" else x[0] < tp1)]
    tp2, s2 = (beyond[0] if beyond else (None, "NONE"))
    if tp2 is None and z is not None and z.top > z.bottom:
        rng = z.top - z.bottom
        exts = [z.bottom + rng * r if direction == "LONG" else z.top - rng * r
                for r in FIB_EXT_RATIOS]
        far = [x for x in exts if (x > tp1 if direction == "LONG" else x < tp1)]
        if far:
            tp2, s2 = (min(far) if direction == "LONG" else max(far)), "FIB_EXT"
    return tp1, tp2, {"tp1_source": s1, "tp2_source": s2}
