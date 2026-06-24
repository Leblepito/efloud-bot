"""Tests for engine.signals diagnostic logging helpers."""

import logging
from types import SimpleNamespace
from typing import Dict
from unittest.mock import MagicMock

import pandas as pd
import pytest

from engine.signals import _format_score_histogram, generate_signals


class TestFormatScoreHistogram:
    """Histogram of confluence-score buckets emitted in the reject summary log."""

    def test_empty_dict_returns_empty_string(self) -> None:
        assert _format_score_histogram({}) == ""

    def test_single_bucket(self) -> None:
        assert _format_score_histogram({60: 5}) == "60×5"

    def test_multiple_buckets_sorted_by_score_descending(self) -> None:
        # Three buckets, all shown; highest score first so the reader sees
        # how close any reject came to the floor.
        buckets: Dict[int, int] = {55: 1, 60: 5, 65: 2}
        assert _format_score_histogram(buckets) == "65×2 60×5 55×1"

    def test_top_n_limits_output_to_three_highest_scores(self) -> None:
        buckets: Dict[int, int] = {50: 1, 55: 2, 60: 5, 65: 3, 70: 1}
        # Default top_n=3 → 70, 65, 60 (highest scores, regardless of count)
        assert _format_score_histogram(buckets) == "70×1 65×3 60×5"

    def test_top_n_override(self) -> None:
        buckets: Dict[int, int] = {55: 1, 60: 5, 65: 2}
        assert _format_score_histogram(buckets, top_n=1) == "65×2"


class TestRejectSummaryLog:
    """Reject summary log + trigger acceptance for CHoCH/BOS breaks.

    The mock engine returns a single user-supplied StructBreak in `e_brks`
    so each test can target one trigger-gate scenario (CHoCH/BOS, fresh/stale,
    aligned/counter-direction) without spinning up the real SMC pipeline.
    """

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
        # First call (for mtf_brks) returns empty; second (e_brks) returns the break.
        engine.structure.side_effect = [[], [break_obj]]
        engine.order_blocks.return_value = []
        engine.sfps.return_value = []
        engine.range_info.return_value = e_range
        engine.ote.return_value = None
        return engine

    def test_reject_log_contains_symbol_prefix_and_histogram(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # A CHoCH aligned with BULL HTF bias, recent, but with no extra
        # confluence layers → score == 25 (HTF bias only), well below floor 70.
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break)
        df = pd.DataFrame({"close": [100.0] * 50})

        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            sigs = generate_signals(
                engine, df, df, df,
                min_confluence=70, min_rr=1.5, fib_ext=1.618,
                recency_bars=40,
                symbol="ETH/USDT",
            )

        assert sigs == []
        reject_msgs = [
            rec.message for rec in caplog.records
            if "0 signals" in rec.message and "Rejects" in rec.message
        ]
        assert reject_msgs, f"No reject summary logged. Records: {[r.message for r in caplog.records]}"
        msg = reject_msgs[0]
        assert "[ETH/USDT]" in msg
        assert "conf<70" in msg
        assert "max=25" in msg
        assert "hist:" in msg
        assert "25×1" in msg

    def test_bos_in_htf_direction_reaches_confluence_scoring(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """BOS aligned with HTF bias must be a valid trigger candidate.

        Pre-change: signals.py drops every non-CHoCH break, so this BOS is
        silently ignored and no reject log is emitted.
        Post-change: BOS goes through to confluence scoring; with no extra
        layers the score is 25 (HTF bias only) → reject log emitted with
        bucket 25.
        """
        bos_break = SimpleNamespace(
            direction="BULL", kind="BOS", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(bos_break)
        df = pd.DataFrame({"close": [100.0] * 50})

        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            sigs = generate_signals(
                engine, df, df, df,
                min_confluence=70, min_rr=1.5, fib_ext=1.618,
                recency_bars=40,
                symbol="ETH/USDT",
            )

        assert sigs == []
        reject_msgs = [
            rec.message for rec in caplog.records
            if "0 signals" in rec.message and "Rejects" in rec.message
        ]
        assert reject_msgs, (
            "BOS trigger was filtered before confluence scoring; "
            f"records: {[r.message for r in caplog.records]}"
        )
        msg = reject_msgs[0]
        assert "[ETH/USDT]" in msg
        assert "max=25" in msg

    def test_bos_past_bos_recency_window_is_rejected(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """BOS more than recency_bars/2 bars old must not trigger.

        Pre-Task-5: BOS uses the global recency_bars=40 → idx=25 in a
        50-bar df is fresh enough → reject log appears.
        Post-Task-5: BOS uses 40/2=20 bar window → idx=25 is stale → no
        reject log emitted (filtered at trigger gate, before scoring).
        """
        stale_bos = SimpleNamespace(
            direction="BULL", kind="BOS", idx=25, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(stale_bos)
        df = pd.DataFrame({"close": [100.0] * 50})

        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            sigs = generate_signals(
                engine, df, df, df,
                min_confluence=70, min_rr=1.5, fib_ext=1.618,
                recency_bars=40,
                symbol="ETH/USDT",
            )

        assert sigs == []
        reject_msgs = [
            rec.message for rec in caplog.records
            if "0 signals" in rec.message and "Rejects" in rec.message
        ]
        assert reject_msgs == [], (
            "Stale BOS slipped through; expected trigger-gate rejection. "
            f"records: {[r.message for r in caplog.records]}"
        )

    def test_choch_at_full_recency_still_triggers(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CHoCH (rare event) keeps the full recency_bars window.

        Guards against accidentally tightening CHoCH along with BOS in
        Task 5. idx=12 in a 50-bar df with recency_bars=40 sits at the
        edge of the CHoCH window (last_bar_idx-recency = 9), still passes.
        """
        old_choch = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=12, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(old_choch)
        df = pd.DataFrame({"close": [100.0] * 50})

        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            generate_signals(
                engine, df, df, df,
                min_confluence=70, min_rr=1.5, fib_ext=1.618,
                recency_bars=40,
                symbol="ETH/USDT",
            )

        reject_msgs = [
            rec.message for rec in caplog.records
            if "0 signals" in rec.message and "Rejects" in rec.message
        ]
        assert reject_msgs, "CHoCH at full recency window was wrongly filtered"

    def test_bos_against_htf_bias_is_rejected(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """BEAR BOS under BULL HTF bias must not produce signals.

        Existing direction filter guards this; the test prevents accidental
        removal during future refactors.
        """
        counter_bos = SimpleNamespace(
            direction="BEAR", kind="BOS", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(counter_bos)
        df = pd.DataFrame({"close": [100.0] * 50})

        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            sigs = generate_signals(
                engine, df, df, df,
                min_confluence=70, min_rr=1.5, fib_ext=1.618,
                recency_bars=40,
                symbol="ETH/USDT",
            )

        assert sigs == []
        reject_msgs = [
            rec.message for rec in caplog.records
            if "0 signals" in rec.message and "Rejects" in rec.message
        ]
        assert reject_msgs == [], "Counter-direction BOS leaked through"

    def test_reject_log_uses_per_symbol_override_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Same setup but XRP override 85 — log must reflect effective threshold.
        choch_break = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0
        )
        engine = self._make_mock_engine(choch_break)
        df = pd.DataFrame({"close": [100.0] * 50})

        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            generate_signals(
                engine, df, df, df,
                min_confluence=70, min_rr=1.5, fib_ext=1.618,
                recency_bars=40,
                symbol="XRP/USDT",
                symbol_confluence_overrides={"XRP/USDT": 85},
            )

        reject_msgs = [
            rec.message for rec in caplog.records
            if "0 signals" in rec.message and "Rejects" in rec.message
        ]
        assert reject_msgs
        msg = reject_msgs[0]
        assert "[XRP/USDT]" in msg
        assert "conf<85" in msg  # effective threshold, not the global 70


class TestDiscoveryRRClamp:
    """Price-discovery TP1 must clamp to min_rr so it survives the R:R gate.

    Pre-fix: discovery sets tp1 = price ± risk×1.272 → rr1 = 1.27, which the
    min_rr gate (>=1.5) rejects 100% of the time → 0 signals (confirmed live:
    6h of 'max seen: 1.27' rejects across the symbol universe).
    Post-fix: tp1 = price ± risk×max(1.272, min_rr) → rr1 == min_rr → emits.
    """

    def _make_engine(self, break_obj, trend: str = "BULL") -> MagicMock:
        e_range = SimpleNamespace(
            discount=False, premium=False, dev_bull=False, dev_bear=False,
            lo=99.0, hi=101.0,
        )
        engine = MagicMock()
        engine.analyze.return_value = {
            "trend": trend,
            "active_fvgs": [],
            "active_obs": [],
            "swing_highs": [],
            "swing_lows": [],
            "range": e_range,
        }
        engine.swings.return_value = ([], [])
        engine.structure.side_effect = [[], [break_obj]]
        engine.order_blocks.return_value = []
        engine.sfps.return_value = []
        engine.range_info.return_value = e_range
        engine.ote.return_value = None
        return engine

    def _df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "high": [100.5] * 50,
            "low": [99.0] * 50,
            "close": [100.0] * 50,
        })

    def test_long_discovery_emits_at_min_rr(self) -> None:
        choch = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45,
            ts="2026-06-05T00:00", price=100.0,
        )
        engine = self._make_engine(choch, trend="BULL")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.5, fib_ext=1.618,
            recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1, f"discovery LONG dropped; got {sigs}"
        sig = sigs[0]
        assert sig.direction == "LONG"
        assert sig.rr1 == 1.5            # clamped to min_rr, not 1.27
        assert sig.tp1 > sig.entry       # correct side
        assert sig.tp2 > sig.tp1         # TP2 beyond TP1

    def test_short_discovery_emits_at_min_rr(self) -> None:
        choch = SimpleNamespace(
            direction="BEAR", kind="CHoCH", idx=45,
            ts="2026-06-05T00:00", price=100.0,
        )
        engine = self._make_engine(choch, trend="BEAR")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.5, fib_ext=1.618,
            recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1, f"discovery SHORT dropped; got {sigs}"
        sig = sigs[0]
        assert sig.direction == "SHORT"
        assert sig.rr1 == 1.5
        assert sig.tp1 < sig.entry
        assert sig.tp2 < sig.tp1

    def test_min_rr_below_fib_keeps_1272(self) -> None:
        """If min_rr < 1.272, max() preserves the 1.272 fib intent."""
        choch = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45,
            ts="2026-06-05T00:00", price=100.0,
        )
        engine = self._make_engine(choch, trend="BULL")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.2, fib_ext=1.618,
            recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1
        assert sigs[0].rr1 == 1.27       # 1.272 preserved (max(1.272, 1.2))


class TestStructuralSLBuffer:
    """Structural SL must subtract the ATR buffer from the chosen swing, not sit
    exactly on it (bug-hunt #4).

    Pre-fix: sl = sl_c[-1].price (raw swing, no buffer) whenever a prior swing
    exists, because the buffer was only applied to the local_lo/local_hi fallback
    and the clamp direction discarded it → stop sits exactly on structure (stop-hunt
    target). Fix: subtract the buffer from the swing too.

    Deterministic buffer: with high=100.5/low=99.0/close=100.0 constant, ATR(14)=1.5
    and buffer = 0.5*ATR = 0.75.
    """

    def _make_engine(self, break_obj, swing_lows=None, swing_highs=None, trend="BULL"):
        e_range = SimpleNamespace(
            discount=False, premium=False, dev_bull=False, dev_bear=False,
            lo=99.0, hi=101.0,
        )
        engine = MagicMock()
        engine.analyze.return_value = {
            "trend": trend, "active_fvgs": [], "active_obs": [],
            "swing_highs": [], "swing_lows": [], "range": e_range,
        }
        engine.swings.return_value = (swing_highs or [], swing_lows or [])
        engine.structure.side_effect = [[], [break_obj]]
        engine.order_blocks.return_value = []
        engine.sfps.return_value = []
        engine.range_info.return_value = e_range
        engine.ote.return_value = None
        return engine

    def _df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "high": [100.5] * 50, "low": [99.0] * 50, "close": [100.0] * 50,
        })

    def test_long_sl_subtracts_buffer_from_swing(self) -> None:
        choch = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45, ts="2026-06-05T00:00", price=100.0,
        )
        swing = SimpleNamespace(idx=40, price=99.5)  # recent swing low in the 20-bar window
        engine = self._make_engine(choch, swing_lows=[swing], trend="BULL")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.5, fib_ext=1.618, recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.direction == "LONG"
        assert sig.sl < swing.price                  # buffer applied BELOW structure
        assert sig.sl == pytest.approx(98.75, abs=1e-6)  # 99.5 - 0.75

    def test_short_sl_adds_buffer_to_swing(self) -> None:
        choch = SimpleNamespace(
            direction="BEAR", kind="CHoCH", idx=45, ts="2026-06-05T00:00", price=100.0,
        )
        swing = SimpleNamespace(idx=40, price=100.3)  # recent swing high in the window
        engine = self._make_engine(choch, swing_highs=[swing], trend="BEAR")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.5, fib_ext=1.618, recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.direction == "SHORT"
        assert sig.sl > swing.price                  # buffer applied ABOVE structure
        assert sig.sl == pytest.approx(101.05, abs=1e-6)  # 100.3 + 0.75


class TestHtfUndefEntryRangeFallback:
    """D2 golden: when HTF (4h) bias is UNDEF and the 40-bar slope is neutral
    (|Δ| ≤ 2%), the pipeline derives HTF bias from the Entry-TF (15m) range
    discount/premium instead of skipping (signals.py:318-322). Pins the
    documented (CLAUDE.md) fallback so a refactor can't silently drop/invert it."""

    def _undef_engine(self, e_range, break_obj=None):
        engine = MagicMock()
        engine.analyze.return_value = {
            "trend": "UNDEF", "active_fvgs": [], "active_obs": [],
            "swing_highs": [], "swing_lows": [], "range": e_range,
        }
        engine.swings.return_value = ([], [])
        engine.structure.side_effect = [[], [break_obj] if break_obj else []]
        engine.order_blocks.return_value = []
        engine.sfps.return_value = []
        engine.range_info.return_value = e_range
        engine.ote.return_value = None
        return engine

    def _flat_df(self):
        # >=40 bars, neutral 40-bar slope (change == 0%).
        return pd.DataFrame({"high": [100.5] * 45, "low": [99.0] * 45, "close": [100.0] * 45})

    def test_neutral_slope_discount_derives_bull(self, caplog):
        e_range = SimpleNamespace(discount=True, premium=False, dev_bull=False,
                                  dev_bear=False, lo=99.0, hi=101.0)
        brk = SimpleNamespace(direction="BULL", kind="CHoCH", idx=44,
                              ts="2026-06-20T00:00", price=100.0)
        engine = self._undef_engine(e_range, brk)
        df = self._flat_df()
        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            generate_signals(engine, df, df, df, min_confluence=20, min_rr=1.5,
                             fib_ext=1.618, recency_bars=40, symbol="ETH/USDT")
        assert any("HTF flat but Range active" in r.message and "(BULL)" in r.message
                   for r in caplog.records), \
            f"expected discount→BULL fallback log; got {[r.message for r in caplog.records]}"
        assert not any("no active range" in r.message for r in caplog.records)

    def test_neutral_slope_premium_derives_bear(self, caplog):
        e_range = SimpleNamespace(discount=False, premium=True, dev_bull=False,
                                  dev_bear=False, lo=99.0, hi=101.0)
        brk = SimpleNamespace(direction="BEAR", kind="CHoCH", idx=44,
                              ts="2026-06-20T00:00", price=100.0)
        engine = self._undef_engine(e_range, brk)
        df = self._flat_df()
        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            generate_signals(engine, df, df, df, min_confluence=20, min_rr=1.5,
                             fib_ext=1.618, recency_bars=40, symbol="ETH/USDT")
        assert any("HTF flat but Range active" in r.message and "(BEAR)" in r.message
                   for r in caplog.records)

    def test_neutral_slope_no_range_skips(self, caplog):
        e_range = SimpleNamespace(discount=False, premium=False, dev_bull=False,
                                  dev_bear=False, lo=99.0, hi=101.0)
        engine = self._undef_engine(e_range)
        df = self._flat_df()
        with caplog.at_level(logging.INFO, logger="efloud.signals"):
            sigs = generate_signals(engine, df, df, df, min_confluence=20, min_rr=1.5,
                                    fib_ext=1.618, recency_bars=40, symbol="ETH/USDT")
        assert sigs == []
        assert any("no active range" in r.message and "skipping" in r.message
                   for r in caplog.records)
