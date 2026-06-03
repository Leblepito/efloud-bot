"""C8: the Gemini structure-validation must be ADVISORY, never a hard gate.

validate_signal_with_gemini was called inside generate_signals and a
low-confidence / invalid verdict did `continue` — dropping the signal. That makes
an external LLM a blocking trade gate inside signal generation, violating the
advisory-only contract (gating lives in safe_orchestrator behind
agent_team.gating=false). The verdict must annotate the signal, not suppress it.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from engine import signals as signals_mod
from engine.signals import generate_signals


def _mock_engine(break_obj):
    e_range = SimpleNamespace(
        discount=False, premium=False, dev_bull=False, dev_bear=False, lo=99.0, hi=101.0,
    )
    engine = MagicMock()
    engine.analyze.return_value = {
        "trend": "BULL", "active_fvgs": [], "active_obs": [],
        "swing_highs": [], "swing_lows": [], "range": e_range,
    }
    engine.swings.return_value = ([], [])
    engine.structure.side_effect = [[], [break_obj]]
    engine.order_blocks.return_value = []
    engine.sfps.return_value = []
    engine.range_info.return_value = e_range
    engine.ote.return_value = None
    return engine


def test_gemini_reject_does_not_drop_signal():
    choch = SimpleNamespace(direction="BULL", kind="CHoCH", idx=45,
                            ts="2026-05-08T00:00", price=100.0)
    engine = _mock_engine(choch)
    df = pd.DataFrame({
        "open": [100.0] * 50, "high": [102.0] * 50, "low": [98.0] * 50,
        "close": [100.0] * 50, "volume": [1.0] * 50,
    })

    with patch.object(
        signals_mod, "validate_signal_with_gemini",
        return_value={"valid": False, "confidence": 0.1, "reasoning": "bad structure"},
    ):
        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=20, min_rr=1.0, fib_ext=1.618,
            recency_bars=40, symbol="ETH/USDT",
        )

    assert len(sigs) == 1, "C8: a Gemini reject must NOT drop the signal (advisory only)"
    meta = sigs[0].meta.get("gemini_structure_validation")
    assert meta is not None, "the verdict must be annotated on the signal"
    assert meta["valid"] is False
    assert meta.get("advisory_only") is True
