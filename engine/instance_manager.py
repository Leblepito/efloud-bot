import logging
import os
import uuid
import asyncio
import re
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

        self._registered = False
        self._loop = None

    def set_event_loop(self, loop):
        self._loop = loop

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

    async def acquire_symbol(self, symbol: str) -> bool:
        token = await self.db.acquire_lease(symbol, self.instance_id)
        if token:
            return True
        log.warning(f"Lease denied for {symbol} - held by another instance")
        return False

    async def release_symbol(self, symbol: str) -> bool:
        return await self.db.release_symbol(symbol, self.instance_id)

    def sync_acquire_symbol(self, symbol: str) -> bool:
        # Coordination disabled by default - fail-open for trading safety
        if not self.coordination_enabled:
            return True

        # Event loop check - critical error for coordination path
        if not self._loop or self._loop.is_closed():
            log.critical("Coordination enabled but event loop missing — disabling coordination, single-instance fallback")
            self.coordination_enabled = False
            return True

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.acquire_symbol(symbol), self._loop
            )
            return future.result(timeout=0.5)
        except (asyncio.TimeoutError, Exception) as e:
            log.warning(f"Lease acquire {symbol} failed ({e}) — fail-open, trading continues")
            return True

    def sync_release_symbol(self, symbol: str) -> bool:
        if not self._loop:
            return True
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.release_symbol(symbol), self._loop
            )
            return future.result(timeout=5)
        except Exception as e:
            log.warning(f"Lease release failed: {e}")
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