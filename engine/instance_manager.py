import logging
import os
import uuid
import asyncio
import re
import json
import time
from typing import Optional

log = logging.getLogger("efloud.instance")


class InstanceManager:
    def __init__(self, db, config: dict):
        self.db = db
        self.config = config
        self.coordination_enabled = config.get("INSTANCE_COORDINATION_ENABLED", False)

        # Validation when coordination enabled
        iid = str(config.get("INSTANCE_ID", "")).strip()
        if self.coordination_enabled:
            if not re.match(r"^[A-Za-z0-9\-_]{1,64}$", iid):
                raise ValueError("INSTANCE_ID required (alnum/-/_ ≤64) when coordination enabled")

        self.instance_id = iid or f"bot-{uuid.uuid4().hex[:8]}"

        # Symbol validation
        raw = str(config.get("INSTANCE_SYMBOLS", "")).strip()
        self.symbols = [s.strip() for s in raw.split(",") if re.match(r"^[A-Z0-9]+$", s.strip())]

        # Instance limit validation
        self.max_instances = int(config.get("INSTANCE_MAX_INSTANCES", 1))
        if not 1 <= self.max_instances <= 10:
            raise ValueError("INSTANCE_MAX_INSTANCES must be 1-10")

        # Timeout configuration (standardized, not magic numbers)
        self.acquire_timeout_sec = float(config.get("INSTANCE_ACQUIRE_TIMEOUT_SEC", 1.5))
        self.release_timeout_sec = float(config.get("INSTANCE_RELEASE_TIMEOUT_SEC", 3.0))
        self.lease_duration_sec = int(config.get("INSTANCE_LEASE_DURATION_SEC", 30))

        self._registered = False
        self._loop = None
        self._active_leases = {}  # symbol -> lease_token tracking (HIGH-3/HIGH-5)

    def set_event_loop(self, loop):
        self._loop = loop

    def _alert(self, event: str, detail: str) -> None:
        """Structured alert sink. `ALERT` prefix + JSON for log-based monitoring."""
        log.critical(f"ALERT event={event} detail={detail}")
        try:
            with open("state/alerts.jsonl", "a") as f:
                f.write(json.dumps({
                    "ts": time.time(), "event": event,
                    "instance_id": self.instance_id, "detail": detail,
                }) + "\n")
        except Exception:
            pass  # never let alerting crash the trade path

    def register(self) -> bool:
        if self._registered:
            return True
        if self._sync_active_instance_count() >= self.max_instances:
            log.error(f"Instance limit reached ({self.max_instances}). Startup blocked.")
            return False
        if self._sync_register_instance():
            self._registered = True
            log.info(f"Instance {self.instance_id} registered for {self.symbols}")
            return True
        return False

    async def heartbeat(self) -> bool:
        return await self.db.heartbeat(self.instance_id)

    async def acquire_symbol(self, symbol: str):
        token = await self.db.acquire_lease(
            symbol, self.instance_id, self.lease_duration_sec
        )
        if token:
            return token
        log.warning(f"Lease denied for {symbol} - held by another instance")
        return None

    async def release_symbol(self, symbol: str) -> bool:
        return await self.db.release_symbol(symbol, self.instance_id)

    def sync_acquire_symbol(self, symbol: str) -> bool:
        # Coordination disabled by default - fail-open for trading safety
        if not self.coordination_enabled:
            return True

        # Event loop check - critical error for coordination path (BLOCK-1)
        if not self._loop or self._loop.is_closed():
            self._alert("coord_event_loop_missing",
                       f"coordination enabled but loop missing — blocking {symbol}")
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.acquire_symbol(symbol), self._loop
            )
            lease_token = future.result(timeout=self.acquire_timeout_sec)
            if lease_token is not None:
                self._active_leases[symbol] = lease_token   # track token (Fix HIGH-3/5)
                return True
            return False   # legit contention — another instance holds it
        except asyncio.TimeoutError:
            self._alert("coord_db_timeout", f"lease acquire {symbol} timed out — blocking")
            return False
        except Exception as e:
            self._alert("coord_db_error", f"lease acquire {symbol} failed ({e}) — blocking")
            return False

    def sync_release_symbol(self, symbol: str) -> bool:
        if not self.coordination_enabled:
            return True
        if not self._loop:
            return True
        token = self._active_leases.get(symbol)
        if token is None:
            return True   # nothing to release
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.db.release_lease(symbol, self.instance_id, token), self._loop
            )
            ok = future.result(timeout=self.release_timeout_sec)
            self._active_leases.pop(symbol, None)
            return ok
        except asyncio.CancelledError:
            # E-6 fix (2026-07-17): CancelledError Python ≥3.8'de BaseException —
            # loop shutdown release coroutine'ini iptal ederse buradaki (ve
            # run_cycle finally'sindeki) `except Exception` yakalamaz; iptal,
            # cycle'ın ASIL hatasını maskeleyerek yukarı kaçıyordu. Lease
            # server-side TTL ile düşer; başarısız release olarak raporla.
            log.warning(f"Release lease {symbol} cancelled (loop shutdown)")
            return False
        except Exception as e:
            log.warning(f"Release lease {symbol} failed: {e}")
            return False

    def _sync_register_instance(self) -> bool:
        if not self._loop:
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.db.register_instance(self.instance_id, self.symbols), self._loop
            )
            return future.result(timeout=5)
        except Exception as e:
            log.warning(f"Register instance failed: {e}")
            return False

    def _sync_active_instance_count(self) -> int:
        if not getattr(self.db, "pool", None) or not self._loop:
            return 0
        try:
            async def _count():
                async with self.db.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT COUNT(*) FROM instance_registry WHERE status = 'active'"
                    )
                    return row["count"] if row else 0
            future = asyncio.run_coroutine_threadsafe(_count(), self._loop)
            return future.result(timeout=5)
        except Exception:
            return 0