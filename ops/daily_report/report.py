"""Daily email report — main entry. Runs once and exits.

Cron-driven via Hetzner crontab: `docker compose run --rm daily-report`.

Reads SMTP + heartbeat config from env, queries Supabase for last-24h
trades + equity_history, composes markdown body, sends via SMTP.
Exits 0 on success, 1 on failure (cron wrapper pings Telegram on non-zero).

Run as: python -m ops.daily_report.report
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)-26s | %(levelname)-5s | %(message)s",
)
log = logging.getLogger("efloud.daily_report")

# Configurable env (defaults match docker-compose.prod.yml)
SMTP_HOST = os.environ.get("EFLOUD_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("EFLOUD_SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("EFLOUD_SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("EFLOUD_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("EFLOUD_SMTP_FROM", SMTP_USERNAME)
SMTP_TO = os.environ.get("EFLOUD_SMTP_TO", "")
HEARTBEAT_FILE = os.environ.get(
    "EFLOUD_ALERTER_HEARTBEAT_FILE", "/app/state/alerter_heartbeat.json"
)


async def _run() -> int:
    """Async entry. Returns exit code."""
    log.info("daily report starting")
    if not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_TO:
        log.error("SMTP env not fully configured (EFLOUD_SMTP_USERNAME/PASSWORD/TO)")
        return 1

    from backend.db import Database
    from ops.daily_report.aggregate import compute_summary
    from ops.daily_report.heartbeat import check_alerter_heartbeat
    from ops.daily_report.render import render_email
    from ops.daily_report.smtp_client import send_email

    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(hours=24)
    report_date = now_utc.date()

    db = Database()
    await db.connect()
    if db.pool is None:
        log.error("DB pool init failed — cannot generate report")
        return 1
    try:
        trades = await db.fetch_trades_since(since_utc)
        equity_history = await db.fetch_equity_history(days=2)
        equity_history = [
            e for e in equity_history if e["ts"] >= since_utc
        ]
        log.info(f"fetched {len(trades)} trades + {len(equity_history)} equity points")
    finally:
        await db.close()

    stale, age = check_alerter_heartbeat(HEARTBEAT_FILE)
    if stale:
        log.warning(f"alerter heartbeat stale (age={age}s) — adding ALERTER DOWN prefix")

    summary = compute_summary(trades=trades, equity_history=equity_history)
    subject, body = render_email(
        summary=summary, trades=trades,
        heartbeat_stale=stale, heartbeat_age_sec=age,
        report_date=report_date,
    )

    ok = send_email(
        host=SMTP_HOST, port=SMTP_PORT,
        username=SMTP_USERNAME, password=SMTP_PASSWORD,
        from_addr=SMTP_FROM, to_addr=SMTP_TO,
        subject=subject, body=body,
    )
    if ok:
        log.info(f"daily report sent: {subject!r}")
        return 0
    log.error("daily report send FAILED")
    return 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
