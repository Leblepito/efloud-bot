"""Multi-Timeframe signal generation — Efloud setup akışı."""

import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from .smc import SMCEngine
from .confluence import calc_confluence
import pandas as pd

log = logging.getLogger("efloud.signals")


def _normalize_symbol(symbol: str) -> str:
    """Canonicalize symbol form to `BASE/QUOTE` (with slash).

    Tolerates exchange-API forms like `ETHUSDT` (no slash) by inserting one
    before the quote currency. Must remain pure (no I/O) so it can be reused
    in tests.
    """
    if not symbol or "/" in symbol:
        return symbol
    # Default: assume the last 4 chars are the quote (USDT, BUSD, USDC).
    # Adjust if/when we trade against shorter-quote pairs.
    for quote in ("USDT", "USDC", "BUSD"):
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            return f"{base}/{quote}"
    return symbol


def resolve_min_confluence(
    symbol: Optional[str],
    global_min: int,
    symbol_overrides: Optional[Dict[str, int]],
) -> int:
    """Pick the effective confluence threshold for a given symbol.

    Lookup precedence: explicit per-symbol override > global default.
    Returns `global_min` if symbol is unknown/missing or overrides are empty.

    Symbol format is normalized so that `ETHUSDT` resolves the same as
    `ETH/USDT`. Override values of 0 (literally zero) are respected — only
    `None`/missing keys fall back.
    """
    if not symbol_overrides or symbol is None:
        return global_min
    canonical = _normalize_symbol(symbol)
    if canonical in symbol_overrides:
        return symbol_overrides[canonical]
    if symbol in symbol_overrides:
        return symbol_overrides[symbol]
    return global_min


@dataclass
class Signal:
    direction: str          # "LONG" | "SHORT"
    entry: float
    sl: float
    tp1: float              # Swing TP
    tp2: float              # Fib 1.618 TP
    rr1: float
    rr2: float
    confluence: int
    reasons: List[str] = field(default_factory=list)
    timestamp: str = ""
    in_ote: bool = False
    in_ob: bool = False
    has_sfp: bool = False
    zone: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def generate_signals(
    engine: SMCEngine,
    df_htf: pd.DataFrame,
    df_mtf: pd.DataFrame,
    df_entry: pd.DataFrame,
    min_confluence: int = 50,
    min_rr: float = 1.5,
    fib_ext: float = 1.618,
    recency_bars: int = 20,
    df_daily: Optional[pd.DataFrame] = None,   # 4. TF — 1d filter (opsiyonel)
    daily_filter_strict: bool = False,          # True = 1d ters yön → reddet
    symbol: Optional[str] = None,               # NEW — for per-symbol threshold lookup
    symbol_confluence_overrides: Optional[Dict[str, int]] = None,  # NEW
) -> List[Signal]:
    """
    4-Timeframe Efloud setup akışı:
    1. Daily (1d) → makro yön filtresi (opsiyonel, +confluence puanı)
    2. HTF (4h)  → bias + POI
    3. MTF (1h)  → CHoCH onay
    4. Entry (15m) → giriş + SL/TP

    daily_filter_strict:
      False = 1d sadece +5 confluence puanı verir (yumuşak)
      True  = 1d ters yön ise sinyal tamamen reddedilir (sıkı)

    recency_bars: Sadece son N bar içinde oluşan break'leri sinyal olarak değerlendir.
    """
    # ── HTF analiz ──
    htf = engine.analyze(df_htf)
    htf_bias = htf["trend"]
    htf_fvgs = htf["active_fvgs"]
    htf_obs = htf["active_obs"]

    if htf_bias == "UNDEF":
        # Fallback: Son 40 HTF bar'ının eğiminden trend çıkar
        # Eğer fiyat başlangıca göre >%2 yukarıdaysa BULL, <%-2 BEAR
        if len(df_htf) >= 40:
            recent_close = float(df_htf["close"].iloc[-1])
            past_close = float(df_htf["close"].iloc[-40])
            change_pct = (recent_close - past_close) / past_close * 100
            if change_pct > 2.0:
                htf_bias = "BULL"
                log.info(f"HTF fallback: +{change_pct:.1f}% slope → BULL")
            elif change_pct < -2.0:
                htf_bias = "BEAR"
                log.info(f"HTF fallback: {change_pct:.1f}% slope → BEAR")
            else:
                log.info(f"HTF undefined and slope neutral ({change_pct:+.1f}%) — skipping")
                return []
        else:
            log.info("HTF bias undefined and insufficient data — skipping")
            return []

    # ── Daily (1d) filter ── (opsiyonel — 4. TF)
    daily_bias = "UNDEF"
    if df_daily is not None and len(df_daily) >= 30:
        d_analysis = engine.analyze(df_daily)
        daily_bias = d_analysis["trend"]
        # UNDEF ise 30-bar slope fallback (1d için ~30 gün)
        if daily_bias == "UNDEF":
            d_close_now = float(df_daily["close"].iloc[-1])
            d_close_past = float(df_daily["close"].iloc[-30])
            d_change = (d_close_now - d_close_past) / d_close_past * 100
            if d_change > 5.0:
                daily_bias = "BULL"
            elif d_change < -5.0:
                daily_bias = "BEAR"
            log.info(f"Daily slope fallback: {d_change:+.1f}% → {daily_bias}")

        # Strict mode: daily ters yönde ise tamamen reddet
        if daily_filter_strict and daily_bias != "UNDEF" and daily_bias != htf_bias:
            log.info(f"📅 Daily filter STRICT: 1d={daily_bias} vs 4h={htf_bias} — skipping all signals")
            return []
        else:
            log.debug(f"📅 Daily bias: {daily_bias} (4h: {htf_bias})")

    # ── MTF analiz ──
    mtf_sh, mtf_sl = engine.swings(df_mtf)
    mtf_brks = engine.structure(df_mtf, mtf_sh, mtf_sl)
    mtf_chochs = [b for b in mtf_brks if b.kind == "CHoCH"]

    # ── Entry TF analiz ──
    e_sh, e_sl = engine.swings(df_entry)
    e_brks = engine.structure(df_entry, e_sh, e_sl)
    e_trend = e_brks[-1].direction if e_brks else "UNDEF"
    e_obs = engine.order_blocks(df_entry, e_sh, e_sl, e_trend)
    e_sfps = engine.sfps(df_entry, e_sh, e_sl)
    e_range = engine.range_info(df_entry)
    e_ote = engine.ote(e_sh, e_sl, e_trend)
    a_obs = [o for o in e_obs if not o.mitigated]

    signals = []
    last_bar_idx = len(df_entry) - 1
    recent_cutoff = last_bar_idx - recency_bars
    
    # Diagnostics: reject reasons
    aligned_chochs = 0
    reject_confluence = 0
    reject_rr = 0
    reject_tp_wrong_side = 0
    max_seen_score = 0
    max_seen_rr = 0.0

    for brk in e_brks:
        # Sadece CHoCH + HTF yönünde + son N bar içinde
        if brk.kind != "CHoCH" or brk.direction != htf_bias:
            continue
        if brk.idx < recent_cutoff:
            continue
        aligned_chochs += 1

        is_long = brk.direction == "BULL"
        price = brk.price

        # Koşul kontrolleri
        in_htf_fvg = any(
            f.direction == htf_bias and f.bot <= price <= f.top
            for f in htf_fvgs
        )
        in_ote = False
        if e_ote:
            lo, hi = min(e_ote.top, e_ote.bot), max(e_ote.top, e_ote.bot)
            in_ote = lo <= price <= hi

        mtf_conf = any(m.direction == htf_bias for m in mtf_chochs[-5:])

        has_sfp = any(
            s.direction == brk.direction and abs(s.idx - brk.idx) < 10
            for s in e_sfps
        )

        in_ob, ob_ns, ob_eq = False, False, False
        for ob in a_obs:
            if ob.direction == brk.direction and ob.bot <= price <= ob.top:
                in_ob = True
                ob_ns = ob.near_swing
                ob_eq = abs(price - ob.eq) / max(ob.eq, 1e-10) < 0.003
                break

        correct_zone = (is_long and e_range.discount) or (not is_long and e_range.premium)
        has_dev = (is_long and e_range.dev_bull) or (not is_long and e_range.dev_bear)

        # Confluence
        score, reasons = calc_confluence(
            is_long, htf_bias, in_htf_fvg, in_ote, mtf_conf,
            has_sfp, in_ob, ob_ns, ob_eq, correct_zone, has_dev
        )

        # Daily filter bonus — 1d ile aynı yönde ise +5 confluence
        if daily_bias != "UNDEF":
            if daily_bias == htf_bias:
                score = min(100, score + 5)
                reasons.append(f"Daily aligned ({daily_bias})")
            elif daily_bias != htf_bias:
                # Soft penalty: daily ters yönde, -5 puan
                score = max(0, score - 5)
                reasons.append(f"Daily diverging ({daily_bias} vs {htf_bias})")

        if score > max_seen_score:
            max_seen_score = score

        effective_threshold = resolve_min_confluence(
            symbol=symbol,
            global_min=min_confluence,
            symbol_overrides=symbol_confluence_overrides,
        )
        if score < effective_threshold:
            reject_confluence += 1
            continue

        # SL / TP
        # LONG CHoCH (yukarı kırılım):
        #   SL  = en son swing low (kırılım'dan önceki, aşağıda)
        #   TP1 = öncelikli ulaşılmamış HTF direnç veya risk × 2 projeksiyon
        # SHORT CHoCH (aşağı kırılım):
        #   SL  = en son swing high (kırılım'dan önceki, yukarıda)
        #   TP1 = öncelikli ulaşılmamış HTF destek veya risk × 2 projeksiyon
        if is_long:
            sl_c = [s for s in e_sl if s.idx < brk.idx]
            sl = sl_c[-1].price if sl_c else price * 0.99
            risk_tmp = abs(price - sl)
            # TP1: fiyatın üstündeki HTF hedefi, ama min_rr'yi sağlamalı.
            # Yakın HTF resistance R:R'yi boğmasın diye min_rr × risk eşiği üstündekileri al.
            min_tp_long = price + risk_tmp * min_rr
            htf_above_targets = [f.top for f in htf_fvgs
                                   if f.direction == "BULL" and f.top >= min_tp_long]
            htf_above_targets += [s.price for s in htf["swing_highs"]
                                    if s.price >= min_tp_long]
            tp1 = min(htf_above_targets) if htf_above_targets else min_tp_long
        else:
            sl_c = [s for s in e_sh if s.idx < brk.idx]
            sl = sl_c[-1].price if sl_c else price * 1.01
            risk_tmp = abs(price - sl)
            min_tp_short = price - risk_tmp * min_rr
            htf_below_targets = [f.bot for f in htf_fvgs
                                   if f.direction == "BEAR" and f.bot <= min_tp_short]
            htf_below_targets += [s.price for s in htf["swing_lows"]
                                    if s.price <= min_tp_short]
            tp1 = max(htf_below_targets) if htf_below_targets else min_tp_short

        risk = abs(price - sl)
        if risk == 0:
            continue
        tp2 = (price + risk * fib_ext) if is_long else (price - risk * fib_ext)
        rr1 = round(abs(tp1 - price) / risk, 2)
        rr2 = round(abs(tp2 - price) / risk, 2)

        # TP1 fiyatın yanlış tarafında olmamalı
        if is_long and tp1 <= price:
            reject_tp_wrong_side += 1
            continue
        if not is_long and tp1 >= price:
            reject_tp_wrong_side += 1
            continue

        if rr1 > max_seen_rr:
            max_seen_rr = rr1

        if rr1 < min_rr:
            reject_rr += 1
            continue

        sig = Signal(
            direction="LONG" if is_long else "SHORT",
            entry=round(price, 8), sl=round(sl, 8),
            tp1=round(tp1, 8), tp2=round(tp2, 8),
            rr1=rr1, rr2=rr2, confluence=score,
            reasons=reasons, timestamp=brk.ts,
            in_ote=in_ote, in_ob=in_ob, has_sfp=has_sfp,
            zone="DISCOUNT" if e_range.discount else "PREMIUM"
        )
        signals.append(sig)
        log.info(f"Signal: {sig.direction} @ {sig.entry} | Conf={sig.confluence} | R:R={sig.rr1}/{sig.rr2}")

    # Diagnostic: reject reason breakdown
    if aligned_chochs > 0 and len(signals) == 0:
        reasons = []
        if reject_confluence > 0:
            reasons.append(f"conf<{min_confluence} ({reject_confluence}×, max seen: {max_seen_score})")
        if reject_tp_wrong_side > 0:
            reasons.append(f"TP wrong side ({reject_tp_wrong_side}×)")
        if reject_rr > 0:
            reasons.append(f"R:R<{min_rr} ({reject_rr}×, max seen: {max_seen_rr:.2f})")
        log.info(f"📉 {aligned_chochs} CHoCH analyzed, 0 signals. Rejects: {' | '.join(reasons)}")

    return signals
