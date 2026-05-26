import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from backtest.cli import _load_data_for_period

def prepare_optimization_data(symbols=None, period_days=30):
    if symbols is None:
        symbols = ["SOL/USDT"]
    
    print(f"[autoresearch] Preparing optimization data for {symbols} over {period_days} days...")
    
    # SOTA standard timeframes: HTF (4h), MTF (1h), Entry (15m), and Daily (1d)
    timeframes = ["4h", "1h", "15m", "1d"]
    
    try:
        data = _load_data_for_period(
            symbols=symbols,
            timeframes=timeframes,
            period_days=period_days,
            cache_dir=str(ROOT / "cache" / "ohlcv"),
            verify_sha=False  # Speed up load for optimization iterations
        )
        print(f"[autoresearch] Success: Data successfully loaded for {len(data)} symbols.")
        return data
    except Exception as e:
        print(f"[autoresearch] Error loading data: {e}")
        print("[autoresearch] Please run prefetch_data first or check your symbols list.")
        sys.exit(1)

if __name__ == "__main__":
    prepare_optimization_data()
