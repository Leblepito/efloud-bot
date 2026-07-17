"""B-9 (2026-07-17): EventBus.publish thread-safety.

asyncio.Queue thread-safe değildir ve executor thread'inden put_nowait loop'u
uyandırmaz — bot thread'inin position_opened event'i dashboard WS'ine bir
sonraki loop uyanışına kadar (30 sn'ye dek) gecikiyordu; ws.py'nin iptal
ettiği get() waiter'ıyla yarışta InvalidStateError event'i düşürebiliyordu.
Fix: loop-dışı publish call_soon_threadsafe ile loop thread'ine aktarılır.
"""
import asyncio
import threading

import pytest

from backend.events import EventBus


async def test_cross_thread_publish_delivers_and_wakes_loop():
    bus = EventBus()
    q = await bus.subscribe()

    def worker():
        bus.publish("position_opened", symbol="ETH/USDT")

    t = threading.Thread(target=worker)
    t.start()
    # Loop uyandırılmazsa bu await timeout'a düşer (eski davranışta yalnız
    # başka bir loop aktivitesi tesadüfen uyandırırdı).
    evt = await asyncio.wait_for(q.get(), timeout=2.0)
    t.join()
    assert evt.type == "position_opened"
    assert evt.payload["symbol"] == "ETH/USDT"


async def test_delivery_happens_on_loop_thread():
    bus = EventBus()
    await bus.subscribe()
    loop_thread = threading.get_ident()
    seen = {}

    orig = bus._deliver
    def spy(evt):
        seen["thread"] = threading.get_ident()
        orig(evt)
    bus._deliver = spy

    t = threading.Thread(target=lambda: bus.publish("x"))
    t.start(); t.join()
    # call_soon_threadsafe callback'i loop thread'inde koşana kadar bekle
    await asyncio.sleep(0.05)
    assert seen.get("thread") == loop_thread, (
        "teslimat publisher thread'inde koştu (thread-safe değil)")


def test_publish_without_loop_still_direct():
    """Loop hiç kurulmadıysa (unit testler) eski senkron davranış korunur."""
    bus = EventBus()
    bus.publish("orphan_event", a=1)  # raise etmemeli


async def test_on_loop_publish_stays_synchronous():
    """Loop üzerinde publish anında teslim eder (davranış değişmedi)."""
    bus = EventBus()
    q = await bus.subscribe()
    bus.publish("sync_event")
    assert q.qsize() == 1
