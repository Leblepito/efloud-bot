import asyncio
import os
import json
import subprocess
from datetime import datetime, timezone
import asyncpg

# Credentials come from the environment only — never hardcode connection
# strings (they land in git history). Set DATABASE_URL (or SUPABASE_DATABASE_URL)
# before running this script.
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DATABASE_URL", "")
LOCAL_POSITIONS_PATH = os.environ.get("LOCAL_POSITIONS_PATH", "state/positions.json")
OUTPUT_REPORT_PATH = os.environ.get(
    "OUTPUT_REPORT_PATH", "reports/LIVE_PERFORMANCE_SUMMARY.md"
)

def run_ssh_command(cmd):
    full_cmd = ["ssh", "efloud-bot", cmd]
    try:
        res = subprocess.run(full_cmd, capture_output=True, text=True, check=True)
        return res.stdout
    except Exception as e:
        print(f"Warning: Remote SSH command failed: {e}")
        return None

async def fetch_db_trades():
    if not DATABASE_URL:
        print("Error: DATABASE_URL (or SUPABASE_DATABASE_URL) env var is not set.")
        return []
    print("Connecting to remote Supabase database...")
    try:
        # Pass statement_cache_size=0 to handle pgBouncer transaction mode
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:
        print(f"Error: Database connection failed: {e}")
        return []
        
    since_ts = datetime(2026, 6, 15, tzinfo=timezone.utc)
    try:
        rows = await conn.fetch(
            """
            SELECT id::text, symbol, direction, entry, exit, sl, tp1, tp2,
                   size, pnl_usdt, pnl_pct, reason, opened_at, closed_at,
                   confluence, bot_id
            FROM trades
            WHERE opened_at >= $1
            ORDER BY opened_at DESC
            """,
            since_ts
        )
        trades = [dict(r) for r in rows]
    except Exception as e:
        print(f"Error fetching trades: {e}")
        trades = []
    finally:
        await conn.close()
        
    return trades

async def fetch_waitlist_count():
    print("Fetching waitlist leads count...")
    try:
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
        row = await conn.fetchrow("SELECT COUNT(*) as count FROM waitlist_leads")
        count = row["count"] if row else 0
        await conn.close()
        return count
    except Exception as e:
        try:
            conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
            row = await conn.fetchrow("SELECT COUNT(*) as count FROM waitlist")
            count = row["count"] if row else 0
            await conn.close()
            return count
        except Exception as e2:
            print(f"Warning: Could not fetch waitlist leads: {e2}")
            return 0

def load_local_positions():
    print("Loading local positions...")
    try:
        with open(LOCAL_POSITIONS_PATH, "r", encoding="utf-8") as f:
            content = json.load(f)
            positions = content.get("data", [])
            return positions
    except Exception as e:
        print(f"Warning: Local positions file not found or corrupted: {e}")
        return []

async def aggregate_stats():
    # 1. Load local positions
    local_pos = load_local_positions()
    
    # 2. Connect and fetch database trades + waitlist
    db_trades = await fetch_db_trades()
    waitlist_count = await fetch_waitlist_count()
    
    # 3. Process Local Positions (since June 15, 2026)
    local_since_june15 = []
    start_date = datetime(2026, 6, 15)
    for pos in local_pos:
        ts_str = pos.get("opened_at") or pos.get("closed_at") or ""
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
            if dt >= start_date:
                local_since_june15.append(pos)
        except Exception:
            pass
            
    # Calculate Local Stats
    local_active = sum(1 for p in local_since_june15 if not p.get("closed_at"))
    local_closed = sum(1 for p in local_since_june15 if p.get("closed_at"))
    local_wins = sum(1 for p in local_since_june15 if p.get("closed_at") and sum(x.get("pnl", 0) for x in p.get("exits", [])) > 0)
    local_losses = sum(1 for p in local_since_june15 if p.get("closed_at") and sum(x.get("pnl", 0) for x in p.get("exits", [])) < 0)
    local_pnl = sum(sum(x.get("pnl", 0) for x in p.get("exits", [])) for p in local_since_june15)
    local_wr = (local_wins / local_closed * 100) if local_closed > 0 else 0.0
    
    # 4. Process DB Trades by bot_id
    db_by_bot = {}
    for t in db_trades:
        bid = t.get("bot_id", "v1")
        if bid not in db_by_bot:
            db_by_bot[bid] = []
        db_by_bot[bid].append(t)
        
    report = []
    report.append(f"# Live Trading & Strategy Performance Report")
    report.append(f"Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
    report.append(f"This report aggregates performance metrics from the **Hetzner Live VPS**, **Supabase Production Database**, and the **Local Optimization Workspace** since June 15, 2026.")
    
    report.append(f"\n## 📊 Waitlist Traction Metrics")
    report.append(f"- **Total Registered Waitlist Leads:** {waitlist_count} leads")
    
    report.append(f"\n## 📈 Performance Summary Table")
    report.append(f"| Environment / Bot Profile | Total Trades | Active | Closed | Wins | Losses | Win Rate | Net P&L (USDT) |")
    report.append(f"|---------------------------|--------------|--------|--------|------|--------|----------|----------------|")
    
    # Add Local
    report.append(f"| **Local Workspace (Optimized)** | {len(local_since_june15)} | {local_active} | {local_closed} | {local_wins} | {local_losses} | {local_wr:.2f}% | {local_pnl:+.2f} |")
    
    # Add DB Bots
    for bid in ["v1", "v2-long"]:
        trades = db_by_bot.get(bid, [])
        active = sum(1 for t in trades if not t.get("closed_at"))
        closed = sum(1 for t in trades if t.get("closed_at"))
        wins = sum(1 for t in trades if t.get("closed_at") and float(t.get("pnl_usdt") or 0.0) > 0)
        losses = sum(1 for t in trades if t.get("closed_at") and float(t.get("pnl_usdt") or 0.0) < 0)
        pnl = sum(float(t.get("pnl_usdt") or 0.0) for t in trades if t.get("pnl_usdt") is not None)
        wr = (wins / closed * 100) if closed > 0 else 0.0
        
        label = "VPS V1 (Mid Profile)" if bid == "v1" else "VPS V2 (Long Profile)"
        report.append(f"| **{label}** | {len(trades)} | {active} | {closed} | {wins} | {losses} | {wr:.2f}% | {pnl:+.2f} |")
        
    report.append(f"\n## 🔍 Detailed Local Optimized Trades (June 22 - June 25)")
    report.append(f"These trades reflect the optimized model configuration run locally on Binance testnet/dry-run:")
    report.append(f"| ID | Symbol | Direction | Opened At | Closed At | Entry | Exit | Net P&L (USDT) | Reason |")
    report.append(f"|----|--------|-----------|-----------|-----------|-------|------|----------------|--------|")
    
    for pos in local_since_june15:
        pid = pos.get("id", "")[:8]
        symbol = pos.get("symbol", "")
        dir_ = pos.get("direction", "")
        opened = (pos.get("opened_at") or "")[:16]
        closed = (pos.get("closed_at") or "")[:16]
        
        entries = pos.get("entries", [])
        exits = pos.get("exits", [])
        entry_price = entries[0].get("price", 0.0) if entries else 0.0
        exit_price = exits[0].get("price", 0.0) if exits else 0.0
        pnl = sum(ex.get("pnl", 0.0) for ex in exits) if closed else 0.0
        reason = exits[0].get("reason", "CLOSED") if exits else "ACTIVE"
        if not closed:
            reason = "ACTIVE"
            
        entry_str = f"{entry_price:.5f}"
        exit_str = f"{exit_price:.5f}" if closed else "N/A"
        pnl_str = f"{pnl:+.2f}" if closed else "N/A"
        
        report.append(f"| {pid} | {symbol} | {dir_} | {opened} | {closed} | {entry_str} | {exit_str} | {pnl_str} | {reason} |")
        
    report.append(f"\n## ⚡ Live VPS V2-Long Trades")
    report.append(f"This reflects the parallel long-bot instance (`v2-long`) running live since June 21, 2026:")
    report.append(f"| ID | Symbol | Direction | Opened At | Closed At | Entry | Exit | Net P&L (USDT) | Reason |")
    report.append(f"|----|--------|-----------|-----------|-----------|-------|------|----------------|--------|")
    
    v2_trades = db_by_bot.get("v2-long", [])
    for t in v2_trades:
        tid = t.get("id", "")[:8]
        symbol = t.get("symbol", "")
        dir_ = t.get("direction", "")
        opened = str(t.get("opened_at", ""))[:16]
        closed_ts = t.get("closed_at")
        closed = str(closed_ts)[:16] if closed_ts else ""
        
        entry = t.get("entry", 0.0)
        exit_price = t.get("exit", 0.0)
        pnl = float(t.get("pnl_usdt") or 0.0)
        reason = t.get("reason", "ACTIVE")
        if not closed_ts:
            reason = "ACTIVE"
            
        entry_str = f"{entry:.5f}"
        exit_str = f"{exit_price:.5f}" if closed_ts else "N/A"
        pnl_str = f"{pnl:+.2f}" if closed_ts else "N/A"
        
        report.append(f"| {tid} | {symbol} | {dir_} | {opened} | {closed} | {entry_str} | {exit_str} | {pnl_str} | {reason} |")
        
    # Write report
    os.makedirs(os.path.dirname(OUTPUT_REPORT_PATH), exist_ok=True)
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
        
    print(f"Report compiled successfully at: {OUTPUT_REPORT_PATH}")

if __name__ == "__main__":
    asyncio.run(aggregate_stats())
