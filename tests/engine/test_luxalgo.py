"""LuxAlgo SMC port testleri (engine/smc_v2/luxalgo.py)."""
import math

import numpy as np
import pandas as pd
import pytest

from engine.smc_v2 import luxalgo as lx
from engine.smc_v2.exceptions import InsufficientTPDistanceError


def _df_from_closes(closes, wick=0.2, start="2026-01-01"):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    highs = np.maximum(opens, closes) + wick
    lows = np.minimum(opens, closes) - wick
    idx = pd.date_range(start, periods=len(closes), freq="15min", tz="UTC")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": 1.0}, index=idx)


def _zigzag(points, steps=6):
    out = []
    for a, b in zip(points[:-1], points[1:]):
        out += list(np.linspace(a, b, steps, endpoint=False))
    out.append(points[-1])
    return out


CFG = lx.LuxConfig(swing_length=4, internal_length=2, eq_length=2, atr_length=10)


def _down_then_up():
    # Düşen yapı (LH/LL), sonra yukarı kırılım (CHoCH) + devam (BOS)
    pts = [100, 110, 104, 108, 98, 103, 92, 97, 88, 99, 94, 112, 105, 120, 113, 128]
    return _df_from_closes(_zigzag(pts))


def test_pivots_need_confirmation_no_lookahead():
    """Repaint-free: önek üzerinde koşulan analiz, tam analizin önekidir."""
    df = _down_then_up()
    full = lx.analyze(df, CFG)
    for k in range(20, len(df), 7):
        part = lx.analyze(df.iloc[:k], CFG)
        assert [(b.idx, b.kind, b.direction, b.internal) for b in part.breaks] == \
            [(b.idx, b.kind, b.direction, b.internal) for b in full.breaks if b.idx < k]
        assert [(o.idx, o.bias, o.internal) for o in part.swing_obs] == \
            [(o.idx, o.bias, o.internal) for o in full.swing_obs if o.created_idx < k]


def test_choch_then_bos_labels_and_trend():
    df = _down_then_up()
    res = lx.analyze(df, CFG)
    sw = [b for b in res.breaks if not b.internal]
    assert sw, "swing kırılımı bekleniyordu"
    bulls = [b for b in sw if b.direction == "BULL"]
    bears = [b for b in sw if b.direction == "BEAR"]
    assert bears and bulls
    # İlk BULL kırılım bear trendden sonra → CHoCH; sonraki BULL → BOS
    first_bull = bulls[0]
    assert first_bull.kind == "CHoCH"
    assert any(b.kind == "BOS" for b in bulls[1:]) or len(bulls) == 1
    assert res.swing_trend == "BULL"
    assert res.strong_low is not None and res.strong_high is None


def test_order_block_is_lowest_candle_between_pivot_and_break():
    df = _down_then_up()
    res = lx.analyze(df, CFG)
    for b in res.breaks:
        ob = b.order_block
        assert ob is not None
        seg = df.iloc[b.pivot_idx:b.idx]
        if b.direction == "BULL":
            assert ob.bar_low == pytest.approx(seg["low"].min())
            assert ob.idx == b.pivot_idx + int(np.argmin(seg["low"].to_numpy()))
        else:
            assert ob.bar_high == pytest.approx(seg["high"].max())
        assert ob.created_idx == b.idx


def test_ob_mitigation_highlow_vs_close():
    df = _down_then_up()
    res = lx.analyze(df, CFG)
    lows, highs, closes = df["low"].to_numpy(), df["high"].to_numpy(), df["close"].to_numpy()
    for ob in res.swing_obs + res.internal_obs:
        later = range(ob.created_idx + 1, len(df))
        if ob.bias == "BULL":
            exp = next((t for t in later if lows[t] < ob.bar_low), -1)
        else:
            exp = next((t for t in later if highs[t] > ob.bar_high), -1)
        assert ob.mitigated_idx == exp
    res_c = lx.analyze(df, lx.LuxConfig(**{**CFG.__dict__, "ob_mitigation": "CLOSE"}))
    for ob in res_c.swing_obs:
        later = range(ob.created_idx + 1, len(df))
        src = closes
        exp = next((t for t in later if (src[t] < ob.bar_low if ob.bias == "BULL"
                                         else src[t] > ob.bar_high)), -1)
        assert ob.mitigated_idx == exp


def test_high_volatility_bar_swaps_parsed_high_low():
    closes = [100.0] * 30
    df = _df_from_closes(closes, wick=0.5)
    df.iloc[20, df.columns.get_loc("high")] = 130.0   # devasa range mumu
    df.iloc[20, df.columns.get_loc("low")] = 90.0
    # 21+ barlarda bir kırılım yaratmak için yükseliş ekle
    up = _df_from_closes(list(np.linspace(100, 140, 15)), wick=0.5,
                         start=str(df.index[-1] + pd.Timedelta("15min")))
    d = pd.concat([df, up])
    res = lx.analyze(d, lx.LuxConfig(swing_length=3, internal_length=2, atr_length=5))
    for ob in res.swing_obs + res.internal_obs:
        if ob.idx == 20:
            assert ob.bar_high == 90.0 and ob.bar_low == 130.0
            assert ob.top == 130.0 and ob.bot == 90.0


def test_equal_highs_detected_within_atr_threshold():
    pts = [100, 110, 102, 110.05, 101, 109.98, 100, 95]
    df = _df_from_closes(_zigzag(pts, steps=5))
    res = lx.analyze(df, lx.LuxConfig(swing_length=3, internal_length=2,
                                      eq_length=2, eq_threshold=0.5, atr_length=5))
    assert any(e.kind == "EQH" for e in res.equals)


def test_fvg_auto_threshold_and_mitigation():
    closes = [100, 100.1, 100.2, 100.1, 100.0, 100.1, 103, 106, 106.2, 106.1, 99]
    df = _df_from_closes(closes, wick=0.05)
    res = lx.analyze(df, lx.LuxConfig(swing_length=3, internal_length=2, atr_length=5))
    bulls = [f for f in res.fvgs if f.bias == "BULL"]
    assert bulls
    assert all(f.top > f.bot for f in bulls)
    assert all(f.mitigated_idx == 10 for f in bulls)   # son bar hepsinin altına iner


def test_premium_discount_zones_math():
    z = lx.LuxZones(top=200.0, bottom=100.0)
    assert z.premium_low == pytest.approx(195.0)
    assert z.discount_high == pytest.approx(105.0)
    assert z.equilibrium == 150.0
    assert z.eq_low == pytest.approx(147.5) and z.eq_high == pytest.approx(152.5)


def test_generate_candidates_long_from_bull_ob_with_strong_low_sl():
    df = _down_then_up()
    res = lx.analyze(df, CFG)
    cands = lx.generate_candidates("BTC/USDT", res, "BULL", trigger_idx_min=0,
                                   require_premium_discount=False)
    assert cands
    for c in cands:
        assert c.direction == "LONG"
        assert c.target_zone.source == "OB"
        assert c.htf_swing_anchor <= c.target_zone.low
        assert c.state == "AWAITING_PULLBACK"
    # bias uyuşmazlığı → aday yok
    assert all(c.direction == "SHORT" for c in
               lx.generate_candidates("BTC/USDT", res, "BEAR", 0,
                                      require_premium_discount=False))
    assert lx.generate_candidates("BTC/USDT", res, "UNDEF", 0) == []


def test_premium_discount_filter_blocks_long_above_equilibrium():
    df = _down_then_up()
    res = lx.analyze(df, CFG)
    eq = res.zones.equilibrium
    cands = lx.generate_candidates("X", res, "BULL", 0, require_premium_discount=True)
    assert all(c.target_zone.high <= eq for c in cands)


def test_tp_targets_nearest_qualifying_and_errors():
    res = lx.LuxResult("BULL", "BULL", [], [
        lx.LuxOrderBlock(112, 110, 1, "", "BEAR", False, 2),
        lx.LuxOrderBlock(125, 121, 3, "", "BEAR", False, 4),
    ], [], [], [], lx.LuxZones(130, 90), None, 90)
    tp1, tp2, tags = lx.tp_targets("LONG", entry=100, sl=96, lux=res, min_rr=2.0)
    assert (tp1, tags["tp1_source"]) == (110, "LUX_OB")        # 10 >= 8
    assert (tp2, tags["tp2_source"]) == (121, "LUX_OB")
    with pytest.raises(InsufficientTPDistanceError):
        lx.tp_targets("LONG", entry=100, sl=90, lux=res, min_rr=5.0)
    empty = lx.LuxResult("BULL", "BULL", [], [], [], [], [], None, None, None)
    tp1, tp2, tags = lx.tp_targets("SHORT", 100, 102, empty, 2.0)
    assert tp1 == 96 and tp2 is None and tags["tp1_source"] == "RR_PROJECTION"


def test_short_tp_equilibrium_like_publication_example():
    # Görsel: "Entry at Premium" → "50% level ... at the Equilibrium = Target"
    res = lx.LuxResult("BEAR", "BEAR", [], [], [], [], [],
                       lx.LuxZones(0.9800, 0.9400), 0.9800, None)
    tp1, _, tags = lx.tp_targets("SHORT", entry=0.9782, sl=0.9870, lux=res, min_rr=1.0)
    assert tags["tp1_source"] == "LUX_EQUILIBRIUM"
    assert tp1 == pytest.approx(0.96)


def test_config_from_dict_and_luxalgo_default_off_in_config():
    c = lx.LuxConfig.from_dict({"swing_length": 30, "ob_mitigation": "CLOSE"})
    assert c.swing_length == 30 and c.ob_mitigation == "CLOSE" and c.internal_length == 5
    import yaml, pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    assert cfg.get("smc_v2", {}).get("luxalgo", {}).get("enabled", False) is False


# ── Orkestratör kablolaması ──────────────────────────────────────────────

class _Store:
    def __init__(self):
        self.added = []

    def add(self, c):
        self.added.append(c)
        return True


def test_emit_uses_precomputed_luxalgo_candidates(monkeypatch):
    from engine.safe_orchestrator import SafeOrchestrator
    import engine.smc_v2.triggers as triggers

    def _boom(**kw):
        raise AssertionError("generate_setup_candidates çağrılmamalıydı")

    monkeypatch.setattr(triggers, "generate_setup_candidates", _boom)
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": {"luxalgo": {"enabled": True}}}
    orch.setup_state_store = _Store()
    res = lx.analyze(_down_then_up(), CFG)
    cands = lx.generate_candidates("BTC/USDT", res, "BULL", 0,
                                   require_premium_discount=False)
    assert cands
    orch._emit_setup_candidates(
        symbol="BTC/USDT", htf_bias="BULL", ltf_structure_breaks=[],
        htf_swings={"swing_highs": [], "swing_lows": []}, htf_bars=[],
        htf_fvgs=[], ote_band=(0.0, 0.0), ltf_trigger_idx_min=0,
        current_price=None, df_entry=None, precomputed_candidates=cands)
    assert orch.setup_state_store.added == cands


def test_emit_without_precomputed_keeps_legacy_path(monkeypatch):
    from engine.safe_orchestrator import SafeOrchestrator
    import engine.smc_v2.triggers as triggers

    sentinel = []
    monkeypatch.setattr(triggers, "generate_setup_candidates",
                        lambda **kw: sentinel.append(1) or [])
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": {}}
    orch.setup_state_store = _Store()
    orch._emit_setup_candidates(
        symbol="X", htf_bias="BULL", ltf_structure_breaks=[],
        htf_swings={"swing_highs": [], "swing_lows": []}, htf_bars=[],
        htf_fvgs=[], ote_band=(0.0, 0.0), ltf_trigger_idx_min=0,
        current_price=None, df_entry=None)
    assert sentinel == [1]


def test_default_config_on_500_bar_random_walk_smoke():
    """kline_limit=500 + LuxAlgo default (swing 50): çalışır, prefix-tutarlı."""
    rng = np.random.default_rng(7)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, 500)))
    df = _df_from_closes(closes, wick=0.15)
    res = lx.analyze(df)
    assert res.breaks and res.zones is not None
    assert any(not b.internal for b in res.breaks)
    part = lx.analyze(df.iloc[:400])
    assert [(b.idx, b.kind) for b in part.breaks] == \
        [(b.idx, b.kind) for b in res.breaks if b.idx < 400]
    bias = res.swing_trend
    for c in lx.generate_candidates("X", res, bias, 0):
        assert c.target_zone.low <= c.target_zone.high
        sl = c.htf_swing_anchor * (0.999 if c.direction == "LONG" else 1.001)
        entry = c.target_zone.high if c.direction == "LONG" else c.target_zone.low
        try:
            tp1, tp2, _ = lx.tp_targets(c.direction, entry, sl, res, 1.5)
        except InsufficientTPDistanceError:
            continue
        assert (tp1 > entry) if c.direction == "LONG" else (tp1 < entry)
