"""Phase 3.1: GCP Pub/Sub Signal Consumer unit tests.

All tests use mocked google.cloud.pubsub_v1 — no real GCP connection needed.
Covers:
  - Consumer is a no-op when pubsub.enabled=false
  - Consumer is a no-op when project_id / subscription not configured
  - Consumer is a no-op when google-cloud-pubsub is not installed
  - Valid signals are parsed, dispatched, and ACK'd
  - Invalid JSON payloads are ACK'd (poison-pill guard)
  - Schema-invalid signals are ACK'd (poison-pill guard)
  - Duplicate message_ids are ACK'd without dispatching twice
  - Transient dispatch errors trigger NACK (retry semantics)
  - consumer.stop() causes run() to exit cleanly
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pubsub_consumer import PubSubConsumer


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_cfg(enabled: bool = True, project: str = "proj", sub: str = "sub") -> dict:
    return {
        "pubsub": {
            "enabled": enabled,
            "project_id": project,
            "subscription": sub,
            "pull_interval_sec": 0.0,   # no sleep in tests
            "max_messages": 5,
        }
    }


def _make_received_msg(data: dict, msg_id: str = "msg-1") -> MagicMock:
    """Build a mock ReceivedMessage with given JSON data and message_id."""
    rm = MagicMock()
    rm.ack_id = f"ack-{msg_id}"
    rm.message = MagicMock()
    rm.message.message_id = msg_id
    rm.message.data = json.dumps(data).encode("utf-8")
    return rm


def _valid_signal_data(**overrides) -> dict:
    # B-7 (2026-07-18): geçerli-dispatchable bir sinyal artık size TAŞIR. Eski
    # fixture size'sızdı ve "size-less sinyal execute olur" bug'lı varsayımını
    # kodluyordu (mock olduğu için Binance'in 0-qty reddini görmüyordu). Pre-trade
    # guard size<=0'ı kalıcı reddettiği için base'e gerçekçi size eklendi; size-
    # less/zero reddi ayrı testte (test_dispatch_rejects_nonpositive_size).
    base = {
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "entry": 60000.0,
        "sl": 58000.0,
        "tp1": 63000.0,
        "size": 0.01,
    }
    base.update(overrides)
    return base


def _make_subscriber(received_msgs: list, *, pull_raises=None) -> MagicMock:
    """Build a mock SubscriberClient."""
    sub = MagicMock()
    sub.subscription_path.return_value = "projects/proj/subscriptions/sub"

    if pull_raises:
        sub.pull.side_effect = pull_raises
    else:
        response = MagicMock()
        response.received_messages = received_msgs
        sub.pull.return_value = response

    sub.acknowledge = MagicMock()
    sub.modify_ack_deadline = MagicMock()
    return sub


# ─────────────────────────────────────────────────────────────────────────────
# Enabled / disabled gates
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consumer_disabled_is_noop():
    """pubsub.enabled=false → run() returns immediately without pulling."""
    consumer = PubSubConsumer(cfg=_make_cfg(enabled=False))
    with patch.object(consumer, "_build_subscriber") as mock_build:
        await consumer.run()
        mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_missing_project_is_noop():
    """Missing project_id → run() returns without building subscriber."""
    consumer = PubSubConsumer(cfg=_make_cfg(project="", sub="my-sub"))
    with patch.object(consumer, "_build_subscriber") as mock_build:
        await consumer.run()
        mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_missing_subscription_is_noop():
    """Missing subscription → run() returns without building subscriber."""
    consumer = PubSubConsumer(cfg=_make_cfg(project="my-project", sub=""))
    with patch.object(consumer, "_build_subscriber") as mock_build:
        await consumer.run()
        mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_no_pubsub_library_is_noop():
    """google-cloud-pubsub absent → run() warns and returns (no crash)."""
    consumer = PubSubConsumer(cfg=_make_cfg())
    with patch.object(consumer, "_build_subscriber", return_value=None):
        await consumer.run()  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Valid signal → ACK
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_signal_dispatched_and_acked():
    """A well-formed signal is dispatched to order_manager and ACK'd."""
    mock_pos = MagicMock()
    order_mgr = MagicMock()
    order_mgr.open_position.return_value = mock_pos

    # B-7h: dispatch artık orchestrator'sız TAM fail-closed → success-path
    # testleri prod kablolamasını (bot_runner orchestrator geçirir) yansıtır.
    consumer = PubSubConsumer(cfg=_make_cfg(), order_manager=order_mgr,
                              orchestrator=_orch(_Breaker()))

    received = [_make_received_msg(_valid_signal_data())]
    subscriber = _make_subscriber(received)

    # Patch _build_subscriber to return our mock, then stop after one pull
    with patch.object(consumer, "_build_subscriber", return_value=subscriber):
        # Run one iteration then stop
        async def _run_once():
            # Manually trigger one message handling
            await consumer._handle_message(
                subscriber,
                "projects/proj/subscriptions/sub",
                received[0],
            )
        await _run_once()

    subscriber.acknowledge.assert_called_once()
    order_mgr.open_position.assert_called_once()


@pytest.mark.asyncio
async def test_valid_signal_with_tp2_dispatched():
    """Signal with optional tp2 and size is forwarded to order_manager."""
    order_mgr = MagicMock()
    order_mgr.open_position.return_value = MagicMock()

    consumer = PubSubConsumer(cfg=_make_cfg(), order_manager=order_mgr,
                              orchestrator=_orch(_Breaker()))  # B-7h: prod kablolaması
    received = [_make_received_msg(_valid_signal_data(tp2=66000.0, size=0.01))]
    subscriber = _make_subscriber(received)

    with patch.object(consumer, "_build_subscriber", return_value=subscriber):
        await consumer._handle_message(
            subscriber, "projects/proj/subscriptions/sub", received[0]
        )

    order_mgr.open_position.assert_called_once()
    call_kwargs = order_mgr.open_position.call_args.kwargs
    assert call_kwargs.get("tp2") == 66000.0


# ─────────────────────────────────────────────────────────────────────────────
# Poison-pill guard — invalid payloads are ACK'd (not NACK'd)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_json_acked_not_retried():
    """Non-JSON data is ACK'd to avoid infinite retry loops."""
    consumer = PubSubConsumer(cfg=_make_cfg())
    subscriber = _make_subscriber([])

    rm = MagicMock()
    rm.ack_id = "ack-bad"
    rm.message = MagicMock()
    rm.message.message_id = "bad-json"
    rm.message.data = b"not-json-at-all!!!"

    await consumer._handle_message(subscriber, "proj/sub", rm)

    subscriber.acknowledge.assert_called_once()
    subscriber.modify_ack_deadline.assert_not_called()


@pytest.mark.asyncio
async def test_schema_invalid_signal_acked():
    """Signal missing required fields is ACK'd (poison-pill guard)."""
    consumer = PubSubConsumer(cfg=_make_cfg())
    subscriber = _make_subscriber([])

    bad_data = {"symbol": "BTC/USDT"}  # missing direction, entry, sl, tp1
    rm = _make_received_msg(bad_data, msg_id="bad-schema")

    await consumer._handle_message(subscriber, "proj/sub", rm)

    subscriber.acknowledge.assert_called_once()
    subscriber.modify_ack_deadline.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_direction_acked():
    """Signal with invalid direction is schema-rejected and ACK'd."""
    consumer = PubSubConsumer(cfg=_make_cfg())
    subscriber = _make_subscriber([])

    bad = _valid_signal_data(direction="UP")  # invalid
    rm = _make_received_msg(bad, msg_id="bad-direction")

    await consumer._handle_message(subscriber, "proj/sub", rm)
    subscriber.acknowledge.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_message_id_acked_without_redispatch():
    """Second delivery of same message_id is ACK'd without calling order_manager again."""
    order_mgr = MagicMock()
    order_mgr.open_position.return_value = MagicMock()

    consumer = PubSubConsumer(cfg=_make_cfg(), order_manager=order_mgr,
                              orchestrator=_orch(_Breaker()))  # B-7h: prod kablolaması
    subscriber = _make_subscriber([])
    sub_path = "proj/sub"

    rm1 = _make_received_msg(_valid_signal_data(), msg_id="dedup-1")
    rm2 = _make_received_msg(_valid_signal_data(), msg_id="dedup-1")  # same id

    await consumer._handle_message(subscriber, sub_path, rm1)
    await consumer._handle_message(subscriber, sub_path, rm2)

    # open_position called only ONCE despite two deliveries
    assert order_mgr.open_position.call_count == 1
    # Both ACK'd
    assert subscriber.acknowledge.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Transient error → NACK
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transient_dispatch_error_causes_nack():
    """If open_position raises a transient error, message is NACK'd for retry."""
    order_mgr = MagicMock()
    order_mgr.open_position.side_effect = ConnectionError("exchange timeout")

    consumer = PubSubConsumer(cfg=_make_cfg(), order_manager=order_mgr,
                              orchestrator=_orch(_Breaker()))  # B-7h: prod kablolaması
    subscriber = _make_subscriber([])

    rm = _make_received_msg(_valid_signal_data(), msg_id="transient")

    await consumer._handle_message(subscriber, "proj/sub", rm)

    subscriber.modify_ack_deadline.assert_called_once()  # NACK
    subscriber.acknowledge.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Stop signal
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_exits_run_loop():
    """consumer.stop() should cause run() to exit within a short time."""
    consumer = PubSubConsumer(cfg=_make_cfg())

    # Subscriber that returns empty responses quickly
    empty_response = MagicMock()
    empty_response.received_messages = []
    mock_sub = MagicMock()
    mock_sub.subscription_path.return_value = "proj/sub"
    mock_sub.pull.return_value = empty_response
    mock_sub.acknowledge = MagicMock()
    mock_sub.modify_ack_deadline = MagicMock()

    with patch.object(consumer, "_build_subscriber", return_value=mock_sub):
        task = asyncio.create_task(consumer.run())
        await asyncio.sleep(0.05)   # let it start
        consumer.stop()
        await asyncio.wait_for(task, timeout=3.0)  # must finish promptly

    assert not consumer._running


# ─────────────────────────────────────────────────────────────────────────────
# B-7 (2026-07-18): pre-trade guard — breaker + size (gate-bypass fix)
# ─────────────────────────────────────────────────────────────────────────────

class _Breaker:
    def __init__(self, can_trade=True, state="OPEN", reason="", raises=False):
        self._can, self._state, self._reason, self._raises = can_trade, state, reason, raises
    def check(self, now=None):
        if self._raises:
            raise RuntimeError("breaker read boom")
        return SimpleNamespace(
            can_trade=self._can,
            state=SimpleNamespace(value=self._state),
            reason=self._reason,
        )


def _orch(breaker):
    return SimpleNamespace(breaker=breaker)


@pytest.mark.asyncio
async def test_dispatch_rejected_when_breaker_halted():
    """Breaker HALTED iken pubsub sinyali canlı emir AÇMAMALI (baypas fix).
    Kalıcı-red → True (ACK-discard), open_position çağrılmaz."""
    order_mgr = MagicMock()
    consumer = PubSubConsumer(
        cfg=_make_cfg(), order_manager=order_mgr,
        orchestrator=_orch(_Breaker(can_trade=False, state="HALTED", reason="weekly_dd")),
    )
    Signal = consumer._PubSubSignal
    sig = Signal(symbol="BTC/USDT", direction="LONG", entry=60000.0, sl=58000.0,
                 tp1=63000.0, size=0.01)
    ok = await consumer._dispatch_signal(sig, {})
    assert ok is True                       # ACK-discard, NACK/retry döngüsü yok
    order_mgr.open_position.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_proceeds_when_breaker_open_and_sized():
    order_mgr = MagicMock()
    order_mgr.open_position.return_value = MagicMock()
    consumer = PubSubConsumer(
        cfg=_make_cfg(), order_manager=order_mgr,
        orchestrator=_orch(_Breaker(can_trade=True, state="OPEN")),
    )
    Signal = consumer._PubSubSignal
    sig = Signal(symbol="BTC/USDT", direction="LONG", entry=60000.0, sl=58000.0,
                 tp1=63000.0, size=0.01)
    ok = await consumer._dispatch_signal(sig, {})
    assert ok is True
    order_mgr.open_position.assert_called_once()
    assert order_mgr.open_position.call_args.kwargs["size"] == 0.01


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_size", [None, 0, 0.0, -1.0])
async def test_dispatch_rejects_nonpositive_size(bad_size):
    """size<=0/None: 'auto-sizing' yok → 0-qty Binance reddi → sonsuz redeliver.
    Artık kalıcı reddedilir (open_position çağrılmaz, tek ACK)."""
    order_mgr = MagicMock()
    consumer = PubSubConsumer(cfg=_make_cfg(), order_manager=order_mgr)  # orchestrator yok
    Signal = consumer._PubSubSignal
    sig = Signal(symbol="BTC/USDT", direction="LONG", entry=60000.0, sl=58000.0,
                 tp1=63000.0, size=bad_size)
    ok = await consumer._dispatch_signal(sig, {})
    assert ok is True
    order_mgr.open_position.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_fail_closed_when_breaker_read_raises():
    """Breaker durumu okunamıyorsa fail-closed: emir açılmaz."""
    order_mgr = MagicMock()
    consumer = PubSubConsumer(
        cfg=_make_cfg(), order_manager=order_mgr,
        orchestrator=_orch(_Breaker(raises=True)),
    )
    Signal = consumer._PubSubSignal
    sig = Signal(symbol="BTC/USDT", direction="LONG", entry=60000.0, sl=58000.0,
                 tp1=63000.0, size=0.01)
    ok = await consumer._dispatch_signal(sig, {})
    assert ok is True
    order_mgr.open_position.assert_not_called()


def test_pretrade_guard_no_orchestrator_fail_closed():
    """B-7h (2026-07-18): orchestrator yokken TAM fail-closed — size>0 olsa bile
    reddedilir. Breaker durumu DOĞRULANAMAYAN bir yoldan canlı emir açılmaz
    (eski davranış: size geçerse breaker'sız geçiyordu — koruma boşluğu)."""
    consumer = PubSubConsumer(cfg=_make_cfg(), order_manager=MagicMock())
    Signal = consumer._PubSubSignal
    sized = Signal(symbol="BTC/USDT", direction="LONG", entry=1.0, sl=0.9, tp1=1.1, size=0.5)
    sizeless = Signal(symbol="BTC/USDT", direction="LONG", entry=1.0, sl=0.9, tp1=1.1)
    assert consumer._pretrade_guard(sized) is not None, \
        "orchestrator=None → breaker doğrulanamaz → fail-closed reject"
    assert consumer._pretrade_guard(sizeless) is not None


@pytest.mark.asyncio
async def test_dispatch_no_orchestrator_rejects_and_acks():
    """B-7h dispatch seviyesi: orchestrator'sız consumer'da geçerli+size'lı
    sinyal bile emir AÇMAZ; kalıcı-red → True (ACK-discard, NACK döngüsü yok)."""
    order_mgr = MagicMock()
    consumer = PubSubConsumer(cfg=_make_cfg(), order_manager=order_mgr)
    Signal = consumer._PubSubSignal
    sig = Signal(symbol="BTC/USDT", direction="LONG", entry=60000.0, sl=58000.0,
                 tp1=63000.0, size=0.01)
    ok = await consumer._dispatch_signal(sig, {})
    assert ok is True
    order_mgr.open_position.assert_not_called()
