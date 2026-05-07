"""Daily report rendering — render_email() composes subject + body."""
from __future__ import annotations

from datetime import date, datetime, timezone

from ops.daily_report.render import render_email


def _summary(**overrides) -> dict:
    """Builds a summary dict with sensible defaults; override per test."""
    base = {
        "trade_count": 4,
        "wins": 3,
        "losses": 1,
        "win_rate_pct": 75.0,
        "best_trade": {"symbol": "BTC/USDT", "pnl_usdt": 15.0, "direction": "LONG", "reason": "TP2"},
        "worst_trade": {"symbol": "ETH/USDT", "pnl_usdt": -8.0, "direction": "SHORT", "reason": "SL"},
        "equity_start": 2000.0,
        "equity_end": 2050.0,
        "equity_delta_usdt": 50.0,
        "equity_delta_pct": 2.5,
    }
    base.update(overrides)
    return base


def _trades(n: int = 2) -> list[dict]:
    return [
        {
            "symbol": "BTC/USDT", "direction": "LONG",
            "entry": 50000.0, "exit": 51000.0, "pnl_usdt": 10.0, "reason": "TP2",
            "closed_at": datetime(2026, 5, 7, 14, 0, tzinfo=timezone.utc),
        },
        {
            "symbol": "ETH/USDT", "direction": "SHORT",
            "entry": 3000.0, "exit": 3050.0, "pnl_usdt": -5.0, "reason": "SL",
            "closed_at": datetime(2026, 5, 7, 16, 0, tzinfo=timezone.utc),
        },
    ][:n]


def test_subject_includes_date_and_equity():
    summary = _summary(equity_end=2050.0, equity_delta_pct=2.5)
    subject, body = render_email(
        summary=summary,
        trades=_trades(2),
        heartbeat_stale=False,
        heartbeat_age_sec=120,
        report_date=date(2026, 5, 7),
    )
    assert "2026-05-07" in subject
    assert "2050" in subject
    assert "+2.5" in subject or "2.5" in subject


def test_body_contains_trade_list():
    summary = _summary()
    subject, body = render_email(
        summary=summary,
        trades=_trades(2),
        heartbeat_stale=False,
        heartbeat_age_sec=120,
        report_date=date(2026, 5, 7),
    )
    assert "BTC/USDT" in body
    assert "ETH/USDT" in body
    assert "75" in body
    assert "50.0" in body or "+50" in body


def test_alerter_down_prefix_when_stale():
    summary = _summary()
    subject, body = render_email(
        summary=summary,
        trades=_trades(2),
        heartbeat_stale=True,
        heartbeat_age_sec=10800,
        report_date=date(2026, 5, 7),
    )
    assert subject.startswith("ALERTER DOWN") or "ALERTER DOWN" in subject
    assert "alerter" in body.lower()
    assert "10800" in body or "3h" in body.lower() or "stale" in body.lower()


def test_empty_trades_renders_no_trades_today():
    summary = _summary(
        trade_count=0, wins=0, losses=0, win_rate_pct=None,
        best_trade=None, worst_trade=None,
    )
    subject, body = render_email(
        summary=summary,
        trades=[],
        heartbeat_stale=False,
        heartbeat_age_sec=120,
        report_date=date(2026, 5, 7),
    )
    assert "no trades" in body.lower() or "0 trades" in body.lower()
