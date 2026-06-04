#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import ccxt

def load_env(env_path=".env"):
    p = Path(env_path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

def main():
    # Load environment variables
    load_env(".env")
    
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    
    if not api_key or not api_secret:
        print("Error: BINANCE_API_KEY or BINANCE_API_SECRET not found in environment.", file=sys.stderr)
        sys.exit(1)
        
    # Initialize CCXT Binance Futures client
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {
            'defaultType': 'future',
        },
    })
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    since_ms = int(since.timestamp() * 1000)
    
    print(f"Querying Binance Futures since {since.strftime('%Y-%m-%d %H:%M:%S UTC')}...")
    
    # 1. Fetch live open positions
    open_positions = []
    try:
        raw_positions = exchange.fetch_positions()
        for pos in raw_positions:
            size = float(pos.get("contracts", 0.0) or 0.0)
            if size != 0.0:
                symbol = pos.get("symbol", "")
                direction = str(pos.get("side", "")).upper()
                if not direction or direction == "NONE":
                    # Fallback to contracts sign if side is undefined
                    contracts_signed = float(pos.get("info", {}).get("positionAmt", 0.0) or 0.0)
                    direction = "LONG" if contracts_signed > 0 else "SHORT"
                
                entry_price = float(pos.get("entryPrice", 0.0) or 0.0)
                mark_price = float(pos.get("markPrice", 0.0) or 0.0)
                unrealized_pnl = float(pos.get("unrealizedPnl", 0.0) or 0.0)
                leverage = int(pos.get("leverage", 1) or 1)
                margin_type = str(pos.get("marginMode", "cross")).upper()
                
                # Calculate unrealized %
                if entry_price > 0:
                    is_long = direction == "LONG"
                    pnl_pct = ((mark_price - entry_price) / entry_price * 100) if is_long else \
                              ((entry_price - mark_price) / entry_price * 100)
                else:
                    pnl_pct = 0.0
                    
                open_positions.append({
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "size": size,
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_pct": pnl_pct,
                    "leverage": leverage,
                    "margin_type": margin_type
                })
    except Exception as e:
        print(f"Error fetching open positions: {e}", file=sys.stderr)
        
    # 2. Fetch income history to find traded symbols in the last 24h
    traded_symbols = set()
    income_events = []
    try:
        raw_income = exchange.fapiPrivateGetIncome(params={'startTime': since_ms, 'limit': 1000})
        for item in raw_income:
            income_type = item.get("incomeType")
            if income_type in ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE"):
                symbol = item.get("symbol")
                if symbol:
                    # Format to standard 'BTC/USDT'
                    ccxt_symbol = symbol
                    if symbol.endswith("USDT"):
                        ccxt_symbol = symbol[:-4] + "/USDT"
                    traded_symbols.add(ccxt_symbol)
                    income_events.append(item)
    except Exception as e:
        print(f"Error fetching income history: {e}", file=sys.stderr)

    # 3. Fetch detailed user trades for symbols that had activity
    trades = []
    for symbol in traded_symbols:
        try:
            raw_trades = exchange.fetch_my_trades(symbol=symbol, since=since_ms)
            for t in raw_trades:
                # Standardize fee info
                fee_cost = 0.0
                if t.get("fee"):
                    fee_cost = float(t["fee"].get("cost", 0.0))
                    
                trades.append({
                    "id": t.get("id"),
                    "symbol": t.get("symbol"),
                    "direction": t.get("side", "").upper(),
                    "price": float(t.get("price", 0.0)),
                    "amount": float(t.get("amount", 0.0)),
                    "cost": float(t.get("cost", 0.0)),
                    "fee": fee_cost,
                    "timestamp": t.get("timestamp"),
                    "datetime": t.get("datetime"),
                    # From API raw response info:
                    "realized_pnl": float(t.get("info", {}).get("realizedPnl", 0.0) or 0.0)
                })
        except Exception as e:
            print(f"Error fetching trades for {symbol}: {e}", file=sys.stderr)

    # Sort trades by timestamp descending
    trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    # 4. Load previous snapshot to find new trades
    snapshot_path = Path("state/binance_monitor_snapshot.json")
    previous_trade_ids = set()
    if snapshot_path.exists():
        try:
            prev_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            previous_trade_ids = set(prev_snapshot.get("trade_ids", []))
        except Exception:
            pass

    # Find new trades
    new_trades = [t for t in trades if t["id"] not in previous_trade_ids]
    
    # Save new snapshot
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_data = {
        "last_checked": now.isoformat(),
        "trade_ids": [t["id"] for t in trades]
    }
    snapshot_path.write_text(json.dumps(snapshot_data, indent=2), encoding="utf-8")

    # 5. Generate Markdown Report
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "binance_live_monitor.md"
    
    now_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    since_str = since.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Calculate stats
    total_realized_pnl = sum(t["realized_pnl"] for t in trades)
    total_fees = sum(t["fee"] for t in trades)
    net_pnl = total_realized_pnl - total_fees
    
    report_lines = [
        f"# Live Binance Futures Monitor Report",
        f"**Last Updated (UTC):** `{now_str}`",
        f"**Monitoring Window:** `{since_str}` to `{now_str}`\n",
        f"## 📊 24h Summary Metrics",
        f"- **Closed Trades (approx):** {len([t for t in trades if t['realized_pnl'] != 0.0])}",
        f"- **Gross Realized PnL:** `{total_realized_pnl:+.4f} USDT`",
        f"- **Total Fees Paid:** `{total_fees:.4f} USDT`",
        f"- **Net PnL (including fees):** `{net_pnl:+.4f} USDT`",
        f""
    ]
    
    # Live Open Positions Section
    report_lines.append("## 🔒 Live Open Positions")
    if not open_positions:
        report_lines.append("- No open positions found on Binance Futures.")
    else:
        report_lines.append("| Symbol | Direction | Entry Price | Mark Price | Size | Unrealized PnL | PnL % | Margin / Leverage |")
        report_lines.append("|---|---|---|---|---|---|---|---|")
        for p in open_positions:
            dir_badge = "🟢 LONG" if p["direction"] == "LONG" else "🔴 SHORT"
            report_lines.append(
                f"| **{p['symbol']}** | {dir_badge} | {p['entry_price']:.4f} | {p['mark_price']:.4f} | {p['size']:.4f} | {p['unrealized_pnl']:+.2f} USDT | {p['unrealized_pnl_pct']:+.2f}% | {p['margin_type']} ({p['leverage']}x) |"
            )
            
    report_lines.append("\n## 📜 Execution History (Last 24 Hours)")
    if not trades:
        report_lines.append("- No executions found in the last 24 hours.")
    else:
        report_lines.append("| Time (UTC) | Symbol | Side | Price | Amount | Realized PnL | Fee | Trade ID |")
        report_lines.append("|---|---|---|---|---|---|---|---|")
        for t in trades:
            time_str = t["datetime"].replace("T", " ").split(".")[0]
            side_badge = "🟢 BUY" if t["direction"] == "BUY" else "🔴 SELL"
            pnl_str = f"**{t['realized_pnl']:+.4f}**" if t["realized_pnl"] > 0 else f"{t['realized_pnl']:+.4f}" if t["realized_pnl"] < 0 else "0.0000"
            report_lines.append(
                f"| {time_str} | **{t['symbol']}** | {side_badge} | {t['price']:.4f} | {t['amount']:.4f} | {pnl_str} | {t['fee']:.4f} | {t['id']} |"
            )
            
    report_file.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Successfully generated report at {report_file}")
    
    # 6. Output new activity to stdout
    if new_trades:
        print(f"\nNEW ACTIVITY DETECTED ({len(new_trades)} new trades):")
        for nt in new_trades:
            print(f"- {nt['datetime']} | {nt['symbol']} | {nt['direction']} | {nt['price']} | PnL: {nt['realized_pnl']}")
    else:
        print("\nNo new trade activity detected since last check.")

if __name__ == "__main__":
    main()
