import math
import os
from scripts.routines.runner import register
from scripts.routines._base import RoutineResult

def build_report(equity_series, closed_trades, healthz):
    realized_pnl = sum(float(t.get("realized_pnl", 0) or t.get("pnl", 0) or 0) for t in closed_trades)

    daily_return = 0.0
    max_dd = 0.0
    sharpe = 0.0

    if len(equity_series) >= 2:
        prev_eq = float(equity_series[-2].get("equity", 0))
        curr_eq = float(equity_series[-1].get("equity", 0))
        if prev_eq > 0:
            daily_return = (curr_eq - prev_eq) / prev_eq * 100

    # Max Drawdown
    peak = -1e9
    for eq in equity_series:
        val = float(eq.get("equity", 0) or 0)
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd

    # Rolling Sharpe
    returns = []
    for i in range(1, len(equity_series)):
        prev_val = float(equity_series[i-1].get("equity", 0) or 0)
        curr_val = float(equity_series[i].get("equity", 0) or 0)
        if prev_val > 0:
            returns.append((curr_val - prev_val) / prev_val)

    if len(returns) >= 2:
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_ret = math.sqrt(variance)
        if std_ret > 0:
            sharpe = (mean_ret / std_ret) * math.sqrt(365)

    report_lines = [
        "# Equity & PnL Report",
        "",
        "## Core Metrics",
        f"- **Realized PnL:** ${realized_pnl:.2f}",
        f"- **Daily Return:** {daily_return:.2f}%",
        f"- **Max Drawdown:** {max_dd:.2f}%",
        f"- **Sharpe Ratio:** {sharpe:.2f}",
        f"- **Current Equity:** ${equity_series[-1].get('equity', 0.0):.2f}" if equity_series else "- **Current Equity:** N/A",
        "",
        "## Liveness Status",
        f"- **Status:** {healthz.get('status', 'unknown')}",
    ]

    if not equity_series:
        report_lines.append("\nNo equity history data available.")
    else:
        report_lines.append("\n## Equity Curve (Last 30 days)")
        report_lines.append("| Date | Equity |")
        report_lines.append("| --- | --- |")
        for eq in equity_series[-30:]:
            report_lines.append(f"| {eq.get('t', 'N/A')} | ${float(eq.get('equity', 0)):.2f} |")

    return "\n".join(report_lines)

@register("equity_report")
def run(client=None, alert=None, cfg=None):
    from scripts.routines._base import write_snapshot, write_report, RoutineResult, get_api
    
    equity_series = []
    closed_trades = []
    healthz = {"status": "offline"}
    
    # Try fetching from API
    try:
        equity_series = get_api("/api/equity", params={"days": 30})
        closed_trades = get_api("/api/history", params={"limit": 200})
        healthz = get_api("/healthz")
    except Exception as e:
        print(f"API endpoints unavailable. Falling back to local files: {e}")
        # Fallback to local files if API is offline
        # For closed trades, read state/trade_journal.jsonl
        journal_path = "state/trade_journal.jsonl"
        if os.path.exists(journal_path):
            import json
            try:
                with open(journal_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            closed_trades.append(json.loads(line))
            except Exception as e_journal:
                print(f"Failed to read trade journal fallback: {e_journal}")

    report_text = build_report(equity_series, closed_trades, healthz)
    
    report_path = "reports/equity_report.md"
    snapshot_path = "state/equity_report_snapshot.json"
    
    write_report(report_path, report_text)
    
    snapshot_data = {
        "equity_series": equity_series,
        "closed_trades": closed_trades,
        "healthz": healthz
    }
    write_snapshot(snapshot_path, snapshot_data)
    
    return RoutineResult(
        name="equity_report",
        ok=True,
        breaches=[],
        report_path=report_path
    )
