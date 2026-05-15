"""Overseer-specific dedup wrapper.

Reuses ops.alerter.dedup.Dedup (SQLite-backed dedup with per-call windows) so
we have one source of truth for dedup transport. The wrapper adds:
  - overseer-default DB path (separate from alerter's DB to avoid key-namespace
    collisions and keep retention concerns independent),
  - a default window (30 min, per Phase A2 reviewer recommendation) that
    every overseer callsite can use without repeating the magic number.

Env override: EFLOUD_OVERSEER_DEDUP_DB → explicit DB path.
"""
from __future__ import annotations

import os
from typing import Optional

from ops.alerter.dedup import Dedup as _AlerterDedup

# Module-level constants so tests can monkeypatch the default safely.
DEFAULT_DB_PATH: str = "/app/state/overseer_dedup.sqlite"
DEFAULT_WINDOW_SECONDS: int = 1800  # 30 min — Phase A2 reviewer recommendation


class OverseerDedup(_AlerterDedup):
    """Overseer-config'li dedup. Underlying SQLite behaviour matches the
    alerter; only the default DB path + default window differ."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        window_seconds: Optional[int] = None,
    ):
        """Resolve DB path (arg > env > DEFAULT_DB_PATH) and store the default
        window so should_fire() can elide the window arg at callsites."""
        resolved_path = (
            db_path
            if db_path is not None
            else os.environ.get("EFLOUD_OVERSEER_DEDUP_DB", DEFAULT_DB_PATH)
        )
        self.default_window_seconds = (
            window_seconds if window_seconds is not None else DEFAULT_WINDOW_SECONDS
        )
        super().__init__(db_path=resolved_path)

    def should_fire(self, alert_key: str, window_sec: Optional[int] = None) -> bool:
        """Same semantics as alerter Dedup.should_fire, but window_sec defaults
        to self.default_window_seconds so callers don't repeat the constant."""
        effective_window = (
            window_sec if window_sec is not None else self.default_window_seconds
        )
        return super().should_fire(alert_key, effective_window)
