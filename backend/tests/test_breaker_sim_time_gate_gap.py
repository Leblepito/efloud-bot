"""Backtest breaker sim-time pins (2026-08-12 audit; defect 1 fixed 2026-11-07).

LIVE IS UNAFFECTED: live calls check(now=None) and record_trade(timestamp=None),
so the wall clock is used exactly as before; these gaps were backtest-only.

Defect 1 — FIXED 2026-11-07: BreakerStatus.can_trade judged a TRIPPED pause
against the wall clock, which is always past a sim resume_at, so every
daily/consecutive TRIP was ignored in backtest. check(now=sim) now stamps the
status `as_of`; can_trade uses it (None in live = wall clock).

Defect 2 — breaker-level default kept: record_trade() without a timestamp
still stamps the wall clock, because live needs that. The orchestrator now
passes the cycle's sim-time (tests/backtest/test_breaker_sim_time.py), so the
backtest daily window is per sim-day. The strict xfail below stays as a
tripwire if the breaker default ever changes.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from engine.safety.breaker import CircuitBreaker, BreakerState


def test_tripped_breaker_blocks_in_sim_time():
    # Defect 1 FIXED 2026-11-07: check(now=sim) stamps the status `as_of`, so
    # can_trade judges the pause at sim-time (live now=None keeps wall clock).
    """Sim-time'da TRIP edilen breaker, cooldown dolmadan sim-now ile
    can_trade=False dönmeli (pre-fix: duvar-saati resume'u geçtiği için True idi)."""
    sim_now = datetime(2020, 1, 1, 12, 0, 0)  # geçmiş → duvar-saati bunu çoktan geçti
    br = CircuitBreaker(daily_loss_pct_limit=3.0, starting_balance=1000.0)

    # Sim gece-yarısından sonra günü -%5 zarara sok (limit -%3)
    br.record_trade(-50.0, timestamp=sim_now)
    status = br.check(now=sim_now)
    assert status.state == BreakerState.TRIPPED

    # 5 dk sonra hâlâ cooldown'da (resume = ertesi sim gece-yarısı)
    later = sim_now + timedelta(minutes=5)
    status2 = br.check(now=later)
    # DOĞRU davranış: sim-time'da hâlâ TRIPPED, trade bloklanmalı.
    assert status2.can_trade is False


@pytest.mark.xfail(
    strict=True,
    reason="Breaker-level default stays wall clock (live needs it). The orchestrator "
           "now passes sim-time (2026-11-07), pinned in tests/backtest/test_breaker_sim_time.py.",
)
def test_daily_window_uses_trade_sim_timestamp():
    """record_trade sim-timestamp taşımazsa günlük pencere yanlış çalışır:
    dünkü bir zarar bugünkü günlük PnL'e sızmamalı."""
    day1 = datetime(2020, 1, 1, 12, 0, 0)
    day2 = datetime(2020, 1, 2, 12, 0, 0)
    br = CircuitBreaker(daily_loss_pct_limit=3.0, starting_balance=1000.0)

    # Dün -%2.5 zarar (timestamp'siz → breaker duvar-saati damgalar = BUGÜN)
    br.record_trade(-25.0)  # orchestrator:1304 ile aynı: timestamp yok
    # Bugün check: dünkü zarar bugünün penceresine SIZMAMALI
    status = br.check(now=day2)
    daily_pnl = status.metrics.get("daily_pnl")
    # DOĞRU: gün2 penceresi gün1 trade'ini görmez → daily_pnl ~ 0
    assert daily_pnl == 0 or daily_pnl is None
