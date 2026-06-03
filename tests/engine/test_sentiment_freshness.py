"""A3: load_ai_sentiment must ignore a STALE registry.

The sentiment loop refreshes every ~4h; the result is injected as a ±5
confluence bonus. load_ai_sentiment read the registry without checking
``last_updated``, so after a restart (or if the loop stalls) an old RISK_ON /
RISK_OFF kept biasing every signal indefinitely. Revert to NEUTRAL when the
registry is older than the refresh window. Missing last_updated stays lenient
(legacy registries always loaded; real ones always stamp it).
"""
import json
from datetime import datetime, timedelta, timezone

from engine.safe_orchestrator import SafeOrchestrator

_CFG = {
    "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
    "structure": {"swing_lookback": 20, "ob_sequential": 2, "body_mode": "close",
                  "eq_threshold_pct": 5.0, "range_lookback": 50},
    "fibonacci": {"ote_lower": 0.62, "ote_upper": 0.79, "ext_tp2": 1.0},
    "safety": {"adx_trend_threshold": 25, "adx_range_threshold": 20,
               "volatile_atr_mult": 2.5, "daily_loss_limit_pct": 3.0,
               "weekly_drawdown_limit_pct": 8.0, "consecutive_loss_limit": 3,
               "starting_balance": 1000},
    "risk": {"min_confluence": 70, "min_rr": 1.8, "max_open_positions": 3, "recency_bars": 40},
    "operation": {"watch_only": True},
    "exchange": {"leverage": 1},
}


def _orch(tmp_path, sentiment, last_updated):
    reg = {"macro_sentiment": sentiment, "confidence_score": 0.85,
           "fear_and_greed": 65.0, "bitcoin_trend": "BULLISH", "reasoning": "test"}
    if last_updated is not None:
        reg["last_updated"] = last_updated
    (tmp_path / "ai_sentiment_registry.json").write_text(json.dumps(reg), encoding="utf-8")
    return SafeOrchestrator(config=dict(_CFG), state_dir=str(tmp_path))


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def test_stale_sentiment_reverts_to_neutral(tmp_path):
    old = _iso(datetime.now(timezone.utc) - timedelta(hours=5))  # > 4h15m window
    orch = _orch(tmp_path, "RISK_ON", old)
    assert orch.sentiment_state["macro_sentiment"] == "NEUTRAL"


def test_fresh_sentiment_loaded_as_is(tmp_path):
    fresh = _iso(datetime.now(timezone.utc) - timedelta(minutes=10))
    orch = _orch(tmp_path, "RISK_ON", fresh)
    assert orch.sentiment_state["macro_sentiment"] == "RISK_ON"


def test_missing_last_updated_is_lenient(tmp_path):
    orch = _orch(tmp_path, "RISK_ON", None)
    assert orch.sentiment_state["macro_sentiment"] == "RISK_ON"
