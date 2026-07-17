from scripts.routines.runner import register
from scripts.routines._base import RoutineResult

def evaluate(exchange_positions, exchange_open_orders, ledger_positions):
    breaches = []
    report_lines = [
        "# Position Audit Report",
        "",
        "## Summary",
    ]
    
    # 1. Bare Position Audit (SL/TP check)
    bare_count = 0
    for pos in exchange_positions:
        symbol = pos.get("symbol")
        side = (pos.get("side") or "").lower()
        size = abs(float(pos.get("contracts", 0) or pos.get("size", 0) or pos.get("positionAmt", 0) or 0))
        if size == 0:
            continue
            
        has_sl = False
        has_tp = False
        
        for order in exchange_open_orders:
            o_symbol = order.get("symbol", "")
            if o_symbol != symbol:
                continue
            o_type = str(order.get("type", "")).upper()
            o_side = str(order.get("side", "")).upper()
            o_reduce = order.get("reduceOnly", False) or order.get("closePosition", False)
            
            o_side_norm = "sell" if o_side in ("SELL", "SHORT") else "buy" if o_side in ("BUY", "LONG") else o_side.lower()
            side_norm = "sell" if side in ("sell", "short") else "buy" if side in ("buy", "long") else side.lower()
            is_opposite = (side_norm == "buy" and o_side_norm == "sell") or (side_norm == "sell" and o_side_norm == "buy")
            
            is_sl = ("STOP" in o_type or "TRAILING" in o_type) and "PROFIT" not in o_type
            is_tp = "PROFIT" in o_type or o_type in ("LIMIT", "MARKET")
            
            if is_opposite and o_reduce:
                if is_sl:
                    has_sl = True
                if is_tp:
                    has_tp = True
                    
        if not has_sl or not has_tp:
            bare_count += 1
            missing = []
            if not has_sl:
                missing.append("Stop Loss (SL)")
            if not has_tp:
                missing.append("Take Profit (TP)")
            breaches.append({
                "severity": "critical",
                "key": f"bare:{symbol}",
                "title": f"Bare Position: {symbol}",
                "body": f"Exchange position {side} of size {size} is missing protective: {', '.join(missing)}"
            })
            
    # 2. Orphan Orders Audit
    orphan_count = 0
    open_symbols = {p["symbol"] for p in exchange_positions if abs(float(p.get("contracts", 0) or p.get("size", 0) or p.get("positionAmt", 0) or 0)) > 0}
    for order in exchange_open_orders:
        symbol = order.get("symbol")
        o_reduce = order.get("reduceOnly", False) or order.get("closePosition", False)
        o_type = str(order.get("type", "")).upper()
        is_sl_or_tp = "STOP" in o_type or "PROFIT" in o_type or o_reduce
        if is_sl_or_tp and symbol not in open_symbols:
            orphan_count += 1
            breaches.append({
                "severity": "warn",
                "key": f"orphan:{symbol}",
                "title": f"Orphan Order: {symbol}",
                "body": f"Open Algo order (type: {o_type}, reduceOnly: {o_reduce}) exists but no active position on exchange."
            })
            
    # 3. Ledger vs Exchange Reconciliation (Drift Check)
    drift_count = 0
    ex_map = {p["symbol"]: p for p in exchange_positions}
    ld_map = {p["symbol"]: p for p in ledger_positions}
    
    all_symbols = set(ex_map.keys()) | set(ld_map.keys())
    for symbol in all_symbols:
        ex_pos = ex_map.get(symbol)
        ld_pos = ld_map.get(symbol)
        
        ex_size = abs(float(ex_pos.get("contracts", 0) or ex_pos.get("size", 0) or ex_pos.get("positionAmt", 0) or 0)) if ex_pos else 0.0
        ld_size = abs(float(ld_pos.get("contracts", 0) or ld_pos.get("size", 0) or ld_pos.get("positionAmt", 0) or 0)) if ld_pos else 0.0
        
        if ex_size == 0 and ld_size == 0:
            continue
            
        if ex_size == 0 or ld_size == 0:
            drift_count += 1
            breaches.append({
                "severity": "critical",
                "key": f"drift:{symbol}",
                "title": f"Position Drift: {symbol}",
                "body": f"Position presence mismatch. Exchange size: {ex_size}, Ledger size: {ld_size}"
            })
        else:
            diff_pct = abs(ex_size - ld_size) / ex_size * 100
            if diff_pct > 1.0:
                drift_count += 1
                breaches.append({
                    "severity": "critical",
                    "key": f"drift:{symbol}",
                    "title": f"Position Drift: {symbol}",
                    "body": f"Exchange size ({ex_size}) vs ledger size ({ld_size}) differs by {diff_pct:.2f}% (limit: 1.0%)"
                })
                
    report_lines.append(f"- **Bare Positions (Missing SL/TP):** {bare_count}")
    report_lines.append(f"- **Orphan Orders:** {orphan_count}")
    report_lines.append(f"- **Position Size Drifts:** {drift_count}")
    report_lines.append("")
    
    if breaches:
        report_lines.append("## Flagged Issues")
        for b in breaches:
            report_lines.append(f"### [{b['severity'].upper()}] {b['title']}")
            report_lines.append(f"{b['body']}")
            report_lines.append("")
            
    report_text = "\n".join(report_lines)
    return report_text, breaches

@register("position_audit")
def run(client=None, alert=None, cfg=None):
    from scripts.routines._base import (
        read_snapshot, write_snapshot, write_report, RoutineResult,
        resolve_state_dir, unwrap_state,
    )
    import os

    # R-3 fix (2026-07-17): env override'lı state_dir — canlı prod ./state_1k'ya
    # yazar; root config baseline'ıyla ./state okumak boş ledger → her açık
    # pozisyonda kalıcı false "Position Drift" CRITICAL üretiyordu.
    ledger_path = os.path.join(resolve_state_dir(cfg), "positions.json")
    report_path = "reports/position_audit.md"
    snapshot_path = "state/position_audit_snapshot.json"
    
    try:
        # Fetch exchange state
        positions = client.fetch_positions()
        active_exchange_positions = [
            p for p in positions 
            if abs(float(p.get("contracts", 0) or p.get("size", 0) or p.get("positionAmt", 0) or 0)) > 0
        ]
        
        open_orders = client.fetch_open_orders()
        
        # Load local ledger positions
        # R-3 fix: StateStore zarfını aç ({"saved_at":…, "data":[…]}) — zarfsız
        # okuma listeyi göremeyip ledger'ı hep boş sayıyordu.
        ledger_data = unwrap_state(read_snapshot(ledger_path))
        # Handle positions.json which could be a list or a dict
        if isinstance(ledger_data, dict) and "positions" in ledger_data:
            ledger_positions = ledger_data["positions"]
        elif isinstance(ledger_data, list):
            ledger_positions = ledger_data
        else:
            ledger_positions = []
            
    except Exception as e:
        import traceback
        print(f"Error executing position audit: {e}")
        traceback.print_exc()
        return RoutineResult(
            name="position_audit",
            ok=False,
            error=str(e)
        )
        
    report_text, breaches = evaluate(active_exchange_positions, open_orders, ledger_positions)
    
    write_report(report_path, report_text)
    
    snapshot_data = {
        "active_exchange_positions": active_exchange_positions,
        "open_orders": open_orders,
        "ledger_positions": ledger_positions,
        "breaches_count": len(breaches)
    }
    write_snapshot(snapshot_path, snapshot_data)
    
    return RoutineResult(
        name="position_audit",
        ok=True,
        breaches=breaches,
        report_path=report_path
    )
