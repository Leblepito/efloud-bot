import json
import os
import time
import math
from pathlib import Path
import pandas as pd
from scripts.routines.runner import register
from scripts.routines._base import RoutineResult, now_utc

def dedup_candles(rows):
    seen = {}
    for r in rows:
        symbol = r.get("symbol")
        ts = r.get("ts")
        src = r.get("src") or r.get("source")
        key = (symbol, ts, src)
        if key not in seen:
            seen[key] = r
    return list(seen.values())

def detect_gaps(ts, step_ms):
    if not ts:
        return []
    sorted_ts = sorted(ts)
    missing = []
    for i in range(1, len(sorted_ts)):
        diff = sorted_ts[i] - sorted_ts[i-1]
        if diff > step_ms:
            curr = sorted_ts[i-1] + step_ms
            while curr < sorted_ts[i]:
                missing.append(curr)
                curr += step_ms
    return missing

def score_market(metrics, thresholds):
    breaches = []
    symbol = metrics.get("symbol", "all")
    
    # Open Interest spike check
    oi_change = float(metrics.get("oi_change_4h_pct", 0) or 0)
    oi_thresh = float(thresholds.get("oi_spike_pct_4h", 10.0) or 10.0)
    if oi_change > oi_thresh:
        breaches.append({
            "severity": "warn",
            "key": f"oi_spike:{symbol}",
            "title": f"Open Interest Spike: {symbol}",
            "body": f"4h Open Interest changed by {oi_change:.2f}% (Limit: {oi_thresh:.2f}%)"
        })
        
    # Funding rate elevated check
    funding = float(metrics.get("funding_8h", 0) or metrics.get("funding_rate_8h", 0) or 0)
    funding_thresh = float(thresholds.get("funding_rate_elevated_8h", 0.001) or 0.001)
    if abs(funding) > funding_thresh:
        breaches.append({
            "severity": "warn",
            "key": f"funding_elevated:{symbol}",
            "title": f"Elevated Funding Rate: {symbol}",
            "body": f"8h Funding rate is {funding:.6f} (Limit: {funding_thresh:.6f})"
        })
        
    return breaches

@register("market_collect")
def run(client=None, alert=None, cfg=None):
    from scripts.routines._base import write_snapshot, write_report, load_config
    from scripts.routines._thresholds import derive
    from data.cache import OHLCVCache
    
    config = cfg if cfg is not None else load_config()
    thresholds = derive(config)
    
    symbols = config.get("symbols", ["BTC/USDT"])
    now_ts = time.time()
    now_ms = int(now_ts * 1000)
    
    # Prepare directories
    Path("data/market").mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(parents=True, exist_ok=True)
    
    # 1. COLLECT & STORE
    new_candles = []
    market_metrics = []
    breaches = []
    
    # Check rate limit weight header if client has last response headers
    weight = 0
    headers = getattr(client, "last_response_headers", {}) or {}
    for k, v in headers.items():
        if "weight" in k.lower():
            try:
                weight = int(v)
            except ValueError:
                pass
                
    for symbol in symbols:
        try:
            # Fetch latest funding rate & open interest
            funding_info = client.fetch_funding_rate(symbol)
            funding_rate = float(funding_info.get("fundingRate", 0.0) or 0.0)
            
            oi_info = client.fetch_open_interest(symbol)
            open_interest = float(oi_info.get("openInterestAmount", 0.0) or 0.0)
            
            # Calculate 4h OI change using funding_oi.jsonl history
            old_oi = None
            funding_oi_path = "data/market/funding_oi.jsonl"
            four_hours_ago = now_ts - 4 * 3600
            best_diff = float("inf")
            
            if os.path.exists(funding_oi_path):
                with open(funding_oi_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("symbol") == symbol:
                                t_val = entry.get("timestamp", 0)
                                diff = abs(t_val - four_hours_ago)
                                if diff < best_diff and diff < 30 * 60: # within 30 mins
                                    best_diff = diff
                                    old_oi = float(entry.get("open_interest", 0.0))
                        except Exception:
                            pass
                            
            oi_change_4h_pct = 0.0
            if old_oi and old_oi > 0:
                oi_change_4h_pct = (open_interest - old_oi) / old_oi * 100
                
            metrics = {
                "symbol": symbol,
                "timestamp": now_ts,
                "funding_8h": funding_rate,
                "open_interest": open_interest,
                "oi_change_4h_pct": oi_change_4h_pct,
                "weight": weight
            }
            market_metrics.append(metrics)
            
            # Append to jsonl
            with open(funding_oi_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(metrics) + "\n")
                
            # Score this symbol
            breaches.extend(score_market(metrics, thresholds))
            
            # Fetch OHLCV (1m and 5m)
            # Fetch last 30 candles
            for tf in ["1m", "5m"]:
                candles = client.fetch_ohlcv(symbol, timeframe=tf, limit=30)
                tf_ms = 60000 if tf == "1m" else 300000
                
                # Filter closed candles
                for c in candles:
                    c_ts = c[0]
                    if c_ts <= now_ms - tf_ms: # closed
                        new_candles.append({
                            "symbol": symbol,
                            "ts": c_ts,
                            "src": tf,
                            "open": c[1],
                            "high": c[2],
                            "low": c[3],
                            "close": c[4],
                            "volume": c[5]
                        })
                        
        except Exception as e:
            print(f"Error collecting market data for {symbol}: {e}")
            
    # 2. STORE OHLCV
    parquet_path = "data/market/ohlcv_24h.parquet"
    new_df = pd.DataFrame(new_candles)
    
    if os.path.exists(parquet_path):
        try:
            old_df = pd.read_parquet(parquet_path)
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
        except Exception:
            combined_df = new_df
    else:
        combined_df = new_df
        
    if not combined_df.empty:
        # Deduplicate
        combined_df.drop_duplicates(subset=["symbol", "ts", "src"], inplace=True)
        
        # Flush older rows (older than 24h) to cache/ohlcv
        limit_ts = now_ms - 24 * 3600 * 1000
        active_df = combined_df[combined_df["ts"] >= limit_ts]
        old_rows_df = combined_df[combined_df["ts"] < limit_ts]
        
        # Write active df back to rolling parquet
        active_df.to_parquet(parquet_path)
        
        # Flush old rows
        if not old_rows_df.empty:
            cache = OHLCVCache(Path("cache/ohlcv"))
            for (symbol, tf), group in old_rows_df.groupby(["symbol", "src"]):
                cached_df = cache.get(symbol, tf)
                if cached_df is not None:
                    # Convert index to 'ts' column or index for merge
                    # Let's see: OHLCVCache.put takes df with DatetimeIndex or RangeIndex?
                    # prefetch_data.py passes result.df, which has ts/open/high/low/close/volume.
                    # Let's set index of group to datetime or ts if needed, or keep unified.
                    # Let's merge on ts
                    group_clean = group[["ts", "open", "high", "low", "close", "volume"]]
                    if isinstance(cached_df.index, pd.DatetimeIndex):
                        group_clean.index = pd.to_datetime(group_clean["ts"], unit="ms")
                        group_clean = group_clean.drop(columns=["ts"])
                    else:
                        # cached_df uses ts column or RangeIndex
                        pass
                    
                    combined_cache = pd.concat([cached_df, group_clean])
                    if isinstance(combined_cache.index, pd.DatetimeIndex):
                        combined_cache = combined_cache[~combined_cache.index.duplicated(keep="first")]
                    else:
                        combined_cache.drop_duplicates(subset=["ts"], inplace=True)
                    
                    cache.put(symbol, tf, combined_cache)
                else:
                    # No existing cache, write new cache
                    group_clean = group[["ts", "open", "high", "low", "close", "volume"]]
                    group_clean.index = pd.to_datetime(group_clean["ts"], unit="ms")
                    group_clean = group_clean.drop(columns=["ts"])
                    cache.put(symbol, tf, group_clean)
                    
    # 3. SURFACE & HYGIENE (D2)
    # Daily hygiene check if it's time (every 24h, or run on every loop but write report)
    # We can detect gaps in the last 24h
    hygiene_lines = ["# Market Data Hygiene Report", ""]
    has_gaps = False
    
    if not combined_df.empty:
        for (symbol, tf), group in combined_df.groupby(["symbol", "src"]):
            ts_list = group["ts"].tolist()
            step = 60000 if tf == "1m" else 300000
            gaps = detect_gaps(ts_list, step)
            if gaps:
                has_gaps = True
                hygiene_lines.append(f"### Gap in {symbol} ({tf})")
                hygiene_lines.append(f"Detected {len(gaps)} missing bars. Timestamps: {gaps[:5]}")
                
            # OHLC sanity checks
            bad_ohlc = group[
                (group["high"] < group["open"]) |
                (group["high"] < group["close"]) |
                (group["low"] > group["open"]) |
                (group["low"] > group["close"])
            ]
            if not bad_ohlc.empty:
                hygiene_lines.append(f"### OHLC Sanity Failure in {symbol} ({tf})")
                hygiene_lines.append(f"Found {len(bad_ohlc)} rows with invalid high/low values.")
                
    if not has_gaps:
        hygiene_lines.append("No gaps or OHLC sanity issues detected in the 24h dataset.")
        
    write_report("reports/market_hygiene.md", "\n".join(hygiene_lines))
    
    # Write 24h market report
    report_lines = [
        "# 24h Market Collection Report",
        f"**Last Checked:** {now_utc().isoformat()}",
        "",
        "## Symbol Metrics",
        "| Symbol | Funding Rate (8h) | Open Interest | 4h OI Change |",
        "| --- | --- | --- | --- |"
    ]
    for m in market_metrics:
        report_lines.append(f"| {m['symbol']} | {m['funding_8h']:.6f} | {m['open_interest']:.2f} | {m['oi_change_4h_pct']:.2f}% |")
        
    write_report("reports/market_24h.md", "\n".join(report_lines))
    
    # Save snapshot
    write_snapshot("state/market_snapshot.json", {
        "metrics": market_metrics,
        "breaches_count": len(breaches)
    })
    
    return RoutineResult(
        name="market_collect",
        ok=True,
        breaches=breaches,
        report_path="reports/market_24h.md"
    )
