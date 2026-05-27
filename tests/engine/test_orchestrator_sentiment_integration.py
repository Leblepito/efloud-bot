"""Tests for Gemini AI Macro Sentiment confluence integration in generate_signals."""

from types import SimpleNamespace
from unittest.mock import MagicMock
import pandas as pd
import pytest
from engine.signals import generate_signals

class TestSentimentConfluenceScoring:
    def _make_mock_engine(self, break_obj) -> MagicMock:
        e_range = SimpleNamespace(
            discount=False, premium=False, dev_bull=False, dev_bear=False,
            lo=99.0, hi=101.0,
        )
        engine = MagicMock()
        engine.analyze.return_value = {
            "trend": "BULL",
            "active_fvgs": [],
            "active_obs": [],
            "swing_highs": [],
            "swing_lows": [],
            "range": e_range,
        }
        engine.swings.return_value = ([], [])
        # First call returns empty (mtf_brks); second returns the break.
        engine.structure.side_effect = [[], [break_obj]]
        engine.order_blocks.return_value = []
        engine.sfps.return_value = []
        engine.range_info.return_value = e_range
        engine.ote.return_value = None
        return engine

    def test_risk_on_bonus_for_long_signal(self) -> None:
        # A CHoCH aligned with BULL HTF bias (base score = 25 for HTF bias only)
        # RISK_ON sentiment should add +5 bonus, raising the score to 30.
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break)
        df = pd.DataFrame({
            "close": [100.0] * 50,
            "high": [100.5] * 50,
            "low": [99.5] * 50
        })

        # We set min_confluence to 0 so the signal is not filtered out
        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=0, min_rr=0.1, fib_ext=1.618,
            recency_bars=40,
            symbol="BTC/USDT",
            ai_sentiment={"macro_sentiment": "RISK_ON"}
        )

        assert len(sigs) == 1
        assert sigs[0].confluence == 30  # 25 + 5
        assert "Gemini AI Macro Sentiment is RISK_ON (+5)" in sigs[0].reasons

    def test_risk_on_penalty_for_short_signal(self) -> None:
        # A CHoCH aligned with BEAR HTF bias (base score = 25) under RISK_ON should get -5 penalty.
        choch_break = SimpleNamespace(
            direction="BEAR", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break)
        # Set htf_bias trend to BEAR in mock engine
        engine.analyze.return_value["trend"] = "BEAR"
        df = pd.DataFrame({
            "close": [100.0] * 50,
            "high": [100.5] * 50,
            "low": [99.5] * 50
        })

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=0, min_rr=0.1, fib_ext=1.618,
            recency_bars=40,
            symbol="BTC/USDT",
            ai_sentiment={"macro_sentiment": "RISK_ON"}
        )

        assert len(sigs) == 1
        assert sigs[0].confluence == 20  # 25 - 5
        assert "Gemini AI Macro Sentiment is RISK_ON (-5)" in sigs[0].reasons

    def test_risk_off_bonus_for_short_signal(self) -> None:
        # A BEAR signal under RISK_OFF gets +5 bonus -> 30
        choch_break = SimpleNamespace(
            direction="BEAR", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break)
        engine.analyze.return_value["trend"] = "BEAR"
        df = pd.DataFrame({
            "close": [100.0] * 50,
            "high": [100.5] * 50,
            "low": [99.5] * 50
        })

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=0, min_rr=0.1, fib_ext=1.618,
            recency_bars=40,
            symbol="BTC/USDT",
            ai_sentiment={"macro_sentiment": "RISK_OFF"}
        )

        assert len(sigs) == 1
        assert sigs[0].confluence == 30  # 25 + 5
        assert "Gemini AI Macro Sentiment is RISK_OFF (+5)" in sigs[0].reasons

    def test_neutral_sentiment_no_modification(self) -> None:
        # NEUTRAL macro sentiment applies no change -> 25
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break)
        df = pd.DataFrame({
            "close": [100.0] * 50,
            "high": [100.5] * 50,
            "low": [99.5] * 50
        })

        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=0, min_rr=0.1, fib_ext=1.618,
            recency_bars=40,
            symbol="BTC/USDT",
            ai_sentiment={"macro_sentiment": "NEUTRAL"}
        )

        assert len(sigs) == 1
        assert sigs[0].confluence == 25
        # None of our AI reasons should be there
        for reason in sigs[0].reasons:
            assert "Gemini AI Macro Sentiment" not in reason
