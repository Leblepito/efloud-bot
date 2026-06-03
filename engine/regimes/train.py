import numpy as np
import pandas as pd
import json
from pathlib import Path
from engine.regimes.model import RegimeMLModel
from engine.regimes import RegimeDetector

ROOT = Path(__file__).resolve().parents[2]

# Integer label mapping (matches RegimeMLModel.class_labels order).
_LABEL_MAP = {
    "TRENDING": 0,
    "RANGING": 1,
    "VOLATILE": 2,
    "REVERSAL": 3,
    "LOW_LIQUIDITY": 4,
    "UNKNOWN": 1,  # UNKNOWN falls back to RANGING
}

# Sliding-window start: min length for indicator lookbacks (adx_period*2=28, bb=20).
_START_IDX = 40


def _extract_features(df: pd.DataFrame, detector, i: int):
    """The 5 normalized regime features at bar i (pure indicators), plus the rule
    analysis (used only by the rule-label path). Shared by both label builders."""
    sub_df = df.iloc[:i + 1]
    analysis = detector.analyze(sub_df)
    feat_adx = float(analysis.adx) / 100.0
    feat_bbw = min(float(analysis.bb_width), 5.0) / 2.0
    feat_atr = min(float(analysis.atr_ratio), 5.0) / 2.0
    ret = df["close"].iloc[i - 20:i + 1].pct_change().std()
    feat_ret_std = float(min(ret * 100.0, 5.0)) if not pd.isna(ret) else 0.0
    vol_sub = df["volume"].iloc[i - 20:i + 1]
    feat_vol = 0.0
    vol_std = vol_sub.std()
    if vol_std > 0:
        feat_vol = float((df["volume"].iloc[i] - vol_sub.mean()) / vol_std)
    feat_vol = float(max(min(feat_vol, 3.0), -3.0))  # clamp [-3, 3]
    return [feat_adx, feat_bbw, feat_atr, feat_ret_std, feat_vol], analysis


def build_features_and_labels(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Features + RULE-based labels (legacy default).

    S7 NOTE: the label is the rule detector's own output, so the ML can only
    learn to REPRODUCE the rules (circular — zero independent signal).
    ``build_features_and_forward_labels`` is the non-circular alternative.
    """
    detector = RegimeDetector()
    X_list, y_list = [], []
    for i in range(_START_IDX, len(df)):
        feats, analysis = _extract_features(df, detector, i)
        X_list.append(feats)
        y_list.append(_LABEL_MAP.get(analysis.regime, 1))
    return np.array(X_list), np.array(y_list)


def _forward_regime_label(future_closes, *, trend_return_pct: float = 1.5,
                          vol_bar_std_pct: float = 1.0) -> int:
    """Classify the regime that ACTUALLY materialised over a forward close window:
    VOLATILE if per-bar return std is high; else TRENDING if the net move is large;
    else RANGING. Returns an int matching ``_LABEL_MAP``."""
    closes = np.asarray(list(future_closes), dtype=float)
    if closes.size < 2 or closes[0] <= 0:
        return 1  # RANGING
    fwd_return_pct = abs(closes[-1] - closes[0]) / closes[0] * 100.0
    rets = np.diff(closes) / closes[:-1]
    bar_std_pct = float(np.std(rets)) * 100.0
    if bar_std_pct > vol_bar_std_pct:
        return 2  # VOLATILE
    if fwd_return_pct > trend_return_pct:
        return 0  # TRENDING
    return 1  # RANGING


def build_features_and_forward_labels(
    df: pd.DataFrame, horizon: int = 10, *,
    trend_return_pct: float = 1.5, vol_bar_std_pct: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """S7: same features, but each label is the FORWARD-REALISED regime over the
    next ``horizon`` bars — breaking the rule-label circularity so the ML learns
    to PREDICT regime. The forward label uses future bars (valid for OFFLINE
    training only); the features stay causal (``df.iloc[:i+1]``)."""
    detector = RegimeDetector()
    closes = df["close"].values
    X_list, y_list = [], []
    for i in range(_START_IDX, len(df) - horizon):
        feats, _ = _extract_features(df, detector, i)
        X_list.append(feats)
        y_list.append(_forward_regime_label(
            closes[i + 1:i + 1 + horizon],
            trend_return_pct=trend_return_pct, vol_bar_std_pct=vol_bar_std_pct,
        ))
    return np.array(X_list), np.array(y_list)

def run_auto_train(
    df: pd.DataFrame, weights_filename: str = "regime_model_weights.json",
    *, forward_labels: bool = False, horizon: int = 10,
) -> dict:
    """Train the RegimeMLModel and save weights.

    S7: ``forward_labels=False`` (default) keeps the legacy rule-based labels —
    live behaviour is UNCHANGED. ``forward_labels=True`` trains on the
    forward-realised regime (non-circular); adopt it for the live model only
    after backtest validation shows it improves regime-conditioned PnL.
    """
    if forward_labels:
        X, y = build_features_and_forward_labels(df, horizon=horizon)
    else:
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
