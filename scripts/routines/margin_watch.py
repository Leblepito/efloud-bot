from scripts.routines.runner import register
from scripts.routines._base import RoutineResult

def evaluate(positions, account, thresholds):
    breaches = []
    rows = []

    # Check individual positions
    for pos in positions:
        symbol = pos.get("symbol")
        side = pos.get("side", "flat")
        
        contracts_val = pos.get("contracts")
        size_val = pos.get("size")
        if contracts_val is None and size_val is None:
            contracts = 1.0
        else:
            contracts = abs(float(contracts_val if contracts_val is not None else size_val if size_val is not None else 0))
            
        if contracts == 0:
            continue

        mark = float(pos.get("markPrice") or pos.get("entryPrice") or 0)
        liq = float(pos.get("liquidationPrice") or 0)

        if mark > 0 and liq > 0:
            dist = abs(mark - liq) / mark * 100

            # Determine tier
            tier = "OK"
            severity = None
            if dist <= thresholds.get("liq_distance_critical_pct", 5.0):
                tier = "critical"
                severity = "critical"
            elif dist <= thresholds.get("liq_distance_alert_pct", 10.0):
                tier = "alert"
                severity = "warn"
            elif dist <= thresholds.get("liq_distance_warn_pct", 20.0):
                tier = "warn"
                severity = "warn"

            if severity:
                breaches.append({
                    "severity": severity,
                    "key": f"liq:{symbol}:{tier}",
                    "title": f"Liquidation Risk: {symbol}",
                    "body": f"Position {side} is {dist:.2f}% away from liquidation (Mark: {mark}, Liq: {liq})."
                })

            rows.append(f"| {symbol} | {side} | {contracts} | {mark:.4f} | {liq:.4f} | {dist:.2f}% | {tier.upper()} |")
        else:
            rows.append(f"| {symbol} | {side} | {contracts} | {mark:.4f} | {liq:.4f} | N/A | OK |")

    # Check account-level marginRatio
    margin_ratio = float(account.get("marginRatio", 0) or account.get("info", {}).get("marginRatio", 0) or 0)
    mr_tier = "OK"
    mr_severity = None
    if margin_ratio >= thresholds.get("margin_ratio_critical", 0.75):
        mr_tier = "critical"
        mr_severity = "critical"
    elif margin_ratio >= thresholds.get("margin_ratio_warn", 0.5):
        mr_tier = "warn"
        mr_severity = "warn"

    if mr_severity:
        breaches.append({
            "severity": mr_severity,
            "key": f"margin_ratio:{mr_tier}",
            "title": "Account Margin Ratio High",
            "body": f"Account margin ratio is {margin_ratio:.2%} (Limit: {thresholds.get('margin_ratio_critical'):.2%})."
        })

    # Generate report
    report_lines = [
        "# Margin & Liquidation Watch Report",
        f"**Account Margin Ratio:** {margin_ratio:.2%} (Status: {mr_tier.upper()})",
        "",
        "## Positions",
        "| Symbol | Side | Size | Mark Price | Liq Price | Distance % | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |"
    ]
    report_lines.extend(rows)
    report_text = "\n".join(report_lines)

    return report_text, breaches

@register("margin_watch")
def run(client=None, alert=None, cfg=None):
    from scripts.routines._base import write_snapshot, write_report, RoutineResult, load_config
    from scripts.routines._thresholds import derive

    config = cfg if cfg is not None else load_config()
    thresholds = derive(config)

    try:
        balance = client.fetch_balance()
        info = balance.get("info", {})
        margin_ratio = 0.0
        if isinstance(info, dict):
            maint_margin = float(info.get("totalMaintMargin", 0) or 0)
            margin_balance = float(info.get("totalMarginBalance", 0) or 0)
            if margin_balance > 0:
                margin_ratio = maint_margin / margin_balance
            
        # Support direct key injection in tests
        if isinstance(balance, dict) and "marginRatio" in balance:
            margin_ratio = balance["marginRatio"]

        account = {
            "marginRatio": margin_ratio,
            "info": info
        }

        positions = client.fetch_positions()
        active_positions = []
        for pos in positions:
            contracts = abs(float(pos.get("contracts", 0) or pos.get("size", 0) or 0))
            if contracts > 0:
                active_positions.append(pos)

    except Exception as e:
        import traceback
        print(f"Error fetching margin data: {e}")
        traceback.print_exc()
        return RoutineResult(
            name="margin_watch",
            ok=False,
            error=str(e)
        )

    report_text, breaches = evaluate(active_positions, account, thresholds)

    report_path = "reports/margin_watch.md"
    snapshot_path = "state/margin_watch_snapshot.json"

    write_report(report_path, report_text)

    # Save snapshot
    snapshot_data = {
        "account": account,
        "positions": active_positions,
        "thresholds": thresholds
    }
    write_snapshot(snapshot_path, snapshot_data)

    return RoutineResult(
        name="margin_watch",
        ok=True,
        breaches=breaches,
        report_path=report_path
    )
