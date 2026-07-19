"""GCP Pub/Sub Signal Consumer — Phase 3.1.

Async consumer that subscribes to a GCP Pub/Sub subscription and forwards
trade signals to SafeOrchestrator.  Designed as a long-running asyncio task
that runs alongside the normal scan loop inside BotRunner.

Features:
  - Zero-import cost when google-cloud-pubsub is not installed
    (graceful degradation: warning logged, task becomes a no-op).
  - Local emulator support via PUBSUB_EMULATOR_HOST env variable.
  - Reliable delivery: message is ACK'd only after successful signal
    processing; NACK on transient errors (retried by Pub/Sub).
  - Message de-duplication: each message_id is tracked for 1 h to prevent
    double-fills on Pub/Sub "at-least-once" re-deliveries.
  - Pydantic schema validation: malformed / untrusted messages are logged
    and ACK'd (to avoid poison-pill loops) without touching the exchange.

Configuration (via config.yaml or environment variables):
  pubsub:
    project_id: "my-gcp-project"          # or EFLOUD_PUBSUB_PROJECT_ID
    subscription: "efloud-signals-sub"    # or EFLOUD_PUBSUB_SUBSCRIPTION
    enabled: true                         # set false to disable at runtime
    max_messages: 10                      # messages pulled per batch (default 10)
    pull_interval_sec: 1.0               # polling interval when using sync pull
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine import SafeOrchestrator

log = logging.getLogger("efloud.pubsub")

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schema — imported lazily so pydantic absence doesn't break startup
# ─────────────────────────────────────────────────────────────────────────────

def _build_signal_model():
    """Build and return PubSubSignal model class, or None if pydantic absent."""
    try:
        from pydantic import BaseModel, Field, field_validator

        class PubSubSignal(BaseModel):
            """Expected shape of a Pub/Sub trade signal message."""
            symbol:    str = Field(..., description="Trading pair e.g. BTC/USDT")
            direction: str = Field(..., description="LONG or SHORT")
            entry:     float
            sl:        float
            tp1:       float
            tp2:       Optional[float] = None
            size:      Optional[float] = None       # override position sizing
            source:    Optional[str]  = None        # signal origin tag
            timestamp: Optional[int]  = None        # UTC ms epoch

            @field_validator("direction")
            @classmethod
            def _direction_upper(cls, v: str) -> str:
                v = v.upper()
                if v not in ("LONG", "SHORT"):
                    raise ValueError(f"direction must be LONG or SHORT, got {v!r}")
                return v

            @field_validator("symbol")
            @classmethod
            def _symbol_not_empty(cls, v: str) -> str:
                if not v.strip():
                    raise ValueError("symbol must not be empty")
                return v.strip().upper()

        return PubSubSignal
    except ImportError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PubSubConsumer
# ─────────────────────────────────────────────────────────────────────────────

class PubSubConsumer:
    """Async Pub/Sub consumer task.

    Usage:
        consumer = PubSubConsumer(cfg=config, orchestrator=orch)
        task = asyncio.create_task(consumer.run())
        # …later…
        consumer.stop()
        await task
    """

    def __init__(
        self,
        cfg: dict,
        orchestrator: "Optional[SafeOrchestrator]" = None,
        order_manager: Any = None,
    ) -> None:
        self.cfg = cfg
        self.orchestrator = orchestrator
        self.order_manager = order_manager
        self._running = False
        self._seen_ids: dict[str, float] = {}  # message_id → ts (dedup cache)
        self._dedup_ttl_sec: float = 3600.0    # 1 h dedup window

        ps_cfg = cfg.get("pubsub", {})
        self.enabled: bool = ps_cfg.get("enabled", False)
        self.project_id: str = (
            ps_cfg.get("project_id")
            or os.environ.get("EFLOUD_PUBSUB_PROJECT_ID", "")
        )
        self.subscription: str = (
            ps_cfg.get("subscription")
            or os.environ.get("EFLOUD_PUBSUB_SUBSCRIPTION", "")
        )
        self.max_messages: int = int(ps_cfg.get("max_messages", 10))
        self.pull_interval_sec: float = float(ps_cfg.get("pull_interval_sec", 1.0))

        self._PubSubSignal = _build_signal_model()
        self._subscriber = None  # lazy-init in run()

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal the consumer coroutine to exit after the current pull."""
        self._running = False
        log.info("[PubSub] Consumer stop requested")

    async def run(self) -> None:
        """Main consumer loop — call as asyncio.create_task(consumer.run())."""
        if not self.enabled:
            log.info("[PubSub] Consumer disabled (pubsub.enabled=false) — skipping")
            return

        if not self.project_id or not self.subscription:
            log.warning(
                "[PubSub] project_id or subscription not configured — consumer idle. "
                "Set pubsub.project_id / pubsub.subscription in config.yaml or env."
            )
            return

        subscriber = self._build_subscriber()
        if subscriber is None:
            log.warning(
                "[PubSub] google-cloud-pubsub not installed or credentials missing — "
                "consumer idle. Install with: pip install google-cloud-pubsub"
            )
            return

        self._subscriber = subscriber
        sub_path = subscriber.subscription_path(self.project_id, self.subscription)
        self._running = True
        log.info(
            f"[PubSub] Consumer started — project={self.project_id!r} "
            f"subscription={self.subscription!r} emulator={bool(os.environ.get('PUBSUB_EMULATOR_HOST'))}"
        )

        loop = asyncio.get_running_loop()

        while self._running:
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: subscriber.pull(
                        request={
                            "subscription": sub_path,
                            "max_messages": self.max_messages,
                        },
                        timeout=5.0,
                    ),
                )
                for msg in response.received_messages:
                    await self._handle_message(subscriber, sub_path, msg)

            except Exception as e:
                log.warning(f"[PubSub] Pull failed: {e} — retrying in {self.pull_interval_sec}s")

            # Clean dedup cache
            now = time.monotonic()
            self._seen_ids = {
                mid: ts for mid, ts in self._seen_ids.items()
                if now - ts < self._dedup_ttl_sec
            }

            await asyncio.sleep(self.pull_interval_sec)

        log.info("[PubSub] Consumer stopped")

    # ─────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────

    def _build_subscriber(self) -> Any:
        """Build and return a google.cloud.pubsub_v1.SubscriberClient, or None."""
        # Local emulator support — set env before building client
        emulator = os.environ.get("PUBSUB_EMULATOR_HOST")
        if emulator:
            log.info(f"[PubSub] Using local emulator @ {emulator}")

        try:
            from google.cloud import pubsub_v1  # type: ignore[import]
            # Service-account JSON from env (optional; default ADC if not set)
            sa_json = os.environ.get("EFLOUD_PUBSUB_SERVICE_ACCOUNT_JSON")
            if sa_json and not emulator:
                import google.oauth2.service_account as _sa  # type: ignore[import]
                creds = _sa.Credentials.from_service_account_info(
                    json.loads(sa_json),
                    scopes=["https://www.googleapis.com/auth/pubsub"],
                )
                return pubsub_v1.SubscriberClient(credentials=creds)
            return pubsub_v1.SubscriberClient()
        except ImportError:
            return None
        except Exception as e:
            log.warning(f"[PubSub] SubscriberClient build failed: {e}")
            return None

    async def _handle_message(self, subscriber, sub_path: str, received_msg) -> None:
        """Parse, validate, deduplicate, and dispatch one Pub/Sub message."""
        msg = received_msg.message
        msg_id = msg.message_id

        # Dedup check
        if msg_id in self._seen_ids:
            log.debug(f"[PubSub] Duplicate message_id={msg_id!r} — ACK without reprocessing")
            self._ack(subscriber, sub_path, [received_msg.ack_id])
            return

        # Decode payload
        try:
            raw = json.loads(msg.data.decode("utf-8"))
        except Exception as e:
            log.warning(f"[PubSub] message_id={msg_id!r}: JSON decode failed ({e}) — ACK + discard")
            self._ack(subscriber, sub_path, [received_msg.ack_id])
            return

        # Pydantic validation
        signal = None
        if self._PubSubSignal is not None:
            try:
                signal = self._PubSubSignal(**raw)
            except Exception as e:
                log.warning(
                    f"[PubSub] message_id={msg_id!r}: schema validation failed ({e}) "
                    f"payload={raw!r} — ACK + discard (poison-pill guard)"
                )
                self._ack(subscriber, sub_path, [received_msg.ack_id])
                return
        else:
            # pydantic absent — minimal sanity check
            required = {"symbol", "direction", "entry", "sl", "tp1"}
            if not required.issubset(raw.keys()):
                log.warning(
                    f"[PubSub] message_id={msg_id!r}: missing required fields "
                    f"{required - raw.keys()} — ACK + discard"
                )
                self._ack(subscriber, sub_path, [received_msg.ack_id])
                return

        log.info(
            f"[PubSub Signal Received] id={msg_id!r} "
            f"symbol={raw.get('symbol')!r} dir={raw.get('direction')!r} "
            f"entry={raw.get('entry')} sl={raw.get('sl')} tp1={raw.get('tp1')}"
        )

        # Dispatch to order_manager (if wired)
        # _dispatch_signal contract:
        #   True  → signal placed or permanently rejected by guards → ACK
        #   False → transient error (network, exchange timeout) → NACK/retry
        if self.order_manager is not None and signal is not None:
            dispatched = await self._dispatch_signal(signal, raw)
            if dispatched:
                self._seen_ids[msg_id] = time.monotonic()
                self._ack(subscriber, sub_path, [received_msg.ack_id])
            else:
                log.warning(
                    f"[PubSub] message_id={msg_id!r}: transient dispatch failure — NACK (will retry)"
                )
                self._nack(subscriber, sub_path, [received_msg.ack_id])
        else:
            log.info(
                f"[PubSub] message_id={msg_id!r}: order_manager not wired — "
                f"signal logged but NOT executed (dry/init mode)"
            )
            self._seen_ids[msg_id] = time.monotonic()
            self._ack(subscriber, sub_path, [received_msg.ack_id])

    def _pretrade_guard(self, signal) -> Optional[str]:
        """B-7 (2026-07-18): pubsub dispatch SafeOrchestrator'ın gate zincirini
        (breaker/max-pos/confluence) TAMAMEN baypas ediyordu. Minimal fail-closed
        guard — reddedilirse sebep string'i döner (kalıcı-red → ACK-discard),
        None = geçebilir:

        1. **size>0 zorunlu.** Eski kod `size or 0.0` gönderiyordu ve "0 triggers
           auto-sizing fallback" yorumu ASILSIZDI: open_position size'ı doğrudan
           kullanır (auto-sizing yok), 0-qty emri Binance reddeder → exception →
           NACK → aynı mesaj sonsuz redeliver döngüsüne girer. Sizesiz sinyal
           artık kalıcı reddedilir (döngü yerine tek ACK-discard).
        2. **Breaker gate.** orchestrator bağlıysa, breaker OPEN değilken
           (HALTED/TRIPPED) canlı emir AÇMA — orchestrator'ın run_cycle'da
           yaptığı `breaker.check().can_trade` kontrolünün birebir aynısı.
           Breaker okunamazsa fail-closed (açma). orchestrator bağlı DEĞİLSE
           breaker kontrolü atlanır (mevcut davranış korunur; not: bu config'de
           pubsub emirleri breaker korumasızdır — operatör kararı)."""
        size = getattr(signal, "size", None)
        if size is None or size <= 0:
            return f"size<=0 ({size!r}) — auto-sizing yok, 0-qty emir reddedilir/döngü yapar"
        if self.orchestrator is not None:
            try:
                st = self.orchestrator.breaker.check()
                if not st.can_trade:
                    return f"breaker {st.state.value}: {getattr(st, 'reason', '')}"
            except Exception as e:  # breaker okunamadı → fail-closed
                return f"breaker durumu okunamadı ({e}) — fail-closed, emir açılmadı"
        return None

    async def _dispatch_signal(self, signal, raw: dict) -> bool:
        """Forward validated signal to OrderManager.

        Returns True if the signal was accepted (or permanently rejected by
        safety logic); False if a transient error should trigger NACK/retry.
        """
        if self.order_manager is None:
            return False

        # B-7: gate zinciri baypası — dispatch ÖNCESİ breaker + size guard.
        # Kalıcı-red = ACK-discard (True döner): geçersiz sinyal NACK/redeliver
        # döngüsüne girmez.
        reject = self._pretrade_guard(signal)
        if reject is not None:
            log.warning(
                f"[PubSub] Signal REJECTED (pre-trade guard): "
                f"{getattr(signal, 'symbol', '?')} — {reject}"
            )
            return True

        loop = asyncio.get_running_loop()

        # Map PubSubSignal to open_position kwargs (size guard yukarıda geçti)
        try:
            pos = await loop.run_in_executor(
                None,
                lambda: self.order_manager.open_position(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    size=signal.size,
                    entry=signal.entry,
                    sl=signal.sl,
                    tp1=signal.tp1,
                    tp2=signal.tp2,
                    confluence_details={
                        "source": signal.source,
                        "ts": signal.timestamp,
                        "pubsub_msg": True,
                    },
                ),
            )
        except Exception as e:
            log.warning(f"[PubSub] open_position raised: {e}")
            return False  # transient → NACK

        if pos is None:
            log.info(f"[PubSub] Signal for {signal.symbol} rejected by OrderManager/guards")
        else:
            log.info(f"[PubSub] ✅ Signal executed: {signal.direction} {signal.symbol} @ {signal.entry}")

        return True  # either placed or permanently rejected by guards

    # ─────────────────────────────────────────────────────────────
    # ACK / NACK helpers (sync, called from executor if needed)
    # ─────────────────────────────────────────────────────────────

    def _ack(self, subscriber, sub_path: str, ack_ids: list) -> None:
        try:
            subscriber.acknowledge(
                request={"subscription": sub_path, "ack_ids": ack_ids}
            )
        except Exception as e:
            log.warning(f"[PubSub] ACK failed (non-critical): {e}")

    def _nack(self, subscriber, sub_path: str, ack_ids: list) -> None:
        try:
            subscriber.modify_ack_deadline(
                request={
                    "subscription": sub_path,
                    "ack_ids": ack_ids,
                    "ack_deadline_seconds": 0,
                }
            )
        except Exception as e:
            log.warning(f"[PubSub] NACK failed (non-critical): {e}")
