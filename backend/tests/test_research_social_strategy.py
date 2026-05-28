"""Tests for the social strategy research runner safety envelope."""
from __future__ import annotations

import yaml

from backend.social.archive import append_doctrine_snapshot


def _write_base_config(path):
    path.write_text(
        yaml.dump(
            {
                "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
                "engine": {"smc_version": "v1", "social_research": {}},
            }
        ),
        encoding="utf-8",
    )


def _write_archive(path):
    append_doctrine_snapshot(
        path,
        {
            "id": "tg-1",
            "source": "telegram",
            "content": "BTC 1D bullish MSB OTE FVG liquidity sweep TP1 BE",
            "timestamp": "2026-05-28T00:00:00Z",
        },
        {
            "feed_id": "tg-1",
            "symbols": ["BTC/USDT"],
            "timeframes": ["1d"],
            "bias": "bullish",
            "structure_terms": ["MSB"],
            "zones": ["OTE", "FVG"],
            "liquidity_terms": ["liquidity_sweep"],
            "risk_terms": ["risk_management"],
        },
    )


def test_run_research_generates_candidate_configs_and_no_promotion_manifest(tmp_path):
    from scripts.research_social_strategy import run_research

    archive = tmp_path / "state" / "social_doctrine.jsonl"
    base_config = tmp_path / "configs" / "base.yaml"
    candidates_dir = tmp_path / "configs" / "candidates"
    reports_dir = tmp_path / "reports" / "social_research"
    base_config.parent.mkdir(parents=True)
    _write_base_config(base_config)
    _write_archive(archive)

    manifest = run_research(
        symbols="BTC/USDT,ETH/USDT",
        period_days=180,
        base_config_path=str(base_config),
        state_path=archive,
        candidates_dir=candidates_dir,
        reports_dir=reports_dir,
        execute_backtests=False,
    )

    assert manifest["research_only"] is True
    assert manifest["no_promotion"] is True
    assert len(manifest["hypotheses"]) == 3
    assert all(item["no_promotion"] is True for item in manifest["hypotheses"])
    assert all(str(candidates_dir) in item["candidate_config"] for item in manifest["hypotheses"])
    assert (reports_dir / "latest_social_research_manifest.yaml").exists()

    candidate_text = (candidates_dir / "candidate_social_ote_fvg_htf_bias_v1.yaml").read_text(
        encoding="utf-8"
    )
    assert "NO_PROMOTION" in candidate_text
    assert "require_htf_structure: true" in candidate_text


def test_run_research_refuses_protected_production_config(tmp_path):
    from scripts.research_social_strategy import run_research

    protected = tmp_path / "config.yaml"
    _write_base_config(protected)

    try:
        run_research("BTC/USDT", 30, str(protected), execute_backtests=False)
    except ValueError as exc:
        assert "Refusing protected production file" in str(exc)
    else:
        raise AssertionError("run_research should refuse production config.yaml")
