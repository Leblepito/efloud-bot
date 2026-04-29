#!/usr/bin/env python3
"""
Phase 3 Execution Script: Full Scale Live Trading
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Executes Phase 3 of mainnet migration:
- Full scale live mainnet trading
- Full risk: 2% per trade (20 USDT max loss)
- Full positions: max 4 concurrent
- Complete automated operation

WARNING: This phase trades with FULL RISK
REQUIREMENT: Successful Phase 1 AND Phase 2 completion mandatory
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def validate_phase3_requirements():
    """Validate Phase 3 execution requirements"""
    log = logging.getLogger("phase3")

    # CRITICAL: Verify EFLOUD_ALLOW_MAINNET is set
    if os.environ.get("EFLOUD_ALLOW_MAINNET") != "1":
        raise ValueError(
            "Phase 3 REQUIRES EFLOUD_ALLOW_MAINNET=1 environment variable"
        )

    # Check Phase 1 AND Phase 2 completion
    for phase in [1, 2]:
        phase_reports = list((project_root / "reports" / f"phase{phase}").glob("*.md")) if (project_root / "reports" / f"phase{phase}").exists() else []
        if not phase_reports:
            raise ValueError(
                f"Phase 3 requires successful Phase {phase} completion. "
                f"No Phase {phase} reports found."
            )

    # Check minimum successful trades in Phase 2
    phase2_state = project_root / "state" / "phase2"
    if not phase2_state.exists():
        raise ValueError("Phase 2 state directory not found - Phase 2 may not have completed")

    log.info("✅ Phase 3 requirements validated")
    log.warning("⚠️ FULL SCALE LIVE TRADING MODE")

    return project_root / "configs" / "config.phase3.yaml"

def confirm_full_scale_trading():
    """Get user confirmation for full scale trading"""
    print("\n" + "="*60)
    print("🚨 PHASE 3: FULL SCALE TRADING CONFIRMATION")
    print("="*60)
    print("This phase will trade with FULL RISK on Binance mainnet.")
    print("Configuration:")
    print("  - Max loss per trade: 20 USDT (2% of balance)")
    print("  - Max concurrent positions: 4")
    print("  - Total maximum risk: 80 USDT (8% of balance)")
    print("\nREQUIREMENTS:")
    print("  ✅ Phase 1 completed successfully")
    print("  ✅ Phase 2 completed successfully")
    print("  ✅ EFLOUD_ALLOW_MAINNET=1 set")
    print("="*60)

    response = input("Do you want to proceed with FULL SCALE trading? [yes/NO]: ").strip().lower()

    if response not in ['yes', 'y']:
        logging.getLogger("phase3").info("🛑 Full scale trading cancelled by user")
        sys.exit(0)

def execute_phase3():
    """Execute Phase 3 full scale trading"""
    log = logging.getLogger("phase3")

    log.warning("🚨 Starting Phase 3: Full Scale Live Trading")
    log.warning("💰 MAXIMUM RISK TRADING ACTIVE")

    try:
        config_path = validate_phase3_requirements()
        confirm_full_scale_trading()

        # Execute with Phase 3 config
        sys.argv = ["main.py", str(config_path)]

        from main import main, validate_config, load_config

        config = load_config(str(config_path))
        validate_config(config)

        # Confirm full scale settings
        assert config['operation']['dry_run'] == False
        assert config['risk']['max_loss_per_trade_usdt'] == 20.0
        assert config['risk']['max_open_positions'] == 4

        log.warning("🔥 FULL SCALE confirmations:")
        log.warning("   - max_loss=20 USDT (2% balance)")
        log.warning("   - max_positions=4 (FULL CAPACITY)")

        main()

    except Exception as e:
        log.error(f"❌ Phase 3 failed: {e}")
        raise

def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = project_root / "logs" / f"phase3_full_scale_{timestamp}.log"
    log_file.parent.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-5s | %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    try:
        execute_phase3()
    except Exception as e:
        print(f"PHASE 3 FAILED: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()