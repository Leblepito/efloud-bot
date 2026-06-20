import pandas as pd
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock
import json
import os
from engine.regimes import RegimeDetector, RegimeAnalysis
from engine.regimes.model import RegimeMLModel

def test_regime_detector_loads_ml_model_and_runs_ensemble(tmp_path):
    """Verify that RegimeDetector loads a saved weights file, makes inference, and ensembles it into notes."""
    np.random.seed(42)
    closes = np.linspace(2000, 2050, 60) + np.random.normal(0, 3, 60)
    highs = closes + np.random.uniform(1, 5, 60)
    lows = closes - np.random.uniform(1, 5, 60)
    opens = closes - np.random.normal(0, 1, 60)
    volumes = np.random.lognormal(10, 0.5, 60)
    
    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes
    })
    
    # Create fake weights file and save it
    model = RegimeMLModel(num_features=5, num_classes=5)
    # Set high weight for VOLATILE (class 2) on high ATR ratio (feature 2)
    model.W = np.zeros((5, 5))
    model.W[2, 2] = 10.0  # ATR feature points strongly to VOLATILE
    
    weights_dir = tmp_path / "state"
    weights_dir.mkdir(parents=True, exist_ok=True)
    weights_path = weights_dir / "regime_model_weights.json"
    model.save_weights(str(weights_path))
    
    # Initialize detector pointing to our temp weights
    detector = RegimeDetector()
    detector.weights_path = weights_path
    detector._load_ml_model()
    
    assert detector.model is not None
    
    analysis = detector.analyze(df)
    
    # Verify model is represented in notes and ensembling took place
    has_ml_note = any("ML Model:" in note for note in analysis.notes)
    assert has_ml_note, f"No ML note in analysis.notes: {analysis.notes}"
    
    # Verify fallback if weights file is deleted
    os.remove(str(weights_path))
    detector._load_ml_model()
    assert detector.model is None
    
    analysis_fallback = detector.analyze(df)
    has_ml_note_fallback = any("ML Model:" in note for note in analysis_fallback.notes)
    assert not has_ml_note_fallback


# ── C3: ML regime override is ADVISORY by default (cannot write the entry gate) ──

_LABELS = ["TRENDING", "RANGING", "VOLATILE", "REVERSAL", "LOW_LIQUIDITY"]


def _flat_df(n=60):
    close = np.full(n, 100.0)
    return pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5,
                         "close": close, "volume": np.full(n, 1000.0)})


def _force_det(detector, adx, bbw, atr):
    """Stub the noisy feature math so the deterministic decision tree is pinned."""
    detector._adx = lambda df, period=14: adx
    detector._bb_width_ratio = lambda df, period=20: bbw
    detector._atr_ratio = lambda df, period=14: atr


def _force_ml(detector, ml_regime, conf=0.99):
    """Force the ML model to predict `ml_regime` at high confidence."""
    probs = np.full(5, (1 - conf) / 4)
    probs[_LABELS.index(ml_regime)] = conf
    model = MagicMock()
    model.predict_proba.return_value = np.array([probs])
    model.class_labels = _LABELS
    detector.model = model


def test_ml_override_cannot_widen_entry_gate():
    """C3 default (advisory): a deterministic RANGING bar (gate-BLOCKED) must NOT
    be flipped to TRENDING by a high-confidence ML prediction — the entry gate
    stays closed. The ML note is still logged (advisory)."""
    det = RegimeDetector(ml_can_override_gate=False)
    _force_det(det, adx=10.0, bbw=0.3, atr=1.0)   # low ADX + BB squeeze → RANGING
    _force_ml(det, "TRENDING", conf=0.99)
    a = det.analyze(_flat_df())
    assert a.regime == "RANGING"
    assert a.can_open_new_position is False
    assert any("ML Model: TRENDING" in n for n in a.notes)


def test_ml_override_cannot_unset_tighten_stops():
    """C3 default: deterministic VOLATILE (should_tighten_stops) must not be
    cleared by ML flipping to TRENDING."""
    det = RegimeDetector(ml_can_override_gate=False)
    _force_det(det, adx=15.0, bbw=1.0, atr=3.0)   # ATR 3.0x > vol_mult 2.5 → VOLATILE
    _force_ml(det, "TRENDING", conf=0.99)
    a = det.analyze(_flat_df())
    assert a.regime == "VOLATILE"
    assert a.should_tighten_stops is True


def test_ml_override_active_only_with_flag():
    """C3: the override path is reachable ONLY when ml_can_override_gate is on.
    Deterministic TRENDING + ML RANGING (a NARROWING, fail-closed-safe override):
    flag OFF keeps TRENDING (gate open); flag ON applies the ML narrowing."""
    df = _flat_df()
    off = RegimeDetector(ml_can_override_gate=False)
    _force_det(off, adx=30.0, bbw=1.0, atr=1.0)   # ADX 30 >= 25 → TRENDING
    _force_ml(off, "RANGING", conf=0.99)
    a_off = off.analyze(df)
    assert a_off.regime == "TRENDING" and a_off.can_open_new_position is True

    on = RegimeDetector(ml_can_override_gate=True)
    _force_det(on, adx=30.0, bbw=1.0, atr=1.0)
    _force_ml(on, "RANGING", conf=0.99)
    a_on = on.analyze(df)
    assert a_on.regime == "RANGING" and a_on.can_open_new_position is False


def test_ml_override_flag_on_cannot_widen_volatile_to_reversal():
    """C3 hardening (risk-ops nit): even with the flag ON, ML must not flip
    deterministic VOLATILE (gate-CLOSED when allow_volatile_entries=False) to
    REVERSAL (gate-OPEN). The guard's open-set respects allow_volatile_entries."""
    det = RegimeDetector(ml_can_override_gate=True)  # allow_volatile_entries default False
    _force_det(det, adx=15.0, bbw=1.0, atr=3.0)      # ATR 3.0x → VOLATILE (gate-blocked)
    _force_ml(det, "REVERSAL", conf=0.99)
    a = det.analyze(_flat_df())
    assert a.regime == "VOLATILE"
    assert a.can_open_new_position is False
