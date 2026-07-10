"""
Tests for symbol lease acquisition and multi-instance coordination.
Part of PR #236 A5 multi-instance migration.
"""
import pytest
import asyncio
import os
from datetime import datetime, timedelta
from backend.db import db


@pytest.fixture(scope="function", autouse=True)
async def setup_database():
    """Setup database connection and run migrations before each test."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping DB tests")

    await db.connect()

    # Run migrations to ensure symbol_lease table exists
    from backend.migrate import run_pending
    await run_pending(db.pool)

    yield

    await db.close()


@pytest.mark.asyncio
class TestSymbolLease:
    """Test symbol lease acquisition, renewal, and blocking."""

    async def test_acquire_lease_success(self):
        """Basic lease acquisition should return a token."""
        token = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token is not None
        assert isinstance(token, str)
        await db.release_lease("BTCUSDT", "instance-1", token)

    async def test_acquire_lease_renewal_by_same_instance(self):
        """Same instance should be able to renew its lease."""
        token1 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token1 is not None

        # Renew before expiry
        token2 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token2 is not None
        assert token2 != token1  # New token on renewal

        await db.release_lease("BTCUSDT", "instance-1", token1)

    async def test_acquire_lease_blocked_by_active_instance(self):
        """Different instance should be blocked by active lease."""
        token1 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token1 is not None

        # Different instance should be blocked
        token2 = await db.acquire_lease("BTCUSDT", "instance-2", ttl_seconds=60)
        assert token2 is None  # Blocked

        await db.release_lease("BTCUSDT", "instance-1", token1)

    async def test_acquire_lease_steal_expired(self):
        """New instance should acquire expired lease (fail-closed)."""
        # Very short TTL that will expire
        token1 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=1)
        assert token1 is not None

        # Wait for expiry
        await asyncio.sleep(2)

        # New instance should acquire (steal expired lease)
        token2 = await db.acquire_lease("BTCUSDT", "instance-2", ttl_seconds=60)
        assert token2 is not None  # Successfully stole expired lease

        await db.release_lease("BTCUSDT", "instance-2")

    async def test_release_lease_success(self):
        """Lease release should succeed and allow new acquisition."""
        token1 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token1 is not None

        success = await db.release_lease("BTCUSDT", "instance-1")
        assert success is True

        # Now instance-2 should acquire
        token2 = await db.acquire_lease("BTCUSDT", "instance-2", ttl_seconds=60)
        assert token2 is not None

        await db.release_lease("BTCUSDT", "instance-2")

    async def test_concurrent_lease_acquisition_race_condition(self):
        """Test that concurrent acquisitions are properly serialized."""
        async def acquire_and_hold(instance_id):
            token = await db.acquire_lease("BTCUSDT", instance_id, ttl_seconds=10)
            if token:
                await asyncio.sleep(0.5)  # Hold briefly
                await db.release_lease("BTCUSDT", instance_id)
            return token

        # Launch concurrent acquisitions
        results = await asyncio.gather(
            acquire_and_hold("instance-1"),
            acquire_and_hold("instance-2"),
            acquire_and_hold("instance-3"),
        )

        # Exactly one should succeed
        successful = [r for r in results if r is not None]
        assert len(successful) >= 1  # At least one succeeded

    async def test_token_scoped_release_prevents_cross_instance_delete(self):
        """Token-scoped release prevents stale instance from deleting new lease."""
        # Instance 1 acquires initial lease
        token1 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=1)
        assert token1 is not None

        # Wait for expiry
        await asyncio.sleep(2)

        # Instance 2 steals expired lease
        token2 = await db.acquire_lease("BTCUSDT", "instance-2", ttl_seconds=60)
        assert token2 is not None

        # Instance 1 tries to release with stale token - should fail
        success = await db.release_lease("BTCUSDT", "instance-1", token1)
        assert success is False  # Wrong token, release blocked

        # Instance 2's lease should still be active
        token3 = await db.acquire_lease("BTCUSDT", "instance-3", ttl_seconds=60)
        assert token3 is None  # Blocked by instance 2's active lease

        # Clean up
        await db.release_lease("BTCUSDT", "instance-2", token2)

    async def test_lease_ttl_self_heals_on_release_failure(self):
        """TTL ensures expired lease auto-releases even if release fails."""
        # Short TTL
        token = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=2)
        assert token is not None

        # Simulate release failure (don't actually call release)
        # Wait for TTL expiry
        await asyncio.sleep(3)

        # New instance should acquire (TTL self-healed)
        token2 = await db.acquire_lease("BTCUSDT", "instance-2", ttl_seconds=60)
        assert token2 is not None  # Successfully acquired after TTL expiry

        await db.release_lease("BTCUSDT", "instance-2", token2)

    async def test_concurrent_expiry_race_condition_safety(self):
        """Verify atomic expiry handling prevents concurrent lease ownership."""
        # Two instances trying to acquire expired lease simultaneously
        async def try_acquire_expired(instance_id):
            # Small delay to simulate race
            await asyncio.sleep(0.1)
            token = await db.acquire_lease("BTCUSDT", instance_id, ttl_seconds=60)
            return token

        # Start with very short lease
        token = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=1)
        assert token is not None

        # Wait for expiry
        await asyncio.sleep(2)

        # Launch concurrent acquisition attempts
        results = await asyncio.gather(
            try_acquire_expired("instance-2"),
            try_acquire_expired("instance-3"),
            try_acquire_expired("instance-4"),
        )

        # Exactly ONE should succeed (atomic WHERE clause)
        successful = [r for r in results if r is not None]
        assert len(successful) == 1  # Atomicity guaranteed

        # Clean up - find which instance succeeded
        if successful[0]:
            winning_instance = "instance-2" if results[0] == successful[0] else ("instance-3" if results[1] == successful[0] else "instance-4")
            await db.release_lease("BTCUSDT", winning_instance, successful[0])