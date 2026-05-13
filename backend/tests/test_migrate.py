"""Migration runner tests — pure logic isolated from DB.

DB integration (asyncpg) ayrı bir smoke test ile doğrulanır.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_discover_migrations_returns_sorted_tuples(tmp_path: Path):
    (tmp_path / "002_add_index.sql").write_text("CREATE INDEX foo;", encoding="utf-8")
    (tmp_path / "001_init.sql").write_text("CREATE TABLE bar();", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not sql", encoding="utf-8")

    from backend.migrate import discover_migrations
    result = discover_migrations(tmp_path)

    assert len(result) == 2
    assert result[0] == ("001_init", "CREATE TABLE bar();")
    assert result[1] == ("002_add_index", "CREATE INDEX foo;")


def test_discover_migrations_empty_dir(tmp_path: Path):
    from backend.migrate import discover_migrations
    assert discover_migrations(tmp_path) == []


def test_discover_migrations_skips_non_sql_files(tmp_path: Path):
    (tmp_path / "001_a.sql").write_text("A;", encoding="utf-8")
    (tmp_path / "readme.md").write_text("# notes", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("k: v", encoding="utf-8")

    from backend.migrate import discover_migrations
    result = discover_migrations(tmp_path)
    assert len(result) == 1
    assert result[0][0] == "001_a"


def test_pending_versions_returns_unapplied():
    from backend.migrate import pending_versions
    all_versions = ["001_init", "002_add_index", "003_alter"]
    applied = {"001_init", "002_add_index"}
    assert pending_versions(all_versions, applied) == ["003_alter"]


def test_pending_versions_preserves_order():
    from backend.migrate import pending_versions
    assert pending_versions(["001", "002", "003"], {"001"}) == ["002", "003"]


def test_pending_versions_empty_when_all_applied():
    from backend.migrate import pending_versions
    assert pending_versions(["001", "002"], {"001", "002"}) == []


def test_pending_versions_handles_unknown_applied():
    """Applied set'inde olup all_versions'da olmayan versiyon (manuel insert?) ignore edilir."""
    from backend.migrate import pending_versions
    assert pending_versions(["001", "002"], {"001", "999_orphan"}) == ["002"]


@pytest.mark.asyncio
async def test_run_pending_no_database_url_returns_silently(monkeypatch, caplog):
    """DATABASE_URL set değilse run_pending sessizce döner (graceful degrade)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from backend.migrate import run_pending
    # Should not raise
    await run_pending()


def test_migration_006_enables_rls_on_trade_audits():
    """Migration 006 must be present in the repo and must enable RLS on
    public.trade_audits — closes the Supabase advisor warning that
    flagged this table as anon-readable after migration 005 created it
    but missed the migration-004 RLS lockdown."""
    from backend.migrate import discover_migrations
    migrations = discover_migrations(Path("backend/migrations"))
    versions = [v for v, _ in migrations]
    assert "006_enable_trade_audits_rls" in versions, (
        "006_enable_trade_audits_rls.sql is missing from backend/migrations/"
    )
    sql = next(s for v, s in migrations if v == "006_enable_trade_audits_rls").upper()
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "TRADE_AUDITS" in sql
