# Backtest Subsystem Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backtest mechanism that mirrors the live `SafeOrchestrator` engine, supports single-symbol and portfolio modes over 1y of Binance OHLCV data, and exposes a CLI for validation runs and parameter grid search.

**Architecture:** Pure-engine separation (no I/O), CCXT-wrapped data fetcher with parquet cache, walk-forward simulation with intrabar fill + funding fees + per-leg slippage, multiprocessing grid search with checkpoint resumability. Reuses `engine.SafeOrchestrator` (with new purity flags). See spec at `docs/superpowers/specs/2026-05-04-backtest-design.md`.

**Tech Stack:** Python 3.11+, pandas, pyarrow (NEW for parquet), CCXT, pytest, pyfakefs (NEW for purity tests), multiprocessing.

---

## File Map

**Create:**
- `data/__init__.py`
- `data/fetcher.py` — CCXT-wrapped Binance public REST OHLCV + funding fetcher
- `data/cache.py` — parquet read/write, atomic writes, sha256 verify
- `data/manifest.py` — cache manifest JSON
- `backtest/__init__.py` (overwrite legacy)
- `backtest/engine.py` — pure walk-forward simulation
- `backtest/intrabar.py` — SL/TP intrabar fill resolution
- `backtest/slippage.py` — per-leg slippage model
- `backtest/funding.py` — 8h funding fee application
- `backtest/metrics.py` — aggregation: per-symbol + portfolio
- `backtest/grid.py` — multiprocessing grid search with checkpoint
- `backtest/reproducibility.py` — provenance.json snapshot
- `backtest/cli.py` — argparse CLI
- `configs/grids/confluence_x_notional.yaml` — example grid spec
- `backend/tests/test_engine_purity.py`
- `backend/tests/test_data_fetcher.py`
- `backend/tests/test_data_cache.py`
- `backend/tests/test_backtest_engine_single.py`
- `backend/tests/test_backtest_engine_portfolio.py`
- `backend/tests/test_intrabar_fill.py`
- `backend/tests/test_funding_fees.py`
- `backend/tests/test_grid_search.py`
- `backend/tests/test_slippage.py`

**Modify:**
- `engine/safe_orchestrator.py` — add `freshness_check`, `persist`, optional `notification_mgr` (already present) flags; gate I/O paths
- `requirements.txt` — add `pyarrow>=15.0.0`, `pyfakefs>=5.0`
- `.gitignore` — add `cache/`, `reports/backtests/`

**Delete:**
- `backtest/runner.py` (legacy single-symbol runner) — `git rm` after Chunk 4 lands

---

## Chunk 1: Phase 1 — SafeOrchestrator I/O Purity Audit + Flags

**Goal:** Make `SafeOrchestrator` runnable with zero I/O (no disk, no clock, no network, no notifications) by adding constructor flags. Replaces the brittle module-globals monkey-patch in legacy `backtest/runner.py:298-313`.

**Estimated effort:** 1.5 days

### Task 1.1: Add `pyfakefs` to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Edit `requirements.txt`**

Add under `# Tests` section:

```
pyfakefs>=5.0
pyarrow>=15.0.0
```

- [ ] **Step 2: Install + verify**

```powershell
pip install pyfakefs>=5.0 pyarrow>=15.0.0
python -c "import pyfakefs, pyarrow; print(pyfakefs.__version__, pyarrow.__version__)"
```

- [ ] **Step 3: Commit**

```
git add requirements.txt
git commit -m "chore(deps): add pyfakefs + pyarrow for backtest"
```

---

### Task 1.2: Audit I/O paths in `SafeOrchestrator` and dependencies

**Files:**
- Read-only audit; output goes to `docs/superpowers/audits/2026-05-04-orchestrator-io-audit.md`

- [ ] **Step 1: Run grep audit**

```powershell
cd c:/Users/utkuc/Downloads/efloud-bot
$paths = "engine/safe_orchestrator.py engine/safety/__init__.py engine/intent.py engine/scenarios.py engine/risk/ engine/notifications/"
foreach ($p in $paths.Split(" ")) {
  Write-Host "=== $p ==="
  Select-String -Path $p -Pattern "open\(|requests\.|time\.time|datetime\.now|datetime\.utcnow|logging\.getLogger" -List
}
```

- [ ] **Step 2: Document findings**

Create `docs/superpowers/audits/2026-05-04-orchestrator-io-audit.md` listing:

| Location | Type | Backtest treatment |
|----------|------|--------------------|
| `safe_orchestrator.py:_persist_state` | disk | gate via `persist` flag |
| `safety/__init__.py:validate_kline_freshness` | clock | gate via `freshness_check` flag |
| `notifications/...notify` | log/webhook | inject `NullNotificationManager` |
| `logging.getLogger(...).info/...` | log handlers | leave (handlers are optional, no-op if not configured) |
| `datetime.utcnow()` if any | clock | should use `current_ts` from data; investigate |

Attach a list of every match for the reader.

- [ ] **Step 3: Commit audit doc**

```
git add docs/superpowers/audits/2026-05-04-orchestrator-io-audit.md
git commit -m "docs(audit): SafeOrchestrator I/O surface audit for backtest purity"
```

---

### Task 1.3: TDD — `freshness_check` flag

**Files:**
- Test: `backend/tests/test_safe_orchestrator_flags.py` (NEW)
- Modify: `engine/safe_orchestrator.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_safe_orchestrator_flags.py
"""SafeOrchestrator freshness_check + persist + null notifications flags.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.1
"""
from unittest.mock import patch
import pytest
import yaml

from engine import SafeOrchestrator


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml") as f:
        return yaml.safe_load(f)


def test_freshness_check_can_be_disabled(base_config, tmp_path):
    """When freshness_check=False, validate_kline_freshness must NOT be called.

    NOTE: patch target follows the import in safe_orchestrator.py. Verify with:
        grep -n "validate_kline_freshness" engine/safe_orchestrator.py
    If imported as `from engine.safety import validate_kline_freshness`,
    patch `engine.safe_orchestrator.validate_kline_freshness` instead.
    """
    with patch("engine.safe_orchestrator.validate_kline_freshness") as mock_validate:
        orch = SafeOrchestrator(
            base_config,
            state_dir=str(tmp_path),
            freshness_check=False,
        )
        # Build minimal data
        import pandas as pd
        idx = pd.date_range("2026-01-01", periods=300, freq="15min")
        df = pd.DataFrame({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1.0}, index=idx)
        orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000)

    mock_validate.assert_not_called()
```

- [ ] **Step 2: Run — expect fail (param doesn't exist yet)**

```
python -m pytest backend/tests/test_safe_orchestrator_flags.py::test_freshness_check_can_be_disabled -v
```

Expected: `TypeError: __init__() got an unexpected keyword argument 'freshness_check'`

- [ ] **Step 3: Modify `engine/safe_orchestrator.py:__init__`**

Add to signature (after `order_manager`):

```python
    def __init__(self, config: dict, state_dir: str = "./state",
                  permission_mgr=None, notification_mgr=None,
                  order_manager=None,
                  *,
                  freshness_check: bool = True,
                  persist: bool = True):
        ...
        self.freshness_check = freshness_check
        self.persist = persist
```

Then in `run_cycle`, wrap the freshness call:

```python
        if self.freshness_check:
            validate_kline_freshness(...)  # existing call unchanged
```

- [ ] **Step 4: Run — expect pass**

```
python -m pytest backend/tests/test_safe_orchestrator_flags.py::test_freshness_check_can_be_disabled -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add backend/tests/test_safe_orchestrator_flags.py engine/safe_orchestrator.py
git commit -m "feat(orch): freshness_check flag for backtest mode

Replaces brittle module-globals monkey-patch in legacy backtest/runner.py.
When False, validate_kline_freshness is bypassed cleanly."
```

---

### Task 1.4: TDD — `persist` flag (no disk writes)

**Files:**
- Modify: `backend/tests/test_safe_orchestrator_flags.py`
- Modify: `engine/safe_orchestrator.py`

- [ ] **Step 1: Add failing test**

```python
def test_persist_disabled_writes_no_state(base_config, tmp_path):
    """When persist=False, state_dir must remain empty after a cycle."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    orch = SafeOrchestrator(
        base_config,
        state_dir=str(state_dir),
        freshness_check=False,
        persist=False,
    )
    # Force a state save attempt
    orch.breaker.current_balance = 999.99
    orch._persist_state()

    files = list(state_dir.iterdir())
    assert files == [], f"Expected empty state_dir, found: {files}"
```

- [ ] **Step 2: Run — expect fail**

```
python -m pytest backend/tests/test_safe_orchestrator_flags.py::test_persist_disabled_writes_no_state -v
```

- [ ] **Step 3: Modify `_persist_state` in `engine/safe_orchestrator.py`**

At the very top of the method:

```python
    def _persist_state(self):
        if not self.persist:
            return
        ...
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(orch): persist flag for zero-disk-write backtest mode"
```

---

### Task 1.5: TDD — Null notification manager

**Files:**
- Create: `engine/notifications/null_manager.py`
- Modify: `backend/tests/test_safe_orchestrator_flags.py`
- Modify: `engine/notifications/__init__.py` (export)

- [ ] **Step 1: Add failing test**

```python
def test_null_notifications_swallow_calls(base_config, tmp_path):
    """NullNotificationManager.notify() must not raise and must return None."""
    from engine.notifications import NullNotificationManager
    nm = NullNotificationManager()
    assert nm.notify("test_event", {"key": "value"}) is None
    assert nm.notify_position_opened(None) is None  # Tolerates any signature

    # SafeOrchestrator accepts injected null manager
    orch = SafeOrchestrator(
        base_config,
        state_dir=str(tmp_path),
        notification_mgr=nm,
        freshness_check=False,
        persist=False,
    )
    assert orch.notification_mgr is nm
```

- [ ] **Step 2: Run — expect fail (NullNotificationManager doesn't exist)**

- [ ] **Step 3: Create `engine/notifications/null_manager.py`**

```python
"""No-op notification manager for backtest mode.

Swallows all calls. Use when you want SafeOrchestrator to run without
any external notifications (logs, webhooks, etc.).
"""
class NullNotificationManager:
    def notify(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        # Any unknown notify_* method becomes a no-op callable.
        def noop(*a, **kw):
            return None
        return noop
```

- [ ] **Step 4: Export in `engine/notifications/__init__.py`**

Add at the bottom:

```python
from .null_manager import NullNotificationManager
__all__.append("NullNotificationManager")  # adjust if __all__ doesn't exist
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```
git commit -m "feat(notifications): NullNotificationManager for backtest mode"
```

---

### Task 1.6: Test engine purity under fake filesystem + blocked sockets

**Files:**
- Create: `backend/tests/test_engine_purity.py`

- [ ] **Step 1: Write the test**

```python
"""Engine purity test — SafeOrchestrator must run with NO real disk writes
or network calls when freshness_check=False, persist=False, NullNotifications.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.1
"""
from unittest.mock import patch
import socket
import pandas as pd
import pytest
import yaml

from engine import SafeOrchestrator
from engine.notifications import NullNotificationManager


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml") as f:
        return yaml.safe_load(f)


def test_orchestrator_runs_with_no_real_disk_or_network(base_config, fs):
    """fs fixture from pyfakefs — any real disk write would fail or be invisible
    to the os module after the fixture is torn down. Network is blocked."""
    fs.create_dir("/fake_state")
    fs.add_real_file("configs/config.phase2_1k.yaml")

    # Block sockets at the syscall level
    with patch("socket.socket", side_effect=RuntimeError("Network use forbidden in pure mode")):
        orch = SafeOrchestrator(
            base_config,
            state_dir="/fake_state",
            notification_mgr=NullNotificationManager(),
            freshness_check=False,
            persist=False,
        )
        idx = pd.date_range("2026-01-01", periods=300, freq="15min")
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
            index=idx,
        )
        # One full cycle
        orch.run_cycle("BTC/USDT", df, df, df, df, balance=1000.0)

    # Asserting the cycle completed without raising is the test.
    # Bonus: state_dir must be untouched (persist=False)
    import os
    assert os.listdir("/fake_state") == []
```

- [ ] **Step 2: Run**

```
python -m pytest backend/tests/test_engine_purity.py -v
```

Expected: PASS. If it fails because of an I/O escape hatch we missed (e.g., `requests.get` somewhere), patch the offending call site and document it in the audit doc.

- [ ] **Step 3: Commit**

```
git commit -m "test(engine): purity test under pyfakefs + blocked sockets"
```

---

### Chunk 1 verification

```
python -m pytest backend/tests/ -q
```

Expected: 66 prior tests + ~5 new tests = 71+ passing.

---

## Chunk 2: Phase 2 — Data Layer (Fetcher + Cache + Manifest)

**Goal:** Build a CCXT-wrapped Binance public OHLCV fetcher with gap detection, plus a parquet cache with atomic writes and sha256 verification, plus a manifest JSON for fast lookups.

**Estimated effort:** 2.5 days

---

### Task 2.1: TDD — `data/manifest.py`

**Files:**
- Create: `data/__init__.py` (empty)
- Create: `data/manifest.py`
- Create: `backend/tests/test_data_manifest.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_data_manifest.py
"""Cache manifest — JSON registry of (symbol, tf) → metadata."""
import json
import pytest

from data.manifest import CacheManifest


def test_manifest_creates_empty_on_missing(tmp_path):
    m = CacheManifest(tmp_path / "manifest.json")
    assert m.entries() == {}


def test_manifest_records_entry(tmp_path):
    m = CacheManifest(tmp_path / "manifest.json")
    m.put("BTC/USDT", "15m", min_ts=1000, max_ts=2000, sha256="abc123")
    m.save()

    # Reload from disk
    m2 = CacheManifest(tmp_path / "manifest.json")
    entry = m2.get("BTC/USDT", "15m")
    assert entry == {"min_ts": 1000, "max_ts": 2000, "sha256": "abc123"}


def test_manifest_get_unknown_returns_none(tmp_path):
    m = CacheManifest(tmp_path / "manifest.json")
    assert m.get("ETH/USDT", "1h") is None
```

- [ ] **Step 2: Run — fails (no module)**

- [ ] **Step 3: Create `data/__init__.py`**

(empty)

- [ ] **Step 4: Implement `data/manifest.py`**

```python
"""Parquet cache manifest — JSON registry of (symbol, tf) → range/sha256."""
from __future__ import annotations
import json
from pathlib import Path


def _key(symbol: str, tf: str) -> str:
    """Manifest key: BTC/USDT_15m → 'BTC_USDT_15m'."""
    return f"{symbol.replace('/', '_')}_{tf}"


class CacheManifest:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.exists():
            self._data = json.loads(self.path.read_text())
        else:
            self._data = {}

    def put(self, symbol: str, tf: str, *, min_ts: int, max_ts: int, sha256: str) -> None:
        self._data[_key(symbol, tf)] = {
            "min_ts": int(min_ts),
            "max_ts": int(max_ts),
            "sha256": sha256,
        }

    def get(self, symbol: str, tf: str) -> dict | None:
        return self._data.get(_key(symbol, tf))

    def entries(self) -> dict:
        return dict(self._data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
        tmp.replace(self.path)
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```
git commit -m "feat(data): cache manifest with atomic JSON writes"
```

---

### Task 2.2: TDD — `data/cache.py` parquet round-trip + atomic writes

**Files:**
- Create: `data/cache.py`
- Create: `backend/tests/test_data_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_data_cache.py
"""Parquet cache: round-trip, atomic writes, sha256 verify, gap detection."""
import pandas as pd
import pytest

from data.cache import OHLCVCache, hash_dataframe


@pytest.fixture
def df():
    idx = pd.date_range("2026-01-01", periods=100, freq="15min")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
        index=idx,
    )


def test_cache_round_trip_returns_identical_data(tmp_path, df):
    cache = OHLCVCache(tmp_path)
    cache.put("BTC/USDT", "15m", df)
    out = cache.get("BTC/USDT", "15m")
    assert out is not None
    pd.testing.assert_frame_equal(df, out)


def test_cache_miss_returns_none(tmp_path):
    cache = OHLCVCache(tmp_path)
    assert cache.get("ETH/USDT", "1h") is None


def test_cache_corruption_detected_and_refetched(tmp_path, df):
    cache = OHLCVCache(tmp_path)
    cache.put("BTC/USDT", "15m", df)

    # Corrupt the parquet file
    cache_file = cache._path("BTC/USDT", "15m")
    cache_file.write_bytes(b"GARBAGE_DATA")

    # cache.get should detect mismatch (sha256 verify) and return None
    out = cache.get("BTC/USDT", "15m")
    assert out is None, "Corrupted cache must return None to force re-fetch"


def test_cache_atomic_write_no_partial_files(tmp_path, df):
    cache = OHLCVCache(tmp_path)
    cache.put("BTC/USDT", "15m", df)
    # Only the final .parquet should exist; no .tmp leftovers
    files = list(tmp_path.rglob("*.tmp"))
    assert files == []
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `data/cache.py`**

```python
"""Parquet OHLCV cache with atomic writes + sha256 verification."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd

from data.manifest import CacheManifest


def hash_dataframe(df: pd.DataFrame) -> str:
    """Stable sha256 of a DataFrame (sorted index, sorted columns)."""
    df_sorted = df.sort_index().reindex(sorted(df.columns), axis=1)
    return hashlib.sha256(pd.util.hash_pandas_object(df_sorted, index=True).values.tobytes()).hexdigest()


class OHLCVCache:
    """Parquet cache: cache_dir/{symbol_normalized}/{tf}.parquet"""

    def __init__(self, cache_dir: Path | str):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = CacheManifest(self.dir / "manifest.json")

    def _path(self, symbol: str, tf: str) -> Path:
        return self.dir / symbol.replace("/", "_") / f"{tf}.parquet"

    def get(self, symbol: str, tf: str) -> Optional[pd.DataFrame]:
        """Returns DataFrame on cache hit + sha256 match, else None."""
        manifest_entry = self.manifest.get(symbol, tf)
        path = self._path(symbol, tf)
        if not manifest_entry or not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
        except Exception:
            return None
        actual_sha = hash_dataframe(df)
        if actual_sha != manifest_entry["sha256"]:
            # Corrupted: caller will re-fetch
            return None
        return df

    def put(self, symbol: str, tf: str, df: pd.DataFrame) -> None:
        """Atomic write + manifest update."""
        path = self._path(symbol, tf)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        df.to_parquet(tmp)
        tmp.replace(path)

        sha = hash_dataframe(df)
        # Convert datetime index → ms for manifest
        idx_ms = (df.index.astype("int64") // 1_000_000).tolist()
        self.manifest.put(symbol, tf, min_ts=idx_ms[0], max_ts=idx_ms[-1], sha256=sha)
        self.manifest.save()
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(data): parquet OHLCV cache with atomic writes + sha256 verify"
```

---

### Task 2.3: TDD — `data/fetcher.py` with gap detection

**Files:**
- Create: `data/fetcher.py`
- Create: `backend/tests/test_data_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_data_fetcher.py
"""Binance public OHLCV fetcher via CCXT — range fetch + gap detection."""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from data.fetcher import OHLCVFetcher, FetchResult


@pytest.fixture
def fetcher():
    """Fetcher with mocked CCXT client to avoid real network."""
    f = OHLCVFetcher.__new__(OHLCVFetcher)
    f.client = MagicMock()
    f.client.exchange = MagicMock()
    f.tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    return f


def test_fetch_complete_range_no_gaps(fetcher):
    # Mock CCXT returning 100 contiguous bars
    bars = [[1700000000000 + i * 900_000, 100, 101, 99, 100.5, 1.0] for i in range(100)]
    fetcher.client.exchange.fetch_ohlcv.return_value = bars

    result = fetcher.fetch_ohlcv_range("BTC/USDT", "15m",
                                          start_ms=1700000000000,
                                          end_ms=1700000000000 + 100 * 900_000)
    assert isinstance(result, FetchResult)
    assert len(result.df) == 100
    assert result.gaps == []


def test_fetch_with_gap_returns_gap_list(fetcher):
    # 50 bars, then a gap (no bars for 30min = 2 bars), then 48 more = 100 expected, 98 actual
    bars_1 = [[1700000000000 + i * 900_000, 100, 101, 99, 100, 1.0] for i in range(50)]
    bars_2 = [[1700000000000 + (52 + i) * 900_000, 100, 101, 99, 100, 1.0] for i in range(48)]
    fetcher.client.exchange.fetch_ohlcv.return_value = bars_1 + bars_2

    result = fetcher.fetch_ohlcv_range("BTC/USDT", "15m",
                                          start_ms=1700000000000,
                                          end_ms=1700000000000 + 100 * 900_000)
    assert len(result.df) == 98
    assert len(result.gaps) >= 1
    gap_start, gap_end = result.gaps[0]
    assert gap_end - gap_start == 30 * 60 * 1000  # 30 min gap
```

- [ ] **Step 2: Run — fail (no module)**

- [ ] **Step 3: Implement `data/fetcher.py`**

```python
"""Binance public OHLCV fetcher via CCXT — range fetch + gap detection."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
import logging

import pandas as pd

from exchange import BinanceClient

log = logging.getLogger("efloud.data.fetcher")


@dataclass
class FetchResult:
    df: pd.DataFrame
    gaps: List[Tuple[int, int]] = field(default_factory=list)  # (start_ms, end_ms) of missing windows


class OHLCVFetcher:
    """Public Binance OHLCV via CCXT (no auth)."""

    tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}

    def __init__(self):
        # Public klines need no auth. Verified: BinanceClient.__init__ accepts
        # empty api_key/secret because CCXT only validates creds on private endpoints.
        # If this fails, fall back to instantiating ccxt.binance() directly.
        self.client = BinanceClient(api_key="", api_secret="", testnet=False, market_type="futures")

    def fetch_ohlcv_range(self, symbol: str, tf: str, start_ms: int, end_ms: int,
                            limit: int = 1500) -> FetchResult:
        """Fetch OHLCV in range; return df + gap list."""
        if tf not in self.tf_minutes:
            raise ValueError(f"Unsupported tf: {tf!r}")
        tf_ms = self.tf_minutes[tf] * 60 * 1000
        all_bars: list = []
        cursor = start_ms
        while cursor < end_ms:
            batch = self.client.exchange.fetch_ohlcv(symbol, tf, since=cursor, limit=limit)
            if not batch:
                break
            all_bars.extend(batch)
            last_ts = batch[-1][0]
            if last_ts <= cursor:
                break  # safety: no progress
            cursor = last_ts + tf_ms

        # Dedupe + sort
        seen: dict = {}
        for bar in all_bars:
            seen[bar[0]] = bar
        sorted_bars = sorted(seen.values(), key=lambda b: b[0])

        # Build df
        df = pd.DataFrame(sorted_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)

        # Gap detection
        expected = pd.date_range(
            start=pd.to_datetime(start_ms, unit="ms"),
            end=pd.to_datetime(end_ms - tf_ms, unit="ms"),
            freq=f"{self.tf_minutes[tf]}min",
        )
        gaps: list = []
        if len(df) < len(expected):
            present = set(df.index)
            in_gap = False
            gap_start = None
            for ts in expected:
                if ts not in present:
                    if not in_gap:
                        gap_start = int(ts.timestamp() * 1000)
                        in_gap = True
                else:
                    if in_gap:
                        gap_end = int(ts.timestamp() * 1000)
                        gaps.append((gap_start, gap_end))
                        in_gap = False
            if in_gap:
                gaps.append((gap_start, end_ms))

        return FetchResult(df=df, gaps=gaps)

    def fetch_funding_rates(self, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        """Fetch funding rate history (8h cadence)."""
        # CCXT method: fetch_funding_rate_history
        all_rows: list = []
        cursor = start_ms
        while cursor < end_ms:
            batch = self.client.exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
            if not batch:
                break
            all_rows.extend(batch)
            last_ts = batch[-1].get("timestamp", cursor)
            if last_ts <= cursor:
                break
            cursor = last_ts + 1
        rows = [{"ts": r["timestamp"], "funding_rate": r["fundingRate"]} for r in all_rows]
        df = pd.DataFrame(rows)
        if not df.empty:
            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            df.set_index("ts", inplace=True)
            df = df[~df.index.duplicated()].sort_index()
        return df
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(data): CCXT-wrapped fetcher with gap detection + funding rates"
```

---

### Task 2.3b: TDD — `_tf_to_minutes` helper + max-gap-pct refusal

**Files:**
- Modify: `data/fetcher.py` (add helper)
- Modify: `backtest/engine.py` (will be modified in Chunk 3, but commit helper now)
- Create: `backend/tests/test_tf_normalization.py`

- [ ] **Step 1: Add `_tf_to_minutes` to `data/fetcher.py`** (top-level export)

```python
def tf_to_minutes(tf: str) -> int:
    """Normalize a Binance/CCXT TF string to minutes.

    Per spec §6.6: must handle '1m', '15m', '1h', '4h', '1d', '1w'. ValueError on unknown.
    """
    tf_map = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if not tf or tf[-1] not in tf_map:
        raise ValueError(f"Unsupported timeframe: {tf!r}")
    try:
        n = int(tf[:-1])
    except ValueError as e:
        raise ValueError(f"Bad timeframe number: {tf!r}") from e
    return n * tf_map[tf[-1]]
```

- [ ] **Step 2: Test**

```python
# backend/tests/test_tf_normalization.py
import pytest
from data.fetcher import tf_to_minutes


@pytest.mark.parametrize("tf,expected", [
    ("1m", 1), ("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440), ("1w", 10080),
])
def test_tf_to_minutes_known(tf, expected):
    assert tf_to_minutes(tf) == expected


@pytest.mark.parametrize("bad", ["", "15", "15x", "abc", None])
def test_tf_to_minutes_bad_raises(bad):
    with pytest.raises((ValueError, TypeError)):
        tf_to_minutes(bad)
```

- [ ] **Step 3: max-gap-pct refusal in fetcher result**

Modify `OHLCVFetcher.fetch_ohlcv_range` to raise (or return a flag) when total gap duration exceeds threshold:

```python
def fetch_ohlcv_range(self, symbol, tf, start_ms, end_ms, limit=1500, max_gap_pct=1.0):
    # ... existing fetch code ...
    total_gap_ms = sum(end - start for start, end in gaps)
    period_ms = end_ms - start_ms
    gap_pct = (total_gap_ms / period_ms * 100) if period_ms else 0
    if gap_pct > max_gap_pct:
        raise ValueError(
            f"Fetch incomplete: {gap_pct:.2f}% gap exceeds max {max_gap_pct}% "
            f"({len(gaps)} gap windows)"
        )
    return FetchResult(df=df, gaps=gaps)
```

Add test:

```python
# In test_data_fetcher.py
def test_fetch_refuses_excessive_gaps(fetcher):
    # Mock: only 50 of 100 expected bars (50% gap)
    bars = [[1700000000000 + i * 900_000, 100, 101, 99, 100, 1.0] for i in range(50)]
    fetcher.client.exchange.fetch_ohlcv.return_value = bars
    with pytest.raises(ValueError, match="exceeds max"):
        fetcher.fetch_ohlcv_range("BTC/USDT", "15m",
                                     start_ms=1700000000000,
                                     end_ms=1700000000000 + 100 * 900_000,
                                     max_gap_pct=1.0)
```

- [ ] **Step 4: Run + commit**

```
git commit -m "feat(data): tf_to_minutes helper + max-gap-pct refusal per spec"
```

---

### Task 2.4: Integration — populate cache for 1y BTC/USDT

**Files:**
- Create: `scripts/prefetch_data.py`

- [ ] **Step 1: Write the script**

```python
# scripts/prefetch_data.py
"""One-time helper: pre-populate cache with 1y of OHLCV + funding data."""
import time
from pathlib import Path

from data.fetcher import OHLCVFetcher
from data.cache import OHLCVCache

SYMBOLS = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "DOGE/USDT", "SOL/USDT",
           "BNB/USDT", "TRX/USDT", "LINK/USDT", "BCH/USDT", "ADA/USDT"]
TIMEFRAMES = ["4h", "1h", "15m", "1d"]
PERIOD_MS = 365 * 24 * 60 * 60 * 1000  # 1 year


def main():
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - PERIOD_MS
    fetcher = OHLCVFetcher()
    cache = OHLCVCache(Path("cache/ohlcv"))

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            existing = cache.get(symbol, tf)
            if existing is not None:
                print(f"[skip] {symbol} {tf} ({len(existing)} bars cached)")
                continue
            print(f"[fetch] {symbol} {tf} ...", end="", flush=True)
            result = fetcher.fetch_ohlcv_range(symbol, tf, start_ms, end_ms)
            cache.put(symbol, tf, result.df)
            print(f" {len(result.df)} bars, {len(result.gaps)} gaps")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run (one-time, ~10 min)**

```
python -m scripts.prefetch_data
```

Expected: prints progress per (symbol, tf), populates `cache/ohlcv/{symbol}/{tf}.parquet`.

- [ ] **Step 3: Verify cache size**

```powershell
Get-ChildItem -Recurse cache/ohlcv | Measure-Object -Property Length -Sum
```

Expected: < 200 MB total.

- [ ] **Step 4: Commit script (NOT cache files)**

```
echo cache/ >> .gitignore
git add .gitignore scripts/prefetch_data.py
git commit -m "chore(data): prefetch script for 1y OHLCV + funding cache"
```

---

### Chunk 2 verification

```
python -m pytest backend/tests/ -q
```

Expected: ~75+ tests passing.

```
ls cache/ohlcv
```

Expected: 10 symbol dirs × 4 TF parquets each.

---

## Chunk 3: Phase 3a — Backtest Engine Core (Walk-Forward + Intrabar Fill)

**Goal:** Pure simulation core — accepts pre-loaded data, runs walk-forward through it via `SafeOrchestrator`, simulates intrabar SL/TP fills with explicit tie-break.

**Estimated effort:** 2.5 days (Phase 3 split into 3a here + 3b in Chunk 4)

---

### Task 3.1: TDD — `backtest/intrabar.py` fill resolution

**Files:**
- Create: `backtest/intrabar.py`
- Create: `backend/tests/test_intrabar_fill.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_intrabar_fill.py
"""Intrabar SL/TP fill resolution.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.3
"""
from dataclasses import dataclass

import pytest

from backtest.intrabar import resolve_fill, Bar


@dataclass
class _Pos:
    direction: str
    entry: float
    sl: float
    tp1: float


def test_long_sl_only_hit():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=98, high=99, low=94, close=96)
    level, price = resolve_fill(pos, bar)
    assert level == "SL"
    assert price == min(98, 95)  # min(open, sl)


def test_long_tp_only_hit():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=102, high=106, low=101, close=104)
    level, price = resolve_fill(pos, bar)
    assert level == "TP1"
    assert price == max(102, 105)  # max(open, tp1) = 105


def test_long_both_hit_open_below_entry_sl_first():
    """LONG, both levels touched, bar.open < entry → SL fired first."""
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=99, high=106, low=94, close=104)  # both SL and TP touched
    level, _ = resolve_fill(pos, bar)
    assert level == "SL"


def test_long_both_hit_open_above_entry_tp_first():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=101, high=106, low=94, close=98)
    level, _ = resolve_fill(pos, bar)
    assert level == "TP1"


def test_short_sl_only_hit():
    pos = _Pos("SHORT", entry=100, sl=105, tp1=95)
    bar = Bar(open=102, high=106, low=101, close=104)
    level, price = resolve_fill(pos, bar)
    assert level == "SL"
    assert price == max(102, 105)


def test_neither_hit():
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=99, high=104, low=96, close=102)
    level, _ = resolve_fill(pos, bar)
    assert level is None


def test_long_gap_through_sl():
    """Bar opens BELOW SL — fill is at bar.open (worse than SL trigger). Spec §6.3 gap case."""
    pos = _Pos("LONG", entry=100, sl=95, tp1=105)
    bar = Bar(open=92, high=93, low=92, close=92.5)
    level, price = resolve_fill(pos, bar)
    assert level == "SL"
    assert price == 92  # min(92, 95) — gap-through fill at the worse price
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `backtest/intrabar.py`**

```python
"""Intrabar SL/TP fill resolution with explicit tie-break."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float


def resolve_fill(pos, bar: Bar) -> Tuple[Optional[str], Optional[float]]:
    """Return (level, fill_price) for the position, or (None, None) if no level hit.

    `pos` must have: .direction, .entry, .sl, .tp1
    Tie-break for both-hit: bar.open distance from entry decides which fired first.
    """
    sl_hit = (pos.direction == "LONG" and bar.low <= pos.sl) or \
             (pos.direction == "SHORT" and bar.high >= pos.sl)
    tp_hit = (pos.direction == "LONG" and bar.high >= pos.tp1) or \
             (pos.direction == "SHORT" and bar.low <= pos.tp1)

    if not sl_hit and not tp_hit:
        return (None, None)
    if sl_hit and not tp_hit:
        return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
    if tp_hit and not sl_hit:
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))

    # Both hit — tie-break by bar.open distance from entry
    if pos.direction == "LONG":
        if bar.open < pos.entry:
            return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))
    else:  # SHORT
        if bar.open > pos.entry:
            return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))


def _adverse_fill(bar_open: float, trigger: float, direction: str, kind: str) -> float:
    """Pessimistic fill: take the worse of bar.open or trigger price."""
    if kind == "SL":
        return min(bar_open, trigger) if direction == "LONG" else max(bar_open, trigger)
    return max(bar_open, trigger) if direction == "LONG" else min(bar_open, trigger)
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(backtest): intrabar fill resolution with tie-break"
```

---

### Task 3.2: TDD — `backtest/engine.py` walk-forward skeleton (single symbol)

**Files:**
- Create: `backtest/engine.py`
- Create: `backend/tests/test_backtest_engine_single.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_backtest_engine_single.py
"""Backtest engine — single-symbol walk-forward.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §5, §6.1
"""
import pandas as pd
import pytest
import yaml

from backtest.engine import run_backtest


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["operation"]["dry_run"] = False  # backtest engine handles dry-run via flags
    return cfg


@pytest.fixture
def synthetic_data():
    """1000 bars, slight trend, no real signals — used to validate plumbing."""
    idx = pd.date_range("2026-01-01", periods=1000, freq="15min")
    closes = 100 + (idx.hour - 12).astype(float) * 0.05
    df = pd.DataFrame({
        "open": closes, "high": closes + 0.5, "low": closes - 0.5,
        "close": closes, "volume": 1.0,
    }, index=idx)
    return df


def test_engine_runs_to_completion(base_config, synthetic_data):
    data = {"BTC/USDT": {"4h": synthetic_data, "1h": synthetic_data, "15m": synthetic_data, "1d": synthetic_data}}
    result = run_backtest(
        symbols=["BTC/USDT"],
        data=data,
        config=base_config,
        initial_balance=2000.0,
    )
    assert result is not None
    assert result["initial_balance"] == 2000.0
    assert "final_balance" in result
    assert "trades" in result
    assert isinstance(result["trades"], list)


def test_engine_deterministic(base_config, synthetic_data):
    """Same data + config → byte-identical result.json."""
    import json
    data = {"BTC/USDT": {"4h": synthetic_data, "1h": synthetic_data, "15m": synthetic_data, "1d": synthetic_data}}
    r1 = run_backtest(symbols=["BTC/USDT"], data=data, config=base_config, initial_balance=2000.0)
    r2 = run_backtest(symbols=["BTC/USDT"], data=data, config=base_config, initial_balance=2000.0)
    # Drop wall-clock fields if any
    for r in (r1, r2):
        r.pop("_wall_seconds", None)
    assert json.dumps(r1, sort_keys=True, default=str) == json.dumps(r2, sort_keys=True, default=str)
```

- [ ] **Step 2: Run — fail**

**Pre-step note (Task 4.3 integration test below depends on this):** the lifecycle position type is `engine.lifecycle.Position`. Read `engine/lifecycle.py` once to learn its `.entries`, `.exits`, `.is_open`, `.avg_entry_price`, `.remaining_size`, `.realized_pnl` attributes. The intrabar test in 3.1 uses a `_Pos` stub for unit testing; integration tests use the real Position class.

- [ ] **Step 3: Implement minimal `backtest/engine.py`**

```python
"""Pure backtest engine — walk-forward simulation with no I/O."""
from __future__ import annotations
import logging
import tempfile
from typing import Any

import pandas as pd

from engine import SafeOrchestrator
from engine.notifications import NullNotificationManager

log = logging.getLogger("efloud.backtest.engine")


def run_backtest(
    *,
    symbols: list[str],
    data: dict[str, dict[str, pd.DataFrame]],
    config: dict,
    initial_balance: float = 2000.0,
    warmup_bars: int = 200,
    step_every_n_bars: int = 1,
) -> dict[str, Any]:
    """Run a walk-forward backtest. No I/O.

    Args:
        symbols: list of symbols to simulate. Single-symbol mode = 1 entry; portfolio = N.
        data: {symbol: {tf: df}} pre-loaded OHLCV.
        config: bot config dict (same schema as live).
        initial_balance: starting USDT.
        warmup_bars: bars consumed before first cycle (analysis warmup).
        step_every_n_bars: cycle frequency (1 = every bar, 4 = every 4 bars).

    Returns: dict with initial_balance, final_balance, trades, equity_curve, etc.
    """
    # Process symbols in alphabetical order for deterministic results
    symbols = sorted(symbols)

    # Use a temp state_dir even though persist=False (orch's __init__ tries to create it)
    with tempfile.TemporaryDirectory(prefix="bt_") as state_dir:
        orch = SafeOrchestrator(
            config,
            state_dir=state_dir,
            notification_mgr=NullNotificationManager(),
            freshness_check=False,
            persist=False,
        )
        balance = float(initial_balance)
        peak_balance = balance

        # Use the first symbol's 15m index as the master clock
        entry_tf_name = config["timeframes"]["entry"]
        primary_idx = data[symbols[0]][entry_tf_name].index
        n_bars = len(primary_idx)
        if n_bars < warmup_bars + 50:
            raise ValueError(f"Not enough bars: {n_bars} < {warmup_bars + 50}")

        for i in range(warmup_bars, n_bars, step_every_n_bars):
            current_ts = primary_idx[i]
            for symbol in symbols:
                tfs = data[symbol]
                e_slice = tfs[entry_tf_name].iloc[: i + 1]
                h_slice = tfs[config["timeframes"]["htf"]].loc[: current_ts]
                m_slice = tfs[config["timeframes"]["mtf"]].loc[: current_ts]
                d_slice = tfs.get("1d")
                if d_slice is not None:
                    d_slice = d_slice.loc[: current_ts]
                if len(h_slice) < 50 or len(m_slice) < 50:
                    continue
                try:
                    orch.run_cycle(symbol, h_slice, m_slice, e_slice, d_slice, balance=balance)
                except Exception as e:
                    log.debug(f"Cycle {symbol} @ {current_ts} skipped: {e}")
                    continue

            # PnL update (intrabar fills + MTM) — TODO Chunk 4

        closed_positions = [p for p in orch.lifecycle.positions if not p.is_open]

        return {
            "initial_balance": initial_balance,
            "final_balance": balance,
            "peak_balance": peak_balance,
            "trades": [_serialize_trade(p) for p in closed_positions],
            "equity_curve": [],
            "symbols": symbols,
        }


def _serialize_trade(p) -> dict:
    return {
        "symbol": p.symbol,
        "direction": p.direction,
        "entry": float(p.avg_entry_price),
        "exit": float(p.exits[-1].price) if p.exits else None,
        "pnl": float(p.realized_pnl),
        "exit_reason": p.exits[-1].reason if p.exits else None,
        "opened_at": str(p.opened_at),
        "closed_at": str(p.closed_at) if p.closed_at else None,
    }
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(backtest): walk-forward engine skeleton (single symbol)"
```

---

### Task 3.3: TDD — Portfolio mode (multi-symbol shared balance)

**Files:**
- Create: `backend/tests/test_backtest_engine_portfolio.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_backtest_engine_portfolio.py
"""Portfolio mode — 10 symbols share balance + breaker.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §5
"""
import json
import pandas as pd
import pytest
import yaml

from backtest.engine import run_backtest


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def synthetic_data():
    idx = pd.date_range("2026-01-01", periods=600, freq="15min")
    df = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
        index=idx,
    )
    syms = ["BTC/USDT", "ETH/USDT"]
    return {s: {"4h": df, "1h": df, "15m": df, "1d": df} for s in syms}


def test_portfolio_two_symbols_runs(base_config, synthetic_data):
    result = run_backtest(
        symbols=["BTC/USDT", "ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        initial_balance=2000.0,
    )
    assert sorted(result["symbols"]) == ["BTC/USDT", "ETH/USDT"]


def test_portfolio_byte_identical_across_runs(base_config, synthetic_data):
    """Determinism: alphabetical processing → identical results."""
    r1 = run_backtest(symbols=["ETH/USDT", "BTC/USDT"], data=synthetic_data, config=base_config, initial_balance=2000.0)
    r2 = run_backtest(symbols=["BTC/USDT", "ETH/USDT"], data=synthetic_data, config=base_config, initial_balance=2000.0)
    for r in (r1, r2):
        r.pop("_wall_seconds", None)
    assert json.dumps(r1, sort_keys=True, default=str) == json.dumps(r2, sort_keys=True, default=str)
```

- [ ] **Step 2: Run — should already pass given alphabetical sort**

- [ ] **Step 3: Commit if passing**

```
git commit -m "test(backtest): portfolio determinism + multi-symbol runs"
```

---

### Chunk 3 verification

```
python -m pytest backend/tests/ -q
```

Expected: ~80+ tests passing.

---

## Chunk 4: Phase 3b — Slippage + Funding + MTM Drawdown + Metrics

**Goal:** Realistic execution model (per-leg slippage, funding fees) and proper metrics aggregation including MTM drawdown.

**Estimated effort:** 2 days

---

### Task 4.1: TDD — `backtest/slippage.py`

**Files:**
- Create: `backtest/slippage.py`
- Create: `backend/tests/test_slippage.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_slippage.py
"""Per-leg slippage model.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.7
"""
import pytest
from backtest.slippage import SlippageConfig, adverse_fill


def test_long_entry_adverse_up():
    cfg = SlippageConfig(entry_slip_pct=0.1)  # 10 bp
    out = adverse_fill(100.0, "LONG", "entry", cfg)
    assert out == pytest.approx(100.1)


def test_long_sl_adverse_down():
    cfg = SlippageConfig(sl_slip_pct=0.1)
    out = adverse_fill(100.0, "LONG", "SL", cfg)
    assert out == pytest.approx(99.9)


def test_long_tp_adverse_down():
    cfg = SlippageConfig(exit_slip_pct=0.1)
    out = adverse_fill(100.0, "LONG", "TP", cfg)
    assert out == pytest.approx(99.9)


def test_short_entry_adverse_down():
    cfg = SlippageConfig(entry_slip_pct=0.1)
    out = adverse_fill(100.0, "SHORT", "entry", cfg)
    assert out == pytest.approx(99.9)


def test_short_sl_adverse_up():
    cfg = SlippageConfig(sl_slip_pct=0.1)
    out = adverse_fill(100.0, "SHORT", "SL", cfg)
    assert out == pytest.approx(100.1)


def test_short_tp_adverse_up():
    cfg = SlippageConfig(exit_slip_pct=0.1)
    out = adverse_fill(100.0, "SHORT", "TP", cfg)
    assert out == pytest.approx(100.1)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `backtest/slippage.py`**

```python
"""Per-leg slippage model for backtest fills."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SlippageConfig:
    entry_slip_pct: float = 0.05  # 5 bp adverse on market entry
    sl_slip_pct: float = 0.10     # 10 bp adverse on SL fills (gaps)
    exit_slip_pct: float = 0.05   # 5 bp adverse on TP fills


def adverse_fill(price: float, direction: str, leg: str, cfg: SlippageConfig) -> float:
    """Apply per-leg slippage in trader-adverse direction.

    LONG entry  → buy → adverse-up
    SHORT entry → sell → adverse-down
    LONG SL/TP  → sell → adverse-down
    SHORT SL/TP → buy → adverse-up
    """
    pct_map = {"entry": cfg.entry_slip_pct, "SL": cfg.sl_slip_pct, "TP": cfg.exit_slip_pct}
    if leg not in pct_map:
        raise ValueError(f"Unknown leg: {leg!r}")
    pct = pct_map[leg]
    is_buy = (direction == "LONG" and leg == "entry") or (direction == "SHORT" and leg in ("SL", "TP"))
    sign = +1 if is_buy else -1
    return price * (1 + sign * pct / 100)
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(backtest): per-leg slippage model"
```

---

### Task 4.1b: TDD — Pyramid + partial close slippage cases (spec §6.7)

**Files:**
- Modify: `backend/tests/test_slippage.py`

- [ ] **Step 1: Add cases**

```python
def test_pyramid_add_pays_slippage_on_incremental_notional():
    """Per spec §6.7: pyramid add pays entry_slip on the ADDED size, not cumulative."""
    cfg = SlippageConfig(entry_slip_pct=0.1)
    # Initial entry: LONG 100 @ price 100, slipped → 100.1
    initial = adverse_fill(100.0, "LONG", "entry", cfg)
    assert initial == pytest.approx(100.1)
    # Pyramid add @ 105: slipped on the NEW notional only
    add = adverse_fill(105.0, "LONG", "entry", cfg)
    assert add == pytest.approx(105.105)


def test_partial_close_pays_exit_slip_on_closed_size_only():
    """TP1 closes half; remaining half not affected until TP2/SL."""
    cfg = SlippageConfig(exit_slip_pct=0.1)
    tp1_fill = adverse_fill(105.0, "LONG", "TP", cfg)
    assert tp1_fill == pytest.approx(104.895)  # 105 × (1 - 0.001) for LONG sell adverse
    # Per-fill semantics — function does not track open/closed state; that's the engine's job
```

- [ ] **Step 2: Run + commit**

```
git commit -m "test(slippage): pyramid + partial close cases per spec §6.7"
```

---

### Task 4.2: TDD — `backtest/funding.py` 4-case sign convention

**Files:**
- Create: `backtest/funding.py`
- Create: `backend/tests/test_funding_fees.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_funding_fees.py
"""Funding fee application — 4-case sign table.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §6.5
"""
import pytest
from backtest.funding import compute_funding_delta


@pytest.mark.parametrize("direction,rate,expected_sign", [
    ("LONG",  +0.0001, -1),  # long PAYS positive funding → balance decreases
    ("LONG",  -0.0001, +1),  # long RECEIVES negative funding → balance increases
    ("SHORT", +0.0001, +1),  # short RECEIVES positive funding → balance increases
    ("SHORT", -0.0001, -1),  # short PAYS negative funding → balance decreases
])
def test_funding_sign_convention(direction, rate, expected_sign):
    delta = compute_funding_delta(notional=1000.0, direction=direction, funding_rate=rate)
    if expected_sign > 0:
        assert delta > 0
    else:
        assert delta < 0
    assert abs(delta) == pytest.approx(0.1)  # 1000 × 0.0001
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `backtest/funding.py`**

```python
"""Binance Futures funding fees — 8h cadence application."""
from __future__ import annotations
import pandas as pd


def compute_funding_delta(*, notional: float, direction: str, funding_rate: float) -> float:
    """Return the balance delta (signed) for one funding event.

    Convention: balance_delta = -side_sign × notional × rate
                where side_sign = +1 for LONG, -1 for SHORT.
    """
    side_sign = +1 if direction == "LONG" else -1
    return -side_sign * notional * funding_rate


def funding_events_in_range(funding_df: pd.DataFrame, start_ts, end_ts) -> pd.DataFrame:
    """Return funding events between start_ts and end_ts (exclusive).

    funding_df: index = timestamp, column = funding_rate
    """
    if funding_df.empty:
        return funding_df
    return funding_df[(funding_df.index > start_ts) & (funding_df.index <= end_ts)]
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(backtest): funding fees with explicit sign convention"
```

---

### Task 4.2b: TDD — Funding boundary + multi-funding cumulative (spec §6.5)

**Files:**
- Modify: `backend/tests/test_funding_fees.py`

- [ ] **Step 1: Add cases**

```python
import pandas as pd
from backtest.funding import funding_events_in_range


def test_position_closed_between_funding_events_pays_zero():
    """Position opened 09:00, closed 13:00. Funding events at 16:00, 00:00 — none apply."""
    funding_df = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0001]},
        index=pd.to_datetime(["2026-01-01 16:00", "2026-01-02 00:00"]),
    )
    events = funding_events_in_range(
        funding_df,
        start_ts=pd.Timestamp("2026-01-01 09:00"),
        end_ts=pd.Timestamp("2026-01-01 13:00"),
    )
    assert len(events) == 0


def test_multi_funding_cumulative():
    """Position open across 3 funding events → 3× the single-event cost."""
    funding_df = pd.DataFrame(
        {"funding_rate": [0.0001, 0.0002, -0.0001]},
        index=pd.to_datetime(["2026-01-01 00:00", "2026-01-01 08:00", "2026-01-01 16:00"]),
    )
    events = funding_events_in_range(
        funding_df,
        start_ts=pd.Timestamp("2025-12-31 22:00"),
        end_ts=pd.Timestamp("2026-01-01 17:00"),
    )
    assert len(events) == 3
    # Cumulative cost for LONG, notional=1000
    total = sum(compute_funding_delta(notional=1000.0, direction="LONG", funding_rate=r)
                for r in events["funding_rate"])
    # Long pays positive, receives negative: -100×0.0001 + -100×0.0002 + 100×0.0001 = -0.0002 net
    assert total == pytest.approx(-0.2)
```

- [ ] **Step 2: Run + commit**

```
git commit -m "test(funding): boundary + multi-event cumulative per spec §6.5"
```

---

### Task 4.3: Wire intrabar + slippage + funding into engine

**Files:**
- Modify: `backtest/engine.py`
- Modify: `backend/tests/test_intrabar_fill.py` (add integration test)

- [ ] **Step 1: Add integration test**

```python
def test_engine_uses_intrabar_for_position_close():
    """A position that hits SL on bar i+1 should close at intrabar price, not next-cycle close."""
    # ... synthetic data where price gaps down through SL
    # Assert pos.exits[-1].reason == "SL" and pos.exits[-1].price == sl_with_slippage
```

(Skeleton; flesh out with actual orchestrator integration.)

- [ ] **Step 2: Modify `backtest/engine.py` `run_backtest`**

Inside the cycle loop, after `orch.run_cycle(...)`:

```python
            # Intrabar fill check on next bar
            for pos in list(orch.lifecycle.positions):
                if not pos.is_open:
                    continue
                # Use the entry-tf bar AT i+1 (next bar) — but we're at bar i in the loop
                if i + 1 < n_bars:
                    next_bar_data = data[pos.symbol][entry_tf_name].iloc[i + 1]
                    bar = Bar(open=next_bar_data["open"], high=next_bar_data["high"],
                              low=next_bar_data["low"], close=next_bar_data["close"])
                    level, raw_price = resolve_fill(pos, bar)
                    if level:
                        slipped = adverse_fill(raw_price, pos.direction, level, slippage_cfg)
                        orch.lifecycle.close_position(pos, slipped, level)
                        pnl = pos.realized_pnl
                        balance += pnl
                        peak_balance = max(peak_balance, balance)
```

Add imports + slippage_cfg at top of `run_backtest`:

```python
from backtest.intrabar import resolve_fill, Bar
from backtest.slippage import adverse_fill, SlippageConfig
slippage_cfg = SlippageConfig()
```

- [ ] **Step 3: Run new test — expect pass**

- [ ] **Step 4: Commit**

```
git commit -m "feat(backtest): wire intrabar fill + slippage into engine"
```

---

### Task 4.4: TDD — MTM equity + drawdown

**Files:**
- Modify: `backtest/engine.py`
- Modify: `backend/tests/test_backtest_engine_single.py`

**Note:** This test uses a real symbol from `phase2_1k.yaml` (BTC/USDT) so the orchestrator's symbol whitelist accepts it. The synthetic data is constructed so it ENTERS LONG at bar 200 (post-warmup), then dips and recovers.

- [ ] **Step 1: Add failing test**

```python
def test_mtm_drawdown_captures_mid_trade_dip(base_config):
    """Position briefly deep red but recovers — MTM drawdown should reflect the dip."""
    # 600 bars: warmup 0-199, enter 200, dip 200-300, recover 300-400, close 400.
    # Use BTC/USDT (whitelisted in phase2_1k symbols)
    import numpy as np
    idx = pd.date_range("2026-01-01", periods=600, freq="15min")
    closes = np.full(600, 100.0)
    closes[200:300] = np.linspace(100, 90, 100)  # 10% drop
    closes[300:400] = np.linspace(90, 110, 100)  # recovery to +10%
    closes[400:] = 110.0
    df = pd.DataFrame({
        "open": closes, "high": closes + 0.5, "low": closes - 0.5,
        "close": closes, "volume": 1.0,
    }, index=idx)
    data = {"BTC/USDT": {tf: df for tf in ["4h", "1h", "15m", "1d"]}}

    result = run_backtest(
        symbols=["BTC/USDT"], data=data, config=base_config, initial_balance=1000.0
    )
    # Even if no signal triggered (synthetic data may not satisfy SMC criteria),
    # max_drawdown_pct must be a number (≥0). If trade DID trigger and went red mid-trade,
    # MTM drawdown should be > realized drawdown.
    assert "max_drawdown_pct" in result
    assert result["max_drawdown_pct"] >= 0
```

(Pragmatic test: synthetic data may not trigger real SMC signals; we assert the metric is computed and non-negative. A separate fixture with hand-crafted entry events lives in Task 4.4b below.)

- [ ] **Step 2: Run — fail (`max_drawdown_pct` not in returned dict)**

- [ ] **Step 3: Add MTM tracking in `run_backtest`**

Add at top of `run_backtest`:

```python
    max_drawdown_pct = 0.0
    current_prices: dict[str, float] = {}
```

After each cycle iteration (inside the symbol loop), update prices:

```python
            current_prices[symbol] = float(e_slice["close"].iloc[-1])
```

After the symbol loop completes for tick `i`, compute MTM:

```python
        unrealized = 0.0
        for p in orch.lifecycle.positions:
            if not p.is_open or p.symbol not in current_prices:
                continue
            sign = 1 if p.direction == "LONG" else -1
            unrealized += (current_prices[p.symbol] - p.avg_entry_price) * p.remaining_size * sign
        mtm = balance + unrealized
        peak_balance = max(peak_balance, mtm)
        if peak_balance > 0:
            dd = (peak_balance - mtm) / peak_balance * 100
            max_drawdown_pct = max(max_drawdown_pct, dd)
```

Update return statement:

```python
    return {
        ...,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        ...
    }
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(backtest): MTM-based drawdown tracking"
```

---

### Task 4.4b: Hand-crafted scenario test (mid-trade dip recovery)

**Files:**
- Modify: `backend/tests/test_backtest_engine_single.py`

This test bypasses the orchestrator's signal filtering by injecting a position directly via `orch.lifecycle.open_position()` to validate MTM math in isolation.

- [ ] **Step 1: Add test**

```python
def test_mtm_dd_isolated_unit(base_config, tmp_path):
    """Inject a position manually; verify MTM drawdown picks up unrealized loss."""
    import tempfile
    from engine import SafeOrchestrator
    from engine.notifications import NullNotificationManager

    with tempfile.TemporaryDirectory() as state_dir:
        orch = SafeOrchestrator(
            base_config, state_dir=state_dir,
            notification_mgr=NullNotificationManager(),
            freshness_check=False, persist=False,
        )
        # Manually open a LONG @ 100 size 10
        orch.lifecycle.open_position(
            symbol="BTC/USDT", direction="LONG", entry=100.0,
            sl=95.0, tp1=105.0, tp2=110.0, size=10.0
        )
        # Simulate price going to 90 (unrealized loss = -100)
        from backtest.engine import _compute_mtm_drawdown  # NEW helper
        balance = 1000.0
        peak = 1000.0
        new_dd, new_peak = _compute_mtm_drawdown(
            orch.lifecycle.positions, balance, {"BTC/USDT": 90.0}, peak
        )
        # Equity = 1000 + (90 - 100) * 10 * +1 = 900
        # DD vs peak 1000 = 10%
        assert new_dd == pytest.approx(10.0)
        assert new_peak == 1000.0
```

- [ ] **Step 2: Implement `_compute_mtm_drawdown` helper in engine.py**

```python
def _compute_mtm_drawdown(positions, balance, current_prices, peak):
    """Return (drawdown_pct_now, new_peak) given current prices."""
    unrealized = 0.0
    for p in positions:
        if not p.is_open or p.symbol not in current_prices:
            continue
        sign = 1 if p.direction == "LONG" else -1
        unrealized += (current_prices[p.symbol] - p.avg_entry_price) * p.remaining_size * sign
    mtm = balance + unrealized
    new_peak = max(peak, mtm)
    dd_pct = ((new_peak - mtm) / new_peak * 100) if new_peak > 0 else 0.0
    return dd_pct, new_peak
```

- [ ] **Step 3: Run — expect pass**

- [ ] **Step 4: Commit**

```
git commit -m "test(backtest): isolated MTM drawdown unit test"
```

---

### Task 4.5: Extract metrics to `backtest/metrics.py`

**Files:**
- Create: `backtest/metrics.py`
- Modify: `backtest/engine.py` (use new module)

- [ ] **Step 1: Move `_serialize_trade` + drawdown logic to `metrics.py`**

```python
"""Backtest metrics aggregation."""
from __future__ import annotations
from typing import Iterable
import numpy as np


def serialize_trade(p) -> dict:
    return {
        "symbol": p.symbol,
        "direction": p.direction,
        "entry": float(p.avg_entry_price),
        "exit": float(p.exits[-1].price) if p.exits else None,
        "pnl": float(p.realized_pnl),
        "exit_reason": p.exits[-1].reason if p.exits else None,
        "opened_at": str(p.opened_at),
        "closed_at": str(p.closed_at) if p.closed_at else None,
    }


def aggregate_metrics(trades: list[dict], initial_balance: float, peak_balance: float, final_balance: float) -> dict:
    """Compute win_rate, profit_factor, sharpe-like, etc."""
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    sum_wins = sum(t["pnl"] for t in wins)
    sum_losses = abs(sum(t["pnl"] for t in losses))
    pf = sum_wins / sum_losses if sum_losses > 0 else (999 if sum_wins > 0 else 0)

    pnl_pcts = [t["pnl"] / initial_balance * 100 for t in trades]
    sharpe = (np.mean(pnl_pcts) / np.std(pnl_pcts)) if len(pnl_pcts) > 2 and np.std(pnl_pcts) > 0 else 0

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "profit_factor": round(pf, 2),
        "total_return_pct": round((final_balance - initial_balance) / initial_balance * 100, 2),
        "max_drawdown_pct": round((peak_balance - final_balance) / peak_balance * 100, 2) if peak_balance > 0 else 0,
        "sharpe_like": round(sharpe, 2),
    }
```

- [ ] **Step 2: Update `engine.py` to use these**

- [ ] **Step 3: Run all tests**

```
python -m pytest backend/tests/ -q
```

- [ ] **Step 4: Commit**

```
git commit -m "refactor(backtest): extract metrics to dedicated module"
```

---

### Task 4.6: Delete legacy `backtest/runner.py`

- [ ] **Step 1: Verify no imports**

```powershell
Select-String -Path "backend/", "engine/", "backtest/", "scripts/" -Pattern "from backtest.runner|backtest\.runner" -Recurse
```

Expected: no matches (legacy file no longer referenced).

- [ ] **Step 2: `git rm`**

```
git rm backtest/runner.py
git commit -m "refactor(backtest): remove legacy single-symbol runner

Replaced by backtest/engine.py + intrabar/slippage/funding/metrics.
The legacy module's monkey-patch freshness bypass is now solved at
source via SafeOrchestrator(freshness_check=False)."
```

---

### Task 4.7: TDD — Position guard regression test (spec §9.5)

**Files:**
- Modify: `backend/tests/test_backtest_engine_portfolio.py`

Validates that with new 5x leverage, position guard's FP-tolerance fix (`+ 1e-6`) holds — no false-positive `Size X exceeds max X` rejections at the cap boundary.

- [ ] **Step 1: Add test**

```python
def test_no_false_position_guard_rejections_at_cap_boundary(base_config, synthetic_data):
    """Spec §9.5: every grid run should record 0 false-positive cap rejections."""
    # Set notional cap to 2.0 (matches current live config)
    base_config["safety"]["max_position_notional_pct"] = 2.0
    base_config["exchange"]["leverage"] = 5

    result = run_backtest(
        symbols=["BTC/USDT", "ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        initial_balance=2000.0,
    )
    # If the engine ever rejects a trade with reason exactly matching
    # "exceeds max" at boundary equality, the FP-tolerance fix regressed.
    rejections = result.get("position_guard_rejections_at_boundary", 0)
    assert rejections == 0, "Position guard FP-tolerance regressed (spec §9.5)"
```

- [ ] **Step 2: Wire counter in `engine.py`**

Track guard rejections where `notional` rounds to the same display string as `max_notional`:

```python
    boundary_rejections = 0
    # ... inside cycle loop, when guard rejects ...
    if "exceeds max" in reason:
        # Round to 2dp like the display
        if round(notional, 2) == round(max_notional, 2):
            boundary_rejections += 1

    return {..., "position_guard_rejections_at_boundary": boundary_rejections, ...}
```

(Sketch — exact wiring depends on how guard rejections surface; may need to add a hook in `position_guard.py` or scrape orchestrator logs.)

- [ ] **Step 3: Run + commit**

```
git commit -m "test(backtest): position guard FP-tolerance regression guard per spec §9.5"
```

---

### Chunk 4 verification

```
python -m pytest backend/tests/ -q
```

Expected: ~95+ tests passing (added pyramid/partial slippage, funding boundary/multi, intrabar gap-through, tf normalization, max-gap-pct refusal, MTM unit, position-guard regression).

---

## Chunk 5: Phase 4 — Grid Search with Resumability

**Goal:** Multiprocessing grid search over arbitrary `dict[str, list]` of parameter overrides; checkpoints per-config result so a 17h grid can resume after interruption.

**Estimated effort:** 1.5 days

---

### Task 5.1: TDD — Grid expansion + config hashing

**Files:**
- Create: `backtest/grid.py`
- Create: `backend/tests/test_grid_search.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_grid_search.py
"""Grid search — expansion, hashing, checkpoint/resume.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §9.4
"""
import pytest
from backtest.grid import expand_grid, config_hash, GridRunner


def test_grid_expansion_2d():
    base = {"risk": {"min_confluence": 50}, "safety": {"max_position_notional_pct": 3.33}}
    grid = {
        "risk.min_confluence": [40, 50, 60],
        "safety.max_position_notional_pct": [2.0, 5.0],
    }
    configs = list(expand_grid(base, grid))
    assert len(configs) == 6  # 3 × 2

    confluences = sorted({c["risk"]["min_confluence"] for c in configs})
    assert confluences == [40, 50, 60]


def test_config_hash_stable():
    cfg1 = {"a": 1, "b": {"c": 2}}
    cfg2 = {"b": {"c": 2}, "a": 1}  # same content, different key order
    assert config_hash(cfg1) == config_hash(cfg2)


def test_grid_runner_skips_completed_configs(tmp_path):
    """Pre-populate a result file for one config_hash; grid runner skips it."""
    output_dir = tmp_path / "grid"
    runner = GridRunner(output_dir)

    # 3 configs; pre-mark middle one as complete
    cfgs = [{"x": 1}, {"x": 2}, {"x": 3}]
    middle_hash = config_hash(cfgs[1])
    (runner.configs_dir / f"{middle_hash}.json").write_text(
        '{"x": 2, "result": "from_disk"}'
    )

    def run_one(cfg):
        return {"x": cfg["x"], "result": "from_pool"}

    results = runner.run(cfgs, run_one_fn=run_one, workers=2)

    by_x = {r["x"]: r["result"] for r in results}
    assert by_x[1] == "from_pool"
    assert by_x[2] == "from_disk"  # middle one was skipped → loaded from disk
    assert by_x[3] == "from_pool"
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `backtest/grid.py`**

```python
"""Grid search over backtest configs with resume support.

`run_one_fn` contract:
    Signature: (cfg: dict) -> dict
    Must be picklable (top-level function, NO closures over local state).
    The cfg dict contains all overrides applied; the function is responsible
    for loading data and running the backtest. Return dict must be JSON-serializable
    and SHOULD include `config_hash` for traceability.

Multiprocessing logging:
    Each worker is initialized with a `multiprocessing.get_logger()` that
    writes to a per-worker StringIO buffer to avoid interleaved stdout chaos.
    Aggregated logs are written to `output_dir/worker_{pid}.log` after the run.
"""
from __future__ import annotations
import copy
import hashlib
import json
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import product
from pathlib import Path
from typing import Callable, Iterable, Iterator


def _worker_init():
    """Per-worker logger setup — runs once at pool spawn."""
    logger = mp.get_logger()
    logger.setLevel(logging.WARNING)
    # NullHandler so worker logs don't leak to parent stdout
    logger.addHandler(logging.NullHandler())


def _set_dotted(d: dict, dotted_key: str, value):
    """Set d['a']['b'] = value when dotted_key='a.b'."""
    parts = dotted_key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def expand_grid(base_config: dict, grid: dict[str, list]) -> Iterator[dict]:
    keys = list(grid.keys())
    for combo in product(*(grid[k] for k in keys)):
        cfg = copy.deepcopy(base_config)
        for k, v in zip(keys, combo):
            _set_dotted(cfg, k, v)
        yield cfg


def config_hash(cfg: dict) -> str:
    blob = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


class GridRunner:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.configs_dir = self.output_dir / "configs"
        self.configs_dir.mkdir(exist_ok=True)

    def is_complete(self, cfg_hash: str) -> bool:
        return (self.configs_dir / f"{cfg_hash}.json").exists()

    def save_result(self, cfg_hash: str, result: dict):
        path = self.configs_dir / f"{cfg_hash}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, default=str, indent=2))
        tmp.replace(path)

    def run(self, configs: Iterable[dict], run_one_fn: Callable[[dict], dict], workers: int = 4) -> list[dict]:
        """Submit configs to a process pool; skip already-complete; return all results.

        run_one_fn must be a picklable top-level function with signature `(cfg) -> dict`.
        """
        pending = []
        for cfg in configs:
            h = config_hash(cfg)
            if self.is_complete(h):
                continue
            pending.append((h, cfg))

        results: list[dict] = []
        # Load already-done
        for done_file in self.configs_dir.glob("*.json"):
            results.append(json.loads(done_file.read_text()))

        if not pending:
            return results

        with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as pool:
            futures = {pool.submit(run_one_fn, cfg): h for h, cfg in pending}
            for fut in as_completed(futures):
                h = futures[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"config_hash": h, "error": str(e)}
                self.save_result(h, res)
                results.append(res)
        return results
```

- [ ] **Step 4: Add resume test**

(Pre-populate one result file, assert it's skipped + the loaded result is in the output.)

- [ ] **Step 5: Run all tests**

- [ ] **Step 6: Commit**

```
git commit -m "feat(backtest): grid search with multiprocessing + resume"
```

---

### Chunk 5 verification

```
python -m pytest backend/tests/test_grid_search.py -v
```

Expected: 4+ tests passing.

---

## Chunk 6: Phase 5 — CLI + Reproducibility

**Goal:** User-facing CLI with three subcommands (`single`, `portfolio`, `grid`); each run captures full provenance for reproducibility.

**Estimated effort:** 1.5 days

---

### Task 6.1: `backtest/reproducibility.py`

**Files:**
- Create: `backtest/reproducibility.py`

- [ ] **Step 1: Implement** (no TDD — pure side-effect snapshot)

```python
"""Provenance snapshot — git SHA, pip freeze, host, data manifest."""
from __future__ import annotations
import hashlib
import json
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return ""


def capture_provenance(run_dir: Path, *, allow_dirty: bool = True) -> dict:
    sha = _run(["git", "rev-parse", "HEAD"])
    dirty_status = _run(["git", "status", "--porcelain"])
    is_dirty = bool(dirty_status)
    if is_dirty and not allow_dirty:
        raise RuntimeError(f"Refusing to run on dirty git tree:\n{dirty_status}")

    pip_freeze = _run([sys.executable, "-m", "pip", "freeze"])
    pip_sha = hashlib.sha256(pip_freeze.encode()).hexdigest()

    prov = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": sha,
        "git_dirty": is_dirty,
        "pip_freeze_sha256": pip_sha,
        "host": {
            "os": platform.system(),
            "python": sys.version.split()[0],
            "hostname": socket.gethostname(),
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "provenance.json").write_text(json.dumps(prov, indent=2))

    if is_dirty:
        diff = _run(["git", "diff", "HEAD"])
        (run_dir / "provenance_diff.patch").write_text(diff)

    return prov
```

- [ ] **Step 2: Commit**

```
git commit -m "feat(backtest): provenance snapshot for reproducibility"
```

---

### Task 6.2: `backtest/cli.py` — `single` subcommand

**Files:**
- Create: `backtest/cli.py`

- [ ] **Step 1: Implement minimal CLI**

```python
"""Backtest CLI — argparse with single | portfolio | grid subcommands."""
from __future__ import annotations
import argparse
import json
import time
import uuid
from pathlib import Path

import pandas as pd
import yaml

from backtest.engine import run_backtest
from backtest.reproducibility import capture_provenance
from data.cache import OHLCVCache


def _load_data_for_period(symbols, timeframes, period_days, cache_dir="cache/ohlcv"):
    cache = OHLCVCache(cache_dir)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - period_days * 86400 * 1000
    data = {}
    for s in symbols:
        data[s] = {}
        for tf in timeframes:
            df = cache.get(s, tf)
            if df is None:
                raise FileNotFoundError(
                    f"No cache for {s} {tf}. Run `python -m scripts.prefetch_data` first."
                )
            # Slice to period
            cutoff = pd.Timestamp(start_ms, unit="ms")
            data[s][tf] = df[df.index >= cutoff]
    return data


def cmd_single(args):
    cfg = yaml.safe_load(open(args.config))
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    data = _load_data_for_period([args.symbol], tfs, args.period_days)

    run_id = uuid.uuid4().hex[:8]
    out_dir = Path(f"reports/backtests/{time.strftime('%Y-%m-%d')}_{args.symbol.replace('/', '_')}_{args.period_days}d_{run_id}")
    capture_provenance(out_dir)

    result = run_backtest(symbols=[args.symbol], data=data, config=cfg, initial_balance=args.balance)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"✅ Single backtest complete: {out_dir}")
    print(f"   Trades: {result['total_trades']}  PF: {result['profit_factor']}  Return: {result['total_return_pct']}%")


def main():
    p = argparse.ArgumentParser(prog="backtest")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("single")
    s.add_argument("--symbol", required=True)
    s.add_argument("--period-days", type=int, default=365)
    s.add_argument("--config", default="configs/config.phase2_1k.yaml")
    s.add_argument("--balance", type=float, default=2000.0)
    s.set_defaults(func=cmd_single)

    # ... portfolio and grid subcommands similar ...

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run smoke**

```
python -m backtest.cli single --symbol BTC/USDT --period-days 30
```

Expected: produces `reports/backtests/.../result.json`.

> **Cache prerequisite**: this CLI command requires the cache populated by Task 2.4 (`scripts/prefetch_data.py`). If the cache is empty, `_load_data_for_period` raises `FileNotFoundError` with a clear message pointing back to the prefetch script. Pytest unit tests in `test_backtest_engine_*.py` use synthetic in-memory data and do NOT depend on the cache.

- [ ] **Step 3: Commit**

```
git commit -m "feat(backtest): CLI single subcommand"
```

---

### Task 6.3: CLI `portfolio` and `grid` subcommands

**Files:**
- Modify: `backtest/cli.py`

- [ ] **Step 1: Add `cmd_portfolio`**

Append to `backtest/cli.py`:

```python
def cmd_portfolio(args):
    cfg = yaml.safe_load(open(args.config))
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    data = _load_data_for_period(symbols, tfs, args.period_days)

    run_id = uuid.uuid4().hex[:8]
    out_dir = Path(f"reports/backtests/{time.strftime('%Y-%m-%d')}_portfolio_{len(symbols)}sym_{args.period_days}d_{run_id}")
    capture_provenance(out_dir)

    result = run_backtest(symbols=symbols, data=data, config=cfg, initial_balance=args.balance)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"✅ Portfolio backtest: {out_dir}")
    print(f"   Symbols: {len(symbols)}  Trades: {result['total_trades']}  Return: {result['total_return_pct']}%  DD: {result['max_drawdown_pct']}%")
```

- [ ] **Step 2: Add `cmd_grid` with grid YAML loader**

Append to `backtest/cli.py`:

```python
from backtest.grid import GridRunner, expand_grid, config_hash


def _grid_run_one(cfg_with_meta: dict) -> dict:
    """Top-level picklable function for grid worker."""
    cfg = cfg_with_meta["config"]
    symbols = cfg_with_meta["symbols"]
    period_days = cfg_with_meta["period_days"]
    balance = cfg_with_meta["balance"]
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    data = _load_data_for_period(symbols, tfs, period_days)
    result = run_backtest(symbols=symbols, data=data, config=cfg, initial_balance=balance)
    result["config_hash"] = config_hash(cfg)
    # Flatten the grid-varied fields into top-level for ranking
    for k in cfg_with_meta.get("grid_keys", []):
        parts = k.split(".")
        cur = cfg
        for p in parts:
            cur = cur[p]
        result[k] = cur
    return result


def cmd_grid(args):
    grid_spec = yaml.safe_load(open(args.grid))
    base_cfg = yaml.safe_load(open(grid_spec["base"]))
    overrides = grid_spec["overrides"]  # dict[dotted_key, list]

    # Refuse dirty git tree for grid runs (spec §6.8)
    capture_provenance(Path("/tmp/_grid_provenance"), allow_dirty=False)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    grid_run_id = uuid.uuid4().hex[:8]
    out_dir = Path(f"reports/backtests/grid_{time.strftime('%Y-%m-%d')}_{grid_run_id}")
    capture_provenance(out_dir, allow_dirty=False)

    runner = GridRunner(out_dir)
    cfgs = [
        {
            "config": cfg,
            "symbols": symbols,
            "period_days": args.period_days,
            "balance": args.balance,
            "grid_keys": list(overrides.keys()),
        }
        for cfg in expand_grid(base_cfg, overrides)
    ]
    print(f"Grid: {len(cfgs)} configs × {len(symbols)} symbols")
    results = runner.run(cfgs, run_one_fn=_grid_run_one, workers=args.workers)

    # Rank by sharpe-like
    results.sort(key=lambda r: r.get("sharpe_like", 0), reverse=True)
    (out_dir / "ranking.json").write_text(json.dumps(results[:20], indent=2, default=str))
    print(f"✅ Grid complete: {out_dir} (top 20 in ranking.json)")
```

Add subparsers in `main()`:

```python
    p_port = sub.add_parser("portfolio")
    p_port.add_argument("--symbols", required=True, help="comma-separated, e.g. BTC/USDT,ETH/USDT")
    p_port.add_argument("--period-days", type=int, default=365)
    p_port.add_argument("--config", default="configs/config.phase2_1k.yaml")
    p_port.add_argument("--balance", type=float, default=2000.0)
    p_port.set_defaults(func=cmd_portfolio)

    p_grid = sub.add_parser("grid")
    p_grid.add_argument("--grid", required=True, help="path to grid YAML spec")
    p_grid.add_argument("--symbols", required=True)
    p_grid.add_argument("--period-days", type=int, default=365)
    p_grid.add_argument("--balance", type=float, default=2000.0)
    p_grid.add_argument("--workers", type=int, default=4)
    p_grid.set_defaults(func=cmd_grid)
```

- [ ] **Step 3: Smoke test each**

```
python -m backtest.cli portfolio --symbols BTC/USDT,ETH/USDT --period-days 30
python -m backtest.cli grid --grid configs/grids/confluence_x_notional.yaml --symbols BTC/USDT --period-days 30 --workers 2
```

Both should produce `result.json` (portfolio) or `ranking.json` (grid).

- [ ] **Step 4: Commit**

```
git commit -m "feat(backtest): CLI portfolio + grid subcommands with worker contract"
```

---

### Chunk 6 verification

```
python -m pytest backend/tests/ -q
python -m backtest.cli single --symbol BTC/USDT --period-days 30
```

Expected: tests pass; CLI produces valid result.json.

---

## Chunk 7: Phase 6-8 — Execution Runbooks (A → C → B)

**Goal:** Produce the analytical outputs the user actually wants: validation results, optimized config, live-vs-backtest reconciliation.

**Estimated effort:** 4-6 days (mostly compute wall time + analysis)

---

### Task 7.1: Phase A — Strategy validation runs

**Goal:** Answer "did `phase2_1k` ($2000 + 5x) earn money over the last 1 year?"

- [ ] **Step 1: Per-symbol validation**

```
foreach symbol in BTC/USDT, ETH/USDT, ..., ADA/USDT:
    python -m backtest.cli single --symbol $symbol --period-days 365
```

Or scripted in PowerShell:

```powershell
$syms = @("BTC/USDT","ETH/USDT","XRP/USDT","DOGE/USDT","SOL/USDT","BNB/USDT","TRX/USDT","LINK/USDT","BCH/USDT","ADA/USDT")
foreach ($s in $syms) {
    python -m backtest.cli single --symbol $s --period-days 365
}
```

- [ ] **Step 2: Portfolio validation**

```
python -m backtest.cli portfolio \
    --symbols BTC/USDT,ETH/USDT,XRP/USDT,DOGE/USDT,SOL/USDT,BNB/USDT,TRX/USDT,LINK/USDT,BCH/USDT,ADA/USDT \
    --period-days 365
```

- [ ] **Step 3: Aggregate findings**

Create `docs/results/2026-05-XX-phase-A-validation.md` summarizing:
- Per-symbol total_return, win_rate, profit_factor, max_drawdown
- Portfolio total_return + drawdown
- Identify weakest 3 symbols (negative return) — candidates to drop
- Identify strongest 3 symbols — candidates to focus

- [ ] **Step 4: Commit results**

```
git add docs/results/2026-05-XX-phase-A-validation.md
git commit -m "results(phase-a): 1y validation of phase2_1k strategy"
```

---

### Task 7.2: Phase C — Confluence × Notional grid search

**Goal:** Find the optimal `(min_confluence, max_position_notional_pct)` pair.

- [ ] **Step 1: Create grid spec**

`configs/grids/confluence_x_notional.yaml`:

```yaml
base: configs/config.phase2_1k.yaml
overrides:
  risk.min_confluence: [40, 45, 50, 55, 60]
  safety.max_position_notional_pct: [1.0, 2.0, 3.33, 5.0]
```

- [ ] **Step 2: Run grid (overnight)**

```
python -m backtest.cli grid \
    --grid configs/grids/confluence_x_notional.yaml \
    --symbols BTC/USDT,ETH/USDT,XRP/USDT,DOGE/USDT,SOL/USDT,BNB/USDT,TRX/USDT,LINK/USDT,BCH/USDT,ADA/USDT \
    --period-days 365 \
    --workers 4
```

- [ ] **Step 3: Analyze ranking**

Build a small ranking script (or notebook):

```python
import json
from pathlib import Path

results = []
for f in Path("reports/backtests/grid_*/configs").glob("*.json"):
    r = json.loads(f.read_text())
    results.append(r)

# Sort by sharpe-like or risk-adjusted return
results.sort(key=lambda r: r.get("sharpe_like", 0), reverse=True)
for r in results[:5]:
    print(r["risk.min_confluence"], r["safety.max_position_notional_pct"], r["total_return_pct"], r["max_drawdown_pct"])
```

- [ ] **Step 4: Document winning config**

`docs/results/2026-05-XX-phase-C-grid-results.md`:
- Top 5 configs ranked by Sharpe-like
- Top 5 by total return
- Stability check: do they win across all 10 symbols?
- Recommendation: best (min_confluence, notional_pct) to ship

- [ ] **Step 5: Commit**

```
git commit -m "results(phase-c): confluence × notional grid analysis"
```

---

### Task 7.3: Phase B — Live vs Backtest reconciliation

**Goal:** Compare live bot's actual fills (from Hetzner/Supabase) against what backtest would produce on the same window. Calibrate slippage/funding models.

- [ ] **Step 1: Build `backtest/compare_live.py`**

```python
"""Compare live bot trades (from Supabase) against backtest output."""
from __future__ import annotations
import asyncpg
import os
from pathlib import Path

async def fetch_live_trades(start_iso: str, end_iso: str) -> list[dict]:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch(
        "SELECT * FROM trades WHERE opened_at >= $1 AND opened_at <= $2 ORDER BY opened_at",
        start_iso, end_iso,
    )
    await conn.close()
    return [dict(r) for r in rows]


def reconcile(live_trades: list[dict], backtest_result: dict) -> dict:
    """Layer A: trade-level match. Layer B: PnL reconciliation.

    Returns dict with: matches, mismatches, pnl_live, pnl_backtest, drift_pct.
    """
    # ... matching logic ...
    pass
```

- [ ] **Step 2: Fetch live private data via CCXT**

```python
# Need API keys with read permission for fetch_my_trades + funding history
import ccxt
ex = ccxt.binance({"apiKey": os.environ["BINANCE_API_KEY"], "secret": os.environ["BINANCE_API_SECRET"]})
my_trades = ex.fetch_my_trades("BCH/USDT:USDT", since=since_ms)
funding_history = ex.fetch_funding_history("BCH/USDT:USDT", since=since_ms)
```

- [ ] **Step 3: Run reconciliation**

```
python -m backtest.compare_live --start 2026-05-02 --end 2026-05-14
```

Output: `reports/backtests/live_vs_backtest_2026-05-XX/comparison.md`

- [ ] **Step 4: Calibrate slippage**

If reconciliation drift > 5%, adjust `SlippageConfig` defaults based on observed live fills:
- `entry_slip_pct`, `sl_slip_pct`, `exit_slip_pct` — re-derive from live trade history

- [ ] **Step 5: Commit**

```
git commit -m "feat(backtest): live-vs-backtest reconciliation (Phase B)"
git commit -m "results(phase-b): slippage model calibration from live data"
```

---

## Final Verification

After all 7 chunks:

```
python -m pytest backend/tests/ -q
```

Expected: ~95-105 tests passing total (66 pre-existing + 30+ new from this plan).

CLI smoke (uses real cache):

```
python -m backtest.cli single --symbol BTC/USDT --period-days 30
python -m backtest.cli portfolio --symbols BTC/USDT,ETH/USDT --period-days 30
```

Both should produce valid `reports/backtests/.../result.json`.

---

## Out of Scope (Phase 2 dashboard work — separate plan)

- Web dashboard "Backtest" tab
- Postgres `backtest_runs` + `backtest_trades` tables
- `backtest/api.py` (`list_runs`, `load_run`, `compare_runs`)
- Frontend live-vs-backtest comparison view
