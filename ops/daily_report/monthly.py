"""Monthly performance statement — T-013 (P-003 W1).

Journal-first (prod is DB-LESS): reads state/trade_journal.jsonl, maps the
journal's native keys to the DB-row keys compute_summary() expects
(backend/api.py read_journal_history precedent), aggregates a rolling window
(default 30 days) and renders CSV + markdown under reports/monthly/.

compute_summary() is called UNCHANGED (T-013 acceptance criterion). Without
DB equity_history the equity_start/end fields stay None — the statement marks
this explicitly instead of hiding it (UR-003 pin).

Operator-only INTERNAL output: customer-facing publication goes through the
T-012/T-014 static snapshot path, never this module or its endpoint.

Run as: python -m ops.daily_report.monthly [--journal PATH] [--out-dir DIR]
                                           [--window-days N]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ops.daily_report.aggregate import compute_summary

log = logging.getLogger("efloud.monthly_report")

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 92  # ~bir çeyrek; endpoint clamp'i de bunu kullanır

EQUITY_NOTE_DBLESS = (
    "equity_start/end: n/a — DB-less mod (equity_history kaynağı yok); "
    "tüm metrikler trade journal'dan türetildi."
)

CSV_FIELDS = (
    "closed_at", "opened_at", "symbol", "direction",
    "entry", "exit", "size", "pnl_usdt", "pnl_pct", "reason",
)


def _parse_ts(value: object) -> Optional[datetime]:
    """ISO timestamp -> aware UTC datetime (naive assumed UTC). None on junk."""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def read_journal_closed_trades(
    journal_path: str | Path,
    now_utc: datetime,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[dict]:
    """Closed trades within the window, mapped to compute_summary() keys.

    Mirrors backend/api.py read_journal_history's key mapping (pnl_usdt /
    opened_at / closed_at / reason) without importing the API module — ops
    must stay importable in cron context where backend deps may be absent.
    Corrupt lines are skipped (append-only journal; torn lines possible).
    """
    p = Path(journal_path)
    if not p.exists():
        return []
    since_utc = now_utc - timedelta(days=window_days)
    rows: list[dict] = []
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        exit_ts = _parse_ts(obj.get("exit_timestamp"))
        if exit_ts is None or exit_ts < since_utc or exit_ts > now_utc:
            continue
        mapped = dict(obj)
        mapped.update({
            "id": obj.get("trade_id"),
            "entry": obj.get("entry_price"),
            "exit": obj.get("exit_price"),
            "size": obj.get("position_size"),
            "pnl_usdt": obj.get("realized_pnl"),
            "pnl_pct": obj.get("realized_pnl_pct"),
            "reason": obj.get("exit_reason"),
            "opened_at": obj.get("entry_timestamp"),
            "closed_at": obj.get("exit_timestamp"),
        })
        rows.append(mapped)
    rows.sort(key=lambda r: r.get("closed_at") or "")
    return rows


def build_monthly_statement(
    trades: list[dict],
    now_utc: datetime,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict:
    """Statement dict: window + compute_summary() output + DB-less equity note."""
    summary = compute_summary(trades=trades, equity_history=[])
    since_utc = now_utc - timedelta(days=window_days)
    statement = {
        "window": {
            "since": since_utc.isoformat(),
            "until": now_utc.isoformat(),
            "days": window_days,
        },
        "summary": summary,
        "equity_note": EQUITY_NOTE_DBLESS if summary["equity_start"] is None else None,
    }
    return statement


def _fmt(value: object, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value}{suffix}"


def render_markdown(statement: dict) -> str:
    """Operator-facing markdown statement."""
    s = statement["summary"]
    w = statement["window"]
    month = str(w["until"])[:7]
    lines = [
        f"# Aylık Statement — {month}",
        "",
        f"Pencere: {str(w['since'])[:10]} → {str(w['until'])[:10]} ({w['days']} gün)",
        "",
        "| Metrik | Değer |",
        "|---|---|",
        f"| Trade sayısı | {s['trade_count']} |",
        f"| Kazanan / Kaybeden | {s['wins']} / {s['losses']} |",
        f"| Win rate | {_fmt(s['win_rate_pct'], '%')} |",
        f"| Equity start | {_fmt(s['equity_start'])} |",
        f"| Equity end | {_fmt(s['equity_end'])} |",
        f"| Equity delta | {_fmt(s['equity_delta_usdt'])} ({_fmt(s['equity_delta_pct'], '%')}) |",
    ]
    best, worst = s.get("best_trade"), s.get("worst_trade")
    if best:
        lines.append(
            f"| En iyi trade | {best.get('symbol')} {best.get('direction')} "
            f"{_fmt(best.get('pnl_usdt'))} USDT |"
        )
    if worst:
        lines.append(
            f"| En kötü trade | {worst.get('symbol')} {worst.get('direction')} "
            f"{_fmt(worst.get('pnl_usdt'))} USDT |"
        )
    if statement.get("equity_note"):
        lines += ["", f"> {statement['equity_note']}"]
    lines += ["", "_Operatör-içi rapor — müşteri yayını T-012/T-014 statik snapshot yolundan._", ""]
    return "\n".join(lines)


def render_csv(trades: list[dict]) -> str:
    """One row per closed trade, oldest first."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(CSV_FIELDS),
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for t in trades:
        writer.writerow({k: t.get(k) for k in CSV_FIELDS})
    return buf.getvalue()


def _default_journal_path() -> str:
    return os.environ.get("EFLOUD_TRADE_JOURNAL", "./state/trade_journal.jsonl")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Monthly statement (T-013)")
    parser.add_argument("--journal", default=_default_journal_path())
    parser.add_argument("--out-dir", default="reports/monthly")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    args = parser.parse_args(argv)

    try:
        now_utc = datetime.now(timezone.utc)
        window_days = min(max(args.window_days, 1), MAX_WINDOW_DAYS)
        trades = read_journal_closed_trades(args.journal, now_utc, window_days)
        statement = build_monthly_statement(trades, now_utc, window_days)

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        month = str(statement["window"]["until"])[:7]
        md_path = out_dir / f"statement_{month}.md"
        csv_path = out_dir / f"statement_{month}.csv"
        md_path.write_text(render_markdown(statement), encoding="utf-8")
        csv_path.write_text(render_csv(trades), encoding="utf-8")
        log.info(f"monthly statement written: {md_path} + {csv_path} "
                 f"({statement['summary']['trade_count']} trades)")
        return 0
    except Exception:
        log.exception("monthly statement FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
