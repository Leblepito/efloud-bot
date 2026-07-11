"""F11-F14 — 2026-07-11 bugfix batch (backtest look-ahead, journal, sl_calc, preflight).

Spec: docs/superpowers/specs/2026-07-11-tp-entry-anchored-targeting-and-bugfix-batch-design.md Bölüm 3.
"""

import json
import math
from types import SimpleNamespace

import pandas as pd
import pytest


class TestF11ClosedHigherTfBars:
    """Backtest HTF/MTF/1d dilimleri forming bar'ı final OHLC ile içermemeli."""

    def _htf_df(self):
        idx = pd.to_datetime(["2026-01-01 00:00", "2026-01-01 04:00",
                              "2026-01-01 08:00"])
        return pd.DataFrame({"open": [1, 2, 3], "high": [1, 2, 3],
                             "low": [1, 2, 3], "close": [1, 2, 3]}, index=idx)

    def test_forming_bar_excluded(self):
        from backtest.engine import _closed_higher_tf_bars
        df = self._htf_df()
        # Karar anı 07:45 → 04:00 barı 08:00'de kapanır (> 07:45) → dışarıda
        out = _closed_higher_tf_bars(df, 240, pd.Timestamp("2026-01-01 07:45"))
        assert len(out) == 1, f"forming 4h bar leaked into slice: {out.index.tolist()}"

    def test_exactly_closed_bar_included(self):
        from backtest.engine import _closed_higher_tf_bars
        df = self._htf_df()
        # Karar anı 08:00 → 04:00 barı tam kapandı (=) → dahil; 08:00 forming → hariç
        out = _closed_higher_tf_bars(df, 240, pd.Timestamp("2026-01-01 08:00"))
        assert len(out) == 2
        assert out.index[-1] == pd.Timestamp("2026-01-01 04:00")


class TestF12JournalRobustLoad:
    def _good_line(self, trade_id):
        return json.dumps({
            "trade_id": trade_id, "symbol": "ETH/USDT", "direction": "LONG",
            "timeframe": "15m", "entry_timestamp": "2026-07-11T00:00:00",
            "entry_price": 100.0, "sl_initial": 99.0, "tp1_initial": 103.0,
            "tp2_initial": 106.0, "position_size": 1.0, "htf_bias": "BULL",
            "intent_score_entry": 50, "intent_label_entry": "NEUTRAL",
            "confluence_score": 60,
        })

    def test_corrupt_line_does_not_truncate_rest(self, tmp_path):
        from engine.journal import TradeJournal
        p = tmp_path / "journal.jsonl"
        lines = [
            self._good_line("t1"),
            '{"corrupt": ',              # bozuk JSON
            self._good_line("t2"),       # ESKİDEN bu kayboluyordu (ve persist siliyordu)
        ]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

        j = TradeJournal(journal_path=str(p))
        ids = {s.trade_id for s in j._cache}
        assert ids == {"t1", "t2"}, f"corrupt line truncated the journal: {ids}"

    def test_unknown_legacy_field_filtered_not_fatal(self, tmp_path):
        from engine.journal import TradeJournal
        p = tmp_path / "journal.jsonl"
        legacy = json.loads(self._good_line("t3"))
        legacy["some_removed_legacy_field"] = 42
        p.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

        j = TradeJournal(journal_path=str(p))
        assert {s.trade_id for s in j._cache} == {"t3"}


class TestF13SlCalcNanAtr:
    def _zone(self):
        return SimpleNamespace(low=99.0, high=100.0)

    def test_nan_atr_rejects_setup(self):
        from engine.smc_v2.sl_calc import calc_sl
        from engine.smc_v2.exceptions import SLTooFarError
        with pytest.raises(SLTooFarError):
            calc_sl(direction="LONG", entry_price=100.0, zone=self._zone(),
                    htf_swing_anchor=98.0, atr_15m=float("nan"),
                    config=SimpleNamespace(sl_atr_buffer=0.5, min_sl_atr=0.5,
                                           max_sl_atr=5.0))

    def test_zero_atr_rejects_setup(self):
        from engine.smc_v2.sl_calc import calc_sl
        from engine.smc_v2.exceptions import SLTooFarError
        with pytest.raises(SLTooFarError):
            calc_sl(direction="SHORT", entry_price=100.0, zone=self._zone(),
                    htf_swing_anchor=102.0, atr_15m=0.0,
                    config=SimpleNamespace(sl_atr_buffer=0.5, min_sl_atr=0.5,
                                           max_sl_atr=5.0))

    def test_valid_atr_still_works(self):
        from engine.smc_v2.sl_calc import calc_sl
        sl = calc_sl(direction="LONG", entry_price=100.0, zone=self._zone(),
                     htf_swing_anchor=98.5, atr_15m=0.5,
                     config=SimpleNamespace(sl_atr_buffer=0.5, min_sl_atr=0.5,
                                            max_sl_atr=10.0))
        assert math.isfinite(sl) and sl < 100.0


class TestF14PreflightDualSide:
    def test_string_true_normalized(self):
        from preflight import _parse_dual_side
        assert _parse_dual_side("true") is True
        assert _parse_dual_side("false") is False

    def test_bool_passthrough(self):
        from preflight import _parse_dual_side
        assert _parse_dual_side(True) is True
        assert _parse_dual_side(False) is False
        assert _parse_dual_side(None) is False
