import pandas as pd
import numpy as np
import pytest
from pathlib import Path
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
