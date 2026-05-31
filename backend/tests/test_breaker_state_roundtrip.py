"""Circuit breaker halt-state survives a restart (persistence round-trip).

Bug this locks down (pre-fix): SafeOrchestrator._restore_state only reloaded
current_balance / peak_balance / consecutive_losses from the persisted breaker
dict. The HALTED/TRIPPED *state* itself, its reason, and the resume_at /
tripped_at timestamps were dropped — so after a container restart a HALTED
breaker came back OPEN and the bot would resume trading without operator
acknowledgment. See incident 2026-05-14 (breaker HALTED → autoheal restart loop
→ bare positions on Binance).

The fix gives CircuitBreaker a full-fidelity to_dict()/restore_from_dict()
round-trip, and SafeOrchestrator uses restore_from_dict() on startup.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from engine.safety.breaker import CircuitBreaker, BreakerState


# ──────────────────────────────────────────────────────────────────
# CircuitBreaker.to_dict / restore_from_dict — pure round-trip
# ──────────────────────────────────────────────────────────────────

def _halt(breaker: CircuitBreaker, reason: str = "test halt") -> None:
    breaker._halt(reason)


def test_to_dict_includes_full_state_timestamps():
    """to_dict must emit tripped_at and resume_at so a TRIPPED/HALTED breaker
    can be faithfully reconstructed (old to_dict dropped them)."""
    breaker = CircuitBreaker(starting_balance=2000.0)
    resume = datetime.utcnow() + timedelta(minutes=120)
    breaker._trip("3 consecutive losses", resume_at=resume)

    d = breaker.to_dict()

    assert d["state"] == "TRIPPED"
    assert d["reason"] == "3 consecutive losses"
    assert d["tripped_at"] is not None
    assert d["resume_at"] is not None
    # ISO strings round-trip through json without custom serializers
    assert datetime.fromisoformat(d["resume_at"]) == resume


def test_restore_from_dict_rebuilds_halted_state():
    """A HALTED breaker dict restores to a HALTED, non-tradeable breaker."""
    src = CircuitBreaker(starting_balance=2000.0)
    _halt(src, "Weekly drawdown 31.00% reached limit 30%")
    src.current_balance = 1380.0
    src.peak_balance = 2000.0
    d = src.to_dict()

    restored = CircuitBreaker(starting_balance=10000.0)  # different defaults
    restored.restore_from_dict(d)

    assert restored.status.state == BreakerState.HALTED
    assert restored.status.reason == "Weekly drawdown 31.00% reached limit 30%"
    assert restored.status.can_trade is False
    assert restored.current_balance == 1380.0
    assert restored.peak_balance == 2000.0


def test_restore_from_dict_halted_stays_halted_after_check():
    """Restored HALTED must remain HALTED on the next check() — manual reset
    is the only exit. This is the core safety property: restart must not
    silently un-halt."""
    src = CircuitBreaker(starting_balance=2000.0)
    _halt(src, "emergency")
    d = src.to_dict()

    restored = CircuitBreaker(starting_balance=2000.0)
    restored.restore_from_dict(d)
    status = restored.check()

    assert status.state == BreakerState.HALTED
    assert status.can_trade is False


def test_restore_from_dict_tripped_with_future_resume_blocks_trading():
    """A TRIPPED breaker whose resume_at is still in the future restores as
    non-tradeable."""
    src = CircuitBreaker(starting_balance=2000.0)
    src._trip("daily loss", resume_at=datetime.utcnow() + timedelta(hours=6))
    d = src.to_dict()

    restored = CircuitBreaker(starting_balance=2000.0)
    restored.restore_from_dict(d)

    assert restored.status.state == BreakerState.TRIPPED
    assert restored.status.can_trade is False


def test_restore_from_dict_tripped_with_past_resume_allows_resume():
    """If resume_at has already passed, the restored TRIPPED breaker can trade
    again (cooldown elapsed during downtime)."""
    src = CircuitBreaker(starting_balance=2000.0)
    src._trip("daily loss", resume_at=datetime.utcnow() - timedelta(minutes=1))
    d = src.to_dict()

    restored = CircuitBreaker(starting_balance=2000.0)
    restored.restore_from_dict(d)

    assert restored.status.state == BreakerState.TRIPPED
    assert restored.status.can_trade is True


def test_restore_from_dict_preserves_consecutive_losses_and_balance():
    """The legacy fields (balance/peak/consec) must still round-trip."""
    src = CircuitBreaker(starting_balance=2000.0)
    src.consecutive_losses = 2
    src.current_balance = 1950.0
    src.peak_balance = 2100.0
    d = src.to_dict()

    restored = CircuitBreaker(starting_balance=2000.0)
    restored.restore_from_dict(d)

    assert restored.consecutive_losses == 2
    assert restored.current_balance == 1950.0
    assert restored.peak_balance == 2100.0


def test_restore_from_db_row_applies_halt():
    """DB-mirror fallback: a halted breaker_state row reconstructs a HALTED
    breaker (used on a fresh box where the file StateStore was lost)."""
    row = {
        "halted": True,
        "halted_reason": "Weekly drawdown 31% reached limit 30%",
        "halted_at": datetime(2026, 5, 14, 10, 0, 0),
        "reset_at": None,
    }
    breaker = CircuitBreaker(starting_balance=2000.0)
    breaker.restore_from_db_row(row)

    assert breaker.status.state == BreakerState.HALTED
    assert breaker.status.can_trade is False
    assert "Weekly drawdown" in breaker.status.reason


def test_restore_from_db_row_open_is_noop():
    row = {"halted": False, "halted_reason": None, "halted_at": None, "reset_at": None}
    breaker = CircuitBreaker(starting_balance=2000.0)
    breaker.restore_from_db_row(row)
    assert breaker.status.state == BreakerState.OPEN


def test_restore_from_db_row_none_is_noop():
    breaker = CircuitBreaker(starting_balance=2000.0)
    breaker.restore_from_db_row(None)
    assert breaker.status.state == BreakerState.OPEN


def test_restore_from_dict_open_state_can_trade():
    src = CircuitBreaker(starting_balance=2000.0)
    d = src.to_dict()

    restored = CircuitBreaker(starting_balance=2000.0)
    restored.restore_from_dict(d)

    assert restored.status.state == BreakerState.OPEN
    assert restored.status.can_trade is True


def test_restore_from_dict_legacy_dict_without_state_keys():
    """Backward-compat: a pre-fix breaker.json has no state/tripped_at/resume_at.
    restore_from_dict must not crash and must default to OPEN while still
    restoring the balance/consec fields that the old format did carry."""
    legacy = {
        "consecutive_losses": 1,
        "current_balance": 1900.0,
        "peak_balance": 2000.0,
    }
    restored = CircuitBreaker(starting_balance=2000.0)
    restored.restore_from_dict(legacy)

    assert restored.status.state == BreakerState.OPEN
    assert restored.consecutive_losses == 1
    assert restored.current_balance == 1900.0


# ──────────────────────────────────────────────────────────────────
# SafeOrchestrator startup restore — HALTED survives a restart
# ──────────────────────────────────────────────────────────────────

_MINIMAL_CFG = {
    "structure": {"swing_lookback": 5, "ob_sequential": 5,
                  "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
    "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
    "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
             "risk_per_trade_pct": 0.75, "recency_bars": 40,
             "position_size_calculation": "legacy",
             "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5},
    "safety": {"daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
               "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
               "starting_balance": 10000, "max_position_notional_pct": 20,
               "max_total_exposure": 5.0, "max_holding_hours": 48,
               "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
               "adx_trend_threshold": 25, "adx_range_threshold": 20,
               "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
               "sl_atr_buffer": 0.5},
    "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
    "operation": {"check_interval_sec": 30, "log_level": "INFO"},
}


def _write_breaker_state(state_dir: Path, breaker_data: dict) -> None:
    (state_dir / "breaker.json").write_text(
        json.dumps({"saved_at": "2026-05-31T00:00:00", "data": breaker_data}),
        encoding="utf-8",
    )


def test_orchestrator_restores_halted_breaker_on_startup(tmp_path):
    """The whole point: write a HALTED breaker.json, construct a fresh
    orchestrator, and verify the breaker comes back HALTED (not OPEN)."""
    from engine.safe_orchestrator import SafeOrchestrator

    src = CircuitBreaker(starting_balance=10000.0)
    src._halt("Weekly drawdown 30.58% reached limit 30%")
    src.current_balance = 6900.0
    src.peak_balance = 10000.0
    _write_breaker_state(tmp_path, src.to_dict())

    orc = SafeOrchestrator(_MINIMAL_CFG, state_dir=str(tmp_path), persist=False)

    assert orc.breaker.status.state == BreakerState.HALTED
    assert orc.breaker.status.can_trade is False
    assert "Weekly drawdown" in orc.breaker.status.reason


def test_orchestrator_restores_open_breaker_normally(tmp_path):
    """Regression: an OPEN breaker.json restores OPEN and tradeable."""
    from engine.safe_orchestrator import SafeOrchestrator

    src = CircuitBreaker(starting_balance=10000.0)
    src.consecutive_losses = 1
    src.current_balance = 9800.0
    _write_breaker_state(tmp_path, src.to_dict())

    orc = SafeOrchestrator(_MINIMAL_CFG, state_dir=str(tmp_path), persist=False)

    assert orc.breaker.status.state == BreakerState.OPEN
    assert orc.breaker.consecutive_losses == 1
    assert orc.breaker.current_balance == 9800.0


# ──────────────────────────────────────────────────────────────────
# DB mirror write sink — _persist_state forwards breaker state
# ──────────────────────────────────────────────────────────────────

def test_persist_state_invokes_breaker_sink(tmp_path):
    """When a breaker_state_sink is wired, _persist_state forwards the
    full breaker dict so the DB mirror can UPSERT it."""
    from engine.safe_orchestrator import SafeOrchestrator

    captured: list[dict] = []
    orc = SafeOrchestrator(_MINIMAL_CFG, state_dir=str(tmp_path), persist=True,
                           breaker_state_sink=captured.append)
    orc._persist_state()

    assert len(captured) == 1
    assert captured[0]["state"] == "OPEN"
    assert "current_balance" in captured[0]


def test_persist_state_sink_error_is_swallowed(tmp_path):
    """A failing sink (DB hiccup) must never break disk persistence / the cycle."""
    from engine.safe_orchestrator import SafeOrchestrator

    def boom(_d):
        raise RuntimeError("sink fail")

    orc = SafeOrchestrator(_MINIMAL_CFG, state_dir=str(tmp_path), persist=True,
                           breaker_state_sink=boom)
    orc._persist_state()  # must not raise
    # disk write still happened
    assert (tmp_path / "breaker.json").exists()


def test_persist_state_without_sink_is_unchanged(tmp_path):
    """Default (no sink) — existing behavior, no error."""
    from engine.safe_orchestrator import SafeOrchestrator

    orc = SafeOrchestrator(_MINIMAL_CFG, state_dir=str(tmp_path), persist=True)
    orc._persist_state()
    assert (tmp_path / "breaker.json").exists()
