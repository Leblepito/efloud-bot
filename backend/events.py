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
        # B-9 fix (2026-07-17): subscribe() sırasında yakalanan loop referansı —
        # thread-dışı publish'ler bu loop'a call_soon_threadsafe ile aktarılır.
        self._loop: asyncio.AbstractEventLoop | None = None

    async def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue)
        self._loop = asyncio.get_running_loop()
        self._subscribers.append(q)
        log.debug(f"Subscriber added (total: {len(self._subscribers)})")
        return q

    async def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)
            log.debug(f"Subscriber removed (total: {len(self._subscribers)})")

    def publish(self, event_type: str, **payload: Any) -> None:
        """Sync publish — bot worker (sync ccxt) -> async subscribers.

        B-9 fix (2026-07-17): asyncio.Queue thread-safe DEĞİLDİR ve executor
        thread'inden put_nowait loop'u UYANDIRMAZ — dashboard WS event'i bir
        sonraki loop uyanışına (30 sn cycle sleep'ine kadar) gecikiyordu;
        ayrıca ws.py'nin her client mesajında iptal ettiği queue.get()
        waiter'ıyla yarışta InvalidStateError event'i sessizce düşürebiliyordu.
        Loop-dışı thread'den çağrıda teslimat call_soon_threadsafe ile loop
        thread'ine aktarılır; loop üzerinde ya da loop hiç yokken (testler)
        davranış birebir eski (_deliver doğrudan).
        """
        evt = Event(type=event_type, payload=payload)
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not loop:
                try:
                    loop.call_soon_threadsafe(self._deliver, evt)
                    return
                except RuntimeError:
                    # Loop kapanma anı — best-effort doğrudan teslim.
                    pass
        self._deliver(evt)

    def _deliver(self, evt: Event) -> None:
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
