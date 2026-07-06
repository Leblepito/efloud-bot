"""Locks the social-hypothesis tagging on the backtest compare path.

Covers Task 5 of docs/superpowers/plans/2026-05-28-social-learning-
backtest-frontend.md and the contract used by docs/runbooks/social-
research-promotion.md Gate 2.

Three independent surfaces are pinned here:

1. ``run_v1_v2_comparison`` accepts ``hypothesis`` / ``doctrine_tags``
   and echoes them into the report.
2. The ``compare`` CLI subparser accepts ``--hypothesis`` and exposes it
   as ``args.hypothesis``.
3. ``generate_hypotheses`` emits the exact ``id`` + ``doctrine_tags``
   contract that ``cmd_compare`` reads when resolving the flag.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from backtest.cli import build_parser
from backtest.comparison import run_v1_v2_comparison
from backend.social.hypotheses import generate_hypotheses


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def synthetic_data():
    rng = np.random.default_rng(11)
    n_15m = 400
    idx_15m = pd.date_range("2025-01-01", periods=n_15m, freq="15min", tz="UTC")
    idx_4h = pd.date_range("2025-01-01", periods=n_15m // 16 + 1, freq="4h", tz="UTC")
    idx_12h = pd.date_range("2025-01-01", periods=n_15m // 48 + 2, freq="12h", tz="UTC")
    idx_1d = pd.date_range("2025-01-01", periods=max(n_15m // 96 + 2, 5), freq="1D", tz="UTC")

    def make_df(idx):
        closes = 100 + np.cumsum(rng.normal(0, 0.5, len(idx)))
        return pd.DataFrame({
            "open": closes,
            "high": closes + 0.3,
            "low": closes - 0.3,
            "close": closes,
            "volume": 1000.0,
        }, index=idx)

    return {
        "ETH/USDT": {
            "4h": make_df(idx_4h),
            "12h": make_df(idx_12h),
            "15m": make_df(idx_15m),
            "1d": make_df(idx_1d),
        }
    }


def test_report_carries_hypothesis_and_doctrine_tags(base_config, synthetic_data):
    report = run_v1_v2_comparison(
        symbols=["ETH/USDT"],
        data=synthetic_data,
        config=base_config,
        hypothesis="social_ote_fvg_htf_bias_v1",
        doctrine_tags=["MSB", "OTE", "FVG", "HTF_BIAS"],
    )
    assert report["hypothesis"] == "social_ote_fvg_htf_bias_v1"
    assert report["doctrine_tags"] == ["MSB", "OTE", "FVG", "HTF_BIAS"]


def test_report_defaults_hypothesis_fields_to_none(base_config, synthetic_data):
    report = run_v1_v2_comparison(
        symbols=["ETH/USDT"], data=synthetic_data, config=base_config
    )
    assert report["hypothesis"] is None
    assert report["doctrine_tags"] is None


def test_compare_cli_accepts_hypothesis_flag():
    parser = build_parser()
    args = parser.parse_args([
        "compare",
        "--config", "configs/config.phase2_1k.yaml",
        "--symbols", "ETH/USDT",
        "--period-days", "7",
        "--hypothesis", "social_ote_fvg_htf_bias_v1",
    ])
    assert args.cmd == "compare"
    assert args.hypothesis == "social_ote_fvg_htf_bias_v1"


def test_compare_cli_defaults_hypothesis_to_none():
    parser = build_parser()
    args = parser.parse_args([
        "compare",
        "--config", "configs/config.phase2_1k.yaml",
        "--symbols", "ETH/USDT",
        "--period-days", "7",
    ])
    assert args.hypothesis is None


def test_generated_hypothesis_contract_matches_cli_resolver():
    """``cmd_compare`` looks each ``--hypothesis`` ID up in the output of
    ``generate_hypotheses`` and extracts ``doctrine_tags``. If either field
    is renamed or removed, the live CLI silently degrades to ``None`` tags
    even though the lookup succeeded. Pin both keys here."""
    doctrines = [
        {
            "symbols": ["BTC/USDT"],
            "timeframes": ["1d"],
            "bias": "bullish",
            "structure_terms": ["MSB"],
            "zones": ["OTE", "FVG"],
            "liquidity_terms": [],
            "risk_terms": [],
        },
        {
            "symbols": ["ETH/USDT"],
            "timeframes": ["4h"],
            "bias": "bullish",
            "structure_terms": ["MSB"],
            "zones": ["FVG"],
            "liquidity_terms": ["liquidity_sweep"],
            "risk_terms": ["risk_management"],
        },
    ]
    hypotheses = generate_hypotheses(doctrines)
    ids = {h["id"] for h in hypotheses}
    assert "social_ote_fvg_htf_bias_v1" in ids
    for h in hypotheses:
        assert "id" in h and isinstance(h["id"], str)
        assert "doctrine_tags" in h
        assert isinstance(h["doctrine_tags"], list)
        assert all(isinstance(tag, str) for tag in h["doctrine_tags"])


def test_cli_resolver_extracts_doctrine_tags_from_archive(tmp_path, monkeypatch):
    """End-to-end-ish: write a synthetic doctrine archive, invoke the same
    resolution code path that ``cmd_compare`` uses, and assert the resolved
    tags match what ``generate_hypotheses`` emitted for that ID. This locks
    the cli.py:172-208 resolution sequence against silent contract drift."""
    archive_path = tmp_path / "social_doctrine.jsonl"
    snapshot = {
        "doctrine": {
            "symbols": ["BTC/USDT"],
            "timeframes": ["1d"],
            "bias": "bullish",
            "structure_terms": ["MSB"],
            "zones": ["OTE", "FVG"],
            "liquidity_terms": [],
            "risk_terms": [],
        }
    }
    archive_path.write_text(__import__("json").dumps(snapshot) + "\n", encoding="utf-8")

    from backend.social.archive import load_doctrine_snapshots

    rows = load_doctrine_snapshots(str(archive_path))
    doctrines = [row.get("doctrine", {}) for row in rows if row.get("doctrine")]
    hypotheses = generate_hypotheses(doctrines)
    match = next(
        (h for h in hypotheses if h["id"] == "social_ote_fvg_htf_bias_v1"),
        None,
    )
    assert match is not None
    assert match["doctrine_tags"]
    assert "OTE" in match["doctrine_tags"]
    assert "FVG" in match["doctrine_tags"]
