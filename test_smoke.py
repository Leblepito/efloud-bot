"""
Quick smoke test — ETH/USDT orkestatör testi.
Binance'den gerçek data çeker, tam analiz raporu üretir.
"""

import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s'
)

import ccxt
import pandas as pd
from engine import SafeOrchestrator


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
        "operation": {"dry_run": True},
        "safety": {
            "daily_loss_limit_pct": 3.0,
            "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3,
            "consecutive_pause_min": 120,
            "starting_balance": 10000,
            "adx_trend_threshold": 25,
            "adx_range_threshold": 20,
            "volatile_atr_mult": 2.5,
            "max_position_notional_pct": 3.0,
            "max_total_exposure": 3.0,
            "max_holding_hours": 48,
            "max_pyramid_adds": 2,
            "min_sl_atr": 0.5,
            "max_sl_atr": 5.0,
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
    import tempfile
    orch = SafeOrchestrator(config, state_dir=tempfile.mkdtemp(prefix="efloud_smoke_"))
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
