import pandas as pd
import numpy as np
import pytest
from engine.regimes.train import build_features_and_labels, run_auto_train

def test_build_features_and_labels():
    """Verify that build_features_and_labels parses a DataFrame and returns correct shape features/labels."""
    np.random.seed(42)
    # Generate 150 bars of mock kline data
    closes = np.linspace(2000, 2100, 150) + np.random.normal(0, 5, 150)
    highs = closes + np.random.uniform(1, 10, 150)
    lows = closes - np.random.uniform(1, 10, 150)
    opens = closes - np.random.normal(0, 2, 150)
    volumes = np.random.lognormal(10, 0.5, 150)
    
    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes
    })
    
    X, y = build_features_and_labels(df)
    
    assert isinstance(X, np.ndarray)
    assert isinstance(y, np.ndarray)
    assert X.shape[0] == y.shape[0]
    assert X.shape[1] == 5  # 5 features
    assert X.shape[0] > 0
    
    # Class index should be within 0-4
    assert np.all((y >= 0) & (y < 5))

def test_run_auto_train(tmp_path):
    """Verify that run_auto_train trains the model on data and outputs the saved weights JSON file."""
    np.random.seed(42)
    closes = np.linspace(2000, 2100, 80) + np.random.normal(0, 5, 80)
    highs = closes + np.random.uniform(1, 10, 80)
    lows = closes - np.random.uniform(1, 10, 80)
    opens = closes - np.random.normal(0, 2, 80)
    volumes = np.random.lognormal(10, 0.5, 80)
    
    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes
    })
    
    weights_filename = "test_regime_weights_auto.json"
    res = run_auto_train(df, weights_filename=weights_filename)
    
    assert res["success"] is True
    assert res["samples"] > 0
    assert res["final_loss"] < res["initial_loss"]
    assert "weights_path" in res
    
    # Clean up test file
    import os
    if os.path.exists(res["weights_path"]):
        os.remove(res["weights_path"])
