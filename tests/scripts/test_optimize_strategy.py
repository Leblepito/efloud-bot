from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from scripts import optimize_strategy

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "optimize_strategy.py"


@pytest.fixture()
def dummy_config(tmp_path) -> Path:
    cfg = {
        "exchange": {"name": "binance", "testnet": True},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "risk": {
            "min_confluence": 55,
            "risk_per_trade_pct": 0.75,
            "recency_bars": 40,
            "min_rr": 1.8,
        },
    }
    cfg_path = tmp_path / "config.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    return cfg_path


def test_cli_help_works():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0
    assert "--config" in result.stdout
    assert "--symbols" in result.stdout
    assert "--period-days" in result.stdout
    assert "--balance" in result.stdout
    assert "--max-dd" in result.stdout


def test_create_candidate_config(tmp_path, dummy_config):
    cand_path = tmp_path / "candidate.yaml"
    optimize_strategy.create_candidate_config(
        dummy_config,
        cand_path,
        min_confluence=75,
        risk_per_trade_pct=1.5,
        recency_bars=50,
        min_rr=2.0,
    )

    assert cand_path.exists()
    with open(cand_path, encoding="utf-8") as f:
        res = yaml.safe_load(f)

    assert res["risk"]["min_confluence"] == 75
    assert res["risk"]["risk_per_trade_pct"] == 1.5
    assert res["risk"]["recency_bars"] == 50
    assert res["risk"]["min_rr"] == 2.0
    # verify other keys preserved
    assert res["exchange"]["name"] == "binance"
    assert res["timeframes"]["htf"] == "4h"


def test_calculate_fitness():
    # 1. Normal case: Sharpe > 0, return > 0, drawdown < limit
    res1 = {
        "total_return_pct": 15.5,
        "max_drawdown_pct": 4.5,
        "sharpe_like": 1.8,
    }
    fit1, ret1, dd1, sharpe1, status1 = optimize_strategy.calculate_fitness(res1, max_drawdown_limit=12.0)
    assert status1 == "keep"
    assert fit1 == round(1.8 * (1 + 15.5 / 100), 4)

    # 2. Drawdown constraint exceeded case
    res2 = {
        "total_return_pct": 35.0,
        "max_drawdown_pct": 14.2,  # > 12.0
        "sharpe_like": 3.5,
    }
    fit2, ret2, dd2, sharpe2, status2 = optimize_strategy.calculate_fitness(res2, max_drawdown_limit=12.0)
    assert status2 == "discard_drawdown_exceeded"
    assert fit2 == 0.0

    # 3. Sharpe negative case
    res3 = {
        "total_return_pct": -8.5,
        "max_drawdown_pct": 9.2,
        "sharpe_like": -0.8,
    }
    fit3, ret3, dd3, sharpe3, status3 = optimize_strategy.calculate_fitness(res3, max_drawdown_limit=12.0)
    assert status3 == "keep"
    assert fit3 == 0.0  # max(0, negative value)


def test_find_latest_portfolio_result(tmp_path):
    search_dir = tmp_path / "reports" / "backtests"
    search_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create a dummy result file not matching 'portfolio' name
    dir1 = search_dir / "2026-05-26_BTC_USDT_365d_abcdef"
    dir1.mkdir()
    file1 = dir1 / "result.json"
    file1.write_text(json.dumps({"sharpe_like": 1.5, "max_drawdown_pct": 5.0}))

    res = optimize_strategy.find_latest_portfolio_result(search_dir, timestamp_cutoff=0.0)
    assert res is None  # because folder name does not contain 'portfolio'

    # 2. Create a dummy portfolio result file
    dir2 = search_dir / "2026-05-26_portfolio_7sym_180d_run123"
    dir2.mkdir()
    file2 = dir2 / "result.json"
    file2.write_text(json.dumps({"total_return_pct": 20.0, "sharpe_like": 2.2, "max_drawdown_pct": 6.0}))

    res = optimize_strategy.find_latest_portfolio_result(search_dir, timestamp_cutoff=0.0)
    assert res is not None
    assert res["sharpe_like"] == 2.2
    assert res["total_return_pct"] == 20.0


def test_append_to_tsv(tmp_path):
    tsv_path = tmp_path / "optimization" / "results.tsv"

    optimize_strategy.append_to_tsv(
        tsv_path,
        min_confluence=60,
        risk_per_trade_pct=1.0,
        recency_bars=35,
        min_rr=1.5,
        total_return_pct=12.5,
        max_drawdown_pct=4.2,
        sharpe_like=1.4,
        fitness=1.575,
        status="keep",
    )

    assert tsv_path.exists()
    lines = tsv_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2  # header + 1 row
    assert "timestamp" in lines[0]
    assert "1.5750" in lines[1]
    assert "keep" in lines[1]
