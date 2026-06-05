# Discovery TP1 R:R Clamp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the legacy signal path from rejecting 100% of "price discovery" triggers by clamping the discovery TP1 to `max(1.272, min_rr)`.

**Architecture:** `engine/signals.py` discovery fallback currently sets `tp1 = price ± risk×1.272` → `rr1 = 1.27`, which the downstream `min_rr` gate (1.5/1.8) always rejects. Clamp the multiplier to `max(1.272, min_rr)` so the projection lands at exactly the gate (a valid RR_PROJECTION, matching `engine/smc_v2/tp_calc.py:76`). Then sync the live config's `min_rr` 1.8 → 1.5.

**Tech Stack:** Python 3.11, pytest, pandas. Mock-engine unit tests (no network, `symbol=None` skips the Gemini structure-validation call).

**Spec:** `docs/superpowers/specs/2026-06-05-discovery-rr-clamp-design.md`

**Branch:** `fix/discovery-rr-clamp` (already created; spec already committed).

---

## File Structure

- **Modify:** `engine/signals.py` — two one-line edits (lines 575 LONG, 617 SHORT). Discovery branch only.
- **Modify:** `configs/config.phase2_1k.yaml:100` — `min_rr: 1.8 → 1.5` (prod config via `EFLOUD_CONFIG_PATH`).
- **Modify (add):** `tests/test_signals.py` — new `TestDiscoveryRRClamp` class (LONG + SHORT regression).

No new files. The discovery branch is the only defective TP path; the other three (range-deviation, ranging-liquidity, trending-FVG) already clamp to `min_tp` and are untouched.

---

### Task 1: Failing regression tests (LONG + SHORT discovery)

**Files:**
- Test: `tests/test_signals.py` (append a new class at end of file)

**Context for the worker — why this setup forces the discovery branch:**
The mock engine returns BULL/BEAR trend with empty swings/FVGs/OBs and a neutral
range (`dev_*`/`discount`/`premium` all False). A single CHoCH break aligned with
the trend passes the recency + direction gates and scores 25 (HTF bias only), so
`min_confluence=20` lets it reach SL/TP. With no swing/EQ/FVG target ≥ `min_rr·risk`,
the trending `else` branch falls through to the discovery fallback. `symbol=None`
skips the `if symbol:` Gemini structure-validation block (no network).

The df carries `high=100.5 / low=99.0 / close=100.0` for 50 bars so the ATR(14) and
20-bar local-structure SL compute to a fixed `sl≈98.25` (LONG) / `sl≈101.25` (SHORT),
giving a non-zero risk and a clean discovery TP1.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_signals.py`:

```python
class TestDiscoveryRRClamp:
    """Price-discovery TP1 must clamp to min_rr so it survives the R:R gate.

    Pre-fix: discovery sets tp1 = price ± risk×1.272 → rr1 = 1.27, which the
    min_rr gate (>=1.5) rejects 100% of the time → 0 signals (confirmed live:
    6h of 'max seen: 1.27' rejects across the symbol universe).
    Post-fix: tp1 = price ± risk×max(1.272, min_rr) → rr1 == min_rr → emits.
    """

    def _make_engine(self, break_obj, trend: str = "BULL") -> MagicMock:
        e_range = SimpleNamespace(
            discount=False, premium=False, dev_bull=False, dev_bear=False,
            lo=99.0, hi=101.0,
        )
        engine = MagicMock()
        engine.analyze.return_value = {
            "trend": trend,
            "active_fvgs": [],
            "active_obs": [],
            "swing_highs": [],
            "swing_lows": [],
            "range": e_range,
        }
        engine.swings.return_value = ([], [])
        engine.structure.side_effect = [[], [break_obj]]
        engine.order_blocks.return_value = []
        engine.sfps.return_value = []
        engine.range_info.return_value = e_range
        engine.ote.return_value = None
        return engine

    def _df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "high": [100.5] * 50,
            "low": [99.0] * 50,
            "close": [100.0] * 50,
        })

    def test_long_discovery_emits_at_min_rr(self) -> None:
        choch = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45,
            ts="2026-06-05T00:00", price=100.0,
        )
        engine = self._make_engine(choch, trend="BULL")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.5, fib_ext=1.618,
            recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1, f"discovery LONG dropped; got {sigs}"
        sig = sigs[0]
        assert sig.direction == "LONG"
        assert sig.rr1 == 1.5            # clamped to min_rr, not 1.27
        assert sig.tp1 > sig.entry       # correct side
        assert sig.tp2 > sig.tp1         # TP2 beyond TP1

    def test_short_discovery_emits_at_min_rr(self) -> None:
        choch = SimpleNamespace(
            direction="BEAR", kind="CHoCH", idx=45,
            ts="2026-06-05T00:00", price=100.0,
        )
        engine = self._make_engine(choch, trend="BEAR")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.5, fib_ext=1.618,
            recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1, f"discovery SHORT dropped; got {sigs}"
        sig = sigs[0]
        assert sig.direction == "SHORT"
        assert sig.rr1 == 1.5
        assert sig.tp1 < sig.entry
        assert sig.tp2 < sig.tp1

    def test_min_rr_below_fib_keeps_1272(self) -> None:
        """If min_rr < 1.272, max() preserves the 1.272 fib intent."""
        choch = SimpleNamespace(
            direction="BULL", kind="CHoCH", idx=45,
            ts="2026-06-05T00:00", price=100.0,
        )
        engine = self._make_engine(choch, trend="BULL")
        sigs = generate_signals(
            engine, self._df(), self._df(), self._df(),
            min_confluence=20, min_rr=1.2, fib_ext=1.618,
            recency_bars=40, symbol=None,
        )
        assert len(sigs) == 1
        assert sigs[0].rr1 == 1.27       # 1.272 preserved (max(1.272, 1.2))
```

- [ ] **Step 2: Run tests to verify they FAIL**

Run: `python -m pytest tests/test_signals.py::TestDiscoveryRRClamp -v`
Expected: `test_long_discovery_emits_at_min_rr` and `test_short_discovery_emits_at_min_rr`
FAIL with `assert len(sigs) == 1` (got 0 — rejected at rr1=1.27).
`test_min_rr_below_fib_keeps_1272` PASSES already (1.2 < 1.272, so 1.27 already
clears the 1.2 gate pre-fix) — it guards the `max()` direction post-fix.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_signals.py
git commit -m "test(signals): discovery TP1 must clamp to min_rr (failing)"
```

---

### Task 2: Implement the clamp

**Files:**
- Modify: `engine/signals.py:575` (LONG), `engine/signals.py:617` (SHORT)

- [ ] **Step 1: Edit the LONG discovery target (line ~575)**

Find:
```python
                    # ── Fibonacci price discovery targets (empty structures) ──
                    # "fiyat oluşmamış bir alanda hedef belirlemek için kullanılabilir. 1.272"
                    tp1 = price + risk_tmp * 1.272
```
Replace with:
```python
                    # ── Fibonacci price discovery targets (empty structures) ──
                    # "fiyat oluşmamış bir alanda hedef belirlemek için kullanılabilir. 1.272"
                    # Clamp to min_rr: a bare 1.272 projection (rr1=1.27) would be
                    # rejected 100% of the time by the min_rr gate below. Mirrors
                    # smc_v2 RR_PROJECTION (engine/smc_v2/tp_calc.py:76).
                    tp1 = price + risk_tmp * max(1.272, min_rr)
```

- [ ] **Step 2: Edit the SHORT discovery target (line ~617)**

Find:
```python
                    # ── Fibonacci price discovery targets (empty structures) ──
                    # "fiyat oluşmamış bir alanda hedef belirlemek için kullanılabilir. 1.272"
                    tp1 = price - risk_tmp * 1.272
```
Replace with:
```python
                    # ── Fibonacci price discovery targets (empty structures) ──
                    # "fiyat oluşmamış bir alanda hedef belirlemek için kullanılabilir. 1.272"
                    # Clamp to min_rr: see LONG branch — mirrors smc_v2 RR_PROJECTION.
                    tp1 = price - risk_tmp * max(1.272, min_rr)
```

- [ ] **Step 3: Run the new tests to verify they PASS**

Run: `python -m pytest tests/test_signals.py::TestDiscoveryRRClamp -v`
Expected: all 3 PASS.

- [ ] **Step 4: Run the full signals test module (no regressions)**

Run: `python -m pytest tests/test_signals.py -v`
Expected: all PASS (existing reject-summary tests still green — they reject at
confluence, never reaching the discovery branch).

- [ ] **Step 5: Commit the fix**

```bash
git add engine/signals.py
git commit -m "fix(signals): clamp discovery TP1 to min_rr (was 1.272, always rejected)"
```

---

### Task 3: Sync live config min_rr 1.8 → 1.5

**Files:**
- Modify: `configs/config.phase2_1k.yaml:100`

- [ ] **Step 1: Edit the prod config**

Find:
```yaml
  min_rr: 1.8                         # Min R:R 1:1.8
```
Replace with:
```yaml
  min_rr: 1.5                         # Min R:R 1:1.5 (optimized from 1.8; discovery clamp uses this)
```

- [ ] **Step 2: Verify no other prod-relevant config still pins 1.8**

Run: `grep -rn "min_rr" configs/config.phase2_1k.yaml config.yaml`
Expected: `configs/config.phase2_1k.yaml` now `1.5`; root `config.yaml` already `1.5`.
(`configs/candidate_opt_best.yaml` may stay 1.8 — not the prod config.)

- [ ] **Step 3: Commit the config change**

```bash
git add configs/config.phase2_1k.yaml
git commit -m "config(risk): min_rr 1.8 -> 1.5 (sync prod to optimized value)"
```

---

### Task 4: Full suite + review gate

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: all green (1139+). If any unrelated test was already failing on master,
note it but do not fix in this PR.

- [ ] **Step 2: Risk-ops review (mandatory — touches `engine/signals.py` + `risk:` config block)**

This change touches trade logic and the `risk:` block → run `efloud-risk-ops-reviewer`
on the branch diff before opening the PR. Address any blocking findings.

- [ ] **Step 3: Open PR**

```bash
git push -u origin fix/discovery-rr-clamp
gh pr create --base master --title "fix(signals): clamp discovery TP1 to min_rr + sync prod min_rr 1.8->1.5" --body "<summary + live evidence + spec link>"
```

- [ ] **Step 4: Deploy (separate, user-gated)**

Live mainnet — deploy only on a quiet window with explicit user approval.
Post-deploy watch: discovery symbols (ADA/ETH/XRP/DOGE/SOL/BNB/LINK) should emit at
`rr1 = 1.5` instead of `max seen: 1.27` rejects.

---

## Self-Review

**Spec coverage:**
- Discovery clamp (LONG+SHORT) → Task 2. ✓
- `max(1.272, min_rr)` semantics (both directions) → Task 1 (3 tests incl. min_rr<1.272). ✓
- Config min_rr 1.8→1.5 → Task 3. ✓
- TDD regression → Task 1. ✓
- Full suite green → Task 4 Step 1. ✓
- Risk-ops review + PR + cautious deploy → Task 4 Steps 2-4. ✓
- Out-of-scope (structural-target detection) → explicitly deferred in spec, no task. ✓

**Placeholder scan:** PR body `<summary>` is a deliberate fill-at-PR-time marker, not
a code placeholder. All code steps contain complete code. No TBD/TODO in code.

**Type consistency:** `generate_signals` signature matches calls (min_confluence,
min_rr, fib_ext, recency_bars, symbol). `Signal` attrs used (direction, rr1, tp1,
tp2, entry) match the dataclass emitted at signals.py:666-674. Mock methods
(analyze/swings/structure/order_blocks/sfps/range_info/ote) match the real calls in
generate_signals. ✓
