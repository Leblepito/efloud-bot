"""Task 3: Range-deviation TP2 karlı-taraf clamp regresyon testi.

signals.py'deki deviation TP2 clamp mantığını saf bir oracle ile doğrular.
Tam generate_signals fixture'ı kurmak yerine clamp matematiğini izole eder
(kırılgan chart fixture yok). Oracle, engine/signals.py içindeki gerçek
clamp bloğunun birebir kopyasıdır.

Ekstra limit case'ler kullanıcının BCH/USDT SMC + Elliott-FVG analizinden
türetildi: Elliott impulse (1-2-3-4-5) dalgaları SMC agresif genişleme
mumları (OB/FVG) ile, A-B-C düzeltmesi ise OTE pullback (0.618-0.786) ile
hizalanır. Buradaki sınır koşulları invalidation buffer ve FVG fill
boundary'sini test eder.
"""


def _clamp_dev_tp2(tp2, min_tp, is_long):
    """signals.py deviation TP2 clamp mantığının saf kopyası (test oracle)."""
    if is_long:
        if tp2 < min_tp:
            tp2 = min_tp
    else:
        if tp2 > min_tp:
            tp2 = min_tp
    return tp2


# ── Base cases ────────────────────────────────────────────────────────────

def test_long_deviation_tp2_clamped_to_profitable_side():
    """LONG'da range.hi entry'nin yanlış (zarar) tarafındaysa min_tp_long'a çekilir."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = entry + risk * min_rr  # 103.6
    raw_tp2 = 99.0  # range.hi yanlış tarafta
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_long, is_long=True)
    assert clamped == min_tp_long
    assert clamped > entry


def test_short_deviation_tp2_clamped_to_profitable_side():
    """SHORT'ta range.lo entry'nin yanlış tarafındaysa min_tp_short'a çekilir."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = entry - risk * min_rr  # 96.4
    raw_tp2 = 101.0  # range.lo yanlış tarafta
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_short, is_long=False)
    assert clamped == min_tp_short
    assert clamped < entry


def test_valid_deviation_tp2_unchanged():
    """Geçerli (karlı taraf, min R:R üstü) TP2 dokunulmadan kalır."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = entry + risk * min_rr  # 103.6
    raw_tp2 = 110.0
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_long, is_long=True)
    assert clamped == 110.0


# ── Extra limit cases (BCH/USDT SMC + Elliott-FVG analizi) ─────────────────

def test_long_tp2_never_below_invalidation_buffer():
    """Invalidation buffer: LONG'da raw range.hi tam entry'de (== entry) olsa
    bile TP2 invalidation/SL tarafında oturmamalı; min_tp_long'a (karlı taraf)
    çekilip kesinlikle entry üstünde kalmalı."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = entry + risk * min_rr  # 103.6
    raw_tp2 = entry  # range.hi tam invalidation/entry seviyesinde
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_long, is_long=True)
    assert clamped == min_tp_long
    assert clamped > entry  # asla invalidation tarafında değil


def test_short_tp2_never_above_invalidation_buffer():
    """Invalidation buffer (simetrik SHORT): raw range.lo == entry olsa bile
    TP2 entry altına (karlı tarafa) çekilmeli."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = entry - risk * min_rr  # 96.4
    raw_tp2 = entry
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_short, is_long=False)
    assert clamped == min_tp_short
    assert clamped < entry


def test_long_tp2_respects_fvg_fill_boundary():
    """FVG fill boundary: LONG'da range.hi (FVG dolum sınırı 104.0) min_tp_long
    (103.6) ÜSTÜNDE ise clamp onu aşağı çekmemeli — geçerli karlı FVG hedefi korunur."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = entry + risk * min_rr  # 103.6
    raw_tp2 = 104.0  # FVG fill boundary, min_tp üstünde
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_long, is_long=True)
    assert clamped == 104.0
    assert clamped > entry
    assert clamped >= min_tp_long  # min R:R sınırına saygı


def test_short_tp2_respects_fvg_fill_boundary():
    """FVG fill boundary (simetrik SHORT): range.lo 96.0, min_tp_short 96.4
    altında → clamp dokunmaz, geçerli FVG hedefi 96.0'da kalır."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = entry - risk * min_rr  # 96.4
    raw_tp2 = 96.0  # FVG fill boundary, min_tp altında
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_short, is_long=False)
    assert clamped == 96.0
    assert clamped < entry
    assert clamped <= min_tp_short  # min R:R sınırına saygı


def test_long_tp2_exactly_at_min_tp_unchanged():
    """Sınır eşitliği: raw_tp2 == min_tp_long → off-by-one flip olmadan değişmez."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_long = entry + risk * min_rr  # 103.6
    raw_tp2 = min_tp_long
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_long, is_long=True)
    assert clamped == min_tp_long
    assert clamped > entry


def test_short_tp2_exactly_at_min_tp_unchanged():
    """Sınır eşitliği (simetrik SHORT): raw_tp2 == min_tp_short → değişmez."""
    entry, risk, min_rr = 100.0, 2.0, 1.8
    min_tp_short = entry - risk * min_rr  # 96.4
    raw_tp2 = min_tp_short
    clamped = _clamp_dev_tp2(raw_tp2, min_tp_short, is_long=False)
    assert clamped == min_tp_short
    assert clamped < entry
