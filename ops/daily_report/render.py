"""Daily report markdown rendering. Inline f-strings (no Jinja2)."""
from __future__ import annotations

from datetime import date
from typing import Optional


def _fmt_pnl(value: Optional[float]) -> str:
    """Format a PnL number with sign + 2 decimals."""
    if value is None:
        return "-"
    return f"{value:+.2f}"


def _fmt_pct(value: Optional[float]) -> str:
    """Format a percentage with 1 decimal + sign."""
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def _trade_row(t: dict) -> str:
    """One row of the trade table."""
    symbol = t.get("symbol", "?")
    direction = t.get("direction", "?")
    entry = t.get("entry") or 0.0
    exit_price = t.get("exit") or 0.0
    pnl = t.get("pnl_usdt") or 0.0
    reason = t.get("reason", "?")
    return f"| {symbol} | {direction} | {entry:.4f} | {exit_price:.4f} | ${pnl:+.2f} | {reason} |"


def render_email(
    summary: dict,
    trades: list[dict],
    heartbeat_stale: bool,
    heartbeat_age_sec: Optional[int],
    report_date: date,
) -> tuple[str, str]:
    """Render the daily report email — returns (subject, body)."""
    eq_end = summary.get("equity_end")
    eq_pct = summary.get("equity_delta_pct")
    if eq_end is None:
        equity_str = "no-equity-data"
    else:
        eq_pct_str = _fmt_pct(eq_pct) if eq_pct is not None else ""
        equity_str = f"equity ${eq_end:.2f} ({eq_pct_str})"
    subject = f"efloud-bot daily report - {report_date.isoformat()} - {equity_str}"
    if heartbeat_stale:
        subject = "ALERTER DOWN - " + subject

    lines: list[str] = []
    lines.append(f"# efloud-bot daily report — {report_date.isoformat()}")
    lines.append("")

    if heartbeat_stale:
        lines.append("## ⚠️ ALERTER DOWN")
        if heartbeat_age_sec is None:
            lines.append("Alerter heartbeat file is missing — alerter never wrote it or file got removed.")
        else:
            hours = heartbeat_age_sec / 3600.0
            lines.append(
                f"Alerter heartbeat is stale ({heartbeat_age_sec}s ≈ {hours:.1f}h since last write). "
                f"This means the alerter sidecar may be down — Telegram alerts may not have fired."
            )
        lines.append("")

    lines.append("## PnL summary")
    if summary.get("equity_start") is not None and summary.get("equity_end") is not None:
        lines.append(
            f"- Equity: ${summary['equity_start']:.2f} → ${summary['equity_end']:.2f} "
            f"({_fmt_pct(summary.get('equity_delta_pct'))})"
        )
    else:
        lines.append("- Equity: no equity_history data available for this window")
    if summary["trade_count"] == 0:
        lines.append("- Trades: 0 trades today")
    else:
        wr = summary.get("win_rate_pct")
        wr_str = f"{wr:.1f}%" if wr is not None else "-"
        lines.append(
            f"- Trades: {summary['trade_count']} ({summary['wins']} wins, "
            f"{summary['losses']} losses, win rate {wr_str})"
        )
        if summary.get("best_trade"):
            bt = summary["best_trade"]
            lines.append(f"- Best trade: {bt['symbol']} {_fmt_pnl(bt.get('pnl_usdt'))}")
        if summary.get("worst_trade"):
            wt = summary["worst_trade"]
            lines.append(f"- Worst trade: {wt['symbol']} {_fmt_pnl(wt.get('pnl_usdt'))}")
    lines.append("")

    lines.append("## Trade list (last 24h)")
    if not trades:
        lines.append("No trades closed in this window.")
    else:
        lines.append("| Symbol | Side | Entry | Exit | PnL | Reason |")
        lines.append("|--------|------|-------|------|-----|--------|")
        for t in trades:
            lines.append(_trade_row(t))
    lines.append("")

    lines.append("## Operational")
    lines.append("- Breaker trips: see Telegram for detail (Step 5b will add count here)")
    lines.append("- Restarts: see Hetzner Docker logs (Step 5b will add count here)")
    lines.append("- Anomalies (alerter): see Telegram for per-event detail")
    if not heartbeat_stale and heartbeat_age_sec is not None:
        lines.append(f"- Alerter heartbeat: fresh ({heartbeat_age_sec}s old)")
    lines.append("")

    body = "\n".join(lines)
    return (subject, body)
