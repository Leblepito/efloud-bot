"""
Quick smoke test — ETH/USDT orkestatör testi.
Binance'den gerçek data çeker, tam analiz raporu üretir.
"""

import sys
import logging
sys.path.insert(0, '/home/claude/efloud-bot')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s'
)

import ccxt
import pandas as pd
from engine import EfloudOrchestrator


def fetch(ex, symbol, tf, limit=500):
    raw = ex.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


def main():
    print("━" * 60)
    print("  EFLOUD BOT v2 — Smoke Test")
    print("━" * 60)

    # Config
    config = {
        "exchange": {"leverage": 1},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "structure": {
            "swing_lookback": 5,
            "ob_sequential": 5,
            "body_mode": True,
            "eq_threshold_pct": 0.1,
            "range_lookback": 50,
        },
        "fibonacci": {
            "ote_lower": 0.618,
            "ote_upper": 0.786,
            "ext_tp2": 1.618,
        },
        "risk": {
            "risk_per_trade_pct": 1.5,
            "max_open_positions": 3,
            "min_rr": 1.5,
            "min_confluence": 50,
        },
    }

    ex = ccxt.binance({"enableRateLimit": True})
    symbol = "ETH/USDT"

    print(f"\n📡 Fetching {symbol} data from Binance...")
    df_htf = fetch(ex, symbol, "4h", 300)
    df_mtf = fetch(ex, symbol, "1h", 300)
    df_entry = fetch(ex, symbol, "15m", 500)
    df_daily = fetch(ex, symbol, "1d", 100)

    print(f"   4h: {len(df_htf)} bars | Last: ${df_htf['close'].iloc[-1]:,.2f}")
    print(f"   1h: {len(df_mtf)} bars")
    print(f"  15m: {len(df_entry)} bars")
    print(f"   1d: {len(df_daily)} bars")

    print(f"\n🧠 Running orchestrator cycle...")
    orch = EfloudOrchestrator(config)
    result = orch.run_cycle(
        symbol=symbol,
        df_htf=df_htf,
        df_mtf=df_mtf,
        df_entry=df_entry,
        df_daily=df_daily,
    )

    print(f"\n📊 Cycle complete:")
    print(f"   Current price: ${result.current_price:,.2f}")
    print(f"   HTF bias: {result.htf_bias}")
    print(f"   Levels extracted: {len(result.levels)}")
    print(f"   Stacked zones: {len(result.stacked_zones)}")
    print(f"   Intent: {result.intent.label} ({result.intent.score}/100)")
    print(f"   Signals: {len(result.signals)}")
    print(f"   Active scenarios: {len(result.scenarios)}")
    print(f"   Actions taken: {result.actions_taken}")

    print("\n" + "═" * 60)
    print("  EFLOUD ANALIZ RAPORU")
    print("═" * 60)
    print(result.report_md)


if __name__ == "__main__":
    main()
