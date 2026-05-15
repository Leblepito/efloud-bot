"""TradeJournal JSONL tail — read-only consumer of bot's trade journal.

Adapts engine/journal.py TradeJournal._load (L99-114): same file format
(one JSON-serialized TradeSnapshot per line) but READ-ONLY. We never write
to the journal — the bot owns that file. Corrupted lines are silently
skipped so a partial write at the bot's tail doesn't break overseer.

Returns the last `max_recent` entries in file order so rule_consecutive_losses
can examine the trailing window directly.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Deque

log = logging.getLogger("efloud.overseer.journal_tail")


class JournalTail:
    """Reads trade_journal.jsonl and returns the trailing N closed snapshots.

    Re-reads the entire file each call (journal is small — bot rewrites
    full file on each exit-update; see TradeJournal._persist). Keeps the
    implementation stateless apart from the configured max_recent cap.
    """

    def __init__(self, journal_path: str, max_recent: int = 50):
        self.journal_path = journal_path
        self.max_recent = max_recent

    def read_recent(self) -> list[dict]:
        """Return the last `max_recent` parsed snapshots in file order.

        - Missing file → empty list (bot may not have written yet).
        - Corrupted line → skipped silently (alerter / journal pattern).
        """
        path = Path(self.journal_path)
        if not path.exists():
            return []

        # deque with maxlen acts as a streaming tail window — we never need
        # to hold the full file in memory even if the journal grows large.
        tail: Deque[dict] = deque(maxlen=self.max_recent)
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tail.append(rec)
        except OSError as e:
            log.warning(f"journal tail read failed: {e}")
            return []
        return list(tail)
