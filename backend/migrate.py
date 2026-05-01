"""Schema migration runner — alfabetik sıralı .sql dosyalarını uygular.

Migrations directory: backend/migrations/*.sql
Tracking table:       schema_migrations (version TEXT PK, applied_at TIMESTAMPTZ)

Pure helpers (`discover_migrations`, `pending_versions`) test edilebilir;
`run_pending` asyncpg pool ile gerçek DB integration yapar.

CLI:
    python -m backend.migrate up
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import asyncpg

log = logging.getLogger("efloud.migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def discover_migrations(migrations_dir: Path) -> list[tuple[str, str]]:
    """Returns [(version, sql_text), ...] alfabetik sıralı, sadece .sql uzantılı."""
    if not migrations_dir.exists():
        return []
    files = sorted(migrations_dir.glob("*.sql"))
    return [(p.stem, p.read_text(encoding="utf-8")) for p in files]


def pending_versions(all_versions: list[str], applied: set[str]) -> list[str]:
    """all_versions sırasını koruyarak applied set'inde olmayanları döndürür."""
    return [v for v in all_versions if v not in applied]


async def _ensure_tracking_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def _get_applied(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in rows}


async def run_pending(pool: Optional[asyncpg.Pool] = None) -> None:
    """Discovers migrations and applies any not yet recorded in schema_migrations.

    DATABASE_URL env yoksa sessizce döner (no-op, graceful degrade).
    Bir pool verilmezse env'den oluşturur ve sonra kapatır.
    """
    owned_pool = False
    if pool is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            log.warning("DATABASE_URL not set — skipping migrations")
            return
        try:
            pool = await asyncpg.create_pool(dsn=url, min_size=1, max_size=2, command_timeout=30)
        except Exception as e:
            log.error(f"Cannot connect to DB for migrations: {e}")
            return
        owned_pool = True

    try:
        migrations = discover_migrations(MIGRATIONS_DIR)
        if not migrations:
            log.info("No migration files found")
            return

        all_versions = [v for v, _ in migrations]
        sql_by_version = dict(migrations)

        async with pool.acquire() as conn:
            await _ensure_tracking_table(conn)
            applied = await _get_applied(conn)

        pending = pending_versions(all_versions, applied)

        if not pending:
            log.info(f"No pending migrations ({len(applied)} already applied)")
            return

        log.info(f"Applying {len(pending)} migration(s): {pending}")
        for version in pending:
            sql = sql_by_version[version]
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        version,
                    )
            log.info(f"  ✓ {version} applied")
    finally:
        if owned_pool and pool is not None:
            await pool.close()


def _cli() -> None:
    import asyncio
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s")

    if len(sys.argv) < 2 or sys.argv[1] != "up":
        print("Usage: python -m backend.migrate up", file=sys.stderr)
        sys.exit(2)

    asyncio.run(run_pending())


if __name__ == "__main__":
    _cli()
