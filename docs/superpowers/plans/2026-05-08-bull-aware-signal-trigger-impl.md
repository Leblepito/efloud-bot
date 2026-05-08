# Bull-Aware Signal Trigger Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt `generate_signals` so both CHoCH (trend reversal) and BOS (trend continuation) breaks can trigger entries, with BOS having a tighter recency window and a recalibrated confluence floor matching the "ChoCH +25 + 2 SMC layers" minimum-evidence rule.

**Architecture:** Single-file engine change in [engine/signals.py](../../engine/signals.py) (trigger filter + BOS recency check) plus a config recalibration in [configs/config.aggressive_v1.yaml](../../../configs/config.aggressive_v1.yaml). No new modules, no API changes, no frontend changes. Existing risk gates (max 5 pos, dedup, breakers) absorb the higher signal frequency.

**Tech Stack:** Python 3.12, pytest, pyyaml. No new dependencies.

**Spec:** [docs/superpowers/specs/2026-05-08-bull-aware-signal-trigger-design.md](../specs/2026-05-08-bull-aware-signal-trigger-design.md)

---

## Chunk 1: Trigger expansion (CHoCH + BOS)

### Task 1: Generalize mock-engine fixture to accept any break kind

**Files:**
- Modify: `tests/test_signals.py:35-58` (existing `_make_mock_engine` helper)

The existing helper takes `choch_break` and returns a mock engine. We rename to `break_obj` and update the docstring/comments — pure refactor, no behavior change. This unblocks Tasks 2-5 from reusing it for BOS scenarios.

- [ ] **Step 1: Rename parameter and update class docstring**

```python
class TestRejectSummaryLog:
    """Reject summary log + trigger acceptance for CHoCH/BOS breaks."""

    def _make_mock_engine(self, break_obj) -> MagicMock:
        e_range = SimpleNamespace(
            discount=False, premium=False, dev_bull=False, dev_bear=False,
            lo=99.0, hi=101.0,
        )
        engine = MagicMock()
        engine.analyze.return_value = {
            "trend": "BULL",
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
```

Then update the two existing call sites in the same class (`test_reject_log_contains_symbol_prefix_and_histogram` and `test_reject_log_uses_per_symbol_override_threshold`) to pass `break_obj=` if currently positional.

- [ ] **Step 2: Run regression tests to confirm no behavior change**

Run: `python -m pytest tests/test_signals.py -v`
Expected: 7 PASS (same as before)

- [ ] **Step 3: Commit**

```bash
git add tests/test_signals.py
git commit -m "test(signals): rename _make_mock_engine param for break-kind reuse"
```

---

### Task 2: Failing test — BOS in HTF direction reaches confluence scoring

**Files:**
- Modify: `tests/test_signals.py` (add new test method to `TestRejectSummaryLog`)

This test asserts that a BOS event aligned with HTF bias is no longer silently filtered at the trigger gate. It will fail today because [engine/signals.py:194](../../engine/signals.py#L194) drops anything that isn't `CHoCH`.

We assert that the reject log mentions a trigger ("BOS" appears in the log line, or `aligned_chochs > 0` semantics include BOS now). The simplest assertion: the reject log is emitted at all (currently no log because `aligned_chochs == 0` when only a BOS is present).

- [ ] **Step 1: Write the failing test**

```python
def test_bos_in_htf_direction_reaches_confluence_scoring(
    self, caplog: pytest.LogCaptureFixture
) -> None:
    """BOS aligned with HTF bias must be a valid trigger candidate.

    Pre-change: signals.py drops every non-CHoCH break, so this BOS is
    silently ignored and no reject log is emitted.
    Post-change: BOS goes through to confluence scoring; with no extra
    layers the score is 25 (HTF bias only) → reject log emitted with
    bucket 25.
    """
    bos_break = SimpleNamespace(
        direction="BULL", kind="BOS", idx=45, ts="2026-05-08T00:00", price=100.0
    )
    engine = self._make_mock_engine(bos_break)
    df = pd.DataFrame({"close": [100.0] * 50})

    with caplog.at_level(logging.INFO, logger="efloud.signals"):
        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=70, min_rr=1.5, fib_ext=1.618,
            recency_bars=40,
            symbol="ETH/USDT",
        )

    assert sigs == []
    reject_msgs = [
        rec.message for rec in caplog.records
        if "0 signals" in rec.message and "Rejects" in rec.message
    ]
    assert reject_msgs, (
        "BOS trigger was filtered before confluence scoring; "
        f"records: {[r.message for r in caplog.records]}"
    )
    msg = reject_msgs[0]
    assert "[ETH/USDT]" in msg
    assert "max=25" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signals.py::TestRejectSummaryLog::test_bos_in_htf_direction_reaches_confluence_scoring -v`
Expected: FAIL with "BOS trigger was filtered before confluence scoring"

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_signals.py
git commit -m "test(signals): RED — BOS aligned with HTF bias should trigger"
```

---

### Task 3: GREEN — accept BOS at the trigger filter

**Files:**
- Modify: `engine/signals.py:194` (the `if brk.kind != "CHoCH"` filter line)

- [ ] **Step 1: Update the trigger filter**

Find the loop body in `generate_signals` that begins with the line below:

```python
    for brk in e_brks:
        # Sadece CHoCH + HTF yönünde + son N bar içinde
        if brk.kind != "CHoCH" or brk.direction != htf_bias:
            continue
        if brk.idx < recent_cutoff:
            continue
```

Change it to:

```python
    for brk in e_brks:
        # CHoCH (reversal) + BOS (continuation) — both must align with HTF bias.
        # See docs/superpowers/specs/2026-05-08-bull-aware-signal-trigger-design.md
        if brk.kind not in ("CHoCH", "BOS") or brk.direction != htf_bias:
            continue
        if brk.idx < recent_cutoff:
            continue
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_signals.py::TestRejectSummaryLog::test_bos_in_htf_direction_reaches_confluence_scoring -v`
Expected: PASS

- [ ] **Step 3: Run full signals test file for regressions**

Run: `python -m pytest tests/test_signals.py -v`
Expected: 8 PASS (5 helper unit + 3 integration including the new one)

- [ ] **Step 4: Commit**

```bash
git add engine/signals.py
git commit -m "feat(signals): accept BOS as a valid trigger alongside CHoCH"
```

---

## Chunk 2: BOS-specific recency window

### Task 4: Failing test — BOS past 20-bar recency rejected

**Files:**
- Modify: `tests/test_signals.py` (add new test to `TestRejectSummaryLog`)

A 50-bar dataframe with a BOS at `idx=25` is 25 bars old. CHoCH `recency_bars=40` would accept it; BOS-specific `recency_bars=20` (half) should reject it. After the next task, this BOS produces no log at all (filtered before confluence scoring).

- [ ] **Step 1: Write the failing test**

```python
def test_bos_past_bos_recency_window_is_rejected(
    self, caplog: pytest.LogCaptureFixture
) -> None:
    """BOS more than recency_bars/2 bars old must not trigger.

    Pre-Task-5: BOS uses the global recency_bars=40 → idx=25 in a
    50-bar df is fresh enough → reject log appears.
    Post-Task-5: BOS uses 40/2=20 bar window → idx=25 is stale → no
    reject log emitted (filtered at trigger gate, before scoring).
    """
    stale_bos = SimpleNamespace(
        direction="BULL", kind="BOS", idx=25, ts="2026-05-08T00:00", price=100.0
    )
    engine = self._make_mock_engine(stale_bos)
    df = pd.DataFrame({"close": [100.0] * 50})

    with caplog.at_level(logging.INFO, logger="efloud.signals"):
        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=70, min_rr=1.5, fib_ext=1.618,
            recency_bars=40,
            symbol="ETH/USDT",
        )

    assert sigs == []
    reject_msgs = [
        rec.message for rec in caplog.records
        if "0 signals" in rec.message and "Rejects" in rec.message
    ]
    assert reject_msgs == [], (
        "Stale BOS slipped through; expected trigger-gate rejection. "
        f"records: {[r.message for r in caplog.records]}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signals.py::TestRejectSummaryLog::test_bos_past_bos_recency_window_is_rejected -v`
Expected: FAIL with "Stale BOS slipped through"

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_signals.py
git commit -m "test(signals): RED — stale BOS (>20 bars) should be filtered"
```

---

### Task 5: GREEN — add BOS-specific recency cap

**Files:**
- Modify: `engine/signals.py` (the section right after the existing recency check around line 196-197)

- [ ] **Step 1: Add BOS recency check**

Inside the loop, just after the existing `if brk.idx < recent_cutoff: continue`, add a tighter cap for BOS:

```python
    for brk in e_brks:
        # CHoCH (reversal) + BOS (continuation) — both must align with HTF bias.
        # See docs/superpowers/specs/2026-05-08-bull-aware-signal-trigger-design.md
        if brk.kind not in ("CHoCH", "BOS") or brk.direction != htf_bias:
            continue
        if brk.idx < recent_cutoff:
            continue
        # BOS events are far more frequent than CHoCH; tighten the recency
        # window to half so we don't enter on stale continuation breaks.
        if brk.kind == "BOS" and brk.idx < (last_bar_idx - recency_bars // 2):
            continue
        aligned_chochs += 1
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_signals.py::TestRejectSummaryLog::test_bos_past_bos_recency_window_is_rejected -v`
Expected: PASS

- [ ] **Step 3: Verify regression — fresh BOS still triggers**

Run: `python -m pytest tests/test_signals.py::TestRejectSummaryLog::test_bos_in_htf_direction_reaches_confluence_scoring -v`
Expected: PASS (idx=45 still inside 20-bar window: 50-1-20=29, 45 > 29 ✓)

- [ ] **Step 4: Commit**

```bash
git add engine/signals.py
git commit -m "feat(signals): half recency window for BOS triggers"
```

---

### Task 6: Regression test — CHoCH recency stays at full window

**Files:**
- Modify: `tests/test_signals.py`

Defensive test: a CHoCH at idx=12 (38 bars old in a 50-bar df) should still pass — CHoCH must not inherit the BOS-tightened recency.

- [ ] **Step 1: Write regression test**

```python
def test_choch_at_full_recency_still_triggers(
    self, caplog: pytest.LogCaptureFixture
) -> None:
    """CHoCH (rare event) keeps the full recency_bars window.

    Guards against accidentally tightening CHoCH along with BOS in
    Task 5. idx=12 in a 50-bar df with recency_bars=40 is 38 bars
    old → exactly at the edge of CHoCH window, should still pass.
    """
    old_choch = SimpleNamespace(
        direction="BULL", kind="CHoCH", idx=12, ts="2026-05-08T00:00", price=100.0
    )
    engine = self._make_mock_engine(old_choch)
    df = pd.DataFrame({"close": [100.0] * 50})

    with caplog.at_level(logging.INFO, logger="efloud.signals"):
        generate_signals(
            engine, df, df, df,
            min_confluence=70, min_rr=1.5, fib_ext=1.618,
            recency_bars=40,
            symbol="ETH/USDT",
        )

    reject_msgs = [
        rec.message for rec in caplog.records
        if "0 signals" in rec.message and "Rejects" in rec.message
    ]
    assert reject_msgs, "CHoCH at full recency window was wrongly filtered"
```

- [ ] **Step 2: Run test — should already pass**

Run: `python -m pytest tests/test_signals.py::TestRejectSummaryLog::test_choch_at_full_recency_still_triggers -v`
Expected: PASS (no impl change needed; this is a regression guard)

- [ ] **Step 3: Commit**

```bash
git add tests/test_signals.py
git commit -m "test(signals): regression — CHoCH keeps full recency window"
```

---

## Chunk 3: Counter-direction guard + log clarity

### Task 7: Counter-direction BOS still rejected

**Files:**
- Modify: `tests/test_signals.py`

A BOS in the wrong direction (e.g. BEAR break under a BULL HTF bias) must still be filtered. The existing `brk.direction != htf_bias` clause handles this; we add a defensive test so future refactors can't break it silently.

- [ ] **Step 1: Write regression test**

```python
def test_bos_against_htf_bias_is_rejected(
    self, caplog: pytest.LogCaptureFixture
) -> None:
    """BEAR BOS under BULL HTF bias must not produce signals.

    Existing filter line guards this; the test prevents accidental
    removal during future refactors.
    """
    counter_bos = SimpleNamespace(
        direction="BEAR", kind="BOS", idx=45, ts="2026-05-08T00:00", price=100.0
    )
    engine = self._make_mock_engine(counter_bos)
    df = pd.DataFrame({"close": [100.0] * 50})

    with caplog.at_level(logging.INFO, logger="efloud.signals"):
        sigs = generate_signals(
            engine, df, df, df,
            min_confluence=70, min_rr=1.5, fib_ext=1.618,
            recency_bars=40,
            symbol="ETH/USDT",
        )

    assert sigs == []
    reject_msgs = [
        rec.message for rec in caplog.records
        if "0 signals" in rec.message and "Rejects" in rec.message
    ]
    assert reject_msgs == [], "Counter-direction BOS leaked through"
```

- [ ] **Step 2: Run test — should pass on existing code**

Run: `python -m pytest tests/test_signals.py::TestRejectSummaryLog::test_bos_against_htf_bias_is_rejected -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_signals.py
git commit -m "test(signals): regression — counter-direction BOS rejected"
```

---

### Task 8: Reject log includes trigger kind label

**Files:**
- Modify: `engine/signals.py:335` (the diagnostic reject log line)
- Modify: `tests/test_signals.py` (existing `test_reject_log_contains_symbol_prefix_and_histogram` to assert "CHoCH/BOS" in the log)

Currently the log says `📉 [SYM] N CHoCH, 0 signals`. Now that BOS also triggers, the count is over both kinds — change wording to `N triggers` (kind-agnostic) so calibration logs stay accurate.

- [ ] **Step 1: Update existing assertion to match new log wording**

In `test_reject_log_contains_symbol_prefix_and_histogram`, replace:

```python
assert "CHoCH" in msg or "BOS" in msg  # already covered by '0 signals' check
```

(no specific kind assertion needed — the test already asserts presence via `"0 signals" in rec.message`).

Update the existing test to assert the new wording:

```python
# Existing assertion shape stays; add:
assert "triggers" in msg or "CHoCH" in msg  # backwards-compatible during transition
```

Actually simpler — keep tests structural (`"0 signals"` and `"Rejects"`) and let the log-content evolution be visible in deploy verify only. **No test change in this task.**

- [ ] **Step 2: Update the log message in engine/signals.py**

Find:

```python
log.info(f"📉 {prefix}{aligned_chochs} CHoCH, 0 signals. Rejects: {' | '.join(reasons)}")
```

Change to:

```python
log.info(f"📉 {prefix}{aligned_chochs} triggers, 0 signals. Rejects: {' | '.join(reasons)}")
```

Rename the local counter for accuracy (cosmetic, single rename inside the function):

```python
# Diagnostics: reject reasons
aligned_triggers = 0  # was: aligned_chochs
```

And replace the two `aligned_chochs += 1` / final `if aligned_chochs > 0` references in the same function. Keep the rename scoped strictly to `generate_signals`.

- [ ] **Step 3: Run full signals tests**

Run: `python -m pytest tests/test_signals.py -v`
Expected: 11 PASS (5 helper + 6 integration = 3 existing + 3 new from Tasks 2/4/6/7)

- [ ] **Step 4: Commit**

```bash
git add engine/signals.py
git commit -m "feat(signals): kind-agnostic reject log wording (CHoCH+BOS)"
```

---

## Chunk 4: Confluence floor recalibration

### Task 9: Update aggressive_v1 config thresholds

**Files:**
- Modify: `configs/config.aggressive_v1.yaml` (lines 95-114)

Floor changes per the spec table:

| Tier | Old | New |
|---|---:|---:|
| Top (ETH/SOL/FIL/RENDER) | 70 | 55 |
| Mid (BTC/SUI/ADA/OP/LTC) | 80 | 65 |
| Selective (XRP) | 85 | 75 |

- [ ] **Step 1: Update `min_confluence` (global default)**

Find:

```yaml
  min_confluence: 70                  # Global default; weak coins overridden in symbol_confluence_overrides
```

Change to:

```yaml
  min_confluence: 55                  # ChoCH(25) + MTF onay(20) + 1 SMC layer(10) — see specs/2026-05-08-bull-aware-signal-trigger-design.md
```

- [ ] **Step 2: Update per-symbol overrides**

Find the `symbol_confluence_overrides` block (lines 108-114) and change all six values:

```yaml
  symbol_confluence_overrides:
    BTC/USDT: 65
    SUI/USDT: 65
    ADA/USDT: 65
    OP/USDT: 65
    LTC/USDT: 65
    XRP/USDT: 75   # User re-added 2026-05-08; tightened gap (was 85) to compensate for -6.63% Phase A perf
```

- [ ] **Step 3: Update the header comment block (lines 8-17)**

Replace the "Changes from H2-A2 baseline" block to reflect the new state. Keep the file's history-narrative structure intact:

```yaml
# Changes from H2-A2 baseline:
#   confluence:           80 → 55 (global) + per-symbol overrides (mid 65, XRP 75)
#   trigger:              CHoCH-only → CHoCH + BOS (continuation)
#   max_open_positions:   1 (de-facto) → 5 (now ENFORCED via new gate)
#   max_position_notional_pct: 6.0 → 10.0 (per-trade exposure 1.67x)
#   ...
```

(Only the first two lines change; rest of comment block stays.)

- [ ] **Step 4: Run YAML lint / config-load smoke**

Run: `python -m pytest backend/tests/test_api_smoke.py tests/config/test_phase_configs.py -v`
Expected: PASS (config loads without error)

- [ ] **Step 5: Commit**

```bash
git add configs/config.aggressive_v1.yaml
git commit -m "config(aggressive_v1): floor 55/65/75 for CHoCH+BOS triggers"
```

---

## Chunk 5: Verify end-to-end + ship

### Task 10: Full test suite + frontend build

- [ ] **Step 1: Backend full smoke**

Run: `python -m pytest tests/ backend/tests/ -q`
Expected: ≥138 pass (136 prior + 3-4 new in test_signals.py), ≤6 skipped, 0 failed.

- [ ] **Step 2: Frontend build (sanity — no frontend code touched, but verify nothing's bleeding)**

Run: `cd frontend && npm run build`
Expected: "Compiled successfully" + "Linting and checking validity of types"

- [ ] **Step 3: Git status clean**

Run: `git status`
Expected: clean tree (all changes committed in prior tasks).

---

### Task 11: PR

- [ ] **Step 1: Push feature branch**

```bash
git push -u origin feature/bull-aware-trigger
```

- [ ] **Step 2: Open PR via gh**

```bash
gh pr create --base master --head feature/bull-aware-trigger \
  --title "feat(signals): bull-aware trigger — CHoCH + BOS, floor 55/65/75" \
  --body "$(cat <<'EOF'
## Summary
- Trigger filter now accepts both **CHoCH** (trend reversal) and **BOS** (trend continuation) breaks aligned with HTF bias.
- BOS gets half the recency window of CHoCH (20 vs 40 bars on entry TF) to avoid stale continuation entries.
- Confluence floors recalibrated to match the "ChoCH +25 + 2 SMC layers" minimum-evidence rule: top 70→55, mid 80→65, XRP 85→75.
- Reject summary log says "triggers" instead of "CHoCH" since BOS now counts.

## Why
24+ hours of zero trades on aggressive_v1 LIVE — diagnostic log refactor (PR #10 follow-up) showed the bot ignores BOS continuation breaks. In a bull market `CHoCH(BULL) → BOS → BOS → ... → CHoCH(BEAR)`, only the first event ever triggered the bot. Approach B from `docs/superpowers/specs/2026-05-08-bull-aware-signal-trigger-design.md`.

## Risk
- Higher signal frequency in trending regimes (target: 3-5 trades/day vs 0). Existing risk gates absorb: max_open_positions=5 enforced, per-symbol 1h dedup, daily-loss 10% breaker.
- Rollback = single revert + redeploy. No data migration.

## Test plan
- [x] 4 new tests in tests/test_signals.py (BOS accept, BOS stale reject, CHoCH recency unchanged, counter-dir BOS reject)
- [x] Full backend suite + frontend build pass
- [ ] Post-merge: SSH Hetzner, deploy, observe 24h log, check per-symbol trigger histogram in [SYM] N triggers logs

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Surface PR URL to user**

Wait for user to merge.

---

### Task 12: Deploy + live verify

- [ ] **Step 1: Pull master locally + sync**

```bash
git checkout master
git pull origin master
git log --oneline -3
```
Expected: most recent commit is the merge commit for the bull-aware trigger PR.

- [ ] **Step 2: Hetzner deploy (requires user confirmation)**

```bash
ssh efloud@178.104.122.91 \
  "cd /opt/efloud-bot && git pull origin master && bash deploy/deploy.sh"
```
Expected: image rebuild, container restart, "✅ Bot is up and healthy" + healthz JSON.

- [ ] **Step 3: Live verify — auth gate, log format**

```bash
# Auth gate
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://bot.ualgotrade.com/api/positions
# Expected: 401

# 5-minute log sample after deploy — look for 'BOS' in trigger logs
ssh efloud@178.104.122.91 \
  "sleep 300 && cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml logs --since=5m efloud-bot 2>&1 | grep -E 'triggers|BOS|max=' | head -30"
```
Expected: at least some log lines mention BOS or have higher per-bucket counts than the historical 60-only stuck distribution.

- [ ] **Step 4: Update memory**

Append a brief note to `efloud_state.md` documenting: master HEAD, new trigger behavior, new floor values, expected daily trade rate, rollback ref.

- [ ] **Step 5: Done — surface results to user**

Report: deployment status, log evidence, any unexpected breaker trips.

---

## Out of scope (follow-up only)

- Phase B reconcile (`scripts/run_phase_b.py`) — run after 1 week of live data to compare BOS-inclusive distribution vs backtest expectations.
- Per-symbol BOS frequency cap (e.g., max 2 BOS-triggered entries per symbol per 24h) — only if pyramid-like behavior emerges in observation.
- Approach C (regime-adaptive thresholds) — revisit if live performance materially diverges from spec expectations.
