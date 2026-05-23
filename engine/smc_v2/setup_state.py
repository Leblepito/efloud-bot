"""SetupCandidate + persistence for SMC v2 pending setups.

A SetupCandidate is created when an LTF CHoCH triggers; the orchestrator
(PR #S2b) advances it across ticks waiting for a pullback into the target
zone and a confirmation. Persisted across bot restarts via SetupStateStore.

Persistence rules (spec §4.1):
- Atomic write via tempfile + os.fsync + os.replace (mirrors OrderManager._persist).
- Persisted file contains ONLY candidates with state ∈ {AWAITING_PULLBACK, IN_ZONE}.
  CONFIRMED and EXPIRED are dropped from the in-memory list before save.
- Per-symbol cap (default 3): trigger phase rejects new candidates if existing
  pending count for that symbol reaches the cap.
- Schema versioned: {"version": 1, "candidates": [...]}.
- Version mismatch on load → archive to setup_candidates.v{N}.bak.json.
- JSON parse error on load → archive to setup_candidates.corrupt.{ts}.bak.json.
- File size cap on load (default 1 MB) → ERROR log, start empty.

Spec: docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md §4.1
"""
from dataclasses import dataclass, field
from typing import List, Literal

from engine.smc_v2.zones import ZoneSpec


@dataclass
class SetupCandidate:
    """A pending pullback setup tracked across orchestrator ticks.

    State machine (one-way forward, no rollback):
        AWAITING_PULLBACK → IN_ZONE → CONFIRMED  (entry placed)
                                  ↘ EXPIRED      (timeout / SL too far / TP too close)

    `bars_waited` increments each tick regardless of price in/out of zone.
    Setup expires only when bars_waited > pullback_timeout_bars.
    """
    symbol: str
    direction: Literal["LONG", "SHORT"]
    trigger_bar_ts: int                            # CHoCH bar timestamp (ms)
    trigger_price: float                           # break price at CHoCH
    htf_bias: str                                  # "BULL" | "BEAR" | "UNDEF"
    target_zone: ZoneSpec
    htf_swing_anchor: float                        # HTF swing for structural SL
    bars_waited: int                               # incremented per orchestrator tick
    state: Literal["AWAITING_PULLBACK", "IN_ZONE", "CONFIRMED", "EXPIRED"]
    confluence_score: int
    reasons: List[str] = field(default_factory=list)
