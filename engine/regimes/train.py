import numpy as np
import pandas as pd
import json
from pathlib import Path
from engine.regimes.model import RegimeMLModel
from engine.regimes import RegimeDetector

ROOT = Path(__file__).resolve().parents[2]

def build_features_and_labels(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Slide through historical OHLCV data to compute training features and rule-based labels.
    
    Acts as a self-training / semi-supervised feature pipeline to learn decision boundaries.
    """
    detector = RegimeDetector()
    X_list = []
    y_list = []
    
    # Consistent mapping to integers (matching RegimeMLModel.class_labels list order)
    label_map = {
        "TRENDING": 0,
        "RANGING": 1,
        "VOLATILE": 2,
        "REVERSAL": 3,
        "LOW_LIQUIDITY": 4,
        "UNKNOWN": 1  # UNKNOWN falls back to RANGING
    }

    # Sliding window starting index to allow technical indicator lookbacks
    # Min length needed for indicators (adx_period * 2 = 28, bb_period = 20)
    start_idx = 40
    
    for i in range(start_idx, len(df)):
        sub_df = df.iloc[:i+1]
        analysis = detector.analyze(sub_df)
        
        # Feature 1: Normalized ADX (0 to 1)
        feat_adx = float(analysis.adx) / 100.0
        
        # Feature 2: Bollinger Band Width Ratio relative to average (normalized)
        feat_bbw = min(float(analysis.bb_width), 5.0) / 2.0
        
        # Feature 3: ATR Ratio relative to baseline (normalized)
        feat_atr = min(float(analysis.atr_ratio), 5.0) / 2.0
        
        # Feature 4: Price return volatility standard deviation of past 20 bars
        ret = df["close"].iloc[i-20:i+1].pct_change().std()
        feat_ret_std = float(min(ret * 100.0, 5.0)) if not pd.isna(ret) else 0.0
        
        # Feature 5: Volume Z-Score relative to past 20 bars
        vol_sub = df["volume"].iloc[i-20:i+1]
        feat_vol = 0.0
        vol_std = vol_sub.std()
        if vol_std > 0:
            feat_vol = float((df["volume"].iloc[i] - vol_sub.mean()) / vol_std)
        feat_vol = float(max(min(feat_vol, 3.0), -3.0))  # Clamp between -3 and 3
        
        X_list.append([feat_adx, feat_bbw, feat_atr, feat_ret_std, feat_vol])
        y_list.append(label_map.get(analysis.regime, 1))

    return np.array(X_list), np.array(y_list)

def run_auto_train(df: pd.DataFrame, weights_filename: str = "regime_model_weights.json") -> dict:
    """Train the RegimeMLModel using historical dataframe features and save weights."""
    X, y = build_features_and_labels(df)
    
    if len(X) < 10:
        return {
            "success": False,
            "reason": f"Insufficient training samples ({len(X)} < 10). Minimum 10 samples required."
        }
        
    model = RegimeMLModel(num_features=5, num_classes=5)
    initial_loss = model.compute_loss(X, y)
    
    # Train the model with gradient descent
    model.fit(X, y, epochs=150, lr=0.1)
    
    final_loss = model.compute_loss(X, y)
    
    if "/" in str(weights_filename) or "\\" in str(weights_filename):
        weights_path = Path(weights_filename)
    else:
        weights_path = ROOT / "state" / weights_filename
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_weights(str(weights_path))
    
    return {
        "success": True,
        "samples": len(X),
        "initial_loss": initial_loss,
        "final_loss": final_loss,
        "weights_path": str(weights_path)
    }
