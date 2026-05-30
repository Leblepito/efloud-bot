"""Task 3: Range-deviation TP2 karlı-taraf clamp + TP2>TP1 collapse regresyonu.

Bu testler GERÇEK production helper'ı (`engine.signals._resolve_deviation_tp2`)
import eder — yerel kopya YOK. Böylece helper'ın gövdesi/çağrısı silinirse
en az bir test kırılır (mutation-sanity).

Ekstra limit case'ler kullanıcının BCH/USDT SMC + Elliott-FVG analizinden
türetildi: Elliott impulse (1-2-3-4-5) dalgaları SMC agresif genişleme
mumları (OB/FVG) ile, A-B-C düzeltmesi ise OTE pullback (0.618-0.786) ile
hizalanır. Buradaki sınır koşulları invalidation buffer ve FVG fill
boundary'sini test eder.
"""

from engine.signals import _enforce_tp2_beyond_tp1, _resolve_deviation_tp2


# ── Base cases ────────────────────────────────────────────────────────────

def test_long_deviation_tp2_clamped_to_profitable_side():
    """LONG'da range.hi entry'nin yanlış (zarar) tarafındaysa min_tp_long'a çekilir."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = price + risk * min_rr  # 103.6
    tp1 = price  # collapse invariant tetiklenmesin (clamp sonrası tp2 > tp1)
    raw_tp2 = 99.0  # range.hi yanlış tarafta
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_long, price, risk, is_long=True)
    assert result == min_tp_long
    assert result > price


def test_short_deviation_tp2_clamped_to_profitable_side():
    """SHORT'ta range.lo entry'nin yanlış tarafındaysa min_tp_short'a çekilir."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = price - risk * min_rr  # 96.4
    tp1 = price
    raw_tp2 = 101.0  # range.lo yanlış tarafta
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_short, price, risk, is_long=False)
    assert result == min_tp_short
    assert result < price


def test_valid_deviation_tp2_unchanged():
    """Geçerli (karlı taraf, min R:R üstü, tp1 üstü) TP2 dokunulmadan kalır."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = price + risk * min_rr  # 103.6
    tp1 = price
    raw_tp2 = 110.0
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_long, price, risk, is_long=True)
    assert result == 110.0


# ── Extra limit cases (BCH/USDT SMC + Elliott-FVG analizi) ─────────────────

def test_long_tp2_never_below_invalidation_buffer():
    """Invalidation buffer: LONG'da raw range.hi tam entry'de (== price) olsa
    bile TP2 invalidation/SL tarafında oturmamalı; min_tp_long'a (karlı taraf)
    çekilip kesinlikle entry üstünde kalmalı."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = price + risk * min_rr  # 103.6
    tp1 = price
    raw_tp2 = price  # range.hi tam invalidation/entry seviyesinde
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_long, price, risk, is_long=True)
    assert result == min_tp_long
    assert result > price  # asla invalidation tarafında değil


def test_short_tp2_never_above_invalidation_buffer():
    """Invalidation buffer (simetrik SHORT): raw range.lo == price olsa bile
    TP2 entry altına (karlı tarafa) çekilmeli."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = price - risk * min_rr  # 96.4
    tp1 = price
    raw_tp2 = price
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_short, price, risk, is_long=False)
    assert result == min_tp_short
    assert result < price


def test_long_tp2_respects_fvg_fill_boundary():
    """FVG fill boundary: LONG'da range.hi (FVG dolum sınırı 104.0) min_tp_long
    (103.6) ÜSTÜNDE ise clamp onu aşağı çekmemeli — geçerli karlı FVG hedefi korunur."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = price + risk * min_rr  # 103.6
    tp1 = price
    raw_tp2 = 104.0  # FVG fill boundary, min_tp üstünde
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_long, price, risk, is_long=True)
    assert result == 104.0
    assert result > price
    assert result >= min_tp_long  # min R:R sınırına saygı


def test_short_tp2_respects_fvg_fill_boundary():
    """FVG fill boundary (simetrik SHORT): range.lo 96.0, min_tp_short 96.4
    altında → clamp dokunmaz, geçerli FVG hedefi 96.0'da kalır."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = price - risk * min_rr  # 96.4
    tp1 = price
    raw_tp2 = 96.0  # FVG fill boundary, min_tp altında
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_short, price, risk, is_long=False)
    assert result == 96.0
    assert result < price
    assert result <= min_tp_short  # min R:R sınırına saygı


def test_long_tp2_exactly_at_min_tp_unchanged():
    """Sınır eşitliği: raw_tp2 == min_tp_long, tp1 < min_tp → değişmez (off-by-one yok)."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = price + risk * min_rr  # 103.6
    tp1 = price  # 100 < 103.6, collapse tetiklenmez
    raw_tp2 = min_tp_long
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_long, price, risk, is_long=True)
    assert result == min_tp_long
    assert result > price


def test_short_tp2_exactly_at_min_tp_unchanged():
    """Sınır eşitliği (simetrik SHORT): raw_tp2 == min_tp_short, tp1 > min_tp → değişmez."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = price - risk * min_rr  # 96.4
    tp1 = price  # 100 > 96.4, collapse tetiklenmez
    raw_tp2 = min_tp_short
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_short, price, risk, is_long=False)
    assert result == min_tp_short
    assert result < price


# ── Collapse (tp1 == tp2) fallback to discovery extension ──────────────────

def test_long_tp2_collapse_falls_back_to_extension():
    """TP2>TP1 invariant: LONG'da clamp sonrası tp2, tp1'e çökerse (raw_tp2 ==
    tp1 == min_tp) 2.618R discovery extension'a düşmeli. Aksi halde lifecycle
    TP2'yi TP1'den önce kontrol edip iki-aşamalı çıkışı sessizce kaybeder."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = price + risk * min_rr  # 103.6
    tp1 = min_tp_long  # TP1 de min_tp'ye clamp olmuş (dar range)
    raw_tp2 = min_tp_long  # range.hi de aynı yere clamp olacak
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_long, price, risk, is_long=True)
    assert result == price + risk * 2.618
    assert result > tp1


def test_short_tp2_collapse_falls_back_to_extension():
    """TP2>TP1 invariant (simetrik SHORT): raw_tp2 == tp1 == min_tp →
    2.618R discovery extension'a düş."""
    price, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = price - risk * min_rr  # 96.4
    tp1 = min_tp_short
    raw_tp2 = min_tp_short
    result = _resolve_deviation_tp2(raw_tp2, tp1, min_tp_short, price, risk, is_long=False)
    assert result == price - risk * 2.618
    assert result < tp1


# ── Inversion Protection Invariant (Y5 Fix) ───────────────────

def test_general_long_target_inversion_protection():
    """LONG tp2 closer than tp1 is pushed further than tp1 (REAL helper call)."""
    price, risk = 100.0, 2.0
    tp1 = 110.0  # FVG target far away
    tp2 = 103.2  # Raw 1.618R target close to entry (TP2 < TP1!)

    result = _enforce_tp2_beyond_tp1(tp2, tp1, price, risk, is_long=True)

    assert result == tp1 + risk * 0.5  # 111.0, which is further than tp1 (110.0)
    assert result > tp1


def test_general_short_target_inversion_protection():
    """SHORT tp2 closer than tp1 is pushed further than tp1 (REAL helper call)."""
    price, risk = 100.0, 2.0
    tp1 = 90.0   # FVG target far away
    tp2 = 96.8   # Raw 1.618R target close to entry (TP2 > TP1!)

    result = _enforce_tp2_beyond_tp1(tp2, tp1, price, risk, is_long=False)

    assert result == tp1 - risk * 0.5  # 89.0, which is further than tp1 (90.0)
    assert result < tp1


def test_trx_short_inversion_real_case():
    """TRX/USDT prod case: SHORT, fib_ext tp2 closer to entry than tp1 → -2021
    immediate-trigger reject. Helper must push tp2 beyond tp1 (REAL helper call)."""
    price, sl = 0.3451, 0.3454
    risk = abs(price - sl)  # 0.0003
    tp1 = 0.3391
    raw_tp2 = 0.3445  # fib_ext, closer than tp1 (raw_tp2 > tp1 for SHORT = inverted)

    result = _enforce_tp2_beyond_tp1(raw_tp2, tp1, price, risk, is_long=False)

    expected = min(raw_tp2, tp1 - risk * 0.5, price - risk * 2.618)
    assert result == expected
    assert result < tp1  # guard pushed it beyond (below) tp1


def test_valid_tp2_not_touched():
    """No-op: tp2 already correctly beyond tp1 returns unchanged (LONG & SHORT)."""
    # LONG: tp2 (110) already further than tp1 (104) → untouched
    assert _enforce_tp2_beyond_tp1(110.0, 104.0, 100.0, 2.0, is_long=True) == 110.0
    # SHORT: tp2 (90) already further than tp1 (96) → untouched
    assert _enforce_tp2_beyond_tp1(90.0, 96.0, 100.0, 2.0, is_long=False) == 90.0
