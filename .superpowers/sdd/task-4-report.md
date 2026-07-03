# Task 4 Report: Sync main.py CLI Loop with Candle-Close Logic

**Status:** ✅ DONE (Already Implemented)

## Summary

The candle-close synchronization feature was **already implemented** in `main.py` (lines 391-411 in `run_cycle` function). All requirements from the brief are present and working correctly.

## Implementation Verification

### Requirements Checklist (from brief)

1. ✅ **Import `_timeframe_ms` from `exchange`**: Present at line 391
   ```python
   from exchange import _timeframe_ms
   ```

2. ✅ **Track `last_scan_candle_ts`**: Variable `last_scan_ts` passed to `run_cycle` (line 716, 378, 417)
   ```python
   last_scan_ts = 0  # line 716 - main loop initialization
   last_scan_ts = run_cycle(..., last_scan_ts)  # line 722 - pass and receive updated value
   return last_scan_ts  # line 417 - run_cycle returns updated timestamp
   ```

3. ✅ **Gate scan with candle boundary check**: Present at lines 398-411 in `run_cycle`
   ```python
   now_ms = int(time.time() * 1000)
   current_candle_ts = ((now_ms - 2000) // entry_tf_ms) * entry_tf_ms

   if last_scan_ts == 0 or current_candle_ts > last_scan_ts:
       scan_mode = cfg["operation"].get("symbol_scan_mode", "sequential")
       log.info(f"⏳ New entry candle closed (boundary: {current_candle_ts} ms). Scanning symbol universe...")
       # ... scan logic
       last_scan_ts = current_candle_ts
   ```

## Test Results

### Manual Smoke Test (passed)

```bash
✓ Test 1 PASS: Candle boundary detection working
✓ Test 2 PASS: Scan only runs on new candles
✓ Test 3 PASS: CLI runs without errors
```

### Test Behavior Verified

1. **First cycle runs**: `last_scan_ts == 0` bypasses skip check (line 401)
2. **Candle boundary detected**: Log message "⏳ New entry candle closed" appears at line 403
3. **Scan executes**: Full symbol universe scan runs (lines 406-409)
4. **Timestamp updated**: `last_scan_ts` updated and returned (line 411)

### Log Output (Smoke Test)

```
2026-06-25 08:03:08,270 | efloud.main | INFO | ═══ Cycle #1 ═══
2026-06-25 08:03:08,270 | efloud.main | INFO | ⏳ New entry candle closed (boundary: 1782349200000 ms). Scanning symbol universe...
2026-06-25 08:03:08,270 | efloud.main | INFO | 📡 Watchlist (20 symbols): BTC/USDT, ETH/USDT, ...
```

## Implementation Details

### Candle Boundary Calculation

- **Formula**: `current_candle_ts = ((now_ms - 2000) // entry_tf_ms) * entry_tf_ms`
- **Buffer**: 2 seconds after candle close (allows Binance backend processing)
- **Scan condition**: `last_scan_ts == 0 or current_candle_ts > last_scan_ts` (inverse of bot_runner's early-return pattern)

### Comparison with bot_runner.py

**bot_runner.py (lines 492-497)**: Early-return pattern
```python
if self.last_scan_candle_ts != 0 and current_candle_ts <= self.last_scan_candle_ts:
    return
self.last_scan_candle_ts = current_candle_ts
```

**main.py (lines 401-411)**: Scan-gate pattern (equivalent logic)
```python
if last_scan_ts == 0 or current_candle_ts > last_scan_ts:
    # scan logic
    last_scan_ts = current_candle_ts
```

Both achieve identical behavior: only scan when a new entry candle closes.

### Example (15m timeframe = 900000 ms)

| Scenario | now_ms | current_candle_ts | Action |
|----------|--------|-------------------|--------|
| First cycle (last=0) | 90,045,000 | 90,000,000 | Scan (bypass check) |
| Mid-candle (45s in) | 90,045,000 | 90,000,000 | Skip (same candle) |
| At boundary + 2s | 90,902,000 | 90,900,000 | Scan (new candle) |

## Safety & Correctness

- ✅ **No safety guard weakening**: Purely additive timing optimization
- ✅ **Preserves existing loop logic**: Wraps scan inside `run_cycle`, doesn't replace main loop
- ✅ **Error handling**: Invalid timeframe defaults to 15m with logging (lines 394-396)
- ✅ **CLI reconcile sync preserved**: Runs before candle check (line 385)
- ✅ **Position checks preserved**: Run after scan regardless of candle state (lines 414-415)

## Files

- **Verified**: `main.py` (implementation already present at lines 391-411, 716-722)
- **Test**: Manual smoke test passed (30-second run)

## Commits

**No new commits required** — implementation already present in codebase at lines 391-411.

## Parity with bot_runner

The CLI loop now has parity with the FastAPI daemon (`bot_runner.py`):
- Both use `_timeframe_ms` for timeframe conversion
- Both calculate candle boundaries with 2-second buffer
- Both skip mid-candle scans to save API weight
- Both always run first scan (initial state bypass)
- Both preserve existing logic (CLI reconcile, position checks)

## Conclusion

Task 4 is **DONE**. The candle-close synchronization was already implemented in `main.py` with the same logic pattern as `bot_runner.py` (inverse condition, equivalent behavior). Manual smoke testing confirms the feature works correctly.
