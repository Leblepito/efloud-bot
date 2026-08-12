"""Senkron ccxt çağrıları event loop'u BLOKLAMAMALI (2026-08-12 audit).

İncident zinciri: panel 15s'de bir /api/positions çeker; yavaş bir Binance
çağrısı event loop'ta koşarsa /healthz dahil TÜM istekler bekler → docker
healthcheck (5s timeout, 3 retry) düşer → autoheal CANLI botu restart eder.
Bu testler yavaş exchange çağrısı sırasında loop'un nefes aldığını pinler.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

import backend.api as api_mod


BLOCK_SEC = 0.25
LOOP_BREATH_SEC = 0.10  # bloklama süresinden belirgin küçük olmalı


def _slow_sync_call(result):
    def call(*a, **kw):
        time.sleep(BLOCK_SEC)
        return result
    return call


async def _loop_breathes_during(coro) -> float:
    """coro çalışırken loop'un maksimum tick gecikmesini ölç."""
    max_gap = 0.0
    done = asyncio.Event()

    async def heartbeat():
        nonlocal max_gap
        prev = time.monotonic()
        while not done.is_set():
            await asyncio.sleep(0.01)
            now = time.monotonic()
            max_gap = max(max_gap, now - prev - 0.01)
            prev = now

    hb = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.03)  # heartbeat gerçekten tick atmaya başlasın
    work = asyncio.create_task(coro)
    try:
        await work
    finally:
        done.set()
        await hb
    return max_gap


@pytest.mark.asyncio
async def test_positions_does_not_block_loop(monkeypatch):
    fake_runner = SimpleNamespace(
        client=SimpleNamespace(
            get_open_positions=_slow_sync_call([]),
            get_price=_slow_sync_call(100.0),
        ),
        order_mgr=SimpleNamespace(_positions_snapshot=lambda: [], positions=[]),
    )
    monkeypatch.setattr(api_mod, "runner", fake_runner)

    gap = await _loop_breathes_during(api_mod.positions())
    assert gap < LOOP_BREATH_SEC, (
        f"/api/positions event loop'u {gap:.3f}s blokladı (sınır {LOOP_BREATH_SEC}s)"
    )


@pytest.mark.asyncio
async def test_orders_does_not_block_loop(monkeypatch):
    fake_runner = SimpleNamespace(
        client=SimpleNamespace(
            exchange=SimpleNamespace(fetch_open_orders=_slow_sync_call([])),
        ),
    )
    monkeypatch.setattr(api_mod, "runner", fake_runner)

    gap = await _loop_breathes_during(api_mod.orders())
    assert gap < LOOP_BREATH_SEC, (
        f"/api/orders event loop'u {gap:.3f}s blokladı (sınır {LOOP_BREATH_SEC}s)"
    )


@pytest.mark.asyncio
async def test_positions_uses_snapshot_not_live_list(monkeypatch):
    """E-3 sınıfı: bot thread'i positions listesini mutate ederken endpoint
    canlı listeyi DEĞİL snapshot'ı okumalı."""
    snapshot_called = {"n": 0}

    def snapshot():
        snapshot_called["n"] += 1
        return []

    fake_runner = SimpleNamespace(
        client=SimpleNamespace(
            get_open_positions=lambda: [],
            get_price=lambda s: 100.0,
        ),
        order_mgr=SimpleNamespace(_positions_snapshot=snapshot, positions=[]),
    )
    monkeypatch.setattr(api_mod, "runner", fake_runner)

    await api_mod.positions()
    assert snapshot_called["n"] >= 1, "/api/positions _positions_snapshot() kullanmıyor"
