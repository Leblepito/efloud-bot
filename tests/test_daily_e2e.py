"""End-to-end: aggregate + render + send_email pipeline with mocked I/O.

No real DB / SMTP. Verifies the full data flow produces a sensible email.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock


def test_full_report_cycle_with_mocked_db_and_smtp(tmp_path: Path):
    """End-to-end: stub DB → aggregate → render → mock SMTP send."""
    from ops.daily_report.aggregate import compute_summary
    from ops.daily_report.heartbeat import check_alerter_heartbeat
    from ops.daily_report.render import render_email
    from ops.daily_report.smtp_client import send_email

    trades = [
        {
            "symbol": "BTC/USDT", "direction": "LONG",
            "entry": 50000.0, "exit": 51000.0, "size": 0.001,
            "pnl_usdt": 10.0, "pnl_pct": 2.0, "reason": "TP2",
            "opened_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 7, 14, 0, tzinfo=timezone.utc),
            "confluence": 80,
        },
        {
            "symbol": "ETH/USDT", "direction": "SHORT",
            "entry": 3000.0, "exit": 3050.0, "size": 0.01,
            "pnl_usdt": -5.0, "pnl_pct": -1.67, "reason": "SL",
            "opened_at": datetime(2026, 5, 7, 11, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 7, 16, 0, tzinfo=timezone.utc),
            "confluence": 80,
        },
        {
            "symbol": "XRP/USDT", "direction": "LONG",
            "entry": 0.5, "exit": 0.51, "size": 100.0,
            "pnl_usdt": 1.0, "pnl_pct": 2.0, "reason": "TP1",
            "opened_at": datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 7, 15, 0, tzinfo=timezone.utc),
            "confluence": 85,
        },
    ]
    equity_history = [
        {"ts": datetime(2026, 5, 7, 8, 0, tzinfo=timezone.utc),
         "balance": 2000.0, "open_positions_count": 0},
        {"ts": datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc),
         "balance": 2006.0, "open_positions_count": 0},
    ]

    hb_path = tmp_path / "alerter_heartbeat.json"
    hb_path.write_text(json.dumps({"alerter_heartbeat_ts": int(time.time())}))

    summary = compute_summary(trades=trades, equity_history=equity_history)
    stale, age = check_alerter_heartbeat(str(hb_path))
    subject, body = render_email(
        summary=summary, trades=trades,
        heartbeat_stale=stale, heartbeat_age_sec=age,
        report_date=date(2026, 5, 8),
    )

    assert "2026-05-08" in subject
    assert "ALERTER DOWN" not in subject
    assert "BTC/USDT" in body
    assert "ETH/USDT" in body
    assert "XRP/USDT" in body
    assert "win rate" in body.lower() or "wins" in body.lower()
    assert "2000" in body or "2006" in body

    with mock.patch("ops.daily_report.smtp_client.smtplib.SMTP") as smtp_cls:
        smtp_inst = smtp_cls.return_value.__enter__.return_value
        ok = send_email(
            host="smtp.example.com", port=587,
            username="bot@example.com", password="x",
            from_addr="bot@example.com", to_addr="ops@example.com",
            subject=subject, body=body,
        )
    assert ok is True
    sent_msg = smtp_inst.send_message.call_args[0][0]
    assert sent_msg["Subject"] == subject
    assert "BTC/USDT" in sent_msg.get_content()
