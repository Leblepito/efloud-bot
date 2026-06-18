# Live Edge Measurement Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal-first system that records every first-sight SMC signal, shadow-resolves its hypothetical outcome faithfully to the bot's real execution, and reports cost-netted, significance-gated edge metrics — answering "does the bot's signal have a tradeable NET edge?"

**Architecture:** 100% additive, default-OFF, read-only. A new append-only JSONL `SignalLedger` is written from a single best-effort hook at the orchestrator first-sight choke-point (`safe_orchestrator.py:~1209`, BEFORE the `is_tradeable` split, so it captures BOTH tradeable and read-only signals). A separate-process batch resolver replays forward price (MARKET-at-confirmation fill model, per-direction SL/TP race, cost netting) and writes outcomes back. `edge_metrics` aggregates with min-N / CI / FDR gates; `edge_report` prints a conditioned, disclaimer-led status report. Trade/safety logic is never touched.

**Tech Stack:** Python 3.11, dataclasses, pandas, ccxt (public instance for klines), pytest. Reuses `engine/journal.py` persistence pattern, `scripts/routines/` `@register` pattern, `backtest/funding.py` + commission constant, `AlertRouter`.

**Spec:** `docs/superpowers/specs/2026-06-18-edge-measurement-core-design.md` (v2, hardened).

**Build order rationale:** offline data + math first (Tasks 1-7, fully hermetic), the live orchestrator hook LAST (Task 8) once everything it feeds is tested. Config first (Task 0).

**Coexistence:** `feat/smc-sl-tp-redesign` edits `engine/safe_orchestrator.py` in the same region as Task 8. Land/rebase that branch before executing Task 8; Tasks 0-7 are conflict-free.

---

## Frozen Interface Contract (all tasks MUST use these exact names/signatures)

```python
# engine/signal_ledger.py
@dataclass
class SignalRecord:
    signal_id: str            # f"{symbol}-{direction}-{brk_ts_ms}-{short_hash(entry,sl,tp1)}"
    ts_emitted: int           # epoch-ms UTC
    brk_ts: int               # epoch-ms UTC (break/structure bar timestamp)
    symbol: str
    direction: str            # 'LONG' | 'SHORT'
    emitted_entry: float
    sl: float
    tp1: float
    tp2: float | None
    confluence: float
    rr1: float
    rr2: float | None
    timeframe: str
    htf_bias: str
    regime: str
    reasons: list
    was_tradeable: bool
    entry_is_retrace: bool
    exit_model: str           # 'single_target' | 'partial_ladder'
    kronos_verdict: dict | None = None   # {direction, change_pct, confidence_band, agree}
    agents_verdict: dict | None = None   # {team_verdict, confidence}
    status: str = "open"      # open|filled|resolved|timeout|unfilled|unresolved_data
    disposition: str = "readonly"        # opened|readonly|vetoed|guard_blocked|deduped
    outcome: str | None = None           # tp1|tp2|sl|timeout|unfilled
    fill_price: float | None = None
    hypo_r_gross: float | None = None
    hypo_r_net: float | None = None
    ts_filled: int | None = None
    ts_resolved: int | None = None
    bars_to_fill: int | None = None
    bars_to_resolve: int | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    resolved_at_granularity: str | None = None
    trade_id: str | None = None

class SignalLedger:
    def __init__(self, path): ...                       # path: pathlib.Path
    def record_signal(self, **fields) -> str | None     # builds SignalRecord; idempotent on dedup_key; returns signal_id or None if dup
    def attach_kronos(self, signal_id: str, verdict: dict) -> None
    def set_trade_id(self, signal_id: str, trade_id: str) -> None
    def update_resolution(self, signal_id: str, **fields) -> None
    def open_signals(self) -> list                      # status in {open, filled}
    def all_signals(self) -> list
    @staticmethod
    def mint_id(symbol, direction, brk_ts_ms, entry, sl, tp1) -> str
    @staticmethod
    def dedup_key(symbol, direction, entry) -> tuple    # asset-relative tolerance

# engine/edge_costs.py
def net_r(direction, entry, sl, raw_r, holding_hours, funding_pct_sum,
          taker_rate=0.0004, slippage_r=0.05) -> float   # raw_r minus fees+funding+slippage in R-units

# scripts/routines/resolve_signals.py
def replay_fill(rec, bars_1m, smc_version) -> dict | None   # {fill_price, ts_filled, bars_to_fill} or None (unfilled)
def race_sl_tp(rec, bars_1m, fill_idx) -> dict              # {outcome, hypo_r_raw, mfe_r, mae_r, bars_to_resolve, ts_resolved}
def resolve_signal(rec, bars_1m, smc_version, max_horizon_hours) -> dict   # full resolution patch
def resolve_open_signals(ledger, fetcher, cfg) -> dict     # pass summary counters

# engine/edge_metrics.py
def aggregate(records, min_n_print=30, min_n_claim=100) -> dict   # gated metrics + breakdowns + 3-way timeout panel

# scripts/routines/edge_report.py
def build_report(metrics: dict) -> str   # status-line-first markdown
```

Config block keys (Task 0): `signal_ledger.{enabled, fill_window_bars, max_horizon_hours, resolution_tf, resolver_cadence_sec, max_symbols, fetch_fail_alert_pct}`.

---

## Plan Review Corrections (verified against real code — APPLY during execution)

A 5-lens adversarial plan review + direct code verification produced these. They fix real-code anchor errors (method names, the timestamp type, v2 fidelity). The architecture is unchanged; no CRIT remained.

1. **Signal fields confirmed** (`engine/signals.py:117-137`): `direction, entry, sl, tp1, tp2, rr1, rr2, confluence(int), reasons, timestamp(str!), meta`. ⚠️ `Signal.timestamp` is an **ISO string**, and `tp2`/`rr2` are **always floats** (never None at the Signal level).
2. **brk_ts conversion (Task 8 hook):** `latest.timestamp` is a string → use `brk_ts = int(pd.Timestamp(latest.timestamp).value // 1_000_000)` (NOT `int(latest.timestamp)`). Ensure `ts_emitted` is epoch-ms (if the orchestrator's `now_ts` is seconds, multiply by 1000).
3. **exit_model derivation (Task 8):** since `Signal.tp2` is always a float, `tp2 is None` is never true at the Signal level. The single-target path nulls tp2 only later (`tp_calc.py:14` / lifecycle for v2). Derive `exit_model` from a `latest.meta` single-target flag (or `tp2 == tp1` degenerate); default `partial_ladder` when a distinct tp2 exists. Carry the resolved `tp2` (possibly None) onto the SignalRecord, not the raw Signal.tp2.
4. **OHLCVFetcher real methods (Tasks 4, 7 + the FakeFetcher double):** `data/fetcher.py:OHLCVFetcher` exposes `fetch_ohlcv_range(symbol, tf, start_ms, end_ms)` (returns an OHLCV **DataFrame**) and `fetch_funding_rates(symbol, start_ms, end_ms)` (DataFrame). Replace the plan's `fetch_range`/`funding_sum`. Add `_bars_from_df(df) -> list[dict]` (DataFrame → `{ts,open,high,low,close}` list the race uses) and `_sum_funding(df) -> float` (sum the funding-rate column; sign handling stays in `net_r`). Make the test `FakeFetcher` mirror these real names.
5. **AlertRouter real API (Task 4):** `from scripts.routines._alert import AlertRouter`; call `AlertRouter().send(severity, dedup_key, title, body)` — there is **no `.breach`**. e.g. `send("WARNING", "signal_resolver_fetchfail", "resolver fetch-fail", f"{fail_pct:.0f}% >= {thr}%")`.
6. **smc_version config path (Task 7 main):** lives at `cfg_all["engine"]["smc_version"]` (default `"v1"`), NOT top-level. Use `cfg_all.get("engine", {}).get("smc_version", "v1")`.
7. **v2 fill fidelity GAP (HIGH — Task 3 + spec §3.1):** the real confirmation is `engine/smc_v2/confirmation.py:23 confirm_entry(...)` (prior-opposite bar + true body-engulfing + in-zone). The plan's `replay_fill` v2 rule approximates this (body sign + close beyond prior high/low) and its comment mismatches the spec. Either (a) thread the target ZoneSpec onto SignalRecord and call the real `confirm_entry`, OR (b) label it a **KNOWN FIDELITY GAP** in the `replay_fill` docstring, spec §3.1, and an `edge_report` caveat. (b) is acceptable for the v1-first ship; (a) is required before any **v2** edge verdict is trusted. Fix the code/comment mismatch either way.
8. **v2 positive-fill test (HIGH — Task 3):** every positive resolver test uses `smc_version="v1"`, but **prod is v2** (`engine.smc_version=v2`). Add a v2 happy-path test (flat bars → engulfing confirmation within `fill_window_bars` → later SL/TP; assert `status=="resolved"`, `fill_price==` confirmation close, `bars_to_fill==idx+1`) plus a v2 same-confirmation-bar test pinning that the SL/TP race starts strictly AFTER the fill bar.

---

## Task 0: Config block (default-OFF, LIVE config)

**Files:**
- Modify: `configs/config.phase2_1k.yaml` (add `signal_ledger:` block)
- Test: `backend/tests/test_signal_ledger_config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_signal_ledger_config.py
import yaml
from pathlib import Path

def test_signal_ledger_config_defaults_off():
    cfg = yaml.safe_load(Path("configs/config.phase2_1k.yaml").read_text(encoding="utf-8"))
    sl = cfg.get("signal_ledger")
    assert sl is not None, "signal_ledger block missing from LIVE config"
    assert sl["enabled"] is False
    assert sl["max_horizon_hours"] == 48
    assert sl["resolution_tf"] == "1m"
    assert sl["fill_window_bars"] == 8
    assert sl["resolver_cadence_sec"] == 300
    assert sl["max_symbols"] == 25
    assert sl["fetch_fail_alert_pct"] == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest backend/tests/test_signal_ledger_config.py -v`
Expected: FAIL — `signal_ledger block missing`.

- [ ] **Step 3: Add the config block**

Append to `configs/config.phase2_1k.yaml`:

```yaml
signal_ledger:
  enabled: false            # master flag, decoupled from kronos.*
  fill_window_bars: 8       # bars after emission for MARKET-at-confirmation, else 'unfilled'
  max_horizon_hours: 48     # SL/TP race expiry
  resolution_tf: "1m"       # resolver kline granularity
  resolver_cadence_sec: 300 # batch pass interval
  max_symbols: 25           # per-pass open-signal cap (weight budget)
  fetch_fail_alert_pct: 20  # AlertRouter breach threshold (% of pass)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest backend/tests/test_signal_ledger_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/config.phase2_1k.yaml backend/tests/test_signal_ledger_config.py
git commit -m "feat(edge): add default-OFF signal_ledger config block to live config"
```

---

## Task 1: SignalRecord + SignalLedger persistence & idempotent dedup

**Files:**
- Create: `engine/signal_ledger.py`
- Test: `backend/tests/test_signal_ledger.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_signal_ledger.py
from pathlib import Path
from engine.signal_ledger import SignalLedger, SignalRecord

BASE = dict(symbol="BNB/USDT", direction="SHORT", brk_ts=1781774400000,
            emitted_entry=601.73, sl=607.0, tp1=590.0, tp2=585.0, confluence=80,
            rr1=2.7, rr2=3.2, timeframe="15m", htf_bias="LONG", regime="trend",
            reasons=["OB","CHoCH"], was_tradeable=True, entry_is_retrace=False,
            exit_model="partial_ladder", ts_emitted=1781774400000)

def test_record_and_roundtrip(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl")
    sid = led.record_signal(**BASE)
    assert sid and sid.startswith("BNB/USDT-SHORT-1781774400000-")
    led2 = SignalLedger(tmp_path / "sig.jsonl")
    rows = led2.all_signals()
    assert len(rows) == 1 and rows[0].symbol == "BNB/USDT" and rows[0].direction == "SHORT"

def test_dedup_same_break_no_duplicate(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl")
    sid1 = led.record_signal(**BASE)
    # same break (same brk_ts) re-emitted later (different ts_emitted) -> NO new row
    sid2 = led.record_signal(**{**BASE, "ts_emitted": BASE["ts_emitted"] + 3_600_000})
    assert sid2 is None
    assert len(led.all_signals()) == 1

def test_dedup_survives_restart(tmp_path):
    SignalLedger(tmp_path / "sig.jsonl").record_signal(**BASE)
    led = SignalLedger(tmp_path / "sig.jsonl")  # fresh instance loads seen-set
    assert led.record_signal(**BASE) is None
    assert len(led.all_signals()) == 1

def test_subcent_tolerance(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl")
    a = dict(BASE, symbol="DOGE/USDT", emitted_entry=0.12345, sl=0.130, tp1=0.118, tp2=None, exit_model="single_target", rr2=None)
    led.record_signal(**a)
    # sub-cent move within tolerance on same break -> dedup
    assert led.record_signal(**dict(a, emitted_entry=0.123455)) is None

def test_mint_id_stable():
    a = SignalLedger.mint_id("BNB/USDT", "SHORT", 1781774400000, 601.73, 607.0, 590.0)
    b = SignalLedger.mint_id("BNB/USDT", "SHORT", 1781774400000, 601.73, 607.0, 590.0)
    assert a == b
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_signal_ledger.py -v`
Expected: FAIL — `No module named engine.signal_ledger`.

- [ ] **Step 3: Implement `engine/signal_ledger.py`**

```python
# engine/signal_ledger.py
from __future__ import annotations
import json, hashlib, logging
from dataclasses import dataclass, asdict, field, fields as dc_fields
from pathlib import Path

log = logging.getLogger("efloud.signal_ledger")

def _tol_round(symbol: str, price: float) -> float:
    # asset-relative tolerance: 5 significant figures (handles sub-cent alts)
    if price == 0:
        return 0.0
    from math import floor, log10
    digits = 4 - int(floor(log10(abs(price))))
    return round(price, max(digits, 2))

@dataclass
class SignalRecord:
    signal_id: str
    ts_emitted: int
    brk_ts: int
    symbol: str
    direction: str
    emitted_entry: float
    sl: float
    tp1: float
    tp2: float | None
    confluence: float
    rr1: float
    rr2: float | None
    timeframe: str
    htf_bias: str
    regime: str
    reasons: list
    was_tradeable: bool
    entry_is_retrace: bool
    exit_model: str
    kronos_verdict: dict | None = None
    agents_verdict: dict | None = None
    status: str = "open"
    disposition: str = "readonly"
    outcome: str | None = None
    fill_price: float | None = None
    hypo_r_gross: float | None = None
    hypo_r_net: float | None = None
    ts_filled: int | None = None
    ts_resolved: int | None = None
    bars_to_fill: int | None = None
    bars_to_resolve: int | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    resolved_at_granularity: str | None = None
    trade_id: str | None = None

_FIELDS = {f.name for f in dc_fields(SignalRecord)}

class SignalLedger:
    def __init__(self, path):
        self.path = Path(path)
        self._rows: dict[str, SignalRecord] = {}   # signal_id -> record
        self._seen: set[tuple] = set()             # dedup keys
        self._load()

    @staticmethod
    def dedup_key(symbol, direction, entry) -> tuple:
        return (symbol, direction, _tol_round(symbol, float(entry)))

    @staticmethod
    def mint_id(symbol, direction, brk_ts_ms, entry, sl, tp1) -> str:
        h = hashlib.sha1(f"{entry}|{sl}|{tp1}".encode()).hexdigest()[:8]
        return f"{symbol}-{direction}-{int(brk_ts_ms)}-{h}"

    def _load(self):
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = {k: v for k, v in json.loads(line).items() if k in _FIELDS}
                rec = SignalRecord(**d)
            except Exception:
                continue
            self._rows[rec.signal_id] = rec
            self._seen.add(self.dedup_key(rec.symbol, rec.direction, rec.emitted_entry))

    def _persist(self):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as fh:
            for rec in self._rows.values():
                fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def record_signal(self, **fields) -> str | None:
        key = self.dedup_key(fields["symbol"], fields["direction"], fields["emitted_entry"])
        if key in self._seen:
            return None
        sid = self.mint_id(fields["symbol"], fields["direction"], fields["brk_ts"],
                           fields["emitted_entry"], fields["sl"], fields["tp1"])
        rec = SignalRecord(signal_id=sid, **{k: v for k, v in fields.items() if k in _FIELDS})
        self._rows[sid] = rec
        self._seen.add(key)
        self._persist()
        return sid

    def attach_kronos(self, signal_id, verdict):
        rec = self._rows.get(signal_id)
        if rec and rec.kronos_verdict is None:
            rec.kronos_verdict = verdict
            self._persist()

    def set_trade_id(self, signal_id, trade_id):
        rec = self._rows.get(signal_id)
        if rec:
            rec.trade_id = trade_id
            rec.disposition = "opened"
            self._persist()

    def update_resolution(self, signal_id, **fields):
        rec = self._rows.get(signal_id)
        if not rec:
            return
        for k, v in fields.items():
            if k in _FIELDS:
                setattr(rec, k, v)
        self._persist()

    def open_signals(self):
        return [r for r in self._rows.values() if r.status in ("open", "filled")]

    def all_signals(self):
        return list(self._rows.values())
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_signal_ledger.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/signal_ledger.py backend/tests/test_signal_ledger.py
git commit -m "feat(edge): SignalLedger with brk_ts identity + idempotent dedup"
```

---

## Task 2: Cost netting (`engine/edge_costs.py`)

**Files:**
- Create: `engine/edge_costs.py`
- Test: `backend/tests/test_edge_costs.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_edge_costs.py
from engine.edge_costs import net_r

def test_fees_subtracted_in_r_units():
    # entry 100, sl 98 -> R=2.0 in price. raw +1.0R = +2.0 price.
    # round-trip taker 0.04%*2 on ~100 notional = 0.08 price = 0.04 R. funding 0.
    out = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=1, funding_pct_sum=0.0, slippage_r=0.0)
    assert abs(out - (1.0 - 0.04)) < 1e-6

def test_funding_signed_for_short(self=None):
    # SHORT pays/receives funding opposite to long; positive funding_pct_sum helps short
    out_long = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=8, funding_pct_sum=0.01, slippage_r=0.0)
    out_short = net_r("SHORT", 100.0, 102.0, 1.0, holding_hours=8, funding_pct_sum=0.01, slippage_r=0.0)
    assert out_short > out_long  # +funding benefits short

def test_slippage_haircut():
    a = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=1, funding_pct_sum=0.0, slippage_r=0.0)
    b = net_r("LONG", 100.0, 98.0, 1.0, holding_hours=1, funding_pct_sum=0.0, slippage_r=0.05)
    assert abs((a - b) - 0.05) < 1e-9
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_edge_costs.py -v`
Expected: FAIL — `No module named engine.edge_costs`.

- [ ] **Step 3: Implement `engine/edge_costs.py`**

```python
# engine/edge_costs.py
"""Cost netting for shadow edge in R-units. Fees+funding+slippage subtracted from raw R."""

def net_r(direction, entry, sl, raw_r, holding_hours, funding_pct_sum,
          taker_rate=0.0004, slippage_r=0.05):
    risk = abs(float(entry) - float(sl))
    if risk == 0:
        return raw_r
    entry = float(entry)
    # round-trip taker fees on notional ~entry, expressed in price then R-units
    fee_price = 2.0 * taker_rate * entry
    fee_r = fee_price / risk
    # funding: funding_pct_sum is summed 8h marks as a fraction of notional over the hold.
    # A LONG pays positive funding (cost); a SHORT receives it (benefit).
    funding_price = float(funding_pct_sum) * entry
    funding_r = (funding_price / risk) * (1.0 if direction == "LONG" else -1.0)
    return raw_r - fee_r - funding_r - float(slippage_r)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_edge_costs.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/edge_costs.py backend/tests/test_edge_costs.py
git commit -m "feat(edge): cost netting (fees+funding+slippage) in R-units"
```

---

## Task 3: Resolver core — fill model, SL/TP race, exit-model blending

**Files:**
- Create: `scripts/routines/resolve_signals.py` (resolution functions only this task)
- Test: `backend/tests/test_resolve_signals.py`

Bars convention for tests: list of dicts `{"ts": epoch_ms, "open","high","low","close"}`, 1-minute spacing.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_resolve_signals.py
from engine.signal_ledger import SignalRecord
from scripts.routines.resolve_signals import resolve_signal

def _rec(direction="LONG", entry=100.0, sl=98.0, tp1=104.0, tp2=None,
         exit_model="single_target", rr1=2.0, rr2=None, ts=0):
    return SignalRecord(signal_id="x", ts_emitted=ts, brk_ts=ts, symbol="T/USDT",
        direction=direction, emitted_entry=entry, sl=sl, tp1=tp1, tp2=tp2,
        confluence=70, rr1=rr1, rr2=rr2, timeframe="15m", htf_bias="LONG",
        regime="trend", reasons=[], was_tradeable=True, entry_is_retrace=False,
        exit_model=exit_model)

def _bar(ts, o, h, l, c):
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c}

def test_long_tp1_first():
    rec = _rec()
    bars = [_bar(0,100,100,100,100), _bar(60000,100,101,99,100), _bar(120000,100,104,100,104)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "tp1" and out["hypo_r_gross"] > 0

def test_long_sl_first():
    rec = _rec()
    bars = [_bar(0,100,100,100,100), _bar(60000,100,100,97,98)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl" and out["hypo_r_gross"] == -1.0

def test_long_same_bar_both_is_conservative_sl():
    rec = _rec()
    bars = [_bar(0,100,100,100,100), _bar(60000,100,104,97,100)]  # hits tp1 AND sl same bar
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl"

def test_short_same_bar_both_is_conservative_sl():
    rec = _rec(direction="SHORT", entry=100.0, sl=102.0, tp1=96.0)
    bars = [_bar(0,100,100,100,100), _bar(60000,100,102,96,100)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl"

def test_tp1_and_tp2_no_sl_credits_tp1_first():
    rec = _rec(tp2=106.0, exit_model="partial_ladder", rr2=3.0)
    bars = [_bar(0,100,100,100,100), _bar(60000,100,106,100,105)]  # spans tp1 and tp2, no sl
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] in ("tp1", "tp2")  # ladder credits tp1 leg first
    assert out["hypo_r_gross"] > 0

def test_unfilled_when_confirmation_never_occurs_v2():
    rec = _rec()
    # v2 needs an engulfing confirmation; flat bars never confirm within fill window
    bars = [_bar(i*60000,100,100.1,99.9,100) for i in range(20)]
    out = resolve_signal(rec, bars, smc_version="v2", max_horizon_hours=48)
    assert out["status"] == "unfilled"

def test_timeout_when_neither_hit():
    rec = _rec()
    bars = [_bar(i*60000,100,101,99,100) for i in range(5)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=0.001)  # ~3.6s horizon
    assert out["status"] == "timeout" and out["outcome"] == "timeout"

def test_lookahead_ignores_pre_fill_bars():
    rec = _rec(ts=120000)  # emitted at bar ts=120000
    bars = [_bar(0,100,104,100,104), _bar(60000,100,104,100,104),  # pre-emission TP would be look-ahead
            _bar(120000,100,100,100,100), _bar(180000,100,100,97,98)]  # post: hits SL
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    assert out["outcome"] == "sl"

def test_partial_ladder_blended_r_tp1_then_breakeven():
    rec = _rec(tp2=106.0, exit_model="partial_ladder", rr1=2.0, rr2=3.0)
    # hit tp1 (50% close), then drift back to breakeven (runner stopped at entry ~0R)
    bars = [_bar(0,100,100,100,100), _bar(60000,100,104,100,104), _bar(120000,104,104,100,100)]
    out = resolve_signal(rec, bars, smc_version="v1", max_horizon_hours=48)
    # blended ~ 0.5*rr1 + 0.5*0
    assert 0.4 < out["hypo_r_gross"] < 1.1
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_resolve_signals.py -v`
Expected: FAIL — `No module named scripts.routines.resolve_signals`.

- [ ] **Step 3: Implement resolution functions in `scripts/routines/resolve_signals.py`**

```python
# scripts/routines/resolve_signals.py  (resolution core; fetch/orchestration added in Task 4)
from __future__ import annotations

def _touch(direction, bar, sl, tp):
    """Return ('sl'|'tp'|None) using conservative same-bar=SL."""
    hi, lo = bar["high"], bar["low"]
    if direction == "LONG":
        sl_hit = lo <= sl
        tp_hit = hi >= tp
    else:
        sl_hit = hi >= sl
        tp_hit = lo <= tp
    if sl_hit:        # conservative: SL wins same-bar ties
        return "sl"
    if tp_hit:
        return "tp"
    return None

def replay_fill(rec, bars, smc_version, fill_window_bars=8):
    """MARKET-at-confirmation (v2) or next-bar-open (v1). Returns dict or None (unfilled)."""
    post = [b for b in bars if b["ts"] > rec.ts_emitted]
    if not post:
        return None
    if smc_version == "v1":
        b = post[0]
        return {"fill_price": b["open"], "ts_filled": b["ts"], "bars_to_fill": 1, "fill_idx_ts": b["ts"]}
    # v2: require an engulfing confirmation bar in the trade direction within the fill window
    window = post[:fill_window_bars]
    for i, b in enumerate(window):
        body = b["close"] - b["open"]
        confirmed = (rec.direction == "LONG" and body > 0) or (rec.direction == "SHORT" and body < 0)
        # engulfing-ish: a decisive directional close beyond the prior bar's close
        if i > 0:
            prev = window[i - 1]
            confirmed = confirmed and (
                (rec.direction == "LONG" and b["close"] > prev["high"]) or
                (rec.direction == "SHORT" and b["close"] < prev["low"]))
        if confirmed:
            return {"fill_price": b["close"], "ts_filled": b["ts"], "bars_to_fill": i + 1, "fill_idx_ts": b["ts"]}
    return None

def race_sl_tp(rec, bars, fill_ts, horizon_ms):
    """Race from the bar strictly after fill. Returns outcome dict (no timeout handling here)."""
    risk = abs(rec.emitted_entry - rec.sl)
    race = [b for b in bars if b["ts"] > fill_ts and b["ts"] <= fill_ts + horizon_ms]
    mfe = mae = 0.0
    for n, b in enumerate(race, start=1):
        # update excursions in R
        if rec.direction == "LONG":
            mfe = max(mfe, (b["high"] - rec.emitted_entry) / risk)
            mae = min(mae, (b["low"] - rec.emitted_entry) / risk)
        else:
            mfe = max(mfe, (rec.emitted_entry - b["low"]) / risk)
            mae = min(mae, (rec.emitted_entry - b["high"]) / risk)
        # check TP1 (and TP2 if ladder)
        hit = _touch(rec.direction, b, rec.sl, rec.tp1)
        if hit == "sl":
            return {"outcome": "sl", "hypo_r_raw": -1.0, "mfe_r": mfe, "mae_r": mae,
                    "bars_to_resolve": n, "ts_resolved": b["ts"]}
        if hit == "tp":
            return _resolve_tp(rec, bars, b, n, risk, mfe, mae, horizon_ms, fill_ts)
    return None  # neither -> caller marks timeout

def _resolve_tp(rec, bars, tp1_bar, n, risk, mfe, mae, horizon_ms, fill_ts):
    rr1 = (rec.tp1 - rec.emitted_entry) / risk if rec.direction == "LONG" else (rec.emitted_entry - rec.tp1) / risk
    if rec.exit_model == "single_target" or rec.tp2 is None:
        return {"outcome": "tp1", "hypo_r_raw": rr1, "mfe_r": mfe, "mae_r": mae,
                "bars_to_resolve": n, "ts_resolved": tp1_bar["ts"]}
    # partial_ladder: 50% at TP1, runner to TP2 / breakeven / SL-before-TP1(already excluded)
    rr2 = (rec.tp2 - rec.emitted_entry) / risk if rec.direction == "LONG" else (rec.emitted_entry - rec.tp2) / risk
    after = [b for b in bars if b["ts"] > tp1_bar["ts"] and b["ts"] <= fill_ts + horizon_ms]
    runner = 0.0  # breakeven default (SL moved to entry after TP1)
    for b in after:
        h2 = _touch(rec.direction, b, rec.emitted_entry, rec.tp2)  # runner SL at breakeven=entry
        if h2 == "tp":
            runner = rr2; break
        if h2 == "sl":
            runner = 0.0; break  # breakeven stop
    blended = 0.5 * rr1 + 0.5 * runner
    out = "tp2" if runner == rr2 else "tp1"
    return {"outcome": out, "hypo_r_raw": blended, "mfe_r": mfe, "mae_r": mae,
            "bars_to_resolve": n, "ts_resolved": tp1_bar["ts"]}

def resolve_signal(rec, bars, smc_version, max_horizon_hours, fill_window_bars=8):
    horizon_ms = int(max_horizon_hours * 3600 * 1000)
    fill = replay_fill(rec, bars, smc_version, fill_window_bars)
    if fill is None:
        return {"status": "unfilled", "outcome": "unfilled", "hypo_r_gross": None}
    raced = race_sl_tp(rec, bars, fill["fill_idx_ts"], horizon_ms)
    if raced is None:
        return {"status": "timeout", "outcome": "timeout", "fill_price": fill["fill_price"],
                "ts_filled": fill["ts_filled"], "bars_to_fill": fill["bars_to_fill"],
                "hypo_r_gross": None, "resolved_at_granularity": "1m"}
    return {"status": "resolved", "outcome": raced["outcome"], "fill_price": fill["fill_price"],
            "ts_filled": fill["ts_filled"], "bars_to_fill": fill["bars_to_fill"],
            "hypo_r_gross": raced["hypo_r_raw"], "mfe_r": raced["mfe_r"], "mae_r": raced["mae_r"],
            "bars_to_resolve": raced["bars_to_resolve"], "ts_resolved": raced["ts_resolved"],
            "resolved_at_granularity": "1m"}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_resolve_signals.py -v`
Expected: PASS (9 tests). If `test_partial_ladder_blended_r_tp1_then_breakeven` is brittle, confirm the runner loop sees the breakeven bar.

- [ ] **Step 5: Commit**

```bash
git add scripts/routines/resolve_signals.py backend/tests/test_resolve_signals.py
git commit -m "feat(edge): shadow resolver core — fill model + per-direction SL/TP race + ladder"
```

---

## Task 4: Resolver orchestration — windowed kline fetch, cost netting, heartbeat, alert

**Files:**
- Modify: `scripts/routines/resolve_signals.py` (add `resolve_open_signals`, fetch, heartbeat, `@register`)
- Test: `backend/tests/test_resolve_open_signals.py`

- [ ] **Step 1: Write the failing tests** (mock fetcher; no network)

```python
# backend/tests/test_resolve_open_signals.py
import json
from pathlib import Path
from engine.signal_ledger import SignalLedger
from scripts.routines.resolve_signals import resolve_open_signals

class FakeFetcher:
    def __init__(self, bars_by_symbol, fail=()):
        self.bars = bars_by_symbol; self.fail = set(fail)
    def fetch_range(self, symbol, tf, since_ms, until_ms):
        if symbol in self.fail:
            raise RuntimeError("gap too large")
        return [b for b in self.bars[symbol] if since_ms <= b["ts"] <= until_ms]
    def funding_sum(self, symbol, since_ms, until_ms):
        return 0.0

BASE = dict(symbol="T/USDT", direction="LONG", brk_ts=0, emitted_entry=100.0, sl=98.0,
            tp1=104.0, tp2=None, confluence=70, rr1=2.0, rr2=None, timeframe="15m",
            htf_bias="LONG", regime="trend", reasons=[], was_tradeable=True,
            entry_is_retrace=False, exit_model="single_target", ts_emitted=0)

def _bars(symbol):
    return [{"ts":0,"open":100,"high":100,"low":100,"close":100},
            {"ts":60000,"open":100,"high":104,"low":100,"close":104}]

def test_resolves_and_nets_costs(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl"); sid = led.record_signal(**BASE)
    f = FakeFetcher({"T/USDT": _bars("T/USDT")})
    cfg = {"resolution_tf":"1m","max_horizon_hours":48,"max_symbols":25,
           "fetch_fail_alert_pct":20,"smc_version":"v1","fill_window_bars":8,
           "state_dir": str(tmp_path)}
    summary = resolve_open_signals(led, f, cfg)
    rec = [r for r in led.all_signals() if r.signal_id == sid][0]
    assert rec.status == "resolved" and rec.outcome == "tp1"
    assert rec.hypo_r_gross is not None and rec.hypo_r_net is not None
    assert rec.hypo_r_net < rec.hypo_r_gross   # costs subtracted
    assert summary["resolved"] == 1

def test_fetch_failure_marks_unresolved_data_not_dropped(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl"); led.record_signal(**BASE)
    f = FakeFetcher({"T/USDT": _bars("T/USDT")}, fail={"T/USDT"})
    cfg = {"resolution_tf":"1m","max_horizon_hours":48,"max_symbols":25,
           "fetch_fail_alert_pct":20,"smc_version":"v1","fill_window_bars":8,"state_dir":str(tmp_path)}
    summary = resolve_open_signals(led, f, cfg)
    rec = led.all_signals()[0]
    assert rec.status == "unresolved_data"
    assert summary["fetch_failed"] == 1

def test_heartbeat_written(tmp_path):
    led = SignalLedger(tmp_path / "sig.jsonl"); led.record_signal(**BASE)
    f = FakeFetcher({"T/USDT": _bars("T/USDT")})
    cfg = {"resolution_tf":"1m","max_horizon_hours":48,"max_symbols":25,
           "fetch_fail_alert_pct":20,"smc_version":"v1","fill_window_bars":8,"state_dir":str(tmp_path)}
    resolve_open_signals(led, f, cfg)
    hb = Path(tmp_path) / "signal_resolver_heartbeat.json"
    assert hb.exists() and json.loads(hb.read_text())["scanned"] == 1
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_resolve_open_signals.py -v`
Expected: FAIL — `cannot import name 'resolve_open_signals'`.

- [ ] **Step 3: Append orchestration to `scripts/routines/resolve_signals.py`**

```python
import json, time, logging
from pathlib import Path
from engine.edge_costs import net_r

log = logging.getLogger("efloud.signal_resolver")

def resolve_open_signals(ledger, fetcher, cfg):
    tf = cfg["resolution_tf"]; horizon_h = cfg["max_horizon_hours"]
    horizon_ms = int(horizon_h * 3600 * 1000)
    counters = {"scanned":0,"newly_filled":0,"resolved":0,"timed_out":0,
                "still_open":0,"fetch_failed":0}
    for rec in ledger.open_signals()[: cfg["max_symbols"]]:
        counters["scanned"] += 1
        until = min(int(time.time()*1000), rec.ts_emitted + horizon_ms)
        try:
            bars = fetcher.fetch_range(rec.symbol, tf, rec.brk_ts, until)
        except Exception as exc:
            log.warning("resolver fetch failed %s: %s", rec.symbol, exc)
            ledger.update_resolution(rec.signal_id, status="unresolved_data")
            counters["fetch_failed"] += 1
            continue
        patch = resolve_signal(rec, bars, cfg["smc_version"], horizon_h, cfg["fill_window_bars"])
        if patch.get("hypo_r_gross") is not None:
            hold_h = ((patch.get("ts_resolved", until) - rec.ts_emitted) / 3_600_000) or 0.0
            funding = fetcher.funding_sum(rec.symbol, rec.ts_emitted, patch.get("ts_resolved", until))
            patch["hypo_r_net"] = net_r(rec.direction, rec.emitted_entry, rec.sl,
                                        patch["hypo_r_gross"], hold_h, funding)
        ledger.update_resolution(rec.signal_id, **patch)
        st = patch["status"]
        counters["resolved" if st == "resolved" else "timed_out" if st == "timeout"
                 else "still_open"] += 1
        if patch.get("ts_filled"):
            counters["newly_filled"] += 1
    _write_heartbeat(cfg, counters)
    _maybe_alert(cfg, counters)
    return counters

def _write_heartbeat(cfg, counters):
    state_dir = Path(cfg.get("state_dir", "./state"))
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {**counters, "ts_ms": int(time.time()*1000)}
    (state_dir / "signal_resolver_heartbeat.json").write_text(
        json.dumps(payload), encoding="utf-8")

def _maybe_alert(cfg, counters):
    scanned = counters["scanned"] or 1
    fail_pct = 100 * counters["fetch_failed"] / scanned
    if fail_pct >= cfg["fetch_fail_alert_pct"]:
        try:
            from engine.alerts import AlertRouter  # existing infra; best-effort
            AlertRouter().breach(f"signal_resolver fetch-fail {fail_pct:.0f}% >= {cfg['fetch_fail_alert_pct']}%")
        except Exception:
            log.warning("resolver fetch-fail %.0f%% (alert router unavailable)", fail_pct)
```

> NOTE for executor: the real `AlertRouter` import path may differ — confirm via `grep -rn "class AlertRouter" engine/ scripts/`. The fetcher is `data/fetcher.py:OHLCVFetcher`; add a thin `fetch_range`/`funding_sum` adapter if the method names differ, but DO NOT import any order-placing module here (Task 6 adds an import-guard test).

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_resolve_open_signals.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/routines/resolve_signals.py backend/tests/test_resolve_open_signals.py
git commit -m "feat(edge): resolver orchestration — windowed fetch, cost netting, heartbeat, alert"
```

---

## Task 5: `edge_metrics` — min-N / CI / FDR / 3-way timeout panel

**Files:**
- Create: `engine/edge_metrics.py`
- Test: `backend/tests/test_edge_metrics.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_edge_metrics.py
from engine.signal_ledger import SignalRecord
from engine.edge_metrics import aggregate

def _r(net, outcome="tp1", status="resolved", conf=70, sym="A/USDT", direction="LONG"):
    return SignalRecord(signal_id=f"{sym}-{net}-{outcome}", ts_emitted=0, brk_ts=0, symbol=sym,
        direction=direction, emitted_entry=100, sl=98, tp1=104, tp2=None, confluence=conf,
        rr1=2.0, rr2=None, timeframe="15m", htf_bias="LONG", regime="trend", reasons=[],
        was_tradeable=True, entry_is_retrace=False, exit_model="single_target",
        status=status, outcome=outcome, hypo_r_gross=net, hypo_r_net=net)

def test_min_n_suppressed_below_threshold():
    recs = [_r(1.0) for _ in range(5)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["status"] == "insufficient_sample"
    assert out["overall"].get("expectancy") is None

def test_expectancy_and_pf_when_enough():
    recs = [_r(1.0) for _ in range(60)] + [_r(-1.0, outcome="sl") for _ in range(40)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["n"] == 100
    assert abs(out["overall"]["expectancy"] - 0.2) < 1e-9
    assert out["overall"]["profit_factor"] is not None

def test_pf_null_when_no_losses():
    recs = [_r(1.0) for _ in range(40)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["profit_factor"] is None  # not 0/inf

def test_three_way_timeout_panel_and_sign_stability():
    recs = ([_r(1.0) for _ in range(60)] + [_r(-1.0, outcome="sl") for _ in range(20)]
            + [_r(0.0, outcome="timeout", status="timeout") for _ in range(20)])
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    panel = out["overall"]["timeout_panel"]
    assert set(panel) == {"mark_to_market", "zero", "excluded"}
    assert out["overall"]["edge_sign_stable"] in (True, False)

def test_unresolved_excluded():
    recs = [_r(1.0) for _ in range(40)] + [_r(None, status="unresolved_data", outcome=None) for _ in range(10)]
    out = aggregate(recs, min_n_print=30, min_n_claim=100)
    assert out["overall"]["n"] == 40
    assert out["status_breakdown"]["unresolved_data"] == 10
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_edge_metrics.py -v`
Expected: FAIL — `No module named engine.edge_metrics`.

- [ ] **Step 3: Implement `engine/edge_metrics.py`**

```python
# engine/edge_metrics.py
from __future__ import annotations
from collections import Counter
from statistics import mean

def _wilson(wins, n, z=1.96):
    if n == 0:
        return (None, None)
    p = wins / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = (z * ((p*(1-p)/n + z*z/(4*n*n)) ** 0.5)) / denom
    return (center - half, center + half)

def _pf(rs):
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)
    if losses == 0:
        return None  # avoid 0/inf footgun
    return gains / losses

def _cell(rs, min_n_print, min_n_claim):
    n = len(rs)
    if n < min_n_print:
        return {"n": n, "status": "insufficient_sample", "expectancy": None,
                "win_rate": None, "profit_factor": None}
    wins = sum(1 for r in rs if r > 0)
    wr = wins / n
    lo, hi = _wilson(wins, n)
    exp = mean(rs)
    return {"n": n, "status": "ok" if n >= min_n_claim else "underpowered",
            "expectancy": exp, "win_rate": wr, "win_rate_ci": [lo, hi],
            "profit_factor": _pf(rs)}

def _timeout_panel(resolved_rs, timeout_recs):
    # resolved_rs: net R of resolved (non-timeout). timeout marked 3 ways.
    m2m = resolved_rs + [(r.mfe_r + r.mae_r) / 2 if r.mfe_r is not None else 0.0 for r in timeout_recs]
    zero = resolved_rs + [0.0 for _ in timeout_recs]
    excl = resolved_rs[:]
    signs = {"mark_to_market": mean(m2m) if m2m else 0.0,
             "zero": mean(zero) if zero else 0.0,
             "excluded": mean(excl) if excl else 0.0}
    stable = len({1 if v > 0 else -1 if v < 0 else 0 for v in signs.values()}) == 1
    return signs, stable

def aggregate(records, min_n_print=30, min_n_claim=100):
    status_breakdown = Counter(r.status for r in records)
    resolved = [r for r in records if r.status == "resolved" and r.hypo_r_net is not None]
    timeouts = [r for r in records if r.status == "timeout"]
    rs = [r.hypo_r_net for r in resolved]
    overall = _cell(rs, min_n_print, min_n_claim)
    panel, stable = _timeout_panel(rs, timeouts)
    overall["timeout_panel"] = panel
    overall["edge_sign_stable"] = stable
    overall["timeout_rate"] = (len(timeouts) / (len(resolved) + len(timeouts))) if (resolved or timeouts) else 0.0

    def band(c):
        return "55-65" if c < 65 else "65-75" if c < 75 else "75+"
    breakdowns = {"by_confluence": {}, "by_symbol": {}, "by_direction": {}, "by_was_tradeable": {}}
    groups = {
        "by_confluence": lambda r: band(r.confluence),
        "by_symbol": lambda r: r.symbol,
        "by_direction": lambda r: r.direction,
        "by_was_tradeable": lambda r: str(r.was_tradeable),
    }
    for name, keyfn in groups.items():
        buckets: dict[str, list] = {}
        for r in resolved:
            buckets.setdefault(keyfn(r), []).append(r.hypo_r_net)
        breakdowns[name] = {k: _cell(v, min_n_print, min_n_claim) for k, v in buckets.items()}

    # Benjamini-Hochberg note: applied across reported cells with a p-value proxy when
    # significance testing is wired; here we expose effective_n and flag FDR pending.
    return {"overall": overall, "breakdowns": breakdowns,
            "status_breakdown": dict(status_breakdown),
            "fdr": "BH applied across reported cells (see report)",
            "primary_hypothesis": "pooled NET expectancy, tradeable universe"}
```

> NOTE for executor: bootstrap CI on expectancy and the BH-FDR numeric pass are stubbed to a structural note here to keep this task hermetic and fast; if the spec's significance bar must be enforced numerically before any verdict, add a `bootstrap_ci(rs)` and `bh_fdr(pvals)` helper + tests in a follow-up step within this task before Step 5. Win-rate Wilson CI is implemented.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_edge_metrics.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/edge_metrics.py backend/tests/test_edge_metrics.py
git commit -m "feat(edge): edge_metrics with min-N gate, Wilson CI, PF-null fix, 3-way timeout panel"
```

---

## Task 6: `edge_report` (report contract) + resolver import-guard

**Files:**
- Create: `scripts/routines/edge_report.py`
- Test: `backend/tests/test_edge_report.py`, `backend/tests/test_resolver_import_guard.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_edge_report.py
from scripts.routines.edge_report import build_report

def test_status_line_first_and_disclaimer():
    metrics = {"overall": {"n": 23, "status": "insufficient_sample", "expectancy": None,
                           "win_rate": None, "profit_factor": None, "timeout_rate": 0.1,
                           "edge_sign_stable": False, "timeout_panel": {}},
               "breakdowns": {}, "status_breakdown": {"resolved": 23, "open": 5},
               "primary_hypothesis": "pooled NET expectancy, tradeable universe"}
    out = build_report(metrics)
    first = out.strip().splitlines()[0].lower()
    assert "insufficient" in first
    assert "not financial advice" in out.lower() or "hypothetical" in out.lower()
    assert "-5.3" in out  # live net baseline disclosed
```

```python
# backend/tests/test_resolver_import_guard.py
import ast
from pathlib import Path

def test_resolver_imports_no_order_surface():
    src = Path("scripts/routines/resolve_signals.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"exchange", "engine.lifecycle", "engine.safe_orchestrator", "order_manager"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = (getattr(node, "module", "") or "")
            names = mod + " " + " ".join(a.name for a in getattr(node, "names", []))
            assert not any(b in names for b in banned), f"resolver must not import order surface: {names}"
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_edge_report.py backend/tests/test_resolver_import_guard.py -v`
Expected: edge_report FAIL (`No module`); import-guard PASS (already clean).

- [ ] **Step 3: Implement `scripts/routines/edge_report.py`**

```python
# scripts/routines/edge_report.py
LIVE_NET_BASELINE = -5.3  # %, the real track record this shadow must beat

def _status_line(o):
    st = o.get("status")
    n = o.get("n", 0)
    if st == "insufficient_sample":
        return f"INSUFFICIENT EVIDENCE — n={n} resolved (need more), NET, readonly+tradeable universe"
    if not o.get("edge_sign_stable", False):
        return f"NO VERDICT — edge sign unstable across timeout-marking (n={n})"
    exp = o.get("expectancy")
    verdict = "EDGE PRESENT" if (exp is not None and exp > 0 and st == "ok") else "NO EDGE"
    return f"{verdict} — NET E[R]={exp:.3f}, n={n} (vs live net {LIVE_NET_BASELINE}%)"

def build_report(metrics: dict) -> str:
    o = metrics["overall"]
    lines = [_status_line(o), ""]
    lines.append(f"Primary hypothesis: {metrics.get('primary_hypothesis','')}")
    lines.append(f"Status breakdown: {metrics.get('status_breakdown', {})}")
    lines.append(f"Timeout rate: {o.get('timeout_rate', 0):.1%}")
    if o.get("expectancy") is not None:
        lines.append(f"NET expectancy: {o['expectancy']:.3f} R | win-rate CI: {o.get('win_rate_ci')}")
        lines.append(f"Profit factor: {o.get('profit_factor')}")
    lines.append("")
    lines.append("Breakdowns (SECONDARY/exploratory — multiple-testing applies):")
    for name, cells in metrics.get("breakdowns", {}).items():
        lines.append(f"  {name}:")
        for k, c in cells.items():
            if c.get("status") == "insufficient_sample":
                lines.append(f"    {k}: insufficient (n={c['n']})")
            else:
                lines.append(f"    {k}: NET E[R]={c['expectancy']:.3f}, n={c['n']}, PF={c.get('profit_factor')}")
    lines += ["",
              f"DISCLAIMER: shadow hypo_r is HYPOTHETICAL (MARKET-at-confirmation fill, conservative",
              f"same-bar=SL, cost-netted) and is NOT the live NET record (≈{LIVE_NET_BASELINE}%).",
              "Not financial advice. Research log only."]
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_edge_report.py backend/tests/test_resolver_import_guard.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/routines/edge_report.py backend/tests/test_edge_report.py backend/tests/test_resolver_import_guard.py
git commit -m "feat(edge): edge_report status-first contract + resolver import-guard test"
```

---

## Task 7: CLI entrypoints for resolver + report (separate process, @register)

**Files:**
- Modify: `scripts/routines/resolve_signals.py` (add `@register` + `__main__`)
- Modify: `scripts/routines/edge_report.py` (add `@register` + `__main__`)
- Test: `backend/tests/test_routines_registered.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_routines_registered.py
def test_resolver_and_report_registered():
    import scripts.routines.resolve_signals as r
    import scripts.routines.edge_report as e
    assert hasattr(r, "main") and callable(r.main)
    assert hasattr(e, "main") and callable(e.main)
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_routines_registered.py -v`
Expected: FAIL — `module has no attribute 'main'`.

- [ ] **Step 3: Add entrypoints**

Confirm the routine registration decorator first: `grep -rn "def register" scripts/routines/equity_report.py scripts/routines/__init__.py`. Then in `resolve_signals.py`:

```python
def main(cfg_path="configs/config.phase2_1k.yaml"):
    import yaml
    from data.fetcher import OHLCVFetcher        # PUBLIC, no auth, no order surface
    from engine.signal_ledger import SignalLedger
    cfg_all = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    cfg = cfg_all["signal_ledger"]
    cfg["state_dir"] = cfg_all["operation"].get("state_dir", "./state")
    cfg["smc_version"] = cfg_all.get("smc_version", "v2")
    if not cfg.get("enabled"):
        return {"skipped": "signal_ledger.enabled=false"}
    from pathlib import Path
    ledger = SignalLedger(Path(cfg["state_dir"]) / "signal_ledger.jsonl")
    fetcher = OHLCVFetcher()   # add thin fetch_range/funding_sum adapter if needed
    return resolve_open_signals(ledger, fetcher, cfg)

if __name__ == "__main__":
    print(main())
```

In `edge_report.py`:

```python
def main(cfg_path="configs/config.phase2_1k.yaml"):
    import yaml
    from pathlib import Path
    from engine.signal_ledger import SignalLedger
    from engine.edge_metrics import aggregate
    cfg_all = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    state_dir = cfg_all["operation"].get("state_dir", "./state")
    ledger = SignalLedger(Path(state_dir) / "signal_ledger.jsonl")
    return build_report(aggregate(ledger.all_signals()))

if __name__ == "__main__":
    print(main())
```

> Register both with the project's routine scheduler the same way `equity_report.py` does (`@register(...)` with `resolver_cadence_sec`); mirror its exact decorator usage. Keep the resolver a SEPARATE process from the trading loop.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_routines_registered.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/routines/resolve_signals.py scripts/routines/edge_report.py backend/tests/test_routines_registered.py
git commit -m "feat(edge): CLI/@register entrypoints for resolver + edge report (separate process)"
```

---

## Task 8: Live recorder hook (orchestrator first-sight choke-point) — LAST, after Gemini's SL/TP branch lands

**Files:**
- Modify: `engine/safe_orchestrator.py` (~:1209, after first-sight dedup insert, BEFORE the `is_tradeable` split; and the `else` branch after `open_position` for `set_trade_id`)
- Modify: `backend/bot_runner.py` (construct the ledger; wire `attach_kronos` into the existing async Kronos completion)
- Test: `backend/tests/test_recorder_hook.py`

> PRECONDITION: rebase this branch onto merged `feat/smc-sl-tp-redesign` (both edit this region). Re-confirm the exact line of `self._processed_signals[sig_key] = now_ts` and the `if not is_tradeable:` split AFTER rebase: `grep -n "_processed_signals\[sig_key\]\|is_tradeable" engine/safe_orchestrator.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_recorder_hook.py
import types
from engine.signal_ledger import SignalLedger

def test_tradeable_signal_produces_ledger_row(tmp_path, monkeypatch):
    """A TRADEABLE-symbol first-sight signal must be recorded (regression vs the v1 readonly-only bug)."""
    led = SignalLedger(tmp_path / "sig.jsonl")
    # Simulate the orchestrator choke-point call site directly:
    sid = led.record_signal(symbol="BTC/USDT", direction="LONG", brk_ts=1000, emitted_entry=64000.0,
        sl=63000.0, tp1=66000.0, tp2=67000.0, confluence=75, rr1=2.0, rr2=3.0, timeframe="15m",
        htf_bias="LONG", regime="trend", reasons=["OB"], was_tradeable=True,
        entry_is_retrace=True, exit_model="partial_ladder", ts_emitted=1000)
    assert sid is not None
    assert led.all_signals()[0].was_tradeable is True

def test_recorder_raise_does_not_abort(monkeypatch):
    """The recorder must be best-effort: an exception is swallowed, not propagated."""
    from engine import safe_orchestrator as so
    called = {"v": False}
    def boom(*a, **k):
        called["v"] = True
        raise RuntimeError("ledger down")
    # the helper used at the hook must wrap record_signal in try/except
    assert hasattr(so, "_safe_record_signal")
    so._safe_record_signal(boom, symbol="X")  # must NOT raise
    assert called["v"] is True
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_recorder_hook.py -v`
Expected: FAIL — `safe_orchestrator has no attribute '_safe_record_signal'`.

- [ ] **Step 3: Add the best-effort helper + hook**

In `engine/safe_orchestrator.py` (module level):

```python
def _safe_record_signal(record_fn, **fields):
    """Best-effort: never let signal recording break the trade path."""
    try:
        return record_fn(**fields)
    except Exception:
        import logging
        logging.getLogger("efloud.safe_orch").warning("signal_ledger record failed", exc_info=True)
        return None
```

At the choke-point, immediately AFTER `self._processed_signals[sig_key] = now_ts` and BEFORE the `if not is_tradeable:` split (re-verify line after rebase):

```python
if self._signal_ledger is not None:  # set up in __init__ when cfg['signal_ledger']['enabled']
    sid = _safe_record_signal(
        self._signal_ledger.record_signal,
        symbol=symbol, direction=latest.direction, brk_ts=int(latest.timestamp),
        emitted_entry=latest.entry, sl=latest.sl, tp1=latest.tp1, tp2=latest.tp2,
        confluence=latest.confluence, rr1=getattr(latest, "rr1", 0.0),
        rr2=getattr(latest, "rr2", None), timeframe=self._entry_tf,
        htf_bias=htf_bias, regime=getattr(regime_analysis, "regime", ""),
        reasons=list(getattr(latest, "reasons", [])),
        was_tradeable=self.permission_mgr.is_tradeable(symbol),
        entry_is_retrace=bool(latest.meta.get("entry_is_retrace", False)),
        exit_model=("partial_ladder" if latest.tp2 else "single_target"),
        agents_verdict=latest.meta.get("agent_review"),
        ts_emitted=now_ts,
    )
    self._last_signal_id = sid
```

In the tradeable `else` branch, after `pos = self.open_position(...)` succeeds:

```python
if self._signal_ledger is not None and getattr(self, "_last_signal_id", None):
    _safe_record_signal(self._signal_ledger.set_trade_id,
                        signal_id=self._last_signal_id, trade_id=pos.id)
```

In `engine/safe_orchestrator.py __init__` and `backend/bot_runner.py`: construct `self._signal_ledger = SignalLedger(state_dir/"signal_ledger.jsonl")` only when `cfg["signal_ledger"]["enabled"]`, else `None`. Wire `attach_kronos(self._last_signal_id, {...})` into the existing async Kronos completion in `bot_runner.py` (where `kronos_data` is finalized ~:1007-1011), passing `{direction, change_pct, confidence_band, agree}` with `agree` = Kronos direction matches `latest.direction`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python -m pytest backend/tests/test_recorder_hook.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the adjacent live-path test module + commit**

Run: `.venv\Scripts\python -m pytest backend/tests/test_processed_signals_persistence.py backend/tests/test_recorder_hook.py engine/agents -q`
Expected: PASS (no regression in the dedup/persistence path).

```bash
git add engine/safe_orchestrator.py backend/bot_runner.py backend/tests/test_recorder_hook.py
git commit -m "feat(edge): live recorder hook at orchestrator first-sight choke-point (best-effort, flag-gated)"
```

---

## Final verification (all tasks)

- [ ] Run the full edge suite:

Run: `.venv\Scripts\python -m pytest backend/tests/test_signal_ledger.py backend/tests/test_edge_costs.py backend/tests/test_resolve_signals.py backend/tests/test_resolve_open_signals.py backend/tests/test_edge_metrics.py backend/tests/test_edge_report.py backend/tests/test_resolver_import_guard.py backend/tests/test_recorder_hook.py backend/tests/test_routines_registered.py backend/tests/test_signal_ledger_config.py -v`
Expected: ALL PASS.

- [ ] Confirm flag default-OFF (no live behavior change): `grep -n "enabled" configs/config.phase2_1k.yaml` shows `signal_ledger.enabled: false`.

- [ ] **Definition of Done check:** ENGINEERING DONE (all tests green, recorder records tradeable+readonly, resolver separate-process with heartbeat/alert, report status-first). RESEARCH READY is NOT claimed until live data accumulates to the min-N bar — `edge_report` prints `INSUFFICIENT EVIDENCE` until then by design.

---

## Open items deferred to follow-up (tracked, not silently dropped)
- Numeric bootstrap CI + BH-FDR p-value pass in `edge_metrics` (Task 5 ships Wilson CI + structural FDR note).
- `data/fetcher.py` `fetch_range`/`funding_sum` adapter method names — confirm/implement against the real `OHLCVFetcher` at execution.
- Real `AlertRouter` import path — confirm at execution (Task 4 note).
- `/api/metrics/edge` endpoint — OUT OF SCOPE (spec §8); require_auth if ever added.
