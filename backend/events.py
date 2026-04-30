"""In-process pub/sub event bus.

Bot worker → backend gateway → WebSocket clients.
Single-process design (Railway tek dyno), so asyncio.Queue per subscriber.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("efloud.events")


@dataclass
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload, "ts": self.ts}


class EventBus:
    """Async pub/sub. Subscribers get their own queue; slow subscribers don't block publishers."""

    def __init__(self, max_queue: int = 256):
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._max_queue = max_queue

    async def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.append(q)
        log.debug(f"Subscriber added (total: {len(self._subscribers)})")
        return q

    async def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)
            log.debug(f"Subscriber removed (total: {len(self._subscribers)})")

    def publish(self, event_type: str, **payload: Any) -> None:
        """Sync publish — bot worker (sync ccxt) -> async subscribers via run_coroutine_threadsafe equivalent."""
        evt = Event(type=event_type, payload=payload)
        for q in list(self._subscribers):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                # Slow subscriber → drop oldest
                try:
                    q.get_nowait()
                    q.put_nowait(evt)
                    log.warning("Slow subscriber: dropped oldest event")
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    async def publish_async(self, event_type: str, **payload: Any) -> None:
        """Async publish (use from coroutines)."""
        self.publish(event_type, **payload)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton
bus = EventBus()
