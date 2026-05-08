"""Grid search — expansion, hashing, checkpoint/resume.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §9.4
"""
import json
import pytest

from backtest.grid import expand_grid, config_hash, GridRunner


def test_grid_expansion_2d():
    base = {"risk": {"min_confluence": 50}, "safety": {"max_position_notional_pct": 3.33}}
    grid = {
        "risk.min_confluence": [40, 50, 60],
        "safety.max_position_notional_pct": [2.0, 5.0],
    }
    configs = list(expand_grid(base, grid))
    assert len(configs) == 6  # 3 × 2

    confluences = sorted({c["risk"]["min_confluence"] for c in configs})
    assert confluences == [40, 50, 60]
    notional_pcts = sorted({c["safety"]["max_position_notional_pct"] for c in configs})
    assert notional_pcts == [2.0, 5.0]


def test_config_hash_stable():
    cfg1 = {"a": 1, "b": {"c": 2}}
    cfg2 = {"b": {"c": 2}, "a": 1}  # same content, different key order
    assert config_hash(cfg1) == config_hash(cfg2)


def test_config_hash_different_for_different_configs():
    cfg1 = {"a": 1}
    cfg2 = {"a": 2}
    assert config_hash(cfg1) != config_hash(cfg2)


# Top-level function for pickling — used by test_grid_runner_skips_completed_configs
def _grid_test_run_one(cfg):
    return {"x": cfg["x"], "result": "from_pool"}


def test_grid_runner_skips_completed_configs(tmp_path):
    """Pre-populate a result file for one config_hash; grid runner skips it."""
    output_dir = tmp_path / "grid"
    runner = GridRunner(output_dir)

    # 3 configs; pre-mark middle one as complete
    cfgs = [{"x": 1}, {"x": 2}, {"x": 3}]
    middle_hash = config_hash(cfgs[1])
    (runner.configs_dir / f"{middle_hash}.json").write_text(
        '{"x": 2, "result": "from_disk"}'
    )

    results = runner.run(cfgs, run_one_fn=_grid_test_run_one, workers=2)

    by_x = {r["x"]: r["result"] for r in results}
    assert by_x[1] == "from_pool"
    assert by_x[2] == "from_disk"  # middle was skipped → loaded from existing file
    assert by_x[3] == "from_pool"
