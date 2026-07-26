"""MPA/1-4 filtre modülleri için birim testleri.

Kapsam:
  MPA/1 engine/smc_v2/po3.py          — Po3 faz tespiti + manipulation gate
  MPA/2 engine/smc_v2/liquidity.py    — SWEEP / GRAB ayrımı
  MPA/3 engine/smc_v2/v_recovery.py   — V-type recovery confirmation
  MPA/4 engine/smc_v2/bias_ledger.py  — BCEL bias değişim defteri

Ayrıca INERT-DEFAULT regresyon testi: config.yaml'daki dört toggle'ın da
varsayılan KAPALI olduğunu doğrular. Bu testin kırılması, canlı V1/V2/V3
botlarının davranışının sessizce değiştiği anlamına gelir.
"""
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.smc import StructBreak, Swing
from engine.smc_v2.bias_ledger import (
    VERDICT_FLIP,
    VERDICT_INTACT,
    VERDICT_TRANSITION,
    Evidence,
    collect_structural_evidence,
    evaluate_bias_ledger,
    find_reset_idx,
    ledger_blocks_new_entry,
)
from engine.smc_v2.liquidity import (
    KIND_GRAB,
    KIND_SWEEP,
    REGIME_COUNTER,
    REGIME_TREND,
    detect_liquidity_event,
    liquidity_score,
    regime_risk_multiplier,
)
from engine.smc_v2.po3 import (
    PHASE_ACCUMULATION,
    PHASE_DISTRIBUTION,
    PHASE_MANIPULATION,
    PHASE_UNDEFINED,
    classify_po3_phase,
    po3_blocks_entry,
    po3_expected_direction,
    po3_score,
)
from engine.smc_v2.v_recovery import detect_v_recovery
from engine.smc_v2.zones import ZoneSpec


def _df(rows, start="2026-07-20 00:00", freq="1h"):
    """rows: list of (open, high, low, close)."""
    idx = pd.date_range(start=start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
        },
        index=idx,
    )


# ─────────────────────────── MPA/1 — Po3 ───────────────────────────

_ACC_BAR = (99.0, 100.0, 98.0, 99.0)   # range 2, body 0


def test_po3_accumulation_while_inside_window():
    """Pencere içindeyken (post bar yok) faz ACCUMULATION olmalı."""
    state = classify_po3_phase(_df([_ACC_BAR] * 8))
    assert state.phase == PHASE_ACCUMULATION
    assert state.acc_high == 100.0
    assert state.acc_low == 98.0
    assert po3_blocks_entry(state) is False


def test_po3_manipulation_blocks_entry():
    """Süpürme var + displacement YOK → MANIPULATION ve giriş bloklanır."""
    rows = [_ACC_BAR] * 8
    rows.append((99.0, 105.0, 98.0, 99.0))   # hour 8: tepeleri süpürdü
    rows.append(_ACC_BAR)                     # hour 9: displacement yok
    state = classify_po3_phase(_df(rows))
    assert state.phase == PHASE_MANIPULATION
    assert state.swept_side == "UP"
    assert state.sweep_idx == 8
    assert po3_blocks_entry(state) is True
    # HARD GATE: manipulation fazında confluence katkısı da sıfırdır
    assert po3_score(state, "SHORT") == 0


def test_po3_distribution_unblocks_after_displacement():
    """Süpürme SONRASI displacement gelince kapı açılır (gate öldürmez, geciktirir)."""
    rows = [_ACC_BAR] * 8
    rows.append((99.0, 105.0, 98.0, 99.0))    # sweep UP
    rows.append((99.0, 100.0, 90.0, 91.0))    # displacement (body 8, BODY_REF ~3.3)
    state = classify_po3_phase(_df(rows))
    assert state.phase == PHASE_DISTRIBUTION
    assert state.confirm_idx == 9
    assert po3_blocks_entry(state) is False


def test_po3_expected_direction_and_score():
    """Tepeler süpürüldüyse beklenen asıl hareket AŞAĞI (SHORT)."""
    rows = [_ACC_BAR] * 8
    rows.append((99.0, 105.0, 98.0, 99.0))
    rows.append((99.0, 100.0, 90.0, 91.0))
    state = classify_po3_phase(_df(rows))
    assert po3_expected_direction(state) == "SHORT"
    assert po3_score(state, "SHORT") == 10
    assert po3_score(state, "LONG") == 0     # yön uyumsuz → katkı yok


def test_po3_undefined_does_not_block():
    """Veri yetersiz → UNDEFINED, ve BLOKLAMAZ (modül docstring'indeki karar)."""
    state = classify_po3_phase(_df([_ACC_BAR]))
    assert state.phase == PHASE_UNDEFINED
    assert po3_blocks_entry(state) is False


def test_po3_empty_df_is_undefined():
    state = classify_po3_phase(pd.DataFrame())
    assert state.phase == PHASE_UNDEFINED
    assert po3_blocks_entry(state) is False


# ──────────────────────── MPA/2 — SWEEP / GRAB ────────────────────────

def _liq_df(mid_high, mid_close):
    return _df([
        (98.0, 99.0, 97.0, 98.0),
        (98.0, mid_high, 98.0, mid_close),
        (98.0, 99.0, 97.0, 98.0),
    ])


def test_liquidity_wide_violation_is_sweep():
    ev = detect_liquidity_event(_liq_df(107.0, 98.0), ref_level=100.0, side="UP", atr=10.0)
    assert ev is not None
    assert ev.kind == KIND_SWEEP          # excess 0.70 > 0.50
    assert ev.idx == 1 and ev.reclaim_idx == 1


def test_liquidity_narrow_violation_is_grab():
    ev = detect_liquidity_event(_liq_df(102.0, 98.0), ref_level=100.0, side="UP", atr=10.0)
    assert ev is not None
    assert ev.kind == KIND_GRAB           # excess 0.20 <= 0.50


def test_liquidity_no_reclaim_is_not_an_event():
    """Kalıcı kırılım likidite olayı değildir — yapı kırılımıdır."""
    df = _df([
        (98.0, 99.0, 97.0, 98.0),
        (98.0, 107.0, 98.0, 105.0),
        (105.0, 108.0, 104.0, 106.0),
    ])
    assert detect_liquidity_event(df, ref_level=100.0, side="UP", atr=10.0) is None


def test_liquidity_noise_below_min_excess_ignored():
    assert detect_liquidity_event(_liq_df(100.5, 98.0), ref_level=100.0, side="UP", atr=10.0) is None


def test_liquidity_invalid_atr_returns_none():
    assert detect_liquidity_event(_liq_df(107.0, 98.0), ref_level=100.0, side="UP", atr=0.0) is None


def test_liquidity_score_counter_trend_penalises_grab():
    """Counter-trend majör SWEEP ister; GRAB gelirse puan yarılanır."""
    sweep = detect_liquidity_event(_liq_df(107.0, 98.0), ref_level=100.0, side="UP", atr=10.0)
    grab = detect_liquidity_event(_liq_df(102.0, 98.0), ref_level=100.0, side="UP", atr=10.0)
    assert liquidity_score(sweep, REGIME_COUNTER) == 11     # 9 + temiz geri kazanım 2
    assert liquidity_score(grab, REGIME_COUNTER) == 4       # 9 // 2 — tip uyumsuz
    assert liquidity_score(grab, REGIME_TREND) == 9         # trend-devam GRAB ister
    assert liquidity_score(None, REGIME_TREND) == 0


def test_liquidity_score_htf_bonus_capped():
    sweep = detect_liquidity_event(_liq_df(107.0, 98.0), ref_level=100.0, side="UP", atr=10.0)
    assert liquidity_score(sweep, REGIME_COUNTER, htf_level=True) == 15   # tavan


def test_regime_risk_multiplier_trims_trend_trade_on_sweep():
    sweep = detect_liquidity_event(_liq_df(107.0, 98.0), ref_level=100.0, side="UP", atr=10.0)
    grab = detect_liquidity_event(_liq_df(102.0, 98.0), ref_level=100.0, side="UP", atr=10.0)
    assert regime_risk_multiplier(sweep, REGIME_TREND) == 0.85
    assert regime_risk_multiplier(grab, REGIME_TREND) == 1.0
    assert regime_risk_multiplier(sweep, REGIME_COUNTER) == 1.0


# ───────────────────── MPA/3 — V-type recovery ─────────────────────

ZONE = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")


def _v_rows(bottom_low, rec_high, rec_close):
    return [
        (129.0, 130.0, 128.0, 129.0),
        (128.0, 129.0, 120.0, 121.0),
        (121.0, 122.0, bottom_low, 104.0),
        (104.0, rec_high, 103.0, rec_close),
    ]


def test_v_recovery_detected_on_partial_fill_and_sharp_reclaim():
    ok, entry = detect_v_recovery(
        _df(_v_rows(102.0, 120.0, 118.0)), ZONE, "LONG", since_ts=0, atr=5.0
    )
    assert ok is True
    assert entry == 118.0


def test_v_recovery_rejects_full_zone_fill():
    """Bölge TAM doldurulduysa bu V-recovery değildir (kaynağın şartı)."""
    ok, entry = detect_v_recovery(
        _df(_v_rows(99.0, 120.0, 118.0)), ZONE, "LONG", since_ts=0, atr=5.0
    )
    assert ok is False and entry is None


def test_v_recovery_rejects_weak_reclaim():
    """Geri kazanım bacağın yarısını almıyorsa 'sert toparlanma' sayılmaz."""
    ok, _ = detect_v_recovery(
        _df(_v_rows(102.0, 108.0, 107.0)), ZONE, "LONG", since_ts=0, atr=5.0
    )
    assert ok is False


def test_v_recovery_rejects_shallow_entry_leg():
    """Giriş bacağı ATR'ye göre sert değilse V-recovery sayılmaz."""
    ok, _ = detect_v_recovery(
        _df(_v_rows(102.0, 120.0, 118.0)), ZONE, "LONG", since_ts=0, atr=50.0
    )
    assert ok is False


def test_v_recovery_rejects_close_below_zone():
    """Bölgenin altına gövde kapanışı → tez geçersiz."""
    rows = _v_rows(102.0, 120.0, 118.0)
    rows[3] = (104.0, 120.0, 95.0, 99.0)
    ok, _ = detect_v_recovery(_df(rows), ZONE, "LONG", since_ts=0, atr=5.0)
    assert ok is False


def test_v_recovery_degenerate_inputs():
    assert detect_v_recovery(_df(_v_rows(102.0, 120.0, 118.0)), ZONE, "LONG", 0, atr=0.0) == (False, None)
    flat = ZoneSpec(low=100.0, high=100.0, source="OTE")
    assert detect_v_recovery(_df(_v_rows(102.0, 120.0, 118.0)), flat, "LONG", 0, atr=5.0) == (False, None)


# ─────────────────────── MPA/4 — BCEL defteri ───────────────────────

def _ev(code, idx, leg):
    return Evidence(code=code, idx=idx, leg_id=leg)


def test_ledger_single_evidence_keeps_bias_intact():
    """TEK emare HTF bias'ı değiştirmez — kaynağın açık kuralı."""
    v = evaluate_bias_ledger([_ev("E1_CHOCH", 18, 1)], current_idx=20)
    assert v.verdict == VERDICT_INTACT and v.score == 2


def test_ledger_reaches_transition_at_three():
    v = evaluate_bias_ledger(
        [_ev("E1_CHOCH", 16, 1), _ev("E2_BOS_AFTER_CHOCH", 18, 2)], current_idx=20
    )
    assert v.verdict == VERDICT_TRANSITION and v.score == 4


def test_ledger_flips_at_five_with_structural_evidence():
    v = evaluate_bias_ledger(
        [
            _ev("E1_CHOCH", 14, 1),
            _ev("E2_BOS_AFTER_CHOCH", 16, 2),
            _ev("E3_DISPLACEMENT_FVG", 18, 3),
        ],
        current_idx=20,
    )
    assert v.verdict == VERDICT_FLIP and v.score == 5 and v.has_structural


def test_ledger_will_not_flip_on_soft_evidence_alone():
    """5 puan yumuşak kanıtla toplansa bile yapı kırılımı yoksa FLIP OLMAZ.

    Bu, tasarımın en kritik güvenlik özelliği — momentum/imbalance
    emareleri tek başına HTF bias'ı çeviremez.
    """
    v = evaluate_bias_ledger(
        [
            _ev("E3_DISPLACEMENT_FVG", 14, 1),
            _ev("E4_SWEEP_SFP", 15, 2),
            _ev("E5_OB_MITIGATED", 16, 3),
            _ev("E6_NO_NEW_EXTREME", 17, 4),
            _ev("E8_MOMENTUM_LOSS", 18, 5),
        ],
        current_idx=20,
    )
    assert v.score == 5
    assert v.has_structural is False
    assert v.verdict == VERDICT_TRANSITION      # FLIP DEĞİL


def test_ledger_drops_evidence_outside_window():
    v = evaluate_bias_ledger([_ev("E1_CHOCH", 3, 1)], current_idx=30, window_bars=20)
    assert v.score == 0 and v.verdict == VERDICT_INTACT
    assert len(v.dropped) == 1


def test_ledger_reset_discards_pre_reset_evidence():
    """Trend yönünde yeni kırılım gelirse önceki karşı kanıtlar geçersizdir."""
    v = evaluate_bias_ledger(
        [_ev("E1_CHOCH", 8, 1), _ev("E2_BOS_AFTER_CHOCH", 9, 2)],
        current_idx=20,
        reset_idx=10,
    )
    assert v.score == 0 and v.verdict == VERDICT_INTACT


def test_ledger_counts_one_evidence_per_leg():
    """Aynı bacaktan en fazla bir kanıt — tek sert hareket defteri dolduramaz."""
    v = evaluate_bias_ledger(
        [
            _ev("E3_DISPLACEMENT_FVG", 15, 7),
            _ev("E1_CHOCH", 16, 7),          # aynı bacak, daha ağır → bu sayılır
            _ev("E8_MOMENTUM_LOSS", 17, 7),
        ],
        current_idx=20,
    )
    assert v.score == 2
    assert [e.code for e in v.counted] == ["E1_CHOCH"]


def test_find_reset_idx_picks_latest_trend_bos():
    breaks = [
        StructBreak(kind="BOS", direction="BULL", price=10.0, idx=4),
        StructBreak(kind="BOS", direction="BULL", price=12.0, idx=12),
        StructBreak(kind="CHoCH", direction="BEAR", price=9.0, idx=15),
    ]
    assert find_reset_idx("BULL", breaks) == 12
    assert find_reset_idx("BEAR", breaks) is None


def test_collect_structural_evidence_e1_e2_e6():
    breaks = [
        StructBreak(kind="CHoCH", direction="BEAR", price=99.0, idx=5),
        StructBreak(kind="BOS", direction="BEAR", price=95.0, idx=8),
    ]
    swings = {
        "swing_highs": [Swing(price=110.0, idx=2), Swing(price=105.0, idx=6)],
        "swing_lows": [],
    }
    df = _df([_ACC_BAR] * 10)
    ev = collect_structural_evidence("BULL", breaks, df, swings=swings)
    codes = {e.code for e in ev}
    assert "E1_CHOCH" in codes
    assert "E2_BOS_AFTER_CHOCH" in codes
    assert "E6_NO_NEW_EXTREME" in codes     # BULL bias'ta lower high


def test_collect_structural_evidence_ignores_aligned_breaks():
    """Trend YÖNÜNDEKİ kırılımlar karşı kanıt değildir."""
    breaks = [StructBreak(kind="CHoCH", direction="BULL", price=99.0, idx=5)]
    ev = collect_structural_evidence("BULL", breaks, _df([_ACC_BAR] * 10))
    assert ev == [] or all(e.code == "E8_MOMENTUM_LOSS" for e in ev)


def test_ledger_blocks_only_trend_continuation_in_transition():
    """G9: TRANSITION'da eski yönde YENİ trend-devam işlemi açılmaz."""
    t = evaluate_bias_ledger(
        [_ev("E1_CHOCH", 16, 1), _ev("E2_BOS_AFTER_CHOCH", 18, 2)], current_idx=20
    )
    assert ledger_blocks_new_entry(t, "LONG", "BULL") is True     # trend-devam → blok
    assert ledger_blocks_new_entry(t, "SHORT", "BULL") is False   # reversal → serbest

    intact = evaluate_bias_ledger([_ev("E1_CHOCH", 18, 1)], current_idx=20)
    assert ledger_blocks_new_entry(intact, "LONG", "BULL") is False


# ─────────────── REGRESYON: toggle'lar varsayılan KAPALI ───────────────

MPA_TOGGLES = ["po3_gate", "liquidity_class", "v_recovery", "bias_ledger"]


def test_mpa_toggles_default_off_in_config():
    """Dördü de config.yaml'da FALSE olmalı.

    Bu test kırılırsa canlı V1/V2/V3 botlarının davranışı sessizce değişmiş
    demektir — MPA filtreleri NET-cost backtest gate'inden geçmeden ve
    operatör onayı olmadan açılamaz.
    """
    cfg_path = Path(__file__).resolve().parents[2] / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    smc_v2 = cfg.get("smc_v2", {})
    for toggle in MPA_TOGGLES:
        assert toggle in smc_v2, f"config.yaml smc_v2.{toggle} tanımlı değil"
        assert smc_v2[toggle] is False, f"smc_v2.{toggle} varsayılan KAPALI olmalı"
