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
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Literal

from engine.smc_v2.zones import ZoneSpec

log = logging.getLogger("efloud.smc_v2.setup_state")


# Persistence config (defaults; can be overridden in constructor)
# AWAITING_REENTRY added for pullback detection (PR #pullback-detection)
PERSISTED_STATES = frozenset({"AWAITING_PULLBACK", "IN_ZONE", "AWAITING_REENTRY"})
# Valid states for validation (includes terminal states for backward compat)
VALID_STATES = frozenset({"AWAITING_PULLBACK", "IN_ZONE", "AWAITING_REENTRY", "CONFIRMED", "EXPIRED"})
SCHEMA_VERSION = 1
DEFAULT_MAX_FILE_BYTES = 1_000_000   # 1 MB sanity cap on load
DEFAULT_MAX_PENDING_PER_SYMBOL = 3


@dataclass
class SetupCandidate:
    """A pending pullback setup tracked across orchestrator ticks.

    State machine (one-way forward, no rollback):
        AWAITING_PULLBACK → IN_ZONE → AWAITING_REENTRY → CONFIRMED  (entry placed)
                           ↘ (timeout) ↘ (timeout)   ↘ EXPIRED

    Pullback detection (PR #pullback-detection):
    - has_left_zone=false: Price has NOT yet left the zone after first entry
    - has_left_zone=true: Price left the zone, now waiting for re-entry (pullback)

    `bars_waited` increments once per CLOSED LTF bar (BT-24, 2026-07-26),
    regardless of price in/out of zone. Ticks that land on a bar already
    counted do not increment it — the orchestrator polls far faster than the
    entry timeframe (check_interval_sec=30 vs a 15m bar), so counting ticks
    made an 8-bar timeout expire in 4 minutes.
    Setup expires only when bars_waited > pullback_timeout_bars.
    """
    symbol: str
    direction: Literal["LONG", "SHORT"]
    trigger_bar_ts: int                            # CHoCH bar timestamp (ms)
    trigger_price: float                           # break price at CHoCH
    htf_bias: str                                  # "BULL" | "BEAR" | "UNDEF"
    target_zone: ZoneSpec
    htf_swing_anchor: float                        # HTF swing for structural SL
    bars_waited: int                               # incremented per CLOSED LTF bar (BT-24)
    state: Literal["AWAITING_PULLBACK", "IN_ZONE", "AWAITING_REENTRY", "CONFIRMED", "EXPIRED"]
    confluence_score: int
    reasons: List[str] = field(default_factory=list)
    has_left_zone: bool = False                    # pullback detection flag


class SetupStateStore:
    """Manages the on-disk pending-candidates file.

    Lifecycle:
      __init__ → in-memory list empty; file not read yet
      .load()  → read file, populate self.candidates (corrupt files quarantined)
      .add(c)  → append, return True; or return False if over per-symbol cap
      .save()  → atomic write; only AWAITING_PULLBACK/IN_ZONE persisted

    Pruning, cap, and corruption-handling are described in spec §4.1.
    """

    def __init__(
        self,
        path: Path,
        max_pending_per_symbol: int = DEFAULT_MAX_PENDING_PER_SYMBOL,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        if max_pending_per_symbol <= 0:
            raise ValueError(
                f"max_pending_per_symbol must be > 0 (got {max_pending_per_symbol})"
            )
        if max_file_bytes <= 0:
            raise ValueError(
                f"max_file_bytes must be > 0 (got {max_file_bytes})"
            )
        self.path = Path(path)
        self.max_pending_per_symbol = max_pending_per_symbol
        self.max_file_bytes = max_file_bytes
        self.candidates: List[SetupCandidate] = []

    def add(self, candidate: "SetupCandidate") -> bool:
        """Append a new pending candidate.

        Returns False (and does not append) if the per-symbol cap is reached
        for candidates in active states (AWAITING_PULLBACK, IN_ZONE).
        """
        active_for_symbol = sum(
            1 for c in self.candidates
            if c.symbol == candidate.symbol and c.state in PERSISTED_STATES
        )
        if active_for_symbol >= self.max_pending_per_symbol:
            return False
        self.candidates.append(candidate)
        return True

    def prune(self) -> None:
        """Prune CONFIRMED/EXPIRED from the in-memory candidates list.

        Separated from disk writing so backtests (persist=False, which skip
        save()) can still bound the in-memory list and avoid memory growth.
        """
        self.candidates = [c for c in self.candidates if c.state in PERSISTED_STATES]

    def save(self) -> None:
        """Atomic write of active candidates only.

        Prunes CONFIRMED/EXPIRED from the in-memory list before serializing.
        """
        # Prune in-memory list first — CONFIRMED/EXPIRED never persisted
        self.prune()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "version": SCHEMA_VERSION,
            "candidates": [asdict(c) for c in self.candidates],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def load(self) -> None:
        """Read the file, populate self.candidates.

        - Nonexistent file → empty list (no error)
        - File > max_file_bytes → ERROR log, empty list
        - Version mismatch → archive + empty list
        - Corrupt JSON → archive + empty list
        - Any candidate with state ∉ PERSISTED_STATES → drop with warning
        """
        self.candidates = []
        if not self.path.exists():
            return

        size = self.path.stat().st_size
        if size > self.max_file_bytes:
            log.error(
                f"setup_state file too large ({size} > {self.max_file_bytes} bytes); "
                f"refusing to load. Investigate {self.path}"
            )
            return

        # Read + parse separately so transient OS errors don't quarantine
        # a valid file as "corrupt". JSONDecodeError → real corruption;
        # OSError → transient (disk busy, lock, etc.) → start empty, no archive.
        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except OSError as e:
            log.error(f"setup_state read failed (transient): {e}; starting empty")
            return
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as e:
            self._archive(f"corrupt.{int(time.time())}", reason=f"parse error: {e}")
            return

        ver = payload.get("version")
        if ver != SCHEMA_VERSION:
            suffix = f"v{ver}" if ver is not None else "v_missing"
            self._archive(suffix, reason=f"schema version mismatch (got {ver})")
            return

        raw = payload.get("candidates", [])
        for item in raw:
            state = item.get("state")
            if state not in VALID_STATES:
                log.warning(
                    f"setup_state load: dropping candidate with state={state} "
                    f"(symbol={item.get('symbol')})"
                )
                continue
            # Validate target_zone shape before constructing ZoneSpec — a
            # malformed zone (missing keys, wrong source enum) would silently
            # poison the in-memory list and crash the orchestrator later.
            zone_raw = item.get("target_zone") or {}
            required_zone_keys = {"low", "high", "source"}
            if not required_zone_keys.issubset(zone_raw):
                log.warning(
                    f"setup_state load: dropping candidate with malformed "
                    f"target_zone (missing keys) — symbol={item.get('symbol')}"
                )
                continue
            if zone_raw["source"] not in {"HTF_FVG", "OTE"}:
                log.warning(
                    f"setup_state load: dropping candidate with invalid "
                    f"target_zone.source={zone_raw['source']!r} — "
                    f"symbol={item.get('symbol')}"
                )
                continue
            try:
                zone = ZoneSpec(
                    low=zone_raw["low"],
                    high=zone_raw["high"],
                    source=zone_raw["source"],
                )
                self.candidates.append(SetupCandidate(
                    symbol=item["symbol"],
                    direction=item["direction"],
                    trigger_bar_ts=item["trigger_bar_ts"],
                    trigger_price=item["trigger_price"],
                    htf_bias=item["htf_bias"],
                    target_zone=zone,
                    htf_swing_anchor=item["htf_swing_anchor"],
                    bars_waited=item["bars_waited"],
                    state=item["state"],
                    confluence_score=item["confluence_score"],
                    reasons=item.get("reasons", []),
                    has_left_zone=item.get("has_left_zone", False),  # backward compat
                ))
            except (KeyError, TypeError, ValueError) as e:
                log.warning(
                    f"setup_state load: dropping malformed candidate ({e}): {item}"
                )
                continue

    def _archive(self, suffix: str, reason: str) -> None:
        """Move a problematic file out of the way so a fresh start can proceed."""
        try:
            backup = self.path.with_suffix(f".{suffix}.bak.json")
            os.replace(self.path, backup)
            log.warning(
                f"setup_state archived {self.path} → {backup} (reason: {reason})"
            )
        except OSError as e:
            log.error(f"setup_state archive failed: {e}")
