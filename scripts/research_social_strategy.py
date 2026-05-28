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

def run_research(symbols: str, period_days: int, base_config_path: str):
    log.info("Starting social strategy research...")
    
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        snapshot = build_social_research_snapshot()
        hypotheses = snapshot.get("hypotheses", [])
    except Exception as exc:
        log.error("Failed to build research snapshot: %s", exc)
        return

    if not hypotheses:
        log.warning("No hypotheses found to research. Have you run collection?")
        return

    log.info("Found %d hypotheses to test.", len(hypotheses))

    with open(base_config_path, "r", encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)

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
        
        candidate_path = CANDIDATES_DIR / f"candidate_{h_id}.yaml"
        with open(candidate_path, "w", encoding="utf-8") as f:
            f.write("# RESEARCH CANDIDATE CONFIG - PROMOTION REQUIRES HUMAN APPROVAL\n")
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
            "--hypothesis", h_id
        ]
        
        log.info("Executing backtest: %s", " ".join(cmd))
        try:
            # We don't capture output to allow real-time progress in CLI
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as err:
            log.error("Backtest failed for %s: %s", h_id, err)

    log.info("-" * 40)
    log.info("Social strategy research finished.")
    log.info("Check reports/backtests/ for detailed comparison JSONs.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run social research backtests.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols")
    parser.add_argument("--period-days", type=int, default=180, help="Backtest period in days")
    parser.add_argument("--base-config", default="configs/config.phase2_1k.yaml", help="Base config path")
    
    args = parser.parse_args()
    run_research(args.symbols, args.period_days, args.base_config)
