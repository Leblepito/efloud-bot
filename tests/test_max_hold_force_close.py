"""M5 (2026-06-20 audit): max_holding_hours force-close path — VERIFY.

The audit could only find the open-guard reading `max_holding_hours` and
flagged the force-close path as "unconfirmed" (may not exist -> a position
held indefinitely). Reading `engine/safe_orchestrator.py` shows the path DOES
exist (STEP 5 of `run_cycle` calls `_force_close_max_hold`, which closes the
EXCHANGE leg first via `order_manager._fallback_close(..., "MAX_HOLD")` then
the logical position) — but there was no test locking this behavior in. This
test exercises it end-to-end through `run_cycle` so a future refactor that
silently drops the check fails loudly instead of reintroducing the
hold-indefinitely gap.
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest
import yaml

from engine import SafeOrchestrator


def _flat_df(n=300):
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    return pd.DataFrame(
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1.0}, index=idx
    )


def _make_orch(tmp_path, max_holding_hours=48):
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["operation"]["dry_run"] = True
    cfg["safety"]["max_holding_hours"] = max_holding_hours
    return SafeOrchestrator(cfg, state_dir=str(tmp_path), freshness_check=False, persist=False)


def test_position_past_max_hold_is_force_closed_exchange_leg_first(tmp_path):
    orch = _make_orch(tmp_path, max_holding_hours=1)
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0, sl=95.0, tp1=105.0, tp2=110.0,
    )
    # Backdate well past the 1-hour limit.
    from datetime import datetime, timedelta, timezone
    pos.opened_at = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)).isoformat()

    exchange_pos = MagicMock(symbol="BTC/USDT", direction="LONG")
    om = MagicMock()
    om.positions = [exchange_pos]
    # E-3 fix (2026-07-17): force-close artik _positions_snapshot() okur
    # (cross-thread guvenli); mock'u da ona gore besle.
    om._positions_snapshot.return_value = [exchange_pos]
    orch.order_manager = om

    df = _flat_df()
    orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000.0)

    # Exchange leg closed first (mirrors _handle_reverse ordering).
    om._fallback_close.assert_called_once()
    call_args = om._fallback_close.call_args
    assert call_args[0][0] is exchange_pos
    assert call_args[0][2] == "MAX_HOLD"
    # Logical position no longer open.
    assert pos not in orch.lifecycle.open_positions()
    assert pos.is_open is False


def test_position_under_max_hold_is_left_open(tmp_path):
    orch = _make_orch(tmp_path, max_holding_hours=48)
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0, sl=95.0, tp1=105.0, tp2=110.0,
    )
    # Well within the 48-hour limit -> must NOT be force-closed.
    om = MagicMock()
    om.positions = []
    om._positions_snapshot.return_value = []
    orch.order_manager = om

    df = _flat_df()
    orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000.0)

    om._fallback_close.assert_not_called()
    assert pos in orch.lifecycle.open_positions()
    assert pos.is_open is True


def test_exchange_close_failure_keeps_logical_position_tracked(tmp_path):
    """If the exchange-leg close raises, the logical position must NOT be
    dropped — losing tracking of a still-live exchange position is worse
    than a late force-close retry next cycle."""
    orch = _make_orch(tmp_path, max_holding_hours=1)
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT", direction="LONG",
        entry_price=100.0, size=1.0, sl=95.0, tp1=105.0, tp2=110.0,
    )
    from datetime import datetime, timedelta, timezone
    pos.opened_at = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)).isoformat()

    exchange_pos = MagicMock(symbol="BTC/USDT", direction="LONG")
    om = MagicMock()
    om.positions = [exchange_pos]
    om._positions_snapshot.return_value = [exchange_pos]
    om._fallback_close.side_effect = RuntimeError("exchange timeout")
    orch.order_manager = om

    df = _flat_df()
    orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000.0)

    assert pos in orch.lifecycle.open_positions()
    assert pos.is_open is True
