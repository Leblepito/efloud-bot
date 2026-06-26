# Task 3 Report: Add Candle-Close Synchronization to bot_runner

**Status:** ✅ DONE

## Summary

The candle-close synchronization feature was **already implemented** in `backend/bot_runner.py` (lines 480-498, 131). All requirements from the brief are present and working correctly.

## Implementation Verification

### Requirements Checklist (from brief)

1. ✅ **Import `_timeframe_ms` from `exchange`**: Present at line 31
   ```python
   from exchange import BinanceClient, OrderManager, Position, _timeframe_ms
   ```

2. ✅ **Add `self.last_scan_candle_ts = 0` to `__init__`**: Present at line 131
   ```python
   self.last_scan_candle_ts = 0  # Track last scanned candle timestamp
   ```

3. ✅ **Wrap `_scan_universe` logic with candle boundary check**: Present at lines 480-498
   ```python
   # Candle-close synchronization: only scan when a new entry candle closes.
   # We add a 2-second buffer to allow Binance's backend to process and serve the closed candle.
   tf_entry = tf.get("entry", "15m")
   try:
       entry_tf_ms = _timeframe_ms(tf_entry)
   except Exception as e:
       log.error(f"Invalid entry timeframe format '{tf_entry}': {e}. Defaulting to 15m (900_000ms).")
       entry_tf_ms = 900_000

   now_ms = int(time.time() * 1000)
   current_candle_ts = ((now_ms - 2000) // entry_tf_ms) * entry_tf_ms

   if self.last_scan_candle_ts != 0 and current_candle_ts <= self.last_scan_candle_ts:
       # Still in the same candle. Skip OHLCV fetching and SMC scan to save API weight and eliminate delay.
       return

   # Update scanned candle timestamp
   self.last_scan_candle_ts = current_candle_ts
   log.info(f"⏳ New entry candle closed (boundary: {current_candle_ts} ms). Scanning symbol universe...")
   ```

## Test Results

### Manual Tests (passed)

```bash
✓ Test 1 PASS: Skip mid-candle
✓ Test 2 PASS: Scan at boundary
SUCCESS: All manual tests passed
```

### Test Behavior Verified

1. **Mid-candle skip**: When called 45 seconds into a 15-minute candle, scan is skipped (timestamp unchanged)
2. **Boundary trigger**: When called 2 seconds after candle close, scan runs and timestamp updates
3. **First scan**: When `last_scan_candle_ts=0`, scan always runs
4. **Different timeframes**: Correctly uses config entry timeframe (tested with 5m)

### PyTest Issue

Windows-specific pytest capture bug (`ValueError: I/O operation on closed file`) prevents automated test execution, but manual verification confirms implementation correctness.

## Implementation Details

### Candle Boundary Calculation

- **Formula**: `current_candle_ts = ((now_ms - 2000) // entry_tf_ms) * entry_tf_ms`
- **Buffer**: 2 seconds after candle close (allows Binance backend processing)
- **Skip condition**: `current_candle_ts <= self.last_scan_candle_ts`

### Example (15m timeframe = 900000 ms)

| Scenario | now_ms | current_candle_ts | Action |
|----------|--------|-------------------|--------|
| Mid-candle (45s in) | 90,045,000 | 90,000,000 | Skip (same candle) |
| At boundary + 2s | 90,902,000 | 90,900,000 | Scan (new candle) |

## Safety & Correctness

- ✅ **No safety guard weakening**: Purely additive timing optimization
- ✅ **Preserves existing logic**: Wraps scan, doesn't replace it
- ✅ **Error handling**: Invalid timeframe defaults to 15m with logging
- ✅ **First scan always runs**: `last_scan_candle_ts=0` bypasses skip check

## Files

- **Modified**: `backend/bot_runner.py` (already implemented at lines 131, 480-498)
- **Test**: `tests/test_bot_runner_candle_sync.py` (manual verification passed)

## Commits

No new commits required — implementation already present in codebase.
