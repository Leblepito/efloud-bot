"""Regression tests for state restore across bot restarts (post-2026-05-08 stacking bug).

Bug history (2026-05-08): bot restart left local position state empty even though
Binance had open FIL+RENDER positions; PositionGuard then allowed duplicate-direction
opens, stacking SL+TP1+TP2 trios on each restart (24 stale conditional orders observed).

Two layers must persist + restore:
  1. OrderManager.positions  — exchange-side bookkeeping (order ids)
  2. lifecycle.positions     — strategy-side state (entries, tp1_hit, scenario_id)

Without both, PositionGuard's duplicate-direction check (`existing_positions`
sourced from lifecycle) silently passes, the bot reopens, and SL/TP orders stack.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from exchange import BinanceClient, OrderManager, Position as ExPosition
from engine import SafeOrchestrator
from engine.safety.position_guard import PositionGuard


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    return client


# ─────────────────────────────────────────────────────────────────────
# Layer 1: OrderManager persistence
# ─────────────────────────────────────────────────────────────────────


class TestOrderManagerPersistence:
    """OrderManager must persist self.positions and restore them on init."""

    def test_open_position_writes_state_file(self, mock_client, tmp_path):
        mgr = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1"}, {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
        ]

        mgr.open_position("FIL/USDT", "LONG", 464.5, 1.089, 1.069, 1.150, 1.161)

        state_file = tmp_path / "order_manager_positions.json"
        assert state_file.exists(), "OrderManager must persist positions to disk"

    def test_restart_restores_positions(self, mock_client, tmp_path):
        # First instance: opens position
        mgr1 = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1"}, {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
        ]
        mgr1.open_position("FIL/USDT", "LONG", 464.5, 1.089, 1.069, 1.150, 1.161)
        assert len(mgr1.positions) == 1

        # Simulate restart: new instance, same state_dir
        mgr2 = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
        assert len(mgr2.positions) == 1, \
            "Restart must restore previously persisted positions"
        restored = mgr2.positions[0]
        assert restored.symbol == "FIL/USDT"
        assert restored.direction == "LONG"
        assert restored.entry == 1.089
        assert restored.sl_order_id == "SL-1"
        assert restored.tp1_order_id == "TP1-1"
        assert restored.tp2_order_id == "TP2-1"
        assert restored.size == 464.5

    def test_close_via_reconcile_persists(self, mock_client, tmp_path):
        """When reconcile detects a close, the persisted state must update too."""
        mgr1 = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
        mgr1.positions = [ExPosition(
            symbol="FIL/USDT", direction="LONG", entry=1.089,
            sl=1.069, tp1=1.150, tp2=1.161, size=464.5,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )]
        mgr1._persist()  # initial save with one position

        # Reconcile: Binance reports position gone, TP2 missing → TP2 fill
        mock_client.get_open_positions.return_value = []
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"}, {"id": "TP1-1"},  # TP2-1 missing = filled
        ]
        mgr1.reconcile()
        assert len(mgr1.positions) == 0
        assert len(mgr1.closed_positions) == 1

        # New instance reads persisted (empty) state
        mgr2 = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
        assert mgr2.positions == [], "Persisted close must propagate to restart"

    def test_no_state_dir_back_compat(self, mock_client):
        """Pre-existing tests construct without state_dir — must not break."""
        mgr = OrderManager(mock_client, dry_run=False)
        assert mgr.positions == []

    def test_corrupt_state_file_is_ignored(self, mock_client, tmp_path):
        bad = tmp_path / "order_manager_positions.json"
        bad.write_text("{not valid json", encoding="utf-8")
        mgr = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
        assert mgr.positions == [], "Corrupt state must not crash; start clean"


# ─────────────────────────────────────────────────────────────────────
# Layer 2: get_open_positions exception propagation
# ─────────────────────────────────────────────────────────────────────


class TestFetchPositionsExceptionPropagation:
    """A failed fetch_positions must NOT silently look like 'no positions'.

    Old behavior: get_open_positions caught the exception and returned [],
    which reconcile then interpreted as 'all local positions closed', wiped
    them, and let the next signal re-open + restack TP/SL orders.
    """

    def test_reconcile_keeps_positions_when_fetch_fails(self, mock_client, tmp_path):
        mgr = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
        pos = ExPosition(
            symbol="FIL/USDT", direction="LONG", entry=1.089,
            sl=1.069, tp1=1.150, tp2=1.161, size=464.5,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Simulate API failure: fetch_positions raises (rate limit, network, etc.)
        mock_client.get_open_positions.side_effect = RuntimeError(
            "Binance API timeout"
        )

        closed = mgr.reconcile()

        assert closed == [], "Failed fetch must not produce phantom closes"
        assert pos in mgr.positions, "Position must be retained when API fails"


# ─────────────────────────────────────────────────────────────────────
# Layer 3: Lifecycle restore + duplicate-direction guard
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_config():
    return {
        "structure": {
            "swing_lookback": 8, "ob_sequential": 2, "body_mode": "bodies",
            "eq_threshold_pct": 0.1, "range_lookback": 50,
        },
        "fibonacci": {"ote_lower": 0.62, "ote_upper": 0.79, "ext_tp2": 1.272},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "risk": {
            "min_confluence": 70, "min_rr": 1.5, "risk_per_trade_pct": 2.0,
            "max_open_positions": 5,
        },
        "safety": {"max_position_notional_pct": 10.0, "starting_balance": 2000},
        "exchange": {"leverage": 5, "market_type": "futures", "testnet": False},
        "operation": {"dry_run": False, "watch_only": False},
    }


class TestSafeOrchestratorRestoresLifecycle:
    """SafeOrchestrator._restore_state must repopulate lifecycle.positions
    so PositionGuard's duplicate-direction check works after a restart.
    """

    def test_lifecycle_populated_from_saved_state(self, minimal_config, tmp_path):
        # First orchestrator instance: simulate an open FIL/LONG position
        orch1 = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path),
            freshness_check=False, persist=True,
        )
        orch1.lifecycle.open_position(
            "FIL/USDT", "LONG", 1.089, 464.5,
            sl=1.069, tp1=1.150, tp2=1.161,
        )
        orch1._persist_state()

        # Second instance: restart simulation, same state_dir
        orch2 = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path),
            freshness_check=False, persist=True,
        )

        assert len(orch2.lifecycle.positions) == 1, \
            "Restart must restore lifecycle positions for duplicate-direction guard"
        restored = orch2.lifecycle.positions[0]
        assert restored.symbol == "FIL/USDT"
        assert restored.direction == "LONG"
        assert restored.is_open is True

    def test_duplicate_direction_blocked_after_restart(
        self, minimal_config, tmp_path
    ):
        """End-to-end: after restart, PositionGuard rejects a duplicate FIL LONG."""
        orch1 = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path),
            freshness_check=False, persist=True,
        )
        orch1.lifecycle.open_position(
            "FIL/USDT", "LONG", 1.089, 464.5,
            sl=1.069, tp1=1.150, tp2=1.161,
        )
        orch1._persist_state()

        # Restart
        orch2 = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path),
            freshness_check=False, persist=True,
        )

        # New signal for same symbol+direction — guard must reject
        guard = orch2.pos_guard
        check = guard.can_open_position(
            balance=2000.0, entry=1.085, size=464.5,
            sl=1.065, atr=0.01, direction="LONG", symbol="FIL/USDT",
            existing_positions=orch2.lifecycle.positions,
            leverage=5,
        )
        assert check.allowed is False
        assert "FIL/USDT" in check.reason
        assert "LONG" in check.reason
