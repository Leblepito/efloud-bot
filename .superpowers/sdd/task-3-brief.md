# Task Brief: Task 3

## Task 3: Add Candle-Close Synchronization to bot_runner

**Files:**
- Modify: `backend/bot_runner.py` — add import, init state, modify `_scan_universe`
- Test: `tests/test_bot_runner_candle_sync.py`

**Interfaces:**
- Consumes: `_timeframe_ms` from `exchange` (converts '15m' → 900000 ms)
- Produces: No API changes — internal gating only

**Description:** Track last scanned candle timestamp. Only fetch candles and run SMC signal scan when `(current_ms - 2000) // tf_ms > last_scan_ts`. This aligns scans to 2 seconds after each 15m candle close.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bot_runner_candle_sync.py`:

```python
import pytest
import time
from unittest.mock import Mock, patch
from backend.bot_runner import BotRunner

def test_candle_close_sync_skips_scan_inside_candle():
    """Verify that scan is skipped when called mid-candle (not at boundary+2s)."""
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}

    mock_exchange = Mock()

    with patch('backend.bot_runner.Exchange', return_value=mock_exchange):
        runner = BotRunner(config=mock_config)
        runner.last_scan_candle_ts = 100  # Initialized to candle index 100

        # Current time: 100 * 900000ms + 45000ms (mid-candle)
        # (current - 2000) // 900000 = 100 (same as last_scan_ts)
        current_ms = 100 * 900000 + 45000

        with patch('time.time', return_value=current_ms / 1000):
            with patch.object(runner, '_scan_universe_inner', Mock()) as mock_inner:
                runner._scan_universe()

                # Should NOT scan because we're inside the same candle
                mock_inner.assert_not_called()
                assert runner.last_scan_candle_ts == 100  # Unchanged

def test_candle_close_sync_runs_scan_at_boundary():
    """Verify that scan runs when called at candle boundary + 2s."""
    mock_config = Mock()
    mock_config.check_interval_sec = 10
    mock_config.timeframes = {'entry': '15m'}

    mock_exchange = Mock()

    with patch('backend.bot_runner.Exchange', return_value=mock_exchange):
        runner = BotRunner(config=mock_config)
        runner.last_scan_candle_ts = 100  # Last scanned candle 100

        # Current time: (101 * 900000ms) + 2000ms (boundary + 2s)
        # (current - 2000) // 900000 = 101 (NEW candle)
        current_ms = 101 * 900000 + 2000

        with patch('time.time', return_value=current_ms / 1000):
            with patch.object(runner, '_scan_universe_inner', Mock()) as mock_inner:
                runner._scan_universe()

                # Should scan because we're at candle boundary + 2s
                mock_inner.assert_called_once()
                assert runner.last_scan_candle_ts == 101  # Updated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_runner_candle_sync.py -v`

Expected: FAIL (last_scan_candle_ts and gating logic not yet implemented)

- [ ] **Step 3: Write minimal implementation**

In `backend/bot_runner.py`:

1. Add import at top:
```python
from exchange import _timeframe_ms
```

2. In `BotRunner.__init__`, add:
```python
self.last_scan_candle_ts = 0
```

3. In `_scan_universe`, wrap the existing scan logic with:

```python
def _scan_universe(self):
    """Scan universe only at candle close + 2s boundary."""
    entry_tf_ms = _timeframe_ms(self.config.timeframes['entry'])
    current_ms = int(time.time() * 1000)
    candle_ts = (current_ms - 2000) // entry_tf_ms

    if candle_ts > self.last_scan_candle_ts:
        log.info(f"Candle boundary detected: candle_ts={candle_ts}, running scan")
        self.last_scan_candle_ts = candle_ts

        # Existing scan logic here (call _scan_universe_inner or inline logic)
        # ... (preserve existing implementation)
    else:
        log.debug(f"Skipping scan: inside candle {candle_ts}, next scan at boundary+2s")
```

Note: Preserve all existing `_scan_universe` logic — wrap only with the gating condition.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_runner_candle_sync.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/bot_runner.py tests/test_bot_runner_candle_sync.py
git commit -m "feat(runner): add candle-close synchronization to scan timing"
```
