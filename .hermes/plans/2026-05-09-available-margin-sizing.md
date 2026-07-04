# Available-Margin-Based Position Sizing — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add an opt-in sizing mode where position size is calculated from `availableBalance` (free margin) instead of `totalMarginBalance`, so the Nth concurrent position uses 10% of *remaining* margin, not 10% of total wallet equity.

**Architecture:**
- New balance-source flag in config: `risk.sizing_balance_source: total | available` (default `total` = backward compatible)
- New `BinanceClient.get_available_margin()` method using Binance `/fapi/v2/account` `availableBalance` field
- `safe_orchestrator.run_cycle()` chooses which balance to feed into `calc_position_size()` based on flag
- Breaker, drawdown, guard, and emergency threshold continue using `totalMarginBalance` (unchanged) — only sizing changes
- `aggressive_v1.yaml` gets `sizing_balance_source: available` set explicitly

**Tech Stack:** Python 3.11, ccxt (Binance Futures), pytest, Docker, FastAPI

**Out of scope (deferred to separate PR):**
- SL distance changes — will be addressed in a follow-up PR after sizing is verified live for ≥24h
- Breaker `current_balance` denominator fix (existing known issue) — separate

---

## Codebase Reference Points

These are the key files and lines the implementer must read or modify:

- **`exchange/__init__.py:84-103`** — `BinanceClient.get_balance()` (existing). New method goes here.
- **`risk/__init__.py:8-48`** — `calc_position_size()`. Pure function, no changes needed (it already accepts `balance` parameter; we just feed it a different number).
- **`engine/safe_orchestrator.py:471-494`** — sizing call site (legacy mode dispatch). The decision of `total` vs `available` happens here.
- **`engine/safe_orchestrator.py:572-580`** — second sizing call site (DCA / add-to-position path). Must apply the same logic.
- **`configs/config.aggressive_v1.yaml`** — production config to update after merge.
- **`backend/tests/`** — test directory. New tests live in `backend/tests/test_sizing_balance_source.py`.

**Existing balance contract that MUST NOT change:**
- `breaker.sync_balance(balance)` continues to receive `totalMarginBalance`
- `PositionGuard.can_open_position(balance=...)` continues to receive `totalMarginBalance`
- `breaker.check()` daily/drawdown calculations: unchanged

**Why:** Risk metrics (drawdown, daily loss, emergency threshold) are economically correct against equity-including-PnL. Only the *new-position-sizing decision* needs `availableBalance` to produce the user's desired compounding-down behavior.

---

## Test Container Pattern (READ THIS FIRST)

The Hermes dev container does not have `pytest`/dependencies. Run tests by mounting the local repo into the production-image container on Hetzner:

```bash
ssh -i ~/.ssh/id_ed25519_hetzner root@<VPS_IP> \
  "cd /opt/efloud-bot && docker run --rm -v /tmp/efloud-bot:/app -w /app efloud-bot:latest pytest <PATH> -v"
```

But the implementer subagent runs locally (no SSH). Instead, the subagent should write tests using mocks-only (no real exchange, no real container) so they pass in any Python env with pytest. The orchestrator (this Hermes session) handles the Hetzner-side full-suite verification at the end.

**Implementer rule:** all tests use `unittest.mock` — never call real Binance API, never spin a container.

---

## Task 1: Add `get_available_margin()` to BinanceClient

**Objective:** Expose `availableBalance` from Binance Futures account endpoint as a separate method, parallel to `get_balance()`.

**Files:**
- Modify: `exchange/__init__.py` (after the existing `get_balance` method, around line 103)
- Test: `backend/tests/test_balance_methods.py` (new)

**Step 1: Write failing test**

Create `backend/tests/test_balance_methods.py`:

```python
"""Unit tests for BinanceClient balance methods.

get_balance() returns totalMarginBalance (wallet + unrealized PnL).
get_available_margin() returns availableBalance (free margin not locked in positions).

Both must:
- Hit the futures endpoint for futures market_type
- Fall back to fetch_balance() for spot
- Return float (never None / dict)
- Never raise on transient API failure
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from exchange import BinanceClient


def _make_client(market_type: str = "futures") -> BinanceClient:
    """Construct a BinanceClient without hitting the real API.

    Bypass __init__ to avoid ccxt setup; inject a mock exchange directly.
    """
    c = BinanceClient.__new__(BinanceClient)
    c.market_type = market_type
    c.exchange = MagicMock()
    return c


class TestGetBalance:
    def test_futures_returns_total_margin_balance(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {
            "totalMarginBalance": "2156.32",
            "availableBalance": "1820.00",
        }
        assert c.get_balance() == pytest.approx(2156.32)

    def test_futures_falls_back_on_api_failure(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.side_effect = RuntimeError("network")
        c.exchange.fetch_balance.return_value = {"USDT": {"total": 2100.0}}
        assert c.get_balance() == pytest.approx(2100.0)


class TestGetAvailableMargin:
    """New method. Mirrors get_balance() shape but returns availableBalance."""

    def test_futures_returns_available_balance(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {
            "totalMarginBalance": "2156.32",
            "availableBalance": "1820.00",
        }
        assert c.get_available_margin() == pytest.approx(1820.00)

    def test_futures_returns_float_not_string(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {"availableBalance": "1500.50"}
        result = c.get_available_margin()
        assert isinstance(result, float)
        assert result == pytest.approx(1500.50)

    def test_futures_handles_missing_field_returns_zero(self):
        """If Binance response is malformed, we must not crash — return 0.0."""
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {"totalMarginBalance": "100"}
        # availableBalance missing → 0.0 (caller will see no margin → no new position)
        assert c.get_available_margin() == 0.0

    def test_futures_falls_back_on_api_failure(self):
        """If fapi endpoint fails, fall back to fetch_balance['USDT']['free']."""
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.side_effect = RuntimeError("network")
        c.exchange.fetch_balance.return_value = {"USDT": {"free": 1500.0, "total": 2100.0}}
        # Available margin maps to USDT 'free' on fallback
        assert c.get_available_margin() == pytest.approx(1500.0)

    def test_spot_uses_free_balance(self):
        c = _make_client("spot")
        c.exchange.fetch_balance.return_value = {"USDT": {"free": 800.0, "total": 1000.0}}
        assert c.get_available_margin() == pytest.approx(800.0)
```

**Step 2: Verify test fails**

Run: `pytest backend/tests/test_balance_methods.py -v`
Expected: 4-5 FAIL with `AttributeError: 'BinanceClient' object has no attribute 'get_available_margin'` (or similar)

**Step 3: Implement `get_available_margin()`**

In `exchange/__init__.py`, immediately after the existing `get_balance()` method, add:

```python
def get_available_margin(self) -> float:
    """USDT available margin — free balance not locked in open positions.

    For futures: /fapi/v2/account 'availableBalance' field. This is the right
    metric for *new-position sizing decisions* — it answers \"how much margin
    do I have left to deploy?\" rather than \"what's my total equity?\".

    Note: get_balance() returns totalMarginBalance (wallet + unrealized PnL),
    which is the right metric for risk breakers (drawdown, daily-loss). The
    two methods serve different purposes; both are valid and intentional.

    Spot fallback returns USDT 'free' (not 'total'), since locked balance is
    economically committed and shouldn't size new entries.
    \"\"\"
    if self.market_type == \"futures\":
        try:
            info = self.exchange.fapiPrivateV2GetAccount()
            return float(info.get(\"availableBalance\", 0))
        except Exception as e:
            log.warning(f\"futures available margin fetch failed: {e} — falling back to fetch_balance\")
    b = self.exchange.fetch_balance()
    return float(b.get(\"USDT\", {}).get(\"free\", 0))
```

**Step 4: Verify all balance tests pass**

Run: `pytest backend/tests/test_balance_methods.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add exchange/__init__.py backend/tests/test_balance_methods.py
git commit -m "feat(exchange): add get_available_margin() for sizing decisions"
```

---

## Task 2: Add `sizing_balance_source` config flag with default

**Objective:** Define the config schema for the new flag, with a sensible default that preserves existing behavior.

**Files:**
- Modify: `configs/config.aggressive_v1.yaml` (add commented-out documentation only — actual flag set in Task 5)

**Note:** This task is config-documentation-only. The actual code that reads the flag goes in Task 3.

**Step 1: Add documentation comment to risk section**

In `configs/config.aggressive_v1.yaml`, in the `risk:` section, add this commented-out block above `position_size_calculation`:

```yaml
  # ── Sizing balance source (PR-A, 2026-05-09) ──
  # 'total'     → use totalMarginBalance (wallet + unrealized PnL). Each new
  #               position sized off full equity. Default for backward compat.
  # 'available' → use availableBalance (free margin not locked in positions).
  #               Each new position sized off REMAINING margin → boyutlar
  #               concurrent pozisyon sayısı arttıkça doğal olarak küçülür.
  #               Manuel deposit/withdraw da otomatik yansır (cüzdan büyür →
  #               sonraki trade büyür; cüzdan küçülür → sonraki trade küçülür).
  # sizing_balance_source: total
```

(Leaving it commented; Task 5 uncomments and sets to `available`.)

**Step 2: Commit**

```bash
git add configs/config.aggressive_v1.yaml
git commit -m "docs(config): document sizing_balance_source flag (no-op)"
```

---

## Task 3: Wire `sizing_balance_source` into `safe_orchestrator.run_cycle()` (legacy sizing path)

**Objective:** Read the flag and pass the chosen balance to `calc_position_size()`. Default `total` keeps current behavior.

**Files:**
- Modify: `engine/safe_orchestrator.py` (line ~487, the legacy `else` branch)
- Test: `backend/tests/test_sizing_balance_source.py` (new)

**Step 1: Write failing test**

Create `backend/tests/test_sizing_balance_source.py`:

```python
"""Unit tests for sizing_balance_source flag dispatch.

The flag controls which balance metric is fed into calc_position_size():
- 'total' (default): bot.client.get_balance() — totalMarginBalance
- 'available':       bot.client.get_available_margin() — availableBalance

Risk breakers, guards, and drawdown calc continue using totalMarginBalance
regardless of the flag — this test only validates the sizing-side choice.
\"\"\"
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


class TestSizingBalanceSource:
    \"\"\"Direct unit test of the dispatch logic.

    We don't construct a full SafeOrchestrator here — too heavy and not
    the unit under test. Instead, test the helper that makes the choice.
    \"\"\"

    def test_total_mode_uses_get_balance(self):
        from engine.safe_orchestrator import _sizing_balance
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        client.get_available_margin.return_value = 1820.00
        result = _sizing_balance(client, source=\"total\", live_balance=2156.32)
        assert result == pytest.approx(2156.32)
        client.get_available_margin.assert_not_called()

    def test_available_mode_calls_get_available_margin(self):
        from engine.safe_orchestrator import _sizing_balance
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        client.get_available_margin.return_value = 1820.00
        result = _sizing_balance(client, source=\"available\", live_balance=2156.32)
        assert result == pytest.approx(1820.00)
        client.get_available_margin.assert_called_once()

    def test_unknown_source_falls_back_to_total_with_warning(self, caplog):
        \"\"\"Defensive: typo in config (e.g. 'availble') must not crash bot.\"\"\"
        import logging
        from engine.safe_orchestrator import _sizing_balance
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        with caplog.at_level(logging.WARNING):
            result = _sizing_balance(client, source=\"availble\", live_balance=2156.32)
        assert result == pytest.approx(2156.32)
        assert any(\"sizing_balance_source\" in r.message for r in caplog.records)

    def test_default_when_source_is_none(self):
        \"\"\"Missing config key → behave as 'total'.\"\"\"
        from engine.safe_orchestrator import _sizing_balance
        client = MagicMock()
        client.get_balance.return_value = 2156.32
        result = _sizing_balance(client, source=None, live_balance=2156.32)
        assert result == pytest.approx(2156.32)

    def test_dry_run_no_client_call(self):
        \"\"\"In dry_run, live_balance is the synthetic 10000.0 float and we must
        not call the client at all — it may be None or unconfigured.\"\"\"
        from engine.safe_orchestrator import _sizing_balance
        # client=None simulates dry_run with no live exchange
        result = _sizing_balance(client=None, source=\"available\", live_balance=10000.0)
        # Falls back to live_balance when client unavailable
        assert result == pytest.approx(10000.0)

    def test_available_returns_zero_no_negative(self):
        \"\"\"If exchange returns 0 (margin fully deployed), sizing must accept
        0.0 cleanly — calc_position_size will then return 0 contracts and
        the guard rejects the trade. No exception.\"\"\"
        from engine.safe_orchestrator import _sizing_balance
        client = MagicMock()
        client.get_available_margin.return_value = 0.0
        result = _sizing_balance(client, source=\"available\", live_balance=2156.32)
        assert result == 0.0
```

**Step 2: Verify test fails**

Run: `pytest backend/tests/test_sizing_balance_source.py -v`
Expected: ImportError on `_sizing_balance` (function doesn't exist yet).

**Step 3: Implement `_sizing_balance()` helper**

In `engine/safe_orchestrator.py`, near the top of the module (after imports, before `class SafeOrchestrator`), add:

```python
def _sizing_balance(client, source: str | None, live_balance: float) -> float:
    \"\"\"Choose which balance metric to feed into position sizing.

    Args:
        client: BinanceClient instance, or None in dry_run.
        source: 'total' | 'available' | None. None and unknown values fall
            back to 'total' (with a warning) for backward compatibility.
        live_balance: the balance already fetched by the caller; used when
            client is None (dry_run) and as the 'total' return value.

    Returns:
        Float USDT amount to use as the 'balance' parameter for
        calc_position_size().

    Contract:
        - 'total' → live_balance (totalMarginBalance, already fetched)
        - 'available' → client.get_available_margin() (availableBalance)
        - None / typo → live_balance + log warning
        - client is None → live_balance (no exchange call)
    \"\"\"
    if client is None:
        return live_balance
    normalized = (source or \"total\").lower()
    if normalized == \"total\":
        return live_balance
    if normalized == \"available\":
        return float(client.get_available_margin())
    # Unknown value — defensive fallback
    log.warning(
        f\"Unknown sizing_balance_source={source!r}, falling back to 'total'. \"
        f\"Valid values: 'total', 'available'.\"
    )
    return live_balance
```

**Step 4: Verify helper tests pass**

Run: `pytest backend/tests/test_sizing_balance_source.py -v`
Expected: all PASS

**Step 5: Wire helper into the legacy sizing path**

Find `engine/safe_orchestrator.py` around line 487 (the `else:` branch that calls `calc_position_size`):

```python
                    else:
                        from risk import calc_position_size
                        max_notional = self.config[\"safety\"].get(\"max_position_notional_pct\", 3.0)
                        size = calc_position_size(
                            actual_balance, risk_cfg[\"risk_per_trade_pct\"],
                            latest.entry, latest.sl,
                            self.config[\"exchange\"].get(\"leverage\", 1),
                            max_notional_pct=max_notional,
                        )
```

Replace with:

```python
                    else:
                        from risk import calc_position_size
                        max_notional = self.config[\"safety\"].get(\"max_position_notional_pct\", 3.0)
                        # Choose sizing balance: 'total' (default) or 'available'
                        sizing_source = risk_cfg.get(\"sizing_balance_source\", \"total\")
                        sizing_balance = _sizing_balance(
                            self.client, sizing_source, actual_balance
                        )
                        size = calc_position_size(
                            sizing_balance, risk_cfg[\"risk_per_trade_pct\"],
                            latest.entry, latest.sl,
                            self.config[\"exchange\"].get(\"leverage\", 1),
                            max_notional_pct=max_notional,
                        )
                        if sizing_source == \"available\" and sizing_balance < actual_balance:
                            log.info(
                                f\"sizing: source=available balance=${sizing_balance:.2f} \"
                                f\"(vs total=${actual_balance:.2f}, delta=${actual_balance-sizing_balance:.2f} locked)\"
                            )
```

**Step 6: Apply same change to the second sizing call site**

Find `engine/safe_orchestrator.py` around line 572 (the DCA / add-to-position path):

```python
                from risk import calc_position_size
                ...
                max_notional = self.config[\"safety\"].get(\"max_position_notional_pct\", 3.0)
                add_size = calc_position_size(
                    actual_balance, ...,
                )
```

Apply the same `_sizing_balance(...)` indirection here. Use `actual_balance` as the `live_balance` argument.

**Step 7: Run new tests AND check no regressions in existing orchestrator tests**

```bash
pytest backend/tests/test_sizing_balance_source.py -v
pytest backend/tests/ -q
```

Expected: new tests pass; existing 225-test suite remains green.

**Step 8: Commit**

```bash
git add engine/safe_orchestrator.py backend/tests/test_sizing_balance_source.py
git commit -m \"feat(sizing): wire sizing_balance_source flag (default total)\"
```

---

## Task 4: Integration smoke test — full-suite regression

**Objective:** Confirm the dispatch helper plays well with the rest of the codebase by running the entire test suite. No new code — verification only.

**Step 1: Run full backend test suite locally (in repo)**

If the local Hermes container has pytest installed:

```bash
pytest backend/tests/ -q
```

If not, the orchestrator (Hermes session, NOT the implementer subagent) will run via the Hetzner container. The implementer subagent can attempt locally and report back; if pytest unavailable, the subagent should skip this step and let the orchestrator handle it.

**Expected:** 225 + 5 (new sizing) + 5-6 (new balance) = ~235 passed.

**Step 2: Sanity check — grep for any leftover direct `actual_balance` → `calc_position_size` call we missed**

```bash
grep -n \"calc_position_size\" engine/safe_orchestrator.py
```

Both call sites must use `_sizing_balance(...)` indirection. If a third call exists, route it through too.

**Step 3: No commit if no changes.** This is a verification task.

---

## Task 5: Final task is the orchestrator's job, NOT the implementer subagent

**The implementer subagent stops after Task 4.**

The orchestrator (this Hermes session) handles:

1. **Push branch + open PR** — `feat/available-margin-sizing` branch via `curl` GitHub API
2. **User reviews + merges** the PR
3. **Hetzner deploy** — `git pull && docker compose up -d --build efloud-bot`
4. **Live verification (24h soak with `total` mode still active in config)** — confirm no regressions
5. **Activation step** — open a tiny separate PR that flips `sizing_balance_source: available` in `aggressive_v1.yaml`. Get explicit user approval before merging this activation PR.
6. **Stage 2 (separate plan): SL distance refactor** — only after the sizing PR has been live and stable for 24h.

This separation is intentional: code-merge and config-flip are independent steps so the user can roll back the activation independently of the code.

---

## Definition of Done (Implementer Subagent)

- [ ] `BinanceClient.get_available_margin()` exists, tested, passes
- [ ] `_sizing_balance()` helper exists in `safe_orchestrator`, tested, passes
- [ ] Both `calc_position_size` call sites in `safe_orchestrator.py` route through the helper
- [ ] Config doc comment added to `aggressive_v1.yaml` (no active flag yet)
- [ ] All new tests pass; no regressions in existing tests
- [ ] All commits follow conventional-commit format
- [ ] No active behavior change in production (config flag absent → `total` mode → same as today)

---

## Definition of Done (Orchestrator)

- [ ] PR opened, all CI checks green
- [ ] User reviewed and merged
- [ ] Hetzner pulled + rebuilt + verified container healthy
- [ ] Activation PR opened (`risk.sizing_balance_source: available`) and explicitly approved by user
- [ ] First trade after activation logged with `sizing: source=available` info line confirming the new mode is active
- [ ] Memory + skill updates: any pitfalls discovered during deploy go into `trading-bot-ops` skill

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Default `total` masks a code bug → behavior changes silently | Low | Backward-compat default + 5 dispatch tests cover the negative case |
| `availableBalance` returns 0 when fully margined → bot stops trading | Medium | Documented as expected; bot returns 0 contracts → guard rejects → no trade. Operator sees \"size=0 sizing.balance=$0\" log. |
| Manual deposit/withdraw timing → stale `availableBalance` for one cycle | Low | Each cycle re-fetches; one stale cycle is acceptable |
| Drawdown calc using `current_balance` mismatch | None | We are NOT changing breaker/drawdown — they continue with `totalMarginBalance` |
| User expects sizing to also reduce existing R:R / SL behavior | High | This PR explicitly does NOT touch SL. SL refactor is separate Stage 2 plan after 24h soak. |
