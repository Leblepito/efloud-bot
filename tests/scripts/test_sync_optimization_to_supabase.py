from __future__ import annotations

import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from scripts import sync_optimization_to_supabase

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def dummy_tsv(tmp_path) -> Path:
    tsv_content = (
        "timestamp\tmin_confluence\trisk_per_trade_pct\trecency_bars\tmin_rr\t"
        "total_return_pct\tmax_drawdown_pct\tsharpe_like\tfitness\tstatus\n"
        "2026-05-26T12:00:00\t60\t1.0000\t35\t1.50\t12.50\t4.20\t1.40\t1.5750\tkeep\n"
        "2026-05-26T12:05:00\t70\t2.0000\t40\t2.00\t0.00\t0.00\t0.00\t0.0000\tcrash\n"
    )
    tsv_path = tmp_path / "results.tsv"
    tsv_path.write_text(tsv_content, encoding="utf-8")
    return tsv_path


@pytest.mark.asyncio
async def test_create_table_if_not_exists():
    mock_conn = AsyncMock()
    await sync_optimization_to_supabase.create_table_if_not_exists(mock_conn)
    mock_conn.execute.assert_called_once()
    assert "CREATE TABLE IF NOT EXISTS strategy_optimization_results" in mock_conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_sync_tsv_to_supabase(dummy_tsv):
    mock_conn = AsyncMock()
    
    with patch("asyncpg.connect", return_value=mock_conn) as mock_connect:
        await sync_optimization_to_supabase.sync_tsv_to_supabase(dummy_tsv, "postgresql://user:pass@host/db")
        
        # Connect should be called with correct URL
        mock_connect.assert_called_once_with("postgresql://user:pass@host/db")
        
        # Execute should be called to create table, and then for each valid TSV row (2 rows)
        assert mock_conn.execute.call_count == 3  # 1 for table creation + 2 for rows insert
        
        # Check close was called
        mock_conn.close.assert_called_once()
