# SMC Entry/SL/TP Rework + Sibling Order Cleanup — Design Spec

**Status:** Draft — pending review
**Date:** 2026-05-23
**Author:** Claude (with Utku)
**Branch:** `feat/smc-v2-spec`
**Related code paths:**
- `engine/signals.py` (current v1 entry/SL/TP logic, line 89, 268-353)
- `engine/smc.py` (SMC indicators)
- `engine/lifecycle.py:58` (`Position` dataclass)
- `exchange/__init__.py:200, 346, 380, 659-668, 686-710, 830-848` (OrderManager + reconcile loop)
- `engine/safe_orchestrator.py:407, 730-792` (orchestrator + reverse handler)
- `engine/safety/position_guard.py:296-309, 322` (SL clamp + reverse guard)
- `config.yaml:60-160` (timeframes, risk, safety blocks)
- `backend/db.py:60-150` (trades schema)

---

## 1. Problem Statement

Live bot (production at master `d03857c`, Hetzner VPS, RUNNING) is producing trades where:

1. **Risk-reward (RR) is disproportionate** — recent ETH SHORT had SL distance far larger than TP1 distance, RR well below user expectations.
2. **SMC entry doctrine is violated** — user expects "after a break, wait for retrace into the FVG, confirm on lower TF, then enter; SL on the opposite side of the structure." Bot instead enters at the break candle close (market) with no pullback wait and no LTF confirmation.
3. **Liquidity pools (equal highs/lows) are ignored** — `engine/smc.py:285` computes `equal_levels()` but nothing in `signals.py` consumes them. Stop-hunts target liquidity; ignoring liquidity means TP1 misses the obvious target.
4. **Stop-loss has no buffer** — `signals.py:276/288` places SL exactly at the previous swing point, with no ATR buffer despite `risk.sl_atr_buffer: 0.5` existing in config (dead key, never read).
5. **Sibling reduceOnly orders are not cancelled on full close** — when the reconcile loop detects a position closed on exchange (size → 0), it removes the local Position but does NOT cancel the orphan SL/TP reduceOnly orders. They persist on Binance "Open Orders" indefinitely. This is a separate but related bug surfaced in the same session.

User wants a **full SMC rework** of entry, SL, and TP logic, and a clean fix for the orphan-order bug.

---

## 2. Goals

### 2.1 SMC v2 Engine (rework)

- **Entry**: pullback to HTF FVG (priority 1) or OTE band (priority 2, fallback), with LTF (15m) CHoCH/OB-tap confirmation inside the zone.
- **Stop loss**: structural — on the far side of the entry zone or HTF swing anchor, plus `0.5 × ATR(15m)` buffer; clamped within `[min_sl_atr, max_sl_atr]` ATR multiples. If structural SL exceeds `max_sl_atr × ATR`, **reject the setup** (no clamping to avoid invalidating SMC structure).
- **TP1**: nearest sweep-able liquidity (equal highs/lows cluster, swing extremum) — fallback to nearest counter-direction HTF FVG near edge. If the nearest liquidity is closer than `min_rr × risk`, **reject the setup** (don't fabricate a far target).
- **TP2**: HTF FVG far edge (gap-fill). Fallback: `fib_ext × risk` projection. Invariant: TP2 must be strictly further from entry than TP1 — if no valid TP2 exists, position becomes single-target (TP1 = full close, no 50/50 split).
- **Pullback timeout**: 8 bars on 15m (≈ 2 hours). After 8 bars without zone entry, the setup expires.
- **Setup state machine**: `AWAITING_PULLBACK → IN_ZONE → CONFIRMED → ENTERED` (or `EXPIRED`).
- **Stateful tracking**: SetupCandidate objects persisted to `./state/setup_candidates.json` to survive bot restart.

### 2.2 Sibling Order Cleanup Fix

- When position fully closes (detected via reconcile loop: `exchange/__init__.py:659-668`), **all sibling reduceOnly orders for that symbol must be cancelled** before removing the position from local state.
- Behaviour must match the existing `_fallback_close` pattern (`exchange/__init__.py:842-848`) which already cancels all three sibling IDs correctly.
- DRY refactor: extract `_cancel_position_siblings(pos, ccxt_sym, reason)` helper, call from reconcile + `_fallback_close` (replacing inline loop).

### 2.3 Non-Goals

- **3-tier TP ladder (TP1+TP2+TP3)** — explicitly deferred; current `lifecycle.Position` only supports TP1+TP2 and changing dataclass shape requires JSON migration + reconcile rewrite. Revisit after live track record exists.
- **Multi-broker forex adapter** — out of scope (see `CLAUDE.md §8`).
- **v1 algorithm removal** — v1 stays as a fallback code path behind feature flag. Removal is a separate post-rollout PR.
- **Auto-rollback on losing streak** — rollback is a manual config flag flip (operator decision). Automated rollback can be a later enhancement.

---

## 3. Top-Level Architecture

```
            ┌───────────────────────────────┐
            │  HTF (4h+1h) Bias + FVG/OB    │
            │  - htf_bias                   │
            │  - unmitigated FVG zones      │
            │  - liquidity pools (eq H/L)   │
            └───────────────┬───────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │  LTF (15m) CHoCH/BoS trigger  │
            │  → SetupCandidate emitted     │
            │  → state: AWAITING_PULLBACK   │
            └───────────────┬───────────────┘
                            │
                ┌───────────┴───────────────┐
                ▼                           ▼
       ┌─────────────────┐         ┌─────────────────┐
       │ Pullback to     │   OR    │ Pullback to     │
       │ HTF FVG zone    │         │ OTE (0.618-     │
       │ (priority 1)    │         │  0.786) zone    │
       │                 │         │ (priority 2)    │
       └────────┬────────┘         └────────┬────────┘
                │                           │
                └───────────┬───────────────┘
                            ▼
            ┌───────────────────────────────┐
            │  15m CHoCH/OB-tap confirmation│
            │  inside the zone              │
            │  → state: IN_ZONE → CONFIRMED │
            └───────────────┬───────────────┘
                            │
                ┌───────────┴───────────────────┐
                ▼               (8-bar timeout) ▼
           ENTRY MARKET                    EXPIRED
                │
                ▼
       ┌────────────────────────────┐
       │ SL = structural opp. side  │
       │   + 0.5 ATR(15m) buffer    │
       │   clamped to [min_sl_atr,  │
       │     max_sl_atr]            │
       │   if > max → REJECT        │
       │                            │
       │ TP1 = nearest sweep-able   │
       │   liquidity (eq H/L,       │
       │   swing cluster) ELSE      │
       │   HTF FVG near edge        │
       │   if RR<min_rr → REJECT    │
       │                            │
       │ TP2 = HTF FVG far edge     │
       │   ELSE fib_ext 1.618       │
       │   if TP2 ≤ TP1 → no TP2,   │
       │     TP1 becomes full close │
       └────────────────────────────┘
```

### v1 vs v2 diff table

| Concern | v1 (current) | v2 (proposed) |
|---|---|---|
| Entry timing | CHoCH break candle (immediate market) | CHoCH → wait pullback → LTF confirmation → market |
| Entry zone | None (break price) | HTF FVG (priority) or OTE 0.618-0.786 (fallback) |
| Confirmation | None | 15m CHoCH/OB-tap inside the zone |
| SL source | Previous LTF swing, no buffer | Structural opp. side + 0.5 ATR buffer, ATR-clamped |
| SL fallback | `price × 0.99` (LONG) / `× 1.01` (SHORT) | None — reject setup if no structural anchor |
| TP1 source | "Nearest HTF target beyond min_rr × risk" (forced beyond floor) | "Nearest liquidity OR FVG near edge that satisfies min_rr" |
| TP2 source | `fib_ext × risk` (fixed) | HTF FVG far edge, fallback fib_ext |
| TP2 < TP1 anomaly | Possible (not checked) | Invariant enforced; if no valid TP2, single-target mode |
| Rejection reasons | confluence_low, RR<min_rr, TP wrong side | + pullback_timeout, + no_confirmation, + sl_too_far, + tp1_too_close, + tp2_invalid |
| State model | Stateless (each bar recomputed) | Stateful: pending SetupCandidates persisted to disk |
| Liquidity (equal H/L) | Not consumed by SL/TP | Primary TP1 source |

---

## 4. Component Design (smc_v2 package)

### 4.1 New files

#### `engine/smc_v2/__init__.py`
Package entry point. Exports `generate_signals_v2(df_d, df_4h, df_1h, df_15m, *, config, symbol, state) -> list[Signal]`. Orchestrates the three phases: trigger detection → pullback wait → confirmation+entry calculation.

#### `engine/smc_v2/setup_state.py`
```python
from dataclasses import dataclass, asdict
from typing import Literal

@dataclass
class ZoneSpec:
    low: float
    high: float
    source: Literal["HTF_FVG", "OTE"]

@dataclass
class SetupCandidate:
    symbol: str
    direction: Literal["LONG", "SHORT"]
    trigger_bar_ts: int             # CHoCH bar timestamp (ms)
    trigger_price: float            # break price at CHoCH
    htf_bias: str                   # "BULL" | "BEAR" | "UNDEF"
    target_zone: ZoneSpec
    htf_swing_anchor: float         # HTF swing on the "wrong side" for structural SL
    bars_waited: int                # incremented per orchestrator tick
    state: Literal["AWAITING_PULLBACK", "IN_ZONE", "CONFIRMED", "EXPIRED"]
    confluence_score: int
    reasons: list[str]
```

Persistence: `./state/setup_candidates.json` (atomic write via `tempfile + os.replace`, mirrors `positions.json` pattern at `exchange/__init__.py:283`). Schema versioned (`{"version": 1, "candidates": [...]}`). On load failure (corruption, schema mismatch), log warning and start empty (graceful degradation).

#### `engine/smc_v2/zones.py`
Pure functions, no I/O.

```python
def build_pullback_zones(
    htf_fvgs: list[FVG],
    ote_band: tuple[float, float],   # (low, high) of OTE 0.618-0.786 band
    direction: str,
    trigger_price: float,
) -> ZoneSpec:
    # Priority 1: nearest unmitigated HTF FVG in pullback direction
    if direction == "SHORT":
        candidates = [f for f in htf_fvgs if f.direction == "BULL" and f.bot > trigger_price]
        if candidates:
            nearest = min(candidates, key=lambda f: f.bot - trigger_price)
            return ZoneSpec(low=nearest.bot, high=nearest.top, source="HTF_FVG")
    else:  # LONG — mirror
        candidates = [f for f in htf_fvgs if f.direction == "BEAR" and f.top < trigger_price]
        if candidates:
            nearest = max(candidates, key=lambda f: f.top - trigger_price)
            return ZoneSpec(low=nearest.bot, high=nearest.top, source="HTF_FVG")
    # Priority 2: OTE band
    return ZoneSpec(low=ote_band[0], high=ote_band[1], source="OTE")

def is_price_in_zone(price: float, zone: ZoneSpec) -> bool:
    return zone.low <= price <= zone.high
```

#### `engine/smc_v2/confirmation.py`
Pure function over `df_15m`.

```python
def confirm_entry(
    df_15m: pd.DataFrame,
    zone: ZoneSpec,
    direction: str,
    since_ts: int,
) -> tuple[bool, float | None]:
    """
    Look at bars since `since_ts` that are inside `zone`.
    Return (True, entry_price) if a counter-direction CHoCH or OB-tap with
    body-engulf confirms the entry; else (False, None).
    """
```

Confirmation rules (initial):
- For SHORT setup: look for 15m bearish engulfing candle that closes within the zone, OR a 15m CHoCH break of the most recent micro swing low formed inside the zone.
- For LONG setup: mirror (bullish engulfing close inside zone, or 15m CHoCH break of micro swing high).

If multiple confirmations are present, take the first. Entry price = close of confirming bar.

#### `engine/smc_v2/sl_calc.py`
```python
class SLTooFarError(ValueError):
    """Raised when structural SL exceeds max_sl_atr × ATR — setup must be rejected."""

def calc_sl(
    direction: str,
    entry_price: float,
    zone: ZoneSpec,
    htf_swing_anchor: float,
    atr_15m: float,
    config: SafetyConfig,
) -> float:
    buffer = config.sl_atr_buffer * atr_15m
    if direction == "LONG":
        structural_sl = min(zone.low, htf_swing_anchor) - buffer
    else:
        structural_sl = max(zone.high, htf_swing_anchor) + buffer

    stop_dist = abs(entry_price - structural_sl)
    min_dist = config.min_sl_atr * atr_15m
    max_dist = config.max_sl_atr * atr_15m

    if stop_dist < min_dist:
        # Stop too tight — widen to ATR floor
        return entry_price - min_dist if direction == "LONG" else entry_price + min_dist
    if stop_dist > max_dist:
        raise SLTooFarError(stop_dist=stop_dist, max_dist=max_dist)
    return structural_sl
```

Note: `sl_atr_buffer`, `min_sl_atr`, `max_sl_atr` already exist in `config.yaml:91, 133, 134` — currently unused in `signals.py` (dead keys). v2 activates them.

#### `engine/smc_v2/tp_calc.py`
```python
class InsufficientTPDistanceError(ValueError):
    """Raised when nearest liquidity is closer than min_rr × risk — setup must be rejected."""

def calc_tp_targets(
    direction: str,
    entry_price: float,
    sl_price: float,
    htf_swings: dict,            # {"swing_highs": [...], "swing_lows": [...]}
    htf_fvgs: list[FVG],         # unmitigated
    eq_levels: list[EqLevel],    # equal highs/lows
    config: RiskConfig,
) -> tuple[float, float | None, dict]:
    risk = abs(entry_price - sl_price)
    min_rr = config.min_rr

    if direction == "LONG":
        # Liquidity above entry, in ascending order
        liq = [e.price for e in eq_levels if e.kind == "EQH" and e.price > entry_price]
        liq += [s.price for s in htf_swings["swing_highs"] if s.price > entry_price]
        fvg_near = [f.bot for f in htf_fvgs if f.direction == "BEAR" and f.bot > entry_price]
        candidates = sorted(set(liq + fvg_near))
        tp1 = next((p for p in candidates if (p - entry_price) >= min_rr * risk), None)
        if tp1 is None and candidates:
            raise InsufficientTPDistanceError(nearest=candidates[0], required=min_rr * risk)
        if tp1 is None:
            tp1 = entry_price + min_rr * risk  # no structural target — projection fallback
        # TP2 must be strictly beyond TP1
        fvg_far = [f.top for f in htf_fvgs if f.direction == "BEAR" and f.top > tp1]
        if fvg_far:
            tp2 = min(fvg_far)
        else:
            fib_tp2 = entry_price + config.fib_ext * risk
            tp2 = fib_tp2 if fib_tp2 > tp1 else None  # invariant: TP2 > TP1
    else:  # SHORT — mirror
        liq = [e.price for e in eq_levels if e.kind == "EQL" and e.price < entry_price]
        liq += [s.price for s in htf_swings["swing_lows"] if s.price < entry_price]
        fvg_near = [f.top for f in htf_fvgs if f.direction == "BULL" and f.top < entry_price]
        candidates = sorted(set(liq + fvg_near), reverse=True)
        tp1 = next((p for p in candidates if (entry_price - p) >= min_rr * risk), None)
        if tp1 is None and candidates:
            raise InsufficientTPDistanceError(nearest=candidates[0], required=min_rr * risk)
        if tp1 is None:
            tp1 = entry_price - min_rr * risk
        fvg_far = [f.bot for f in htf_fvgs if f.direction == "BULL" and f.bot < tp1]
        if fvg_far:
            tp2 = max(fvg_far)
        else:
            fib_tp2 = entry_price - config.fib_ext * risk
            tp2 = fib_tp2 if fib_tp2 < tp1 else None

    tp1_source = ("LIQUIDITY" if tp1 in liq
                  else "FVG_NEAR" if tp1 in fvg_near
                  else "RR_PROJECTION")
    tp2_source = ("FVG_FAR" if tp2 in fvg_far
                  else "FIB_EXT" if tp2 is not None
                  else "NONE")
    return tp1, tp2, {"tp1_source": tp1_source, "tp2_source": tp2_source}
```

### 4.2 Modified files

| File | Change | Rationale |
|---|---|---|
| `config.yaml` | New keys: `engine.smc_version: v1` (flag), `engine.smc_v2_symbols: []` (symbol whitelist for phased rollout), `smc_v2:` block (`pullback_timeout_bars: 8`, `fvg_priority: true`, `ote_band: [0.618, 0.786]`, `require_confirmation: true`) | Feature flag + tunables |
| `engine/safe_orchestrator.py:730-792` | Load `setup_candidates.json` at tick start, advance pending candidates (bars_waited++, expire check, zone entry check, confirmation check, entry execution), persist at tick end | Stateful tracking |
| `engine/safety/position_guard.py:296-309` | The `min_sl_atr`/`max_sl_atr` guard becomes a sanity assertion only (signals.py already clamps). If a v1 signal reaches it (legacy path), it still rejects | DRY — clamp at single source |
| `engine/lifecycle.py:58` `Position` dataclass | Add `entry_setup_source: str | None = None` (values: `"FVG_PULLBACK"`, `"OTE_RETRACE"`, `"V1_LEGACY"`), `tp1_target_type: str | None = None` (values: `"LIQUIDITY"`, `"FVG_NEAR"`, `"RR_PROJECTION"`), `tp2_target_type: str | None = None` (values: `"FVG_FAR"`, `"FIB_EXT"`, `"NONE"`), `bars_to_pullback: int | None = None` | Telemetry for post-mortem analysis |
| `engine/lifecycle.py` (close handling) | Single-target mode: if `pos.tp2 is None`, on TP1 fill close 100% of position (skip `_move_sl_to_breakeven`) | Support TP2-less setups |
| `backend/db.py:60` `trades` schema | Add columns: `entry_setup_source TEXT NULL`, `tp1_target_type TEXT NULL`, `tp2_target_type TEXT NULL`, `bars_to_pullback INT NULL`. Migration via `backend/migrations/NNN_smc_v2_telemetry.sql` | RR distribution analysis |
| `engine/smc.py` | Add `liquidity_pools(df, eq_threshold) -> list[EqLevel]` building on existing `equal_levels()`. Returns clustered equal highs/lows with cluster strength (count of touches) | TP1 liquidity source |
| `backtest/engine.py` | Branch on `config.engine.smc_version` to run v1 or v2 path. v2 path must construct an in-memory SetupCandidate state (no disk) since walk-forward runs many years per second | Backtest parity |

### 4.3 Data Flow (per orchestrator tick)

```
TICK n:
  1. Load state: setup_candidates.json → in-memory list
  2. For each pending candidate:
       - bars_waited += 1
       - if bars_waited > pullback_timeout_bars: state = EXPIRED, drop
       - if state == AWAITING_PULLBACK and is_price_in_zone(current_price, zone):
           state = IN_ZONE
       - if state == IN_ZONE:
           confirmed, entry_px = confirm_entry(df_15m, zone, direction, trigger_ts)
           if confirmed:
               try:
                   sl = calc_sl(...)
                   tp1, tp2, tags = calc_tp_targets(...)
                   rr1 = abs(tp1-entry_px)/abs(entry_px-sl)
               except SLTooFarError | InsufficientTPDistanceError:
                   state = EXPIRED, drop
               else:
                   emit Signal → OrderManager.open_position(..., tp2=tp2_or_None)
                   state = CONFIRMED, drop
  3. Trigger phase on current 15m bar:
       - Detect new CHoCH/BoS aligned with HTF bias
       - For each: build_pullback_zones → SetupCandidate(AWAITING_PULLBACK) appended
  4. Save state: setup_candidates.json (atomic write)
```

### 4.4 Test Isolation Strategy

- **Pure modules** (`zones.py`, `confirmation.py`, `sl_calc.py`, `tp_calc.py`): unit tests with hand-crafted DataFrames + config dicts. No CCXT, no network, no file I/O. Coverage target: 100% line + branch.
- **State module** (`setup_state.py`): file I/O tested with `tmp_path` fixture. Includes corruption recovery test, schema-mismatch test, atomic-write crash-recovery test (simulate kill between tempfile write and rename).
- **Orchestrator integration**: existing `test_safe_orchestrator.py` patterns extended with v2 path (mock state file, assert state transitions across multiple ticks).
- **Backtest parity**: snapshot test — same 30-day fixture run through v1 and v2, assert v2 produces a stable set of trades (regression baseline).

---

## 5. SL/TP Math + Worked Examples

### 5.1 SL formula

```
buffer = sl_atr_buffer × ATR(15m)        # default 0.5
structural_sl_LONG  = min(zone.low,  htf_swing_anchor) - buffer
structural_sl_SHORT = max(zone.high, htf_swing_anchor) + buffer

stop_dist = |entry_price - structural_sl|
min_dist  = min_sl_atr × ATR(15m)        # default 0.5
max_dist  = max_sl_atr × ATR(15m)        # default 5.0

if stop_dist < min_dist:  widen to min_dist (ATR floor)
elif stop_dist > max_dist: raise SLTooFarError → REJECT setup
else: use structural_sl
```

Three protection layers:
1. **Structural** — SL on the far side of FVG/swing (unreachable by normal price action)
2. **Buffer** — 0.5 × ATR(15m) padding (liquidity-hunt absorption)
3. **ATR clamp** — floor widens too-tight stops; ceiling rejects too-far setups (don't clamp — that invalidates structure)

### 5.2 TP formula

```
risk = |entry_price - sl_price|

# TP1: nearest liquidity (eq H/L cluster + swing extrema), fallback FVG near edge
candidates = sorted(
    [eq_levels of correct kind on correct side] +
    [HTF swing highs/lows on correct side] +
    [HTF FVG near-edge on correct side]
)
tp1 = first candidate where |tp1 - entry| >= min_rr × risk
if no candidate satisfies min_rr but candidates exist: REJECT setup
if no candidates exist at all: tp1 = entry ± min_rr × risk (projection)

# TP2: HTF FVG far edge (gap fill), fallback fib_ext × risk
fvg_far = HTF FVG far-edge beyond tp1
tp2 = first(fvg_far) if exists
    else (fib_ext × risk projection) if it lies beyond tp1
    else None (single-target mode)
```

Invariant: `|tp2 - entry| > |tp1 - entry|` always (or `tp2 is None`).

### 5.3 ETH SHORT worked example (from user's 15m/1h/4h charts, 22-23 May 2026)

**Market state**:
- 4h bias: BEAR (3-day downtrend, 22 May sweep of $2120, 23 May 03:00 sweep of $2055)
- 1h bear leg: 22 May 21:00 - 23 May 01:00, $2120 → $2055
- 1h unmitigated FVG (formed during bear leg): ~$2102 - $2118 (BULL-style FVG that price left behind going down — a counter-direction gap that price tends to retrace into)
- 15m: $2055 bounce → $2070

**v1 behaviour (what the bot does today)**:
```
CHoCH BEAR detected at 15m close $2065
Entry  = $2065 (market, immediate)
SL     = $2087 (previous 15m swing high, no buffer)
risk   = $22
min_tp_short = $2065 - $22 × 1.8 = $2025.40
htf_below_targets (swing lows + FVG bots below $2025) → e.g. $2020
TP1    = $2020   rr1 = 2.05  ✅ passes
TP2    = $2065 - $22 × 1.618 = $2029.40
                       ⚠️ TP2 ($2029) > TP1 ($2020) in absolute price = WRONG for SHORT
                       (i.e. TP2 closer to entry than TP1 — invariant violated, not checked in v1)
```
Issues: SL at $2087 sits below the 1h FVG ($2102-2118), so a normal counter-rally into the FVG stops the bot out before the actual SMC entry zone is even tested. TP1/TP2 invariant violation possible.

**v2 behaviour (proposed, same market)**:
```
TICK n: CHoCH BEAR detected on 15m at $2065
   → emit SetupCandidate(
       direction=SHORT,
       trigger_price=$2065,
       target_zone=ZoneSpec(low=$2102, high=$2118, source=HTF_FVG),
       htf_swing_anchor=$2147 (last 4h swing high before bear leg),
       state=AWAITING_PULLBACK, bars_waited=0)

TICK n+4 (1 hour later): price = $2108
   → is_price_in_zone($2108, [$2102, $2118]) = TRUE
   → state = IN_ZONE
   → confirm_entry: look for 15m bearish engulfing or CHoCH inside zone
       → confirmed = TRUE, entry_price = $2110 (engulfing close)

   ATR(15m, 14) = $4.5 (illustrative)
   buffer = 0.5 × $4.5 = $2.25

   calc_sl: structural = max($2118, $2147) + $2.25 = $2149.25
            stop_dist = $39.25
            max_dist  = 5.0 × $4.5 = $22.50
            $39.25 > $22.50 → SLTooFarError → REJECT
```

In this exact configuration v2 rejects the setup — because the 4h swing anchor at $2147 is too far. **This is correct behaviour**: an SL at $2149 with entry at $2110 means risking $39 to short into a FVG that's only 50% retraced of the bear leg — poor R-anchor.

**Alternative scenario (more realistic)**: If $2147 was already retested in the last 24h, the HTF swing anchor invalidates and the next-nearest valid swing is closer (say $2125). Then:
```
   calc_sl: structural = max($2118, $2125) + $2.25 = $2127.25
            stop_dist = $17.25 ✓ within ATR clamp
            risk = $17.25

   calc_tp_targets(SHORT, entry=$2110, sl=$2127.25, ...):
       eq_lows on 4h chart: $2080 (touched twice), $2055 (recent sweep)
       candidates_desc = [$2080, $2055]
       tp1 candidate $2080: ($2110-$2080)/$17.25 = 1.74 < 1.8 ✗
       tp1 candidate $2055: ($2110-$2055)/$17.25 = 3.19 ✓
       TP1 = $2055, rr1 = 3.19, source = LIQUIDITY

       fvg_far (BULL FVG bots below $2055): say $2020 (next leg FVG)
       TP2 = $2020 ✓ (beyond TP1), source = FVG_FAR
       rr2 = ($2110-$2020)/$17.25 = 5.22

   → emit Signal: SHORT @ $2110, SL $2127.25, TP1 $2055 (rr 3.19), TP2 $2020 (rr 5.22)
```

This is the SMC-doctrinal trade the user described.

---

## 6. Setup Rejection Catalogue

Each rejection reason gets its own counter, logged in the per-symbol breakdown (matches existing pattern at `signals.py:340-351`):

| Reason | Trigger condition | Source |
|---|---|---|
| `pullback_timeout` | `bars_waited > pullback_timeout_bars` and price never entered zone | smc_v2 state machine |
| `no_confirmation` | Price entered zone but no LTF CHoCH/engulfing within remaining bars | confirmation.py |
| `sl_too_far` | Structural SL distance > `max_sl_atr × ATR` | sl_calc.py SLTooFarError |
| `tp1_too_close` | Nearest liquidity exists but closer than `min_rr × risk` | tp_calc.py InsufficientTPDistanceError |
| `tp2_invalid` | No FVG far-edge AND fib_ext projection ≤ TP1 — degraded to single-target | (not a rejection — logged for telemetry) |
| `confluence_low` | Existing — score below threshold | signals.py (unchanged) |
| `daily_filter` | Existing — strict mode, daily opposite direction | signals.py (unchanged) |

---

## 7. Sibling Order Cleanup Fix (Separate, ships first)

### 7.1 Code change

Add helper to `OrderManager`:

```python
def _cancel_position_siblings(
    self,
    pos: Position,
    ccxt_sym: str,
    reason: str,
) -> dict:
    """
    Best-effort cancel of SL + TP1 + TP2 reduceOnly orders attached to a position.
    Used at any full-close path (reconcile, fallback close, reverse).
    """
    result = {"cancelled": [], "failed": [], "missing": []}
    for label, oid in [("SL", pos.sl_order_id),
                       ("TP1", pos.tp1_order_id),
                       ("TP2", pos.tp2_order_id)]:
        if not oid:
            result["missing"].append(label)
            continue
        try:
            self.client.exchange.cancel_order(oid, ccxt_sym)
            result["cancelled"].append(label)
        except ccxt.OrderNotFound:
            result["missing"].append(label)  # already gone (fired/cancelled by exchange)
        except Exception as e:
            log.warning(f"[cleanup] {pos.symbol}: failed to cancel {label} ({oid}): {e}")
            result["failed"].append(label)
    cancelled_str = "+".join(result["cancelled"]) or "none"
    log.info(f"[cleanup] {pos.symbol}: cancelled {cancelled_str} (reason={reason})")
    return result
```

### 7.2 Call sites

1. **Reconcile loop** (`exchange/__init__.py:659-668`):
   ```python
   for pos in self.positions[:]:
       if pos.symbol not in bn_open_symbols:
           ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
           self._cancel_position_siblings(pos, ccxt_sym, reason="RECONCILED")  # NEW
           exit_price = self._estimate_exit_price(pos, bn_orders_raw)
           self._record_close(pos, exit_price, reason="RECONCILED")
           closed_now.append(pos)
           self.positions.remove(pos)
           continue
   ```

2. **`_fallback_close`** (`exchange/__init__.py:842-848`): replace existing inline loop with `self._cancel_position_siblings(pos, ccxt_sym, reason="FALLBACK_CLOSE")`. Behaviour preserved (was already correct).

3. **`_move_sl_to_breakeven`** (`exchange/__init__.py:686-710`): **DO NOT** use the new helper. By design TP2 stays open after TP1 partial — only the old SL is cancelled and re-placed at entry. Leave existing code untouched.

### 7.3 Tests (TDD: red first)

`backend/tests/test_order_manager_v2.py`:
1. `test_reconcile_full_close_cancels_all_siblings` — exchange returns contracts==0; assert `cancel_order` called 3x for SL, TP1, TP2 with correct CCXT symbol form
2. `test_reconcile_partial_position_keeps_all_orders` — exchange returns contracts>0; assert zero cancel calls
3. `test_reconcile_cancel_handles_already_cancelled` — `cancel_order` raises `ccxt.OrderNotFound`; assert no propagation, position still removed from local state
4. `test_reconcile_cancel_handles_network_error` — `cancel_order` raises generic Exception; assert logged at WARNING, position still removed (best-effort)
5. `test_reconcile_cancel_skips_empty_oids` — Position with `tp2_order_id=""`; assert only SL+TP1 cancelled

New file `backend/tests/test_order_cleanup_helper.py`:
1. `test_helper_returns_correct_summary_dict`
2. `test_helper_handles_all_missing_ids`
3. `test_helper_uses_correct_symbol_format` (`BTC/USDT:USDT` not `BTC/USDT`)

### 7.4 Rollout

- PR ships independently before any SMC v2 work
- Pre-deploy: testnet verification — open position, manually trigger SL on Binance Testnet, watch reconcile detect close, assert open-orders list is empty after the next reconcile tick
- Production deploy: Hermes approval, `docker compose -f docker-compose.prod.yml up -d` (recreate)
- Rollback: single `git revert <sha>`; no schema changes, no state migration

---

## 8. Rollout Plan (SMC v2)

### 8.1 PR sequence

```
PR #C1: Sibling order cleanup fix             [ships first, independent]
                                              [Hermes approval]
─────────────────────────────────────────────
PR #S1: smc_v2 pure-function modules
        - engine/smc_v2/zones.py
        - engine/smc_v2/sl_calc.py
        - engine/smc_v2/tp_calc.py
        - engine/smc.py liquidity_pools()
        - 100% unit test coverage
        - no integration yet
─────────────────────────────────────────────
PR #S2: smc_v2 SetupCandidate state
        - engine/smc_v2/setup_state.py
        - persistence + atomic write
        - corruption recovery tests
        - orchestrator state tick wiring (still v1 emit-path)
─────────────────────────────────────────────
PR #S3: smc_v2 confirmation + signals dispatch
        - engine/smc_v2/confirmation.py
        - engine/smc_v2/__init__.py orchestration
        - config flag dispatch (smc_version: v1|v2)
        - integration tests
─────────────────────────────────────────────
PR #S4: backtest engine v2 path
        - in-memory SetupCandidate state
        - 6-month walk-forward harness
        - v1 vs v2 comparison report generator
─────────────────────────────────────────────
PR #S5: lifecycle.py + db.py telemetry
        - Position dataclass fields
        - trades schema migration
        - notifications enrichment
─────────────────────────────────────────────
PR #S6: config.yaml smc_v2 block + dry_run
        - smc_v2 block with defaults
        - smc_v2_symbols whitelist (initially empty)
        - dry_run shadow mode: log v2 signals without execution
        [Hermes approval before merge]
        [1-week dry_run paralel observation]
─────────────────────────────────────────────
PR #S7: production rollout (config-only)
        - smc_v2_symbols: [ETH/USDT, BTC/USDT] (Phase 1)
        - 1 week observation → +5 mid-cap (Phase 2)
        - 1 week observation → all 20 coins (Phase 3)
        [Hermes approval at each phase]
```

### 8.2 Backtest validation criteria

Walk-forward 6 months (2025-11 → 2026-04), 7 symbols (ETH, BTC, SOL, BNB, ADA, LINK, AVAX):

| Metric | v1 baseline | v2 acceptance | Hard reject |
|---|---|---|---|
| Win rate | (computed from current log) | ≥ baseline | < baseline × 0.95 |
| Avg realized RR | (computed) | ≥ 1.5 | < 1.2 |
| Max drawdown | (computed) | ≤ baseline | > baseline × 1.1 |
| Stop-hunt rate (SL hit, then price moves to original target within 1h) | (computed) | < baseline × 0.5 | ≥ baseline |
| Setup rejection rate | ~30% | 40-60% | > 75% (over-restrictive) |
| Sharpe (annualized) | (computed) | ≥ baseline | < baseline × 0.9 |

If any "hard reject" criterion fires, v2 goes back for redesign — no shadow rollout.

### 8.3 Dry-run validation (1 week paralel)

- Production: v1 active, executes real orders (unchanged)
- v2: runs in shadow mode (`smc_v2_symbols: ["*"]` + `smc_v2_shadow: true` flag, separate from execution flag)
- Every tick: v1 signal vs v2 signal logged side-by-side to `logs/smc_v2_shadow.log` with hypothetical outcome (computed from forward bars)
- Operator daily review: what did v2 reject? what did v2 trigger that v1 missed? hypothetical PnL difference?

Pass criteria (1 week):
- 0 critical errors (NaN, division by zero, JSON corruption, exception propagation killing tick)
- v2 setup hit rate (TP1 reached before SL) ≥ 50%
- v2 rejected setups' hindsight win rate ≤ v2 triggered setups' hindsight win rate (i.e. rejections were correctly negative-EV)

### 8.4 Production rollout (Hermes approval gate)

Three phases:
1. **Phase 1**: `smc_v2_symbols: [ETH/USDT, BTC/USDT]`. 1 week. Monitor live trades.
2. **Phase 2**: +5 mid-cap (`SOL`, `BNB`, `ADA`, `LINK`, `AVAX`). 1 week.
3. **Phase 3**: All 20 coins. v1 marked as legacy code path; removal in a separate post-rollout PR after 30 days of stable v2 operation.

Per-phase rollback criterion: 3 consecutive losing trades OR cumulative phase PnL ≤ -2% → operator flips `smc_version: v1` (manual config edit + `docker compose up -d`). Automated rollback explicitly out of scope.

---

## 9. Config Schema (final)

New `config.yaml` block:

```yaml
engine:
  smc_version: v1                # "v1" | "v2" — feature flag, default v1
  smc_v2_symbols: []             # empty = none; ["*"] = all; or whitelist
  smc_v2_shadow: false           # true = compute v2 signals but don't execute (dry-run mode)

smc_v2:
  pullback_timeout_bars: 8       # 15m bars; 8 ≈ 2 hours
  fvg_priority: true             # FVG before OTE
  ote_band: [0.618, 0.786]       # OTE fib levels for fallback zone
  require_confirmation: true     # require 15m CHoCH/engulfing inside zone
```

Existing keys activated by v2 (already in `config.yaml`, currently unused in signals.py):

```yaml
risk:
  sl_atr_buffer: 0.5             # was dead key, v2 activates
safety:
  min_sl_atr: 0.5                # was post-hoc reject only; v2 enforces pre-emptively
  max_sl_atr: 5.0                # was post-hoc reject only; v2 enforces, REJECT if exceeded
```

---

## 10. Open Questions / Risks

1. **HTF swing anchor selection** — spec says "last HTF swing on the wrong side", but multiple candidates exist. Need a tie-breaker: most recent? highest-volume? Highest-touch? Initial: most recent unbroken swing. Revisit after backtest.
2. **Equal-level cluster threshold** — `engine/smc.py` `equal_levels()` uses `eq_threshold_pct: 0.1`. For TP1 liquidity, do we want a stricter cluster (e.g. require ≥2 touches)? Initial: use same `equal_levels()` output as-is; tighten if backtest shows TP1 hitting non-significant levels.
3. **OTE band reference points** — OTE 0.618-0.786 of which leg? Initial: most recent HTF impulse (4h CHoCH-to-extremum leg). May need refinement.
4. **Concurrent setups on same symbol** — Can a symbol have multiple pending SetupCandidates? Spec says yes (e.g. one LONG pending pullback + one SHORT just emitted). Position cap (`max_open_positions: 7`) only applies at entry, not at setup state. Risk: state file grows. Mitigation: cap pending candidates per symbol at 3.
5. **Telegram notification volume** — v2 will reject more setups (40-60% vs 30%). Operator may get notification spam. Initial: don't notify on rejection in production (already current behaviour); only log.
6. **Live position migration** — when v2 ships, existing v1-opened positions remain managed by v1 lifecycle (TP1+TP2 with fib_ext). New positions use v2. No migration needed because Position dataclass changes are additive (nullable fields).

---

## 11. Out of Scope (explicitly)

- Removal of v1 code (separate post-rollout PR, after ≥30 days stable v2)
- 3-tier TP ladder (TP3 + 40/40/20 split) — requires Position dataclass shape change + JSON migration
- Forex broker adapter (separate workstream, see `CLAUDE.md §8`)
- Automated rollback on losing streak (manual operator action sufficient for first version)
- UI/dashboard changes to display v2 setup states (operator reads logs for now)
- Refactor of `signals.py` v1 internals (left untouched; v2 is parallel implementation)

---

## 12. Acceptance Criteria

The implementation is complete when:

1. **PR #C1 deployed and verified** — orphan reduceOnly orders are gone from Binance Open Orders after any full-close path.
2. **All 7 SMC v2 PRs merged** to master with Hermes approval.
3. **Backtest report** (PR #S4 output) shows v2 meets all acceptance criteria in §8.2.
4. **1 week dry-run** (PR #S6) produced zero critical errors and met §8.3 pass criteria.
5. **Phase 3 reached** — all 20 coins running v2 in production for ≥7 days with no manual rollback.
6. **Telemetry verified** — Postgres `trades` table contains `entry_setup_source`, `tp1_target_type`, `tp2_target_type` for every v2 trade.

---

## 13. References

- `CLAUDE.md` §3 (Live Ops), §4 (PR discipline), §6 (Hermes/Claude role split), §9 (DON'Ts)
- Memory: `feedback_deploy_caution.md`, `reverse_position_guard_policy.md`, `binance_isolated_hedge_off_autoflip.md`
- ICT/SMC reference: pullback-to-FVG entry with LTF confirmation, structural SL, liquidity-as-TP doctrine
