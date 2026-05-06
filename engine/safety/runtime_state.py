"""Persistent runtime state for healthz / crash-loop detection.

Tracks four signals:
  - last_loop_tick_ms — main bot loop liveness (volatile, NOT persisted)
  - last_exchange_ping_ms — exchange connectivity (volatile, NOT persisted)
  - fatal_exception_state — sticky flag (PERSISTED across restarts)
  - crash_count + last_crash_ms — crash-loop detection (PERSISTED)

Volatile fields are intentionally not persisted: a bot that just restarted has
no fresh loop-tick or exchange-ping evidence yet, so loading stale values would
falsely report healthy. The healthz endpoint correctly reports 503 (unhealthy)
during the startup window until the first cycle ticks succeed.

Persistence: state/runtime.json (atomic write via tmp + os.replace + fsync).
Concurrency: threading.Lock guards in-memory writes; reads via snapshot() also
take the lock for atomic snapshot of all fields.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("efloud.runtime_state")

# 5 minutes — fatal flag auto-clears after this many ms of clean ticks since it was set
FATAL_CLEAR_AFTER_MS = 5 * 60 * 1000


class RuntimeState:
    """Thread-safe in-memory + persistent runtime state."""

    def __init__(self, state_dir: str = "./state"):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "runtime.json"
        self._lock = threading.Lock()
        # Volatile (in-memory only)
        self.last_loop_tick_ms: Optional[int] = None
        self.last_exchange_ping_ms: Optional[int] = None
        # Persistent
        self.fatal_exception_state: bool = False
        self.fatal_exception_set_at_ms: Optional[int] = None
        self.crash_count: int = 0
        self.last_crash_ms: Optional[int] = None
        self._load()

    def _load(self) -> None:
        """Load persistent fields from disk. Missing/corrupted file → clean state."""
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.fatal_exception_state = bool(data.get("fatal_exception_state", False))
            self.fatal_exception_set_at_ms = data.get("fatal_exception_set_at_ms")
            self.crash_count = int(data.get("crash_count", 0))
            self.last_crash_ms = data.get("last_crash_ms")
        except Exception as e:
            log.error(f"runtime_state load failed: {e}; starting clean")
            # Move corrupted file aside so subsequent saves succeed
            try:
                backup = self.path.with_suffix(f".corrupted.{int(time.time())}")
                self.path.rename(backup)
                log.warning(f"corrupted runtime.json moved to {backup}")
            except Exception:
                pass

    def _save(self) -> None:
        """Atomic write of persistent fields. Caller MUST hold self._lock.

        Note: this method does fsync inside the lock — a pathological hung disk
        would block all healthz reads. In practice fsync is fast on healthy VMs
        and only fires on the auto-clear branch (~once per 5 min) or on fatal-set
        (only when the bot is already broken). Acceptable trade-off for atomicity.
        """
        tmp = self.path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "fatal_exception_state": self.fatal_exception_state,
                    "fatal_exception_set_at_ms": self.fatal_exception_set_at_ms,
                    "crash_count": self.crash_count,
                    "last_crash_ms": self.last_crash_ms,
                }, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(self.path))
        except Exception as e:
            log.error(f"runtime_state save failed: {e}")
            try:
                tmp.unlink()
            except Exception:
                pass

    def update_loop_tick(self) -> None:
        """Called from main loop after each successful cycle.

        Side effect: auto-clears fatal_exception_state if 5+ min have elapsed
        since the flag was set (i.e. the bot has been running cleanly for long
        enough to be considered recovered).
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.last_loop_tick_ms = now_ms
            if self.fatal_exception_state and self.fatal_exception_set_at_ms is not None:
                if now_ms - self.fatal_exception_set_at_ms >= FATAL_CLEAR_AFTER_MS:
                    self.fatal_exception_state = False
                    self.fatal_exception_set_at_ms = None
                    self._save()

    def update_exchange_ping(self) -> None:
        """Called when an exchange API call succeeds (e.g. reconcile)."""
        with self._lock:
            self.last_exchange_ping_ms = int(time.time() * 1000)

    def set_fatal_exception(self) -> None:
        """Called when bot main loop catches an uncaught cycle exception.

        Idempotent: if already set, only updates the timestamp to the latest
        exception (sliding 5-min auto-clear window).
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.fatal_exception_state = True
            self.fatal_exception_set_at_ms = now_ms
            self._save()

    def increment_crash(self) -> None:
        """Called once at startup if fatal_exception_state is set on disk
        (i.e. the previous run died with the flag set).
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.crash_count += 1
            self.last_crash_ms = now_ms
            self._save()

    def reset_crash_count(self) -> None:
        """Called once at startup if fatal_exception_state is CLEAN on disk
        (previous run shut down healthy). Resets crash counter to 0.
        """
        with self._lock:
            if self.crash_count != 0 or self.last_crash_ms is not None:
                self.crash_count = 0
                self.last_crash_ms = None
                self._save()

    def snapshot(self) -> dict:
        """Atomic read of all fields for healthz endpoint."""
        with self._lock:
            return {
                "last_loop_tick_ms": self.last_loop_tick_ms,
                "last_exchange_ping_ms": self.last_exchange_ping_ms,
                "fatal_exception_state": self.fatal_exception_state,
                "fatal_exception_set_at_ms": self.fatal_exception_set_at_ms,
                "crash_count": self.crash_count,
                "last_crash_ms": self.last_crash_ms,
            }
