"""
Offline smoke test — synthetic ETH data ile orkestatörü test eder.
ETH Apr 2026 gerçek örneğine yakın bir simülasyon.
"""

import sys
import logging
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s'
)

from engine import SafeOrchestrator


def gen_synthetic_ohlcv(
    n: int = 500,
    start_price: float = 2000.0,
    drift: float = 0.0002,
    volatility: float = 0.008,
    tf_minutes: int = 15,
    seed: int = 42
) -> pd.DataFrame:
    """Log-normal random walk ile OHLCV simüle et."""
    np.random.seed(seed)
    returns = np.random.normal(drift, volatility, n)
    closes = start_price * np.exp(np.cumsum(returns))

    # OHLC simülasyonu
    highs, lows, opens = [], [], []
    for i, c in enumerate(closes):
        prev_close = closes[i - 1] if i > 0 else start_price
        o = prev_close * (1 + np.random.normal(0, volatility * 0.3))
        body_high = max(o, c)
        body_low = min(o, c)
        wick_size = volatility * prev_close * np.random.uniform(0.2, 1.5)
        h = body_high + wick_size * np.random.uniform(0, 1)
        l = body_low - wick_size * np.random.uniform(0, 1)
        opens.append(o); highs.append(h); lows.append(l)

    volumes = np.random.lognormal(10, 0.5, n)

    end_time = pd.Timestamp.now().floor('h')
    timestamps = pd.date_range(
        end=end_time, periods=n, freq=f'{tf_minutes}min'
    )

    df = pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows, 'close': closes, 'volume': volumes
    }, index=timestamps)
    df.index.name = 'timestamp'
    return df


def main():
    print("━" * 70)
    print("  EFLOUD BOT v2 — Offline Test (Synthetic ETH/USDT)")
    print("━" * 70)

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
            "min_confluence": 40,  # Düşük eşik — test için
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

    # Synthetic data üret — 3 TF
    print("\n📡 Generating synthetic OHLCV data...")
    df_entry = gen_synthetic_ohlcv(n=500, tf_minutes=15, seed=42,
                                     drift=0.0003, volatility=0.006)
    df_mtf = gen_synthetic_ohlcv(n=300, tf_minutes=60, seed=42,
                                   drift=0.0003, volatility=0.006)
    df_htf = gen_synthetic_ohlcv(n=200, tf_minutes=240, seed=42,
                                   drift=0.0003, volatility=0.006)
    df_daily = gen_synthetic_ohlcv(n=90, tf_minutes=1440, seed=42,
                                     drift=0.0003, volatility=0.015)

    print(f"  15m: {len(df_entry)} bars | Price range: "
          f"${df_entry['low'].min():.2f}-${df_entry['high'].max():.2f}")
    print(f"   1h: {len(df_mtf)} bars")
    print(f"   4h: {len(df_htf)} bars")
    print(f"   1d: {len(df_daily)} bars")
    print(f"\n   Current price: ${df_entry['close'].iloc[-1]:,.2f}")

    # Orchestrator
    print(f"\n🧠 Running orchestrator cycle...")
    print("─" * 70)
    import tempfile
    orch = SafeOrchestrator(config, state_dir=tempfile.mkdtemp(prefix="efloud_test_"))
    result = orch.run_cycle(
        symbol="ETH/USDT",
        df_htf=df_htf, df_mtf=df_mtf, df_entry=df_entry,
        df_daily=df_daily,
    )

    print("\n" + "═" * 70)
    print("  SUMMARY")
    print("═" * 70)
    print(f"  Symbol:           {result.symbol}")
    print(f"  Current price:    ${result.current_price:,.2f}")
    print(f"  HTF bias:         {result.htf_bias}")
    print(f"  Levels extracted: {len(result.levels)}")
    for l in result.levels[:8]:
        print(f"    {l}")
    print(f"  Stacked zones:    {len(result.stacked_zones)}")
    for z in result.stacked_zones[:3]:
        print(f"    ★ {z.bottom:.2f}-{z.top:.2f} ({z.label})")
    print(f"  Intent:           {result.intent.label} ({result.intent.score}/100)")
    print(f"    body={result.intent.body_ratio:.2f} vol={result.intent.volume_ratio:.1f}x "
          f"streak={result.intent.consecutive}")
    print(f"  Signals:          {len(result.signals)}")
    if result.signals:
        last = result.signals[-1]
        print(f"    Latest: {last.direction} @ {last.entry:.2f} | Conf={last.confluence}")
    print(f"  Active scenarios: {len(result.scenarios)}")
    for s in result.scenarios:
        print(f"    [{s.kind}] {s.name} — {s.state}")
    print(f"  Actions taken:    {result.actions_taken}")

    print("\n" + "═" * 70)
    print("  EFLOUD STYLE REPORT")
    print("═" * 70)
    print(result.report_md)


if __name__ == "__main__":
    main()
