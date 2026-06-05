"""Kill-switch must PERSIST the breaker HALT immediately (bug-hunt #3, HIGH).

`_halt()` only mutates in-memory breaker status. Without an immediate persist, a
restart inside the ~30s cycle window (autoheal/redeploy/crash) reloads the stale
pre-kill-switch breaker from disk (typically OPEN) and the bot resumes trading —
defeating the operator's emergency stop. Mirror the /breaker/reset hardening:
write disk (authoritative on restore) + DB mirror.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.api as api


@pytest.mark.asyncio
async def test_kill_switch_persists_breaker_halt(monkeypatch):
    orch = MagicMock()
    orch.breaker.to_dict.return_value = {"state": "HALTED"}
    runner_mock = MagicMock()
    runner_mock.order_mgr.kill_switch.return_value = ["BTC/USDT", "ETH/USDT"]
    runner_mock.orch = orch
    monkeypatch.setattr(api, "runner", runner_mock)

    db_mock = MagicMock()
    db_mock.upsert_breaker_state = AsyncMock()
    db_mock.log_audit = AsyncMock()
    monkeypatch.setattr(api, "db", db_mock)

    res = await api.kill_switch()

    assert res["ok"] is True
    assert res["closed"] == ["BTC/USDT", "ETH/USDT"]
    assert res["persisted"] is True  # operator-facing confirmation
    # The HALT was tripped...
    orch.breaker._halt.assert_called_once()
    # ...AND persisted to disk (authoritative on restart restore — the fix)...
    orch._persist_state.assert_called_once()
    # ...AND mirrored to the DB (matches /breaker/reset hardening — the fix).
    db_mock.upsert_breaker_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_kill_switch_returns_ok_even_if_persist_fails(monkeypatch):
    """Persistence failure must not break the emergency stop (positions already closed)."""
    orch = MagicMock()
    orch._persist_state.side_effect = RuntimeError("disk full")
    runner_mock = MagicMock()
    runner_mock.order_mgr.kill_switch.return_value = []
    runner_mock.orch = orch
    monkeypatch.setattr(api, "runner", runner_mock)

    db_mock = MagicMock()
    db_mock.upsert_breaker_state = AsyncMock()
    db_mock.log_audit = AsyncMock()
    monkeypatch.setattr(api, "db", db_mock)

    res = await api.kill_switch()
    assert res["ok"] is True
    # Emergency stop still succeeds, but the operator is told persistence failed
    # (in-memory HALT only — do not restart before investigating disk).
    assert res["persisted"] is False
    orch.breaker._halt.assert_called_once()
