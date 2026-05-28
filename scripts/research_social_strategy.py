"""Research runner for social strategy hypotheses.

This script automates the 'Social Learning' loop:
1. Load hypotheses generated from the social doctrine archive.
2. Produce candidate config files for each hypothesis.
3. Run `backtest.cli compare` to measure performance against baseline.

Safety: No production files are modified. Results are saved in research paths.
Usage: python -m scripts.research_social_strategy --symbols BTC/USDT --period-days 180
"""
import argparse
import logging
import sys
import yaml
import subprocess
from pathlib import Path

# Ensure project root is in path
sys.path.append(str(Path(__file__).parent.parent))

from backend.social.reports import build_social_research_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("efloud.scripts.research_social_strategy")

CANDIDATES_DIR = Path("configs/candidates")
REPORTS_DIR = Path("reports/social_research")

# Defense-in-depth (input side): the base config the runner reads from must
# never be a production-control file. The protected set is intentionally
# *narrower* than PROTECTED_OUTPUT_NAMES below: it excludes the live
# production config (`config.phase2_1k.yaml`) because that file is the
# legitimate base for research runs. The other three names exist on disk
# only as live ops surfaces and have no business being read as a research
# base.
PROTECTED_CONFIG_NAMES = frozenset({"config.yaml", "docker-compose.prod.yml", ".env"})

# Defense-in-depth (output side): every write path produced by this script
# is validated against this set before `open(..., "w")`. Pinned by
# docs/runbooks/social-research-promotion.md Gate 1 and the unit test in
# backend/tests/test_research_script_output_guard.py.
PROTECTED_OUTPUT_NAMES = frozenset({
    "config.yaml",
    "config.phase2_1k.yaml",
    "docker-compose.prod.yml",
    ".env",
})


def _refuse_protected_base_config(base_config_path) -> None:
    """Raise if the script would read a production-control file as base."""
    if Path(base_config_path).name in PROTECTED_CONFIG_NAMES:
        raise ValueError(
            f"Refusing protected production file as research base config: {base_config_path}"
        )


def _refuse_protected_output(path) -> None:
    """Raise if the script would write to a production-control file."""
    if Path(path).name in PROTECTED_OUTPUT_NAMES:
        raise ValueError(
            f"Refusing to write to production-control file: {path}"
        )


def apply_patch(config: dict, patch: dict):
    """Apply dotted-key patch (e.g. 'engine.risk.max_dd': 0.1) to a config dict."""
    for key, value in patch.items():
        parts = key.split(".")
        cur = config
        for part in parts[:-1]:
            if part not in cur:
                cur[part] = {}
            cur = cur[part]
        cur[parts[-1]] = value


def run_research(
    symbols: str,
    period_days: int,
    base_config_path: str,
    state_path: str | Path = "state/social_doctrine.jsonl",
    candidates_dir: str | Path = CANDIDATES_DIR,
    reports_dir: str | Path = REPORTS_DIR,
    execute_backtests: bool = True,
):
    log.info("Starting social strategy research...")
    _refuse_protected_base_config(base_config_path)

    candidates_path = Path(candidates_dir)
    reports_path = Path(reports_dir)
    candidates_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)

    try:
        snapshot = build_social_research_snapshot(state_path)
        hypotheses = snapshot.get("hypotheses", [])
    except Exception as exc:
        log.error("Failed to build research snapshot: %s", exc)
        return {"research_only": True, "no_promotion": True, "hypotheses": [], "commands": []}

    if not hypotheses:
        log.warning("No hypotheses found to research. Have you run collection?")
        return {"research_only": True, "no_promotion": True, "hypotheses": [], "commands": []}

    log.info("Found %d hypotheses to test.", len(hypotheses))

    with open(base_config_path, "r", encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)

    manifest = {
        "research_only": True,
        "no_promotion": True,
        "state_path": str(state_path),
        "base_config": str(base_config_path),
        "hypotheses": [],
        "commands": [],
    }

    for h in hypotheses:
        h_id = h["id"]
        log.info("-" * 40)
        log.info("RESEARCHING HYPOTHESIS: %s", h_id)
        log.info("Title: %s", h.get("title"))

        # 1. Generate candidate config
        candidate_cfg = yaml.safe_load(yaml.dump(base_cfg))  # deep copy
        patch = h.get("candidate_config_patch", {})
        if patch:
            apply_patch(candidate_cfg, patch)

        candidate_path = candidates_path / f"candidate_{h_id}.yaml"
        _refuse_protected_output(candidate_path)
        with open(candidate_path, "w", encoding="utf-8") as f:
            f.write("# RESEARCH CANDIDATE CONFIG - NO_PROMOTION - HUMAN APPROVAL REQUIRED\n")
            f.write(f"# Hypothesis ID: {h_id}\n")
            yaml.dump(candidate_cfg, f, default_flow_style=False)

        log.info("Candidate config generated: %s", candidate_path)

        # 2. Run backtest comparison
        # We use subprocess to run the CLI to ensure clean environment/context
        cmd = [
            sys.executable, "-m", "backtest.cli", "compare",
            "--symbols", symbols,
            "--period-days", str(period_days),
            "--config", str(candidate_path),
            "--hypothesis", h_id,
        ]
        manifest["hypotheses"].append(
            {
                "id": h_id,
                "risk": h.get("risk", "research_only"),
                "candidate_config": str(candidate_path),
                "no_promotion": True,
            }
        )
        manifest["commands"].append(cmd)

        log.info("Prepared backtest: %s", " ".join(cmd))
        if execute_backtests:
            try:
                # We don't capture output to allow real-time progress in CLI
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as err:
                log.error("Backtest failed for %s: %s", h_id, err)

    manifest_path = reports_path / "latest_social_research_manifest.yaml"
    _refuse_protected_output(manifest_path)
    with open(manifest_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
    manifest["manifest_path"] = str(manifest_path)

    log.info("-" * 40)
    log.info("Social strategy research finished.")
    log.info("Manifest: %s", manifest_path)
    log.info("Check reports/backtests/ for detailed comparison JSONs.")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run social research backtests.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols")
    parser.add_argument("--period-days", type=int, default=180, help="Backtest period in days")
    parser.add_argument("--base-config", default="configs/config.phase2_1k.yaml", help="Base config path")
    parser.add_argument("--state", default="state/social_doctrine.jsonl", help="Doctrine archive JSONL path")
    parser.add_argument("--plan-only", action="store_true", help="Generate candidate configs/manifest without running backtests")

    args = parser.parse_args()
    run_research(
        args.symbols,
        args.period_days,
        args.base_config,
        state_path=args.state,
        execute_backtests=not args.plan_only,
    )
