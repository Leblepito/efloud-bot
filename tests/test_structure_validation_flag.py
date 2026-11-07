"""Structure validation is OFF unless explicitly enabled (decision 2, spec 2026-11-07).

Live measurement (19 days): 23,085/23,085 calls fell back (no provider key on
that call site) — a synchronous, never-gating advisory call on the hot path.
Default OFF; `engine.structure_validation.enabled: true` turns it back on.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import yaml

import engine.signals as signals_mod
from engine.signals import generate_signals
from tests.test_gemini_advisory_not_blocking import _mock_engine


def _df():
    return pd.DataFrame({"open": [100.0] * 50, "high": [102.0] * 50, "low": [98.0] * 50,
                         "close": [100.0] * 50, "volume": [1.0] * 50})


def _choch():
    return SimpleNamespace(direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0)


def test_default_does_not_call_the_llm():
    with patch.object(signals_mod, "validate_signal_with_gemini") as val:
        sigs = generate_signals(_mock_engine(_choch()), _df(), _df(), _df(), min_confluence=20,
                                min_rr=1.0, fib_ext=1.618, recency_bars=40, symbol="ETH/USDT")
    val.assert_not_called()
    assert len(sigs) == 1 and "gemini_structure_validation" not in sigs[0].meta


def test_enabled_still_annotates():
    with patch.object(signals_mod, "validate_signal_with_gemini",
                      return_value={"valid": True, "confidence": 0.9, "reasoning": "ok"}) as val:
        sigs = generate_signals(_mock_engine(_choch()), _df(), _df(), _df(), min_confluence=20,
                                min_rr=1.0, fib_ext=1.618, recency_bars=40, symbol="ETH/USDT",
                                structure_validation=True)
    val.assert_called_once()
    assert sigs[0].meta["gemini_structure_validation"]["advisory_only"] is True


def test_live_config_keeps_it_off():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["engine"]["structure_validation"]["enabled"] is False
