# Task Brief: Task 4

## Task 4: Sync main.py CLI Loop with Candle-Close Logic

**Files:**
- Modify: `main.py` — loop timing logic
- Test: Manual verification (CLI smoke test)

**Interfaces:**
- Consumes: `_timeframe_ms` from `exchange`
- Produces: No API changes

**Description:** Apply same candle-close synchronization to CLI execution loop in `main.py` so local runs behave consistently with daemon runner.

- [ ] **Step 1: Identify existing loop logic**

Open `main.py` and locate the main execution loop (search for `while True:` or `while running:`). Note how sleep/scanning currently works.

- [ ] **Step 2: Apply same gating pattern**

Add similar logic:
```python
from exchange import _timeframe_ms

# In main():
last_scan_candle_ts = 0
entry_tf_ms = _timeframe_ms(config.timeframes['entry'])

while True:
    current_ms = int(time.time() * 1000)
    candle_ts = (current_ms - 2000) // entry_tf_ms

    if candle_ts > last_scan_candle_ts:
        print(f"Candle boundary detected: running scan")
        last_scan_candle_ts = candle_ts
        # ... existing scan logic

    time.sleep(config.check_interval_sec)
```

- [ ] **Step 3: Manual smoke test**

Run: `python main.py --dry-run --config configs/config.testnet.yaml`

Expected: Scan logs appear at :02 seconds after :00, :15, :30, :45 minute marks.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(main): add candle-close sync to CLI loop"
```
