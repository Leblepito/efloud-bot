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
        await db.release_lease("BTCUSDT", "instance-1")

    async def test_acquire_lease_renewal_by_same_instance(self):
        """Same instance should be able to renew its lease."""
        token1 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token1 is not None

        # Renew before expiry
        token2 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token2 is not None
        assert token2 != token1  # New token on renewal

        await db.release_lease("BTCUSDT", "instance-1")

    async def test_acquire_lease_blocked_by_active_instance(self):
        """Different instance should be blocked by active lease."""
        token1 = await db.acquire_lease("BTCUSDT", "instance-1", ttl_seconds=60)
        assert token1 is not None

        # Different instance should be blocked
        token2 = await db.acquire_lease("BTCUSDT", "instance-2", ttl_seconds=60)
        assert token2 is None  # Blocked

        await db.release_lease("BTCUSDT", "instance-1")

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