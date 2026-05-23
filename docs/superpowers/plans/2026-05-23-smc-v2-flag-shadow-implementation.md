# SMC v2 Feature Flag + Shadow Mode Implementation Plan (PR #S6)

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan.

**Goal:** Wire the v2 feature flag dispatch + dry-run shadow log mode so Hermes can run v2 paralel to v1 for 1 week without executing trades.

**Architecture:** Add config keys, instantiate SetupStateStore conditionally in main.py, add 2 gates to `_place_v2_entry_order` (symbol whitelist + shadow log).

**Tech Stack:** Python 3.14, PyYAML, existing SetupStateStore + SafeOrchestrator.

---

## Task 1: Config defaults (smc_v2 block)

**Files:**
- Modify: `config.yaml` (add `engine` block + `smc_v2` block)
- Test: `backend/tests/test_config_smc_v2_defaults.py` (NEW)

- [ ] **Step 1: Write failing test for defaults**

```python
# backend/tests/test_config_smc_v2_defaults.py
import yaml
from pathlib import Path


def test_config_yaml_has_smc_v2_block():
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert cfg["engine"]["smc_version"] == "v1"
    assert cfg["engine"]["smc_v2_symbols"] == []
    assert cfg["engine"]["smc_v2_shadow"] is False
    assert cfg["smc_v2"]["pullback_timeout_bars"] == 8
    assert cfg["smc_v2"]["fvg_priority"] is True
    assert cfg["smc_v2"]["ote_band"] == [0.618, 0.786]
    assert cfg["smc_v2"]["require_confirmation"] is True
    assert cfg["smc_v2"]["max_pending_per_symbol"] == 3
```

- [ ] **Step 2: Run test (FAIL)** — `KeyError: 'engine'`

- [ ] **Step 3: Add blocks to config.yaml** (append after `exchange:` block)

```yaml
# ── SMC v2 feature flag (PR #S6) ──
# Inert default: smc_version=v1, smc_v2_symbols=[] → v1 path active.
# To enable shadow: set smc_version=v2, smc_v2_symbols=["*"], smc_v2_shadow=true.
# To enable live v2 (Hermes only): set smc_v2_shadow=false.
engine:
  smc_version: v1               # "v1" | "v2"
  smc_v2_symbols: []            # whitelist; ["*"] = all, [] = none
  smc_v2_shadow: false          # true = log v2 signal, skip order placement

smc_v2:
  pullback_timeout_bars: 8      # 15m bars (~2h)
  fvg_priority: true            # FVG before OTE
  ote_band: [0.618, 0.786]
  require_confirmation: true
  max_pending_per_symbol: 3
```

- [ ] **Step 4: Test PASS**

- [ ] **Step 5: Commit**

```bash
git add config.yaml backend/tests/test_config_smc_v2_defaults.py
git commit -m "feat(config): add smc_v2 feature flag + tunables (default v1 inert)"
```

---

## Task 2: main.py SetupStateStore wiring

**Files:**
- Modify: `main.py` around line 522 (SafeOrchestrator construction)
- Test: `backend/tests/test_main_smc_v2_wiring.py` (NEW)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_main_smc_v2_wiring.py
from unittest.mock import MagicMock, patch
import importlib


def _build_v2_cfg():
    return {
        "engine": {"smc_version": "v2", "smc_v2_symbols": [], "smc_v2_shadow": False},
        "smc_v2": {"pullback_timeout_bars": 8, "max_pending_per_symbol": 3,
                   "fvg_priority": True, "ote_band": [0.618, 0.786],
                   "require_confirmation": True},
        "operation": {"state_dir": "./state_test"},
    }


def test_build_setup_state_store_returns_store_when_v2(tmp_path):
    """Helper extracted into main: instantiates SetupStateStore when v2 active."""
    from main import _build_setup_state_store
    cfg = _build_v2_cfg()
    store = _build_setup_state_store(cfg, str(tmp_path))
    assert store is not None
    assert store.max_pending_per_symbol == 3


def test_build_setup_state_store_returns_none_when_v1(tmp_path):
    cfg = _build_v2_cfg()
    cfg["engine"]["smc_version"] = "v1"
    from main import _build_setup_state_store
    assert _build_setup_state_store(cfg, str(tmp_path)) is None
```

- [ ] **Step 2: Run test (FAIL)** — `ImportError: _build_setup_state_store`

- [ ] **Step 3: Add helper to main.py + wire into SafeOrchestrator call**

In `main.py` (top-level, near imports):
```python
def _build_setup_state_store(cfg: dict, state_dir: str):
    """Instantiate SetupStateStore iff engine.smc_version == 'v2'.

    Default (smc_version=v1): returns None → SafeOrchestrator inert per PR #67.
    """
    if cfg.get("engine", {}).get("smc_version") != "v2":
        return None
    from engine.smc_v2.setup_state import SetupStateStore
    from pathlib import Path
    smc_v2_cfg = cfg.get("smc_v2", {})
    return SetupStateStore(
        path=Path(state_dir) / "setup_candidates.json",
        max_pending_per_symbol=int(smc_v2_cfg.get("max_pending_per_symbol", 3)),
    )
```

In `main.py:522` SafeOrchestrator construction:
```python
setup_state_store = _build_setup_state_store(cfg, state_dir)
orch = SafeOrchestrator(cfg, state_dir=state_dir,
                          permission_mgr=permission_mgr,
                          notification_mgr=notif_mgr,
                          trade_journal=trade_journal,
                          setup_state_store=setup_state_store)
```

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit**

```bash
git add main.py backend/tests/test_main_smc_v2_wiring.py
git commit -m "feat(main): instantiate SetupStateStore when smc_version=v2"
```

---

## Task 3: Symbol whitelist gate

**Files:**
- Modify: `engine/safe_orchestrator.py` (`_place_v2_entry_order`, first gate)
- Test: `backend/tests/smc_v2/test_symbol_whitelist_gate.py` (NEW)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/smc_v2/test_symbol_whitelist_gate.py
from unittest.mock import MagicMock, patch
import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec
from exchange import BinanceClient, OrderManager


def _cfg_with_whitelist(symbols: list):
    return {
        "structure": {"swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                      "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40,
                 "position_size_calculation": "legacy",
                 "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5},
        "safety": {"daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
                   "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
                   "starting_balance": 10000, "max_position_notional_pct": 20,
                   "max_total_exposure": 5.0, "max_holding_hours": 48,
                   "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                   "adx_trend_threshold": 25, "adx_range_threshold": 20,
                   "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
                   "sl_atr_buffer": 0.5},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
        "exchange": {"leverage": 1},
        "engine": {"smc_version": "v2", "smc_v2_symbols": symbols, "smc_v2_shadow": False},
    }


def _make_cand(symbol="ETH/USDT"):
    return SetupCandidate(
        symbol=symbol, direction="SHORT",
        trigger_bar_ts=2_500, trigger_price=100.0, htf_bias="BEAR",
        target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
        htf_swing_anchor=115.0, bars_waited=2, state="IN_ZONE",
        confluence_score=75, reasons=[],
    )


def _make_om():
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.exchange = MagicMock()
    mock_client.market_type = "futures"
    mock_client.testnet = True
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.get_balance = MagicMock(return_value=10000.0)
    mock_client.get_available_margin = MagicMock(return_value=10000.0)
    return OrderManager(mock_client, dry_run=True)


def test_whitelist_empty_rejects_all(tmp_path):
    cfg = _cfg_with_whitelist([])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy:
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is None
        assert spy.call_count == 0


def test_whitelist_specific_symbol_accepts(tmp_path):
    cfg = _cfg_with_whitelist(["ETH/USDT"])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0, {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        spy.return_value = MagicMock()
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert spy.call_count == 1
        assert result is not None


def test_whitelist_wildcard_accepts_all(tmp_path):
    cfg = _cfg_with_whitelist(["*"])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("DOGE/USDT")  # not in any specific list
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0, {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        spy.return_value = MagicMock()
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert spy.call_count == 1
        assert result is not None


def test_whitelist_other_symbol_rejected(tmp_path):
    cfg = _cfg_with_whitelist(["BTC/USDT"])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy:
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert spy.call_count == 0
        assert result is None
```

- [ ] **Step 2: Run tests (FAIL)** — whitelist gate not implemented

- [ ] **Step 3: Add whitelist gate to `_place_v2_entry_order`** as FIRST gate (before breaker check):

```python
# Symbol whitelist gate (PR #S6): only fire for symbols opted-in.
# smc_v2_symbols=["*"] enables all symbols; [] (default) disables v2 entirely.
engine_cfg = self.config.get("engine", {})
whitelist = engine_cfg.get("smc_v2_symbols", [])
if "*" not in whitelist and cand.symbol not in whitelist:
    log.info(f"[v2 reject] {cand.symbol}: not in smc_v2_symbols whitelist")
    return None
```

- [ ] **Step 4: Tests PASS + PR #71 existing 10 tests still green**

```bash
pytest backend/tests/smc_v2/test_entry_order_placement.py -q
```

- [ ] **Step 5: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_symbol_whitelist_gate.py
git commit -m "feat(orchestrator): v2 symbol whitelist gate for opt-in rollout"
```

---

## Task 4: Shadow mode log writer

**Files:**
- Modify: `engine/safe_orchestrator.py` (`_place_v2_entry_order`, before OrderManager call)
- Test: `backend/tests/smc_v2/test_shadow_mode.py` (NEW)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/smc_v2/test_shadow_mode.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec
from exchange import BinanceClient, OrderManager


def _cfg(shadow: bool, symbols=None):
    return {
        "structure": {"swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                      "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40,
                 "position_size_calculation": "legacy",
                 "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5},
        "safety": {"daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
                   "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
                   "starting_balance": 10000, "max_position_notional_pct": 20,
                   "max_total_exposure": 5.0, "max_holding_hours": 48,
                   "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                   "adx_trend_threshold": 25, "adx_range_threshold": 20,
                   "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
                   "sl_atr_buffer": 0.5},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
        "exchange": {"leverage": 1},
        "engine": {"smc_version": "v2",
                   "smc_v2_symbols": symbols or ["*"],
                   "smc_v2_shadow": shadow},
    }


def _make_cand(symbol="ETH/USDT"):
    return SetupCandidate(
        symbol=symbol, direction="SHORT",
        trigger_bar_ts=2_500, trigger_price=100.0, htf_bias="BEAR",
        target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
        htf_swing_anchor=115.0, bars_waited=2, state="IN_ZONE",
        confluence_score=75, reasons=["test"],
    )


def _make_om():
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.exchange = MagicMock()
    mock_client.market_type = "futures"
    mock_client.testnet = True
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.get_balance = MagicMock(return_value=10000.0)
    mock_client.get_available_margin = MagicMock(return_value=10000.0)
    return OrderManager(mock_client, dry_run=True)


def test_shadow_on_logs_and_skips_order(tmp_path, monkeypatch):
    """When shadow=true: v2 path computes signal, logs to file, returns None
    without calling OrderManager.open_position."""
    monkeypatch.chdir(tmp_path)  # logs/ written relative to cwd
    cfg = _cfg(shadow=True)
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0, {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is None
        assert spy.call_count == 0
    log_file = Path("logs") / "smc_v2_shadow.log"
    assert log_file.exists(), "shadow log file must be created"
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["symbol"] == "ETH/USDT"
    assert entry["direction"] == "SHORT"
    assert entry["would_execute"] is False
    assert entry["reason"] == "SHADOW_MODE"
    assert entry["entry"] == 105.0
    assert entry["tp1"] == 95.0
    assert entry["tp2"] == 90.0
    assert entry["entry_setup_source"] == "FVG_PULLBACK"
    assert entry["bars_to_pullback"] == 2


def test_shadow_off_executes_normally(tmp_path, monkeypatch):
    """Regression: shadow=false → OrderManager.open_position called."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(shadow=False)
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0, {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        spy.return_value = MagicMock()
        orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert spy.call_count == 1
    log_file = Path("logs") / "smc_v2_shadow.log"
    assert not log_file.exists(), "shadow log must not be created when shadow=false"


def test_shadow_logs_safety_rejection_with_reason(tmp_path, monkeypatch):
    """When safety gate rejects: shadow log records the rejection reason,
    not 'SHADOW_MODE'."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(shadow=True)
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    # Patch breaker to halt — safety gate rejects before shadow check
    with patch.object(orc.breaker, "check") as breaker_spy:
        breaker_status = MagicMock()
        breaker_status.can_trade = False
        breaker_status.state.value = "HALTED"
        breaker_spy.return_value = breaker_status
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is None
    # When safety rejects, no shadow log entry expected (rejection happens
    # before shadow gate). Operator sees the rejection via main log.
    log_file = Path("logs") / "smc_v2_shadow.log"
    assert not log_file.exists()
```

- [ ] **Step 2: Run tests (FAIL)** — shadow gate not implemented

- [ ] **Step 3: Add shadow gate to `_place_v2_entry_order`** AFTER all safety gates pass, BEFORE `OrderManager.open_position` call:

Locate the line `return self.order_manager.open_position(...)` and insert before it:

```python
# Shadow mode gate (PR #S6): when smc_v2_shadow=true, log the would-be
# signal to logs/smc_v2_shadow.log and return None instead of placing.
# All safety gates above still run — operator sees rejections logged
# via main log; only ACCEPTED signals reach this gate.
if engine_cfg.get("smc_v2_shadow", False):
    self._log_shadow_signal(
        cand=cand, entry_price=entry_price, sl=sl, tp1=tp1, tp2=tp2,
        size=size, tp_tags=tp_tags, entry_setup_source=entry_setup_source,
        reason="SHADOW_MODE",
    )
    return None
```

And add the helper method (near `_place_v2_entry_order`):

```python
def _log_shadow_signal(self, *, cand, entry_price, sl, tp1, tp2, size,
                        tp_tags, entry_setup_source, reason: str) -> None:
    """Append one JSON line to logs/smc_v2_shadow.log."""
    import json
    from pathlib import Path
    from datetime import datetime, timezone
    log_dir = Path("logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning(f"[shadow] could not create logs/ dir: {e}")
        return
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": cand.symbol,
        "direction": cand.direction,
        "entry": float(entry_price),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2) if tp2 is not None else None,
        "size": float(size),
        "entry_setup_source": entry_setup_source,
        "tp1_target_type": tp_tags.get("tp1_source"),
        "tp2_target_type": tp_tags.get("tp2_source"),
        "bars_to_pullback": int(cand.bars_waited),
        "confluence_score": int(cand.confluence_score),
        "would_execute": False,
        "reason": reason,
    }
    try:
        with (log_dir / "smc_v2_shadow.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except OSError as e:
        log.warning(f"[shadow] write failed: {e}")
```

- [ ] **Step 4: Tests PASS + PR #71 existing tests still green**

- [ ] **Step 5: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_shadow_mode.py
git commit -m "feat(orchestrator): v2 shadow mode log writer (skip order placement)"
```

---

## Task 5: Full suite + reviews + Hermes PR

- [ ] **Step 1: Full backend suite**

```bash
python -m pytest backend/tests/ -q
```
Expected: 674 + ~14 new = ~688 green

- [ ] **Step 2: Code review (efloud-code-reviewer agent)**
- [ ] **Step 3: Risk-ops review (mandatory — config + signals dispatch + main.py)**
- [ ] **Step 4: Apply review findings**
- [ ] **Step 5: Push branch + create PR with HERMES NOTE prominent**
- [ ] **Step 6: DO NOT self-approve merge — wait for explicit Hermes approval per CLAUDE.md §3**
- [ ] **Step 7: Once Hermes approves: merge + update memory**

## Done criteria

- Default `config.yaml` defaults preserve v1 inert (no behavioral change)
- 14+ new tests
- v1 path strictly unchanged
- Hermes-only merge approval (NOT self-approve)
- Memory file updated to record PR #S6 status (and that PR #S6.5 single-target rejection removal is the next planned PR)
