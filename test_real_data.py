"""
Real data test — Binance Futures'tan canlı ETH/USDT verisi çeker.
Orchestrator'ı gerçek piyasa koşullarıyla test eder.

Çalıştırma:
  python test_real_data.py              # ETH default
  python test_real_data.py BTC/USDT     # Başka pair
  python test_real_data.py ETH/USDT 5m  # Farklı entry TF
"""

import sys
import logging
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s'
)
log = logging.getLogger("test_real")

import pandas as pd
import ccxt

from engine import EfloudOrchestrator


def fetch_binance(symbol: str, timeframe: str, limit: int = 500,
                   market_type: str = "future") -> pd.DataFrame:
    """Binance'den OHLCV çek. Futures veya spot."""
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": market_type},
    })
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


def get_tf_config(entry_tf: str) -> dict:
    """Entry TF'ye göre HTF/MTF seçimi."""
    configs = {
        "5m":  {"htf": "1h",  "mtf": "15m", "entry": "5m"},
        "15m": {"htf": "4h",  "mtf": "1h",  "entry": "15m"},
        "1h":  {"htf": "4h",  "mtf": "1h",  "entry": "1h"},
        "4h":  {"htf": "1d",  "mtf": "4h",  "entry": "4h"},
    }
    return configs.get(entry_tf, configs["15m"])


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ETH/USDT"
    entry_tf = sys.argv[2] if len(sys.argv) > 2 else "15m"
    tfs = get_tf_config(entry_tf)

    print("━" * 70)
    print(f"  EFLOUD BOT v2 — Real Data Test ({symbol} / {entry_tf})")
    print("━" * 70)

    config = {
        "exchange": {"leverage": 1},
        "timeframes": tfs,
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

    print(f"\n📡 Fetching {symbol} data from Binance Futures...")
    print(f"   Chain: {tfs['entry']} → {tfs['mtf']} → {tfs['htf']}")

    try:
        df_htf = fetch_binance(symbol, tfs["htf"], 300)
        time.sleep(0.3)
        df_mtf = fetch_binance(symbol, tfs["mtf"], 300)
        time.sleep(0.3)
        df_entry = fetch_binance(symbol, tfs["entry"], 500)
        time.sleep(0.3)
        df_daily = fetch_binance(symbol, "1d", 100)
        time.sleep(0.3)
        df_weekly = fetch_binance(symbol, "1w", 60)
        time.sleep(0.3)
        try:
            df_monthly = fetch_binance(symbol, "1M", 30)
        except Exception as e:
            log.warning(f"Monthly fetch failed (non-critical): {e}")
            df_monthly = None
    except Exception as e:
        log.error(f"Data fetch failed: {e}")
        print("\n❌ Binance bağlantısı başarısız. Network / SSL sorunu olabilir.")
        print("   Alternatif: test_offline.py (synthetic data)")
        return 1

    current_price = df_entry["close"].iloc[-1]
    print(f"\n   Current {symbol}: ${current_price:,.2f}")
    print(f"   {tfs['entry']}: {len(df_entry)} bars | range "
          f"${df_entry['low'].min():,.2f}-${df_entry['high'].max():,.2f}")
    print(f"   {tfs['mtf']}: {len(df_mtf)} bars")
    print(f"   {tfs['htf']}: {len(df_htf)} bars")
    print(f"    1d: {len(df_daily)} bars")
    print(f"    1w: {len(df_weekly)} bars")
    if df_monthly is not None:
        print(f"    1M: {len(df_monthly)} bars")

    # Orchestrator
    print(f"\n🧠 Running orchestrator cycle...")
    print("─" * 70)
    orch = EfloudOrchestrator(config)
    result = orch.run_cycle(
        symbol=symbol,
        df_htf=df_htf, df_mtf=df_mtf, df_entry=df_entry,
        df_daily=df_daily, df_weekly=df_weekly, df_monthly=df_monthly,
    )

    print("\n" + "═" * 70)
    print("  SUMMARY")
    print("═" * 70)
    print(f"  Symbol:           {result.symbol}")
    print(f"  Current price:    ${result.current_price:,.2f}")
    print(f"  HTF bias:         {result.htf_bias}")
    print(f"  Levels extracted: {len(result.levels)}")
    for l in result.levels[:10]:
        print(f"    {l}")
    if len(result.levels) > 10:
        print(f"    ... and {len(result.levels) - 10} more")
    print(f"  Stacked zones:    {len(result.stacked_zones)}")
    for z in result.stacked_zones[:5]:
        print(f"    ★ ${z.bottom:,.2f}-${z.top:,.2f} ({z.label})")
    print(f"  Intent:           {result.intent.label} ({result.intent.score}/100)")
    print(f"    body={result.intent.body_ratio:.2f} vol={result.intent.volume_ratio:.1f}x "
          f"streak={result.intent.consecutive}")
    print(f"  Signals:          {len(result.signals)}")
    if result.signals:
        last = result.signals[-1]
        print(f"    Latest: {last.direction} @ ${last.entry:,.2f} | Conf={last.confluence}")
    print(f"  Active scenarios: {len(result.scenarios)}")
    for s in result.scenarios:
        print(f"    [{s.kind:13}] {s.name} — {s.state}")
    print(f"  Actions taken:    {result.actions_taken}")

    # Raporu dosyaya yaz
    report_file = Path(f"reports/{symbol.replace('/', '_')}_{entry_tf}_"
                       f"{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.md")
    report_file.parent.mkdir(exist_ok=True)
    report_file.write_text(result.report_md, encoding="utf-8")
    print(f"\n📄 Report saved: {report_file}")

    print("\n" + "═" * 70)
    print("  EFLOUD STYLE REPORT")
    print("═" * 70)
    print(result.report_md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
