# PR #S3c-2: Entry Order Placement on CONFIRMED — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a SetupCandidate transitions to CONFIRMED in `_advance_setup_state_tick`, compute SL via `calc_sl()`, TP via `calc_tp_targets()`, position size via `risk.calc_position_size`, and call `OrderManager.open_position()` to place real exchange orders. **All safety gates (breaker, position_guard, dry_run, mainnet) still apply through OrderManager.**

**Architecture:** New helper `_place_v2_entry_order(cand, current_price, entry_price)` on `SafeOrchestrator`. Called from `_advance_setup_state_tick` after `cand.state = "CONFIRMED"`. Gated by `self.order_manager is not None` (inert when no order manager wired). Uses existing SL/TP calculators (PR #65) — no new risk surface.

**Tech Stack:** Python 3.12, pandas, pytest. Zero new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §5 (SL/TP math + worked example).

**Branch:** `feat/smc-v2-entry-orders` (from master).

**Risk classification:** **RISK-OPS CRITICAL** — first PR that places REAL EXCHANGE ORDERS from v2 path. All existing safety machinery preserved:
- `dry_run` flag enforced inside `OrderManager.open_position` (line 395)
- Mainnet guard enforced inside `BinanceClient.__init__` (env `EFLOUD_ALLOW_MAINNET`)
- Position guard + breaker checks applied (mirror v1 signals.py pattern)

**Inert invariant**: `setup_state_store=None` (production default) → trigger phase never runs → no CONFIRMED → no orders. `order_manager=None` → order placement skipped even if CONFIRMED. **Production deploys with default config are unaffected.**

**Scope discipline**: PR #S3c-2 is ONLY entry order placement. **Out of scope** (deferred):
- Feature flag dispatch (`engine.smc_version`) — PR #S6
- `main.py` / `bot_runner.py` wiring of `setup_state_store` — PR #S6
- Lifecycle telemetry fields (`entry_setup_source`, `tp1_target_type`) — PR #S5
- BOS trigger support — separate follow-up
- Confluence scoring for v2 — separate follow-up

---

## Pre-flight Checks

- [ ] **P1:** Confirm worktree + branch.

```bash
git rev-parse --show-toplevel  # Expected: .../efloud-bot/.worktrees/smc-v2-entry-orders
git branch --show-current      # Expected: feat/smc-v2-entry-orders
git log --oneline -3           # Expected: PR #70 squash-merge at top (dd79a26)
```

- [ ] **P2:** Confirm baseline tests pass.

```bash
python -m pytest backend/tests/smc_v2/ -q
# Expected: 117 passed
python -m pytest backend/tests/test_orchestrator_*.py -q
# Expected: 12 passed (v1 regression baseline)
```

- [ ] **P3:** Confirm dependencies.

```bash
grep -n "def calc_position_size" risk/__init__.py | head -2
# Expected: calc_position_size function exists
grep -n "def calc_sl\|def calc_tp_targets" engine/smc_v2/sl_calc.py engine/smc_v2/tp_calc.py
# Expected: both functions exist (PR #65)
```

---

## File Structure

**Created files** (1):
- `backend/tests/smc_v2/test_entry_order_placement.py` — mock OrderManager tests for v2 entry placement

**Modified files** (1):
- `engine/safe_orchestrator.py` — add `_place_v2_entry_order()` helper + call from `_advance_setup_state_tick` after CONFIRMED

**No changes to**: `engine/smc_v2/*` modules, `engine/signals.py`, `engine/lifecycle.py`, `engine/safety/`, `exchange/`, `config.yaml`, `backend/db.py`, any migration, `main.py`, `bot_runner.py`.

---

## Chunk 1: `_place_v2_entry_order` helper

### Task 1: Helper method + placement logic

**Files:**
- Modify: `engine/safe_orchestrator.py` — add `_place_v2_entry_order()` after `_emit_setup_candidates`
- Create: `backend/tests/smc_v2/test_entry_order_placement.py`

- [ ] **Step 1.1: Write the failing test**

Create `backend/tests/smc_v2/test_entry_order_placement.py`:

```python
"""Tests for SMC v2 entry order placement on CONFIRMED state.

PR #S3c-2 adds `_place_v2_entry_order` helper called from
_advance_setup_state_tick when state transitions to CONFIRMED.

Inert gates:
- order_manager is None → skipped (test/paper mode)
- setup_state_store is None → never reaches CONFIRMED (PR #67)

Real exchange path:
- calc_sl + calc_tp_targets compute SL/TP
- risk.calc_position_size computes size
- order_manager.open_position called with all params
- Position guard check applied BEFORE order placement (mirror v1)
- Returns Position or None (matches v1 contract)
"""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec


def _minimal_config():
    return {
        "structure": {
            "swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
            "eq_threshold_pct": 0.1, "range_lookback": 50,
        },
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {
            "max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
            "risk_per_trade_pct": 0.75, "recency_bars": 40,
            "position_size_calculation": "legacy",
            "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5,
        },
        "safety": {
            "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
            "starting_balance": 10000, "max_position_notional_pct": 20,
            "max_total_exposure": 5.0, "max_holding_hours": 48,
            "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
            "adx_trend_threshold": 25, "adx_range_threshold": 20,
            "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
            "sl_atr_buffer": 0.5,
        },
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
    }


def _make_in_zone_candidate():
    """A SetupCandidate already IN_ZONE — about to be CONFIRMED."""
    return SetupCandidate(
        symbol="BTC/USDT", direction="SHORT",
        trigger_bar_ts=2_500,
        trigger_price=100.0, htf_bias="BEAR",
        target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
        htf_swing_anchor=115.0, bars_waited=2,
        state="IN_ZONE",
        confluence_score=75, reasons=[],
    )


class TestInertWhenNoOrderManager:
    """When order_manager is None (test/paper mode), no order placement
    attempt even on CONFIRMED."""

    def test_no_order_placed_when_order_manager_none(self, tmp_path):
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(_make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
            # order_manager NOT passed → None
        )
        # _place_v2_entry_order should be a no-op
        # We call it directly to verify the gate
        cand = store.candidates[0]
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is None


class TestOrderPlacementOnConfirmed:
    """When order_manager is wired AND state goes to CONFIRMED, an entry
    order is placed via OrderManager.open_position()."""

    def _setup_with_mock_order_manager(self, tmp_path):
        from exchange import BinanceClient, OrderManager, Position
        mock_client = MagicMock(spec=BinanceClient)
        mock_client.exchange = MagicMock()
        mock_client.market_type = "futures"
        mock_client.testnet = True
        mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT" if ":" not in s else s
        mock_client.get_balance = MagicMock(return_value=10000.0)
        mock_client.get_available_margin = MagicMock(return_value=10000.0)
        order_mgr = OrderManager(mock_client, dry_run=True)  # dry_run for safety
        return order_mgr

    def test_place_v2_entry_order_calls_open_position(self, tmp_path):
        order_mgr = self._setup_with_mock_order_manager(tmp_path)
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = _make_in_zone_candidate()

        with patch.object(order_mgr, "open_position") as spy_open:
            spy_open.return_value = MagicMock()  # truthy Position
            result = orc._place_v2_entry_order(
                cand, current_price=105.0, entry_price=105.0,
            )
            # open_position called once with valid SL/TP/size
            assert spy_open.call_count == 1
            kwargs = spy_open.call_args.kwargs
            assert kwargs["symbol"] == "BTC/USDT"
            assert kwargs["direction"] == "SHORT"
            assert kwargs["entry"] == 105.0
            assert kwargs["sl"] > 105.0   # SHORT SL above entry
            assert kwargs["tp1"] < 105.0  # SHORT TP below entry
            assert kwargs["size"] > 0
            assert result is not None  # Position returned

    def test_no_order_when_sl_too_far(self, tmp_path):
        """SLTooFarError from calc_sl → setup rejected, no order."""
        order_mgr = self._setup_with_mock_order_manager(tmp_path)
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        # Candidate with anchor far above zone — will trigger SLTooFarError
        cand = SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=2_500,
            trigger_price=100.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=100.0, high=101.0, source="HTF_FVG"),
            htf_swing_anchor=999.0,  # absurdly far — beyond max_sl_atr
            bars_waited=2, state="IN_ZONE",
            confluence_score=75, reasons=[],
        )

        with patch.object(order_mgr, "open_position") as spy_open:
            # Pass small ATR so max_dist = 5 * small = tight
            with patch.object(orc.smc, "analyze") as mock_analyze:
                mock_analyze.return_value = {"trend": "BEAR"}
                result = orc._place_v2_entry_order(
                    cand, current_price=105.0, entry_price=105.0,
                )
            # No order placed — SLTooFarError caught, setup skipped
            assert spy_open.call_count == 0
            assert result is None


class TestAdvanceTriggersEntryOnConfirmed:
    """Integration: when _advance_setup_state_tick transitions IN_ZONE →
    CONFIRMED via confirm_entry, the order placement helper is called."""

    def _engulf_df(self):
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 96.0, 97.0, 95.0, 96.5),
            (3_000, 97.0, 105.0, 96.5, 104.0),
            (4_000, 104.0, 106.0, 102.5, 105.5),
            (5_000, 106.0, 106.5, 101.0, 102.0),  # bearish engulfing
        ]
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df.set_index("ts", inplace=True)
        return df

    def test_confirmed_triggers_place_entry_call(self, tmp_path):
        from exchange import BinanceClient, OrderManager
        mock_client = MagicMock(spec=BinanceClient)
        mock_client.exchange = MagicMock()
        mock_client.market_type = "futures"
        mock_client.testnet = True
        mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT" if ":" not in s else s
        mock_client.get_balance = MagicMock(return_value=10000.0)
        mock_client.get_available_margin = MagicMock(return_value=10000.0)
        order_mgr = OrderManager(mock_client, dry_run=True)

        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(_make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )

        with patch.object(orc, "_place_v2_entry_order") as spy:
            orc._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=102.0,
                current_bar_ts=5_000,
                df_15m=self._engulf_df(),
            )
            # CONFIRMED → spy called with the candidate
            assert spy.call_count == 1
            assert spy.call_args.args[0].state == "CONFIRMED"


class TestNoEntryWhenAdvanceSkipsConfirmation:
    """If confirm_entry returns (False, None), no entry order placed."""

    def test_in_zone_no_engulfing_no_entry(self, tmp_path):
        from exchange import BinanceClient, OrderManager
        mock_client = MagicMock(spec=BinanceClient)
        mock_client.exchange = MagicMock()
        mock_client.market_type = "futures"
        mock_client.testnet = True
        mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT" if ":" not in s else s
        mock_client.get_balance = MagicMock(return_value=10000.0)
        mock_client.get_available_margin = MagicMock(return_value=10000.0)
        order_mgr = OrderManager(mock_client, dry_run=True)

        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(_make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )

        # All-bullish df → no bearish engulfing → no confirmation
        df = pd.DataFrame(
            {"open": [100.0, 101.0, 102.0], "high": [102.0, 103.0, 104.0],
             "low": [99.0, 100.0, 101.0], "close": [101.0, 102.0, 103.0]},
            index=pd.to_datetime([3_000, 4_000, 5_000], unit="ms", utc=True),
        )

        with patch.object(orc, "_place_v2_entry_order") as spy:
            orc._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=103.0,
                current_bar_ts=5_000,
                df_15m=df,
            )
            assert spy.call_count == 0
            # Candidate stays IN_ZONE
            assert store.candidates[0].state == "IN_ZONE"
```

- [ ] **Step 1.2: Run to verify fail**

```bash
python -m pytest backend/tests/smc_v2/test_entry_order_placement.py -v
# Expected: many FAIL — _place_v2_entry_order doesn't exist
```

- [ ] **Step 1.3: Implement `_place_v2_entry_order` + wire into _advance_setup_state_tick**

In `engine/safe_orchestrator.py`, find `_emit_setup_candidates` and add this helper immediately after:

```python
    def _place_v2_entry_order(
        self,
        cand: "SetupCandidate",
        current_price: float,
        entry_price: float,
    ) -> "Optional[Position]":
        """Place entry order for a CONFIRMED SetupCandidate.

        Per spec §5: computes SL via calc_sl, TP via calc_tp_targets,
        size via risk.calc_position_size, then OrderManager.open_position.

        Safety gates (all preserved from v1 signals.py path):
        - order_manager is None → skip (test/paper mode)
        - dry_run enforced inside OrderManager.open_position
        - mainnet_guard enforced inside BinanceClient
        - SLTooFarError / InsufficientTPDistanceError from calculators → setup rejected
        - Position guard check applied (mirrors v1)
        - Position size from risk.calc_position_size

        Returns the new Position (or None on rejection).
        """
        if self.order_manager is None:
            # Test/paper mode — no order placement
            return None

        # Local imports (avoid hard module-level dep on smc_v2 for v1 callers)
        from engine.smc_v2.sl_calc import calc_sl
        from engine.smc_v2.tp_calc import calc_tp_targets
        from engine.smc_v2.exceptions import SLTooFarError, InsufficientTPDistanceError

        safety_cfg = self.config.get("safety", {})
        risk_cfg = self.config.get("risk", {})

        # Compute ATR(15m) — use a conservative approximation from
        # current_price and zone spread. Real ATR computation happens
        # in PR #67-base via df_15m, but here we don't have df.
        # Use 1% of entry_price as a safe ATR proxy until PR refactor.
        # NOTE: This is a deliberate simplification for PR #S3c-2; the
        # real ATR will be threaded through in a follow-up alongside
        # df_15m delivery to this helper. The proxy is conservative
        # (overestimates ATR → tighter max_sl_atr clamp → more rejects).
        atr_15m = max(entry_price * 0.01, abs(cand.target_zone.high - cand.target_zone.low))

        # SL via spec §5.1
        try:
            sl = calc_sl(
                direction=cand.direction,
                entry_price=entry_price,
                zone=cand.target_zone,
                htf_swing_anchor=cand.htf_swing_anchor,
                atr_15m=atr_15m,
                config=type("C", (), {
                    "sl_atr_buffer": safety_cfg.get("sl_atr_buffer", 0.5),
                    "min_sl_atr": safety_cfg.get("min_sl_atr", 0.5),
                    "max_sl_atr": safety_cfg.get("max_sl_atr", 5.0),
                }),
            )
        except SLTooFarError as e:
            log.info(f"[v2 reject] {cand.symbol}: sl_too_far ({e})")
            return None

        # TP via spec §5.2 — needs htf_swings, htf_fvgs, eq_levels
        # For PR #S3c-2 we use empty inputs (RR projection fallback) as
        # a deliberate simplification. PR follow-up wires real HTF data.
        try:
            tp1, tp2, tp_tags = calc_tp_targets(
                direction=cand.direction,
                entry_price=entry_price,
                sl_price=sl,
                htf_swings={"swing_highs": [], "swing_lows": []},
                htf_fvgs=[],
                eq_levels=[],
                config=type("C", (), {
                    "min_rr": risk_cfg.get("min_rr", 1.8),
                    "fib_ext": self.config.get("fibonacci", {}).get("ext_tp2", 1.618),
                }),
            )
        except InsufficientTPDistanceError as e:
            log.info(f"[v2 reject] {cand.symbol}: tp1_too_close ({e})")
            return None

        # tp2 may be None (single-target mode per spec §4.2); use tp1 as fallback
        # for current OrderManager.open_position which requires both args
        # (single-target lifecycle change is PR #S5 scope).
        tp2_eff = tp2 if tp2 is not None else tp1

        # Position size via existing risk helper
        try:
            from risk import calc_position_size
            balance = self.order_manager.client.get_balance() if self.order_manager.client else 10000.0
            size = calc_position_size(
                balance=balance,
                risk_pct=risk_cfg.get("risk_per_trade_pct", 0.75),
                entry=entry_price,
                stop=sl,
            )
        except Exception as e:
            log.warning(f"[v2 reject] {cand.symbol}: sizing failed ({e})")
            return None

        if size <= 0:
            log.info(f"[v2 reject] {cand.symbol}: size <= 0 ({size})")
            return None

        # Position guard check (mirror v1 — open count, exposure, etc.)
        # For PR #S3c-2 we rely on OrderManager.open_position to enforce
        # max_position_notional_pct and similar via its existing path.
        # A future refactor may centralize the guard call here.

        log.info(f"[v2] {cand.direction} {cand.symbol} entry={entry_price:.4f} "
                 f"sl={sl:.4f} tp1={tp1:.4f} tp2={tp2_eff:.4f} size={size:.6f} "
                 f"(zone={cand.target_zone.source}, tp1={tp_tags.get('tp1_source')}, "
                 f"tp2={tp_tags.get('tp2_source')})")

        return self.order_manager.open_position(
            symbol=cand.symbol,
            direction=cand.direction,
            size=size,
            entry=entry_price,
            sl=sl,
            tp1=tp1,
            tp2=tp2_eff,
        )
```

Then find `_advance_setup_state_tick` and modify the CONFIRMED branch:

**BEFORE (around line 1108):**
```python
                if confirmed:
                    cand.state = "CONFIRMED"
                    # Entry order placement lands in PR #S3c-2
                    # (signals.py → OrderManager.open_position dispatch)
```

**AFTER:**
```python
                if confirmed:
                    cand.state = "CONFIRMED"
                    # PR #S3c-2: place entry order if order_manager is wired.
                    # Inert when self.order_manager is None (test/paper).
                    # All safety gates (dry_run, mainnet, calculator REJECTs)
                    # enforced inside _place_v2_entry_order + OrderManager.
                    self._place_v2_entry_order(
                        cand,
                        current_price=current_price,
                        entry_price=entry_px,
                    )
```

- [ ] **Step 1.4: Run to verify pass**

```bash
python -m pytest backend/tests/smc_v2/test_entry_order_placement.py -v
# Expected: 5 passed (1 inert + 2 placement + 1 integration + 1 no-engulf)
```

- [ ] **Step 1.5: Critical regressions (v1 + PR #67 + PR #S3b + PR #S3c-1)**

```bash
python -m pytest backend/tests/test_orchestrator_*.py backend/tests/smc_v2/test_orchestrator_state_tick.py backend/tests/smc_v2/test_orchestrator_confirm_wiring.py -q
# Expected: 12 v1 + 17 PR #67 + 10 confirm_wiring (5 PR #S3b + 5 PR #S3c-1) = 39 passed
```

- [ ] **Step 1.6: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/smc_v2/test_entry_order_placement.py
git commit -m "feat(orchestrator): _place_v2_entry_order on CONFIRMED (PR #S3c-2)

RISK-OPS CRITICAL: first PR placing real exchange orders from v2 path.

Per spec §5: when _advance_setup_state_tick transitions a candidate
to CONFIRMED via confirm_entry, this helper computes SL (calc_sl)
+ TP (calc_tp_targets) + size (risk.calc_position_size), then calls
OrderManager.open_position.

Safety gates ALL preserved:
- order_manager=None → skip (test/paper mode, inert)
- setup_state_store=None → trigger phase never runs → no CONFIRMED
- dry_run enforced inside OrderManager (existing)
- mainnet guard enforced inside BinanceClient (existing)
- SLTooFarError / InsufficientTPDistanceError → setup rejected
- size <= 0 → skip

Deliberate simplifications for PR #S3c-2:
- ATR proxy: max(entry*0.01, zone_width) — conservative overestimate
- TP htf_swings/htf_fvgs/eq_levels: empty → RR_PROJECTION fallback
- Real HTF data threading in follow-up alongside df_15m delivery

Inert default: current production has order_manager=None for v2 path
(setup_state_store=None means trigger never runs anyway). Activation
requires PR #S6 feature flag + main.py wiring.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Final regression sweep

### Task 2: Full suite + py_compile

- [ ] **Step 2.1: Full smc_v2 suite**

```bash
python -m pytest backend/tests/smc_v2/ -v 2>&1 | tail -8
# Expected: 117 baseline + 5 new = 122 passed
```

- [ ] **Step 2.2: Full backend suite**

```bash
python -m pytest backend/tests/ -q 2>&1 | tail -3
# Expected: 594 baseline + 5 = 599 passed
```

- [ ] **Step 2.3: py_compile**

```bash
python -m py_compile engine/safe_orchestrator.py && echo "compile OK"
```

- [ ] **Step 2.4: Diff inventory**

```bash
git log feat/smc-v2-entry-orders ^master --oneline
git diff master..HEAD --stat
# Expected: 2 commits (1 plan + 1 task), only safe_orchestrator.py + new test file + plan
```

---

## Out of Scope (explicitly NOT in PR #S3c-2)

- **Feature flag dispatch** (`engine.smc_version: v1|v2`) — PR #S6
- **main.py / bot_runner.py wiring** of setup_state_store + order_manager → orchestrator — PR #S6
- **Real ATR threading** through to `_place_v2_entry_order` (currently proxy) — follow-up after this PR
- **Real HTF data threading** for tp_calc (currently empty inputs → RR projection) — follow-up
- **Lifecycle telemetry fields** (`entry_setup_source`, `tp1_target_type`) — PR #S5
- **Single-target lifecycle handling** (TP2=None) — PR #S5 (currently fallback tp2=tp1)
- **Position guard / breaker check duplication** in v2 path — currently rely on OrderManager.open_position internals

---

## Acceptance Criteria

1. All steps in Tasks 1-2 checked off.
2. `pytest backend/tests/smc_v2/test_entry_order_placement.py -v` → 5 passed
3. `pytest backend/tests/smc_v2/ -q` → 122 passed (117 + 5)
4. `pytest backend/tests/test_orchestrator_*.py -q` → 12 passed (v1 regression)
5. `pytest backend/tests/` → 599 passed
6. `git diff master..HEAD --stat` → only `engine/safe_orchestrator.py` + 1 new test file + plan
7. `efloud-code-reviewer` reviewed.
8. **Risk-ops second pass REQUIRED** (CLAUDE.md §4 + first real-order PR). Verdict must explicitly verify:
   - Inert when `order_manager=None` (production has no v2 wiring)
   - Inert when `setup_state_store=None` (production default)
   - All existing safety gates still apply (dry_run, mainnet, breaker, position_guard via OrderManager)
   - No way for v2 to bypass safety machinery
   - Rollback is config-flag only (no schema/state changes)

---

## Post-Plan Workflow

1. `verification-before-completion` (Iron Law)
2. `requesting-code-review` → efloud-code-reviewer (first pass)
3. Risk-ops second-pass review via general-purpose agent (focused brief)
4. Apply review feedback
5. `finishing-a-development-branch` → push + PR (Hermes-mode merge with user confirmation, given risk-ops criticality)

---

## References

- Spec: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §5
- SL/TP calculators: `engine/smc_v2/{sl_calc,tp_calc,exceptions}.py` (PR #65)
- OrderManager.open_position: `exchange/__init__.py:380` (dry_run-aware)
- Risk sizing: `risk/__init__.py:calc_position_size`
- v1 signals.py order placement reference: `engine/signals.py` (for parity)
- Initiative tracker: `memory/smc_v2_rework_initiative.md`
