"""File-position tracking JSON log line reader.

Adapts the alerter's _tail_logs pattern (ops/alerter/alerter.py L101-125):
  - Track byte offset across calls; only return lines past the cursor.
  - On size shrink (rotation/truncate), reset offset to 0 so we don't miss
    the new file's content.
  - JSON-decode each non-empty line; invalid lines silently skipped so a
    single corrupted entry doesn't poison the whole batch.

Differs from the alerter by adding a bounded ring buffer of parsed records
so rules that need *recent context* (last N events, regardless of read_new
boundary) can pull a fixed-size window without re-reading the file.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Deque

log = logging.getLogger("efloud.overseer.log_tail")


class JsonLogTail:
    """Reads JSON lines from a growing log file with position tracking.

    Maintains a byte-offset cursor between read_new() calls and a fixed-size
    ring buffer of parsed records for read_recent().
    """

    def __init__(self, log_path: str, max_buffer: int = 1000):
        """Open in read-position mode at offset 0; first read_new() returns
        all existing content. Caller can discard initial output if they want
        only "from now on" behaviour (alerter does this in _init_log_offset).
        """
        self.log_path = log_path
        self.max_buffer = max_buffer
        self._offset = 0
        self._buffer: Deque[dict] = deque(maxlen=max_buffer)

    def read_new(self) -> list[dict]:
        """Return parsed dicts for any lines appended since the last call.

        Behaviour:
          - File missing → empty list, cursor untouched.
          - File shrank → cursor resets to 0 (rotation handling).
          - Invalid JSON line → silently skipped.

        Each returned dict is also appended to the internal ring buffer.
        """
        path = Path(self.log_path)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return []

        if size < self._offset:
            # File rotated/truncated since last read — restart from offset 0.
            log.info("log file shrank — assuming rotation, resetting offset")
            self._offset = 0

        if size == self._offset:
            return []

        results: list[dict] = []
        with path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self._offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # Skip non-JSON / corrupted lines silently — same policy
                    # as ops.alerter.alerter._tail_logs.
                    continue
                results.append(rec)
                self._buffer.append(rec)
            self._offset = f.tell()
        return results

    def read_recent(self) -> list[dict]:
        """Return the last `max_buffer` parsed records (oldest first).

        Snapshots the deque so the caller can iterate freely without seeing
        a future write mutate the list mid-iteration.
        """
        return list(self._buffer)
