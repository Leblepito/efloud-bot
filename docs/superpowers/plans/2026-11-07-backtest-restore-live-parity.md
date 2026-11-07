# Backtest restore on the live trade logic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `backtest/` back from `562a6a3^` so a NET-cost backtest runs the bot's **current** trade logic (`configs/config.phase2_1k.yaml` → real `SafeOrchestrator.run_cycle`), with exits that match the exchange (TP1 50 % → SL to break-even → TP2) and no network/LLM calls.

**Architecture:** Restore the old package and its 13 test modules verbatim, then close four live-parity gaps in `backtest/engine.py` + `backtest/intrabar.py`: config-derived `smc_version`, an exchange-parity exit model, an offline guard for LLM/agent/Kronos, and a CLI that fails on too many skipped cycles. The live journal parity check is informational.

**Tech Stack:** Python 3.11/3.12, pandas, pytest, existing `engine/` + `data/cache.OHLCVCache` + `scripts/prefetch_data.py`.

Spec: `docs/superpowers/specs/2026-11-07-operator-decisions-and-backtest-restore-design.md` §2–§3.

## Global Constraints

- No change to any trading logic or parameter outside `backtest/` (CLAUDE.md Karpathy #1/#3).
- Default run = `configs/config.phase2_1k.yaml` unchanged; its `backtest:` block (commission 0.04 %/side, funding 0.01 %/8 h) makes the default NET.
- A backtest must never reach a network: LLM factory patched to a null client; `agent_team.enabled` and `kronos.enabled` forced false in the run's config copy.
- Intrabar order inside one bar is pessimistic: SL before TP1; TP2 is never filled in the same bar as TP1.
- Windows: `grid` stays serial by default.
- After adding test files, run `python scripts/regression_ledger.py render`.

## File map

| File | Responsibility |
|---|---|
| `backtest/*.py` (restored, 12 files) | Harness; only `engine.py`, `intrabar.py`, `cli.py` change |
| `backtest/intrabar.py` | + `resolve_exit(pos, bar)`: exchange-parity exit for one bar |
| `backtest/engine.py` | config-derived `smc_version`; uses `resolve_exit` + `lifecycle.partial_close`; `_offline_run_config()` + `_offline_llm()` |
| `backtest/cli.py` | exit code 3 when skipped cycles > 1 % |
| `backend/tests/test_backtest_*.py`, `tests/test_backtest_max_hold.py`, `backend/tests/test_evaluate_backtest_gates.py`, `scripts/evaluate_backtest_gates.py` (restored) | existing coverage |
| `tests/backtest/test_live_parity.py` (new) | exit model, smc_version, offline guard, NET default, CLI exit code |

---

### Task 1: Restore the package and tests verbatim; triage drift

**Files:**
- Restore: everything under `562a6a3^:backtest/`, `562a6a3^:scripts/evaluate_backtest_gates.py`, and the 13 test modules listed in the spec §3.1
- Modify (only if a restored test fails because live code legitimately changed): the failing test, with a one-line comment `# drift since 562a6a3: <what changed>`

- [ ] **Step 1: Restore**

```bash
git checkout 562a6a3^ -- backtest scripts/evaluate_backtest_gates.py \
  backend/tests/test_backtest_cli_compare.py backend/tests/test_backtest_commission.py \
  backend/tests/test_backtest_comparison.py backend/tests/test_backtest_engine_portfolio.py \
  backend/tests/test_backtest_engine_single.py backend/tests/test_backtest_engine_v2.py \
  backend/tests/test_backtest_funding.py backend/tests/test_backtest_hygiene_batch1.py \
  backend/tests/test_backtest_metrics_tp2_optional.py backend/tests/test_backtest_sim_time.py \
  backend/tests/test_backtest_social_tags.py backend/tests/test_evaluate_backtest_gates.py \
  tests/test_backtest_max_hold.py
```

- [ ] **Step 2: Run the restored tests**

Run: `python -m pytest -q -p no:cacheprovider backend/tests/test_backtest_*.py backend/tests/test_evaluate_backtest_gates.py tests/test_backtest_max_hold.py`
Expected: see "Task 1 drift findings" at the end of this plan. Fix only drift caused by live-code changes. Any failure that points at a harness bug stays red and is handled in Task 2–4.

- [ ] **Step 3: Re-render the ledger, then commit**

```bash
python scripts/regression_ledger.py render
git add backtest scripts/evaluate_backtest_gates.py backend/tests/test_backtest_*.py \
  backend/tests/test_evaluate_backtest_gates.py tests/test_backtest_max_hold.py REGRESSION.md
git commit -m "feat(backtest): restore backtest/ and its tests from 562a6a3^"
```

### Task 2: Exchange-parity exit model (TP1 50 % → BE → TP2)

**Files:**
- Modify: `backtest/intrabar.py` (add `resolve_exit`)
- Modify: `backtest/engine.py` (`_PosView`, intrabar loop)
- Test: `tests/backtest/test_live_parity.py`

**Interfaces:**
- Produces: `resolve_exit(pos, bar: Bar) -> tuple[Optional[str], Optional[float]]`, where `pos` exposes `.direction, .sl, .tp1, .tp2, .tp1_hit`; level ∈ {"SL","TP1","TP2", None}.

- [ ] **Step 1: Write the failing tests** (`tests/backtest/test_live_parity.py`; `tests/backtest/__init__.py` empty)

```python
"""Backtest live-parity (spec 2026-11-07 §3.2)."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

import backtest.engine as bt_engine
from backtest.engine import run_backtest
from backtest.intrabar import Bar, resolve_exit
from backtest.slippage import SlippageConfig, adverse_fill
from engine import SafeOrchestrator


def _pos(direction="LONG", sl=90.0, tp1=110.0, tp2=120.0, tp1_hit=False):
    return SimpleNamespace(direction=direction, sl=sl, tp1=tp1, tp2=tp2, tp1_hit=tp1_hit)


class TestResolveExit:
    def test_sl_wins_when_sl_and_tp1_touch_the_same_bar(self):
        assert resolve_exit(_pos(), Bar(100, 111, 89, 100)) == ("SL", 90.0)

    def test_tp1_before_hit(self):
        assert resolve_exit(_pos(), Bar(100, 111, 95, 108)) == ("TP1", 110.0)

    def test_tp2_not_filled_in_the_tp1_bar(self):
        assert resolve_exit(_pos(), Bar(100, 125, 95, 121)) == ("TP1", 110.0)

    def test_tp2_after_tp1_hit(self):
        assert resolve_exit(_pos(sl=100.0, tp1_hit=True), Bar(115, 121, 112, 120)) == ("TP2", 120.0)

    def test_break_even_stop_after_tp1(self):
        assert resolve_exit(_pos(sl=100.0, tp1_hit=True), Bar(105, 106, 99, 100)) == ("SL", 100.0)

    def test_gap_fills_at_open(self):
        assert resolve_exit(_pos(), Bar(85, 86, 80, 82)) == ("SL", 85.0)
        assert resolve_exit(_pos(direction="SHORT", sl=110.0, tp1=90.0, tp2=80.0),
                            Bar(88, 89, 85, 86)) == ("TP1", 88.0)

    def test_single_target_after_tp1_has_no_tp2(self):
        assert resolve_exit(_pos(tp2=None, tp1_hit=True, sl=100.0), Bar(115, 200, 112, 150)) == (None, None)


@pytest.fixture
def live_cfg():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["safety"]["max_holding_hours"] = 0  # max-hold is locked in tests/test_backtest_max_hold.py
    return cfg


def _flat(n=400, highs=None, lows=None, price=100.0):
    idx = pd.date_range("2026-01-01", periods=n, freq="15min")
    df = pd.DataFrame({"open": price, "high": price, "low": price, "close": price,
                       "volume": 1.0}, index=idx)
    for i, v in (highs or {}).items():
        df.iloc[i, df.columns.get_loc("high")] = v
    for i, v in (lows or {}).items():
        df.iloc[i, df.columns.get_loc("low")] = v
    return df


class _Scripted(SafeOrchestrator):
    SCRIPT: list = []
    SEEN: dict = {}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        type(self).SEEN["config"] = self.config
        self._steps = [{"at": at, "fn": fn, "done": False} for at, fn in type(self).SCRIPT]

    def run_cycle(self, symbol, df_htf, df_mtf, df_entry, df_daily=None, balance=0.0, now=None):
        for s in self._steps:
            if not s["done"] and pd.Timestamp(now) >= s["at"]:
                s["fn"](self)
                s["done"] = True


def _run(monkeypatch, cfg, df, script, **kw):
    monkeypatch.setattr(_Scripted, "SCRIPT", script)
    monkeypatch.setattr(bt_engine, "SafeOrchestrator", _Scripted)
    tfs = {cfg["timeframes"][k]: df for k in ("htf", "mtf", "entry")}
    tfs["1d"] = df
    return run_backtest(symbols=["BTC/USDT"], data={"BTC/USDT": tfs}, config=cfg,
                        initial_balance=2000.0, commission_pct=0.0, funding_pct_per_8h=0.0, **kw)


def _open(tp2):
    def fn(orch):
        orch.lifecycle.open_position(symbol="BTC/USDT", direction="LONG", entry_price=100.0,
                                     sl=90.0, tp1=110.0, tp2=tp2, size=1.0)
    return fn


class TestEngineExits:
    def test_dual_target_takes_half_at_tp1_then_rest_at_tp2(self, monkeypatch, live_cfg):
        # after TP1 (bar 300) price holds at 112: above the break-even stop, below TP2
        df = _flat(highs={300: 111.0})
        df.iloc[301:, :4] = 112.0
        df.iloc[330, df.columns.get_loc("high")] = 121.0
        res = _run(monkeypatch, live_cfg, df, [(df.index[210], _open(120.0))])
        t = res["trades"][0]
        assert t["exit_reason"] == "TP2" and t["sl_moved_to_be"] is True
        entry = t["entry"]  # slipped entry
        cfg = SlippageConfig()
        tp1 = adverse_fill(110.0, "LONG", "TP", cfg)
        tp2 = adverse_fill(120.0, "LONG", "TP", cfg)
        assert t["pnl"] == pytest.approx(0.5 * (tp1 - entry) + 0.5 * (tp2 - entry), rel=1e-6)

    def test_dual_target_stops_at_break_even_after_tp1(self, monkeypatch, live_cfg):
        df = _flat(highs={300: 111.0})
        df.iloc[301:, :4] = 105.0  # above the break-even stop until bar 330
        df.iloc[330, df.columns.get_loc("low")] = 95.0
        res = _run(monkeypatch, live_cfg, df, [(df.index[210], _open(120.0))])
        t = res["trades"][0]
        assert t["exit_reason"] == "SL" and t["sl_moved_to_be"] is True
        assert t["pnl"] > 0  # half banked at TP1, rest out near entry

    def test_single_target_closes_everything_at_tp1(self, monkeypatch, live_cfg):
        df = _flat(highs={300: 111.0})
        res = _run(monkeypatch, live_cfg, df, [(df.index[210], _open(None))])
        assert res["trades"][0]["exit_reason"] == "TP1"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q -p no:cacheprovider tests/backtest/test_live_parity.py`
Expected: FAIL with `ImportError: cannot import name 'resolve_exit'`

- [ ] **Step 3: Implement `resolve_exit`** (append to `backtest/intrabar.py`)

```python
def resolve_exit(pos, bar: Bar) -> Tuple[Optional[str], Optional[float]]:
    """Exchange-parity exit for one bar (spec 2026-11-07 §3.2), pessimistic.

    Live (`exchange.OrderManager`): TP1 closes 50 % (100 % when ``tp2`` is None)
    and moves the stop to break-even; TP2 closes the rest. ``pos`` exposes
    ``.direction .sl .tp1 .tp2 .tp1_hit``. Order inside one bar: SL first, then
    TP1. TP2 is only considered once TP1 was hit on an earlier bar. Fills gap to the open.
    """
    long = pos.direction == "LONG"
    if (bar.low <= pos.sl) if long else (bar.high >= pos.sl):
        return "SL", (min(bar.open, pos.sl) if long else max(bar.open, pos.sl))
    if not pos.tp1_hit:
        if (bar.high >= pos.tp1) if long else (bar.low <= pos.tp1):
            return "TP1", (max(bar.open, pos.tp1) if long else min(bar.open, pos.tp1))
        return None, None
    if pos.tp2 is not None and ((bar.high >= pos.tp2) if long else (bar.low <= pos.tp2)):
        return "TP2", (max(bar.open, pos.tp2) if long else min(bar.open, pos.tp2))
    return None, None
```

- [ ] **Step 4: Wire it into the engine loop** (`backtest/engine.py`)

Replace `_PosView` with:

```python
@dataclass
class _PosView:
    direction: str
    entry: float
    sl: float
    tp1: float
    tp2: float | None = None
    tp1_hit: bool = False
```

Change the import to `from backtest.intrabar import resolve_exit, Bar`. In the intrabar loop, build the view with `tp2=pos.tp2, tp1_hit=bool(pos.tp1_hit)`, call `level, raw_price = resolve_exit(view, bar)`, and replace the close block with:

```python
                    slip_leg = "SL" if level == "SL" else "TP"
                    slipped = adverse_fill(raw_price, pos.direction, slip_leg, slippage_cfg)
                    pnl_before = pos.realized_pnl
                    if level == "TP1":
                        # live: 50 % + SL→BE (single-target: 100 %), see lifecycle.partial_close
                        orch.lifecycle.partial_close(pos, slipped, 0.5, "TP1")
                    else:
                        orch.lifecycle.close_position(pos, slipped, level)
                    balance += (pos.realized_pnl - pnl_before)
                    peak_balance = max(peak_balance, balance)
                    if not pos.is_open:
                        sim_close_ts[pos.id] = symbol_df.index[j]
```

- [ ] **Step 5: Run the new tests plus the restored engine tests**

Run: `python -m pytest -q -p no:cacheprovider tests/backtest/test_live_parity.py backend/tests/test_backtest_hygiene_batch1.py backend/tests/test_backtest_engine_single.py tests/test_backtest_max_hold.py`
Expected: PASS. If a restored test asserted a 100 % close at TP1 with a numeric `tp2`, update it to the live 50/50 behaviour and note it in the commit.

- [ ] **Step 6: Commit**

```bash
git add backtest/intrabar.py backtest/engine.py tests/backtest/
git commit -m "feat(backtest): exchange-parity exits (TP1 50% -> BE -> TP2)"
```

### Task 3: `smc_version` from config + offline guard

**Files:**
- Modify: `backtest/engine.py` (`run_backtest` signature + start of body)
- Test: `tests/backtest/test_live_parity.py` (append)

**Interfaces:**
- Produces: `run_backtest(..., smc_version: Literal["v1","v2"] | None = None, ...)`; `_offline_run_config(config: dict) -> dict`; `_offline_llm()` context manager; `_NullLLM.complete_json(*a, **k) -> {}`.

- [ ] **Step 1: Write the failing tests** (append)

```python
class TestLiveConfigAndOffline:
    def test_smc_version_comes_from_the_config(self, monkeypatch, live_cfg):
        assert live_cfg["engine"]["smc_version"] == "v2"
        res = _run(monkeypatch, live_cfg, _flat(), [])
        assert res["smc_version"] == "v2"

    def test_explicit_smc_version_still_overrides(self, monkeypatch, live_cfg):
        assert _run(monkeypatch, live_cfg, _flat(), [], smc_version="v1")["smc_version"] == "v1"

    def test_run_config_disables_agent_team_and_kronos(self, monkeypatch, live_cfg):
        live_cfg.setdefault("agent_team", {})["enabled"] = True
        _run(monkeypatch, live_cfg, _flat(), [])
        seen = _Scripted.SEEN["config"]
        assert seen["agent_team"]["enabled"] is False
        assert seen.get("kronos", {}).get("enabled") is False
        assert live_cfg["agent_team"]["enabled"] is True  # caller's dict untouched

    def test_llm_factory_is_null_during_the_run(self, monkeypatch, live_cfg):
        seen = []

        def probe(orch):
            import engine.agents.llm as llm
            seen.append(llm.make_llm_client({"provider": "openrouter"}).complete_json("x"))

        import engine.agents.llm as llm
        original = llm.make_llm_client
        df = _flat()
        _run(monkeypatch, live_cfg, df, [(df.index[210], probe)])
        assert seen == [{}]
        assert llm.make_llm_client is original  # restored after the run

    def test_live_config_backtest_block_makes_runs_net(self, live_cfg):
        assert live_cfg["backtest"]["commission_pct"] == 0.04
        assert live_cfg["backtest"]["funding_pct_per_8h"] == 0.01
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q -p no:cacheprovider tests/backtest/test_live_parity.py -k LiveConfigAndOffline`
Expected: FAIL (`smc_version` is "v1"; `_NullLLM` attribute missing)

- [ ] **Step 3: Implement** (`backtest/engine.py`; add `import copy` and `from contextlib import contextmanager` at the top)

```python
class _NullLLM:
    """Offline stand-in: every advisory LLM call degrades to its designed fallback."""

    def complete_json(self, *args, **kwargs) -> dict:
        return {}

    def complete(self, *args, **kwargs) -> str:
        return ""


@contextmanager
def _offline_llm():
    """A backtest must never reach a network: patch the shared LLM factory."""
    import engine.agents.llm as llm
    original = llm.make_llm_client
    llm.make_llm_client = lambda *a, **k: _NullLLM()
    try:
        yield
    finally:
        llm.make_llm_client = original


def _offline_run_config(config: dict) -> dict:
    """Copy of the live config with the network-bound advisory layers off."""
    cfg = copy.deepcopy(config)
    for key in ("agent_team", "kronos"):
        block = cfg.get(key) if isinstance(cfg.get(key), dict) else {}
        cfg[key] = {**block, "enabled": False}
    return cfg
```

Change the signature to `smc_version: Literal["v1", "v2"] | None = None,` and make the first lines of the body:

```python
    smc_version = smc_version or config.get("engine", {}).get("smc_version", "v1")
    config = _offline_run_config(config)
    symbols = sorted(symbols)
    with _offline_llm(), tempfile.TemporaryDirectory(prefix="bt_") as state_dir:
```

(Replace the old `symbols = sorted(symbols)` and `with tempfile.TemporaryDirectory(prefix="bt_") as state_dir:` lines; the rest of the body is unchanged.)

- [ ] **Step 4: Run all backtest tests**

Run: `python -m pytest -q -p no:cacheprovider tests/backtest backend/tests/test_backtest_*.py tests/test_backtest_max_hold.py`
Expected: PASS. `test_backtest_engine_v2.py` may already pass `smc_version="v2"`, which still works.

- [ ] **Step 5: Commit**

```bash
git add backtest/engine.py tests/backtest/test_live_parity.py
git commit -m "feat(backtest): smc_version from the live config; offline LLM/agent/Kronos guard"
```

### Task 4: CLI — fail on skipped cycles; real-data smoke + live parity report; docs

**Files:**
- Modify: `backtest/cli.py` (`cmd_single`, `cmd_portfolio`)
- Test: `tests/backtest/test_live_parity.py` (append)
- Modify: `TESTS.md` (§1 row "Edge / backtest gate", new TEST-BT rows), `docs/adr/0003-risk-fixes-default-off-behind-gates.md` (Known gap → resolved), `CLAUDE.md` (remove the "⚠️ backtest aracı master'da yok" bullet), `REGRESSION.md` (render)
- Create: `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md` (smoke + reconcile numbers)

**Interfaces:**
- Produces: `backtest.cli.skipped_ratio_exceeded(result: dict, limit: float = 0.01) -> bool`; both commands `raise SystemExit(3)` when it returns True (after writing `result.json`).

- [ ] **Step 1: Write the failing test** (append)

```python
def test_cli_flags_runs_with_too_many_skipped_cycles():
    from backtest.cli import skipped_ratio_exceeded
    assert skipped_ratio_exceeded({"skipped_cycles": 2, "cycles": 100}) is True
    assert skipped_ratio_exceeded({"skipped_cycles": 1, "cycles": 100}) is False
    assert skipped_ratio_exceeded({"skipped_cycles": 0}) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q -p no:cacheprovider tests/backtest/test_live_parity.py::test_cli_flags_runs_with_too_many_skipped_cycles`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement**

Also change the `grid` subcommand default to serial: `p_grid.add_argument("--workers", type=int, default=1)` (ProcessPool hangs on Windows/py3.14; opt in with `--workers N`).

In `backtest/engine.py`, count cycles: add `cycles = 0` next to `skipped_cycles = 0`, add `cycles += 1` just before `try: orch.run_cycle(...)`, and add `"cycles": cycles,` to the returned dict. In `backtest/cli.py`:

```python
def skipped_ratio_exceeded(result: dict, limit: float = 0.01) -> bool:
    """True when more than ``limit`` of the cycles raised inside run_cycle."""
    cycles = int(result.get("cycles") or 0)
    return cycles > 0 and int(result.get("skipped_cycles") or 0) / cycles > limit
```

At the end of `cmd_single` and `cmd_portfolio`, after the print:

```python
    if skipped_ratio_exceeded(result):
        print(f"FAIL: {result['skipped_cycles']}/{result['cycles']} cycles raised - see DEBUG log")
        raise SystemExit(3)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q -p no:cacheprovider tests/backtest backend/tests/test_backtest_*.py tests/test_backtest_max_hold.py backend/tests/test_evaluate_backtest_gates.py`
Expected: PASS

- [ ] **Step 5: Real-data smoke on the live config** (network: public Binance klines only)

```bash
python -m scripts.prefetch_data --symbols BTC/USDT --days 45
python -m backtest.cli single --symbol BTC/USDT --period-days 40 --config configs/config.phase2_1k.yaml
```

Expected: `OK Single backtest complete: reports/backtests/...`, exit 0, `smc_version: v2` in result.json. If `prefetch_data` flags differ, check `python -m scripts.prefetch_data --help` and use its flags.

- [ ] **Step 6: Live parity report** (read-only copy of the journal)

```bash
ssh efloud-bot 'docker exec efloud-bot cat /app/state_1k/trade_journal.jsonl' > "$CLAUDE_JOB_DIR/tmp/live_journal.jsonl"
```

Run a portfolio backtest over 2026-09-28 → 2026-11-06 for the journal's symbols, then call `backtest.compare_live.reconcile(live_trades=..., backtest_trades=...)` with the journal rows mapped to `{symbol, direction, entry_time=entry_timestamp, pnl=realized_pnl}`. Write match rate, PnL drift and the unmatched list to `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md` (informational; spec §3.4). Also list there any remaining wall-clock use found in the backtest path (for example `datetime.now()` in `lifecycle.partial_close` exit timestamps) as known divergences (spec §3.2 last row).

- [ ] **Step 7: Docs**

- `TESTS.md` §1: the "Edge / backtest gate" row command becomes `python -m backtest.cli single|portfolio --config configs/config.phase2_1k.yaml` (NET via the config `backtest:` block); drop the "Not runnable" note. Add §4.8 rows TEST-BT-001 (exit model: `tests/backtest/test_live_parity.py::TestResolveExit`, `tests/backtest/test_live_parity.py::TestEngineExits`), TEST-BT-002 (live config + offline guard: `tests/backtest/test_live_parity.py::TestLiveConfigAndOffline`).
- ADR-0003: replace the "Known gap" section body with "Resolved 2026-11-07: `backtest/` restored with live-parity exits (spec 2026-11-07)."
- `CLAUDE.md`: delete the `⚠️ NET-cost backtest kapısının aracı …` bullet.
- `python scripts/regression_ledger.py render`

- [ ] **Step 8: Commit**

```bash
git add backtest/cli.py backtest/engine.py tests/backtest TESTS.md docs/adr/0003-risk-fixes-default-off-behind-gates.md CLAUDE.md REGRESSION.md collab/outputs/claude-code/
git commit -m "feat(backtest): fail on skipped cycles; live parity report; docs say the gate runs again"
```

---

## Task 1 drift findings (dry restore, 2026-11-07, Windows)

- 78/79 restored tests pass on current master unchanged.
- **Drift 1:** `backend/tests/test_backtest_engine_v2.py::test_v2_orchestrator_receives_setup_state_store`
  asserts `max_pending_per_symbol == 3`, but the live config now says 6. Fix: assert it equals
  `base_config["smc_v2"]["max_pending_per_symbol"]` (comment `# drift since 562a6a3: live config 3 → 6`).
- **Runtime:** the suite takes ~647 s. Six tests account for ~640 s (full SMC runs on synthetic data):
  `test_backtest_engine_single.py::{test_engine_deterministic,test_engine_runs_to_completion,test_mtm_drawdown_field_present}`,
  `test_backtest_engine_portfolio.py::{test_portfolio_byte_identical_across_runs,test_portfolio_two_symbols_runs}`,
  `test_backtest_sim_time.py::test_run_backtest_trades_carry_sim_time_keys`.
  The main CI pytest job is ~1.5 min with a 15 min timeout, so these six get `@pytest.mark.slow`.
  Register the marker in `pyproject.toml` (`markers = ["slow: full-engine backtests (CI job backtest-slow)"]`).
  The main CI pytest command adds `-m "not slow"`, and a new parallel CI job `backtest (slow)`
  (`timeout-minutes: 30`) runs `python -m pytest -q -m slow backend/tests tests`.

Task 1 therefore adds these steps between Step 2 and Step 3:

- [ ] **Step 2a:** apply Drift 1 and run `python -m pytest -q -p no:cacheprovider backend/tests/test_backtest_engine_v2.py` → PASS
- [ ] **Step 2b:** add `@pytest.mark.slow` to the six tests, register the marker, change `.github/workflows/ci.yml` as above,
  and check `python -m pytest -q -p no:cacheprovider -m "not slow" backend/tests/test_backtest_*.py tests/test_backtest_max_hold.py`
  finishes in under 60 s → PASS. `tests/ci/test_workflow_hardening.py` must still pass.
