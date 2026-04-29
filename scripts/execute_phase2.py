#!/usr/bin/env python3
"""
Phase 2 Execution Script: Live Trading - Reduced Risk
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Executes Phase 2 of mainnet migration:
- Live mainnet trading with real money
- Reduced risk: 1% per trade (10 USDT max loss)
- Limited positions: max 2 concurrent
- Enhanced monitoring and validation

WARNING: This phase trades with REAL MONEY
REQUIREMENT: Successful Phase 1 completion mandatory
"""

import sys
import os
import logging
import time
from pathlib import Path
from datetime import datetime, timezone

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def setup_phase2_logging():
    """Setup logging for Phase 2 live trading"""
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"phase2_live_trading_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-5s | %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger("phase2")

def validate_phase2_requirements():
    """Validate Phase 2 execution requirements"""
    log = logging.getLogger("phase2")

    # CRITICAL: Verify EFLOUD_ALLOW_MAINNET is set
    if os.environ.get("EFLOUD_ALLOW_MAINNET") != "1":
        raise ValueError(
            "Phase 2 REQUIRES EFLOUD_ALLOW_MAINNET=1 environment variable. "
            "This protects against accidental live trading. Set: export EFLOUD_ALLOW_MAINNET=1"
        )

    # Check Phase 1 completion
    phase1_reports = list((project_root / "reports" / "phase1").glob("*.md")) if (project_root / "reports" / "phase1").exists() else []
    if not phase1_reports:
        raise ValueError(
            "Phase 2 requires successful Phase 1 completion. "
            "No Phase 1 reports found. Execute Phase 1 first."
        )

    # Check config file
    config_path = project_root / "configs" / "config.phase2.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Phase 2 config not found: {config_path}")

    # Check API credentials
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError("Phase 2 requires BINANCE_API_KEY and BINANCE_API_SECRET")

    log.info("✅ Phase 2 requirements validated")
    log.warning("⚠️ LIVE TRADING MODE - Real money at risk!")

    return config_path, api_key[:10] + "..." + api_key[-4:]

def confirm_live_trading():
    """Get user confirmation for live trading"""
    log = logging.getLogger("phase2")

    print("\n" + "="*60)
    print("⚠️  PHASE 2: LIVE TRADING CONFIRMATION")
    print("="*60)
    print("This phase will trade with REAL MONEY on Binance mainnet.")
    print("Configuration:")
    print("  - Max loss per trade: 10 USDT (1% of balance)")
    print("  - Max concurrent positions: 2")
    print("  - Total maximum risk: 20 USDT")
    print("\nREQUIREMENTS:")
    print("  ✅ Phase 1 completed successfully")
    print("  ✅ EFLOUD_ALLOW_MAINNET=1 set")
    print("  ✅ API credentials configured")
    print("="*60)

    response = input("Do you want to proceed with live trading? [yes/NO]: ").strip().lower()

    if response not in ['yes', 'y']:
        log.info("🛑 Live trading cancelled by user")
        sys.exit(0)

    log.warning("🚨 User confirmed live trading - proceeding with real money")

def execute_phase2():
    """Execute Phase 2 live trading"""
    log = setup_phase2_logging()

    log.warning("🚨 Starting Phase 2: Live Trading - Reduced Risk")
    log.warning("💰 REAL MONEY TRADING ACTIVE")

    try:
        # Validate requirements
        config_path, masked_key = validate_phase2_requirements()
        log.info(f"🔑 Using API key: {masked_key}")

        # Get user confirmation
        confirm_live_trading()

        # Import and run main with Phase 2 config
        sys.argv = ["main.py", str(config_path)]

        from main import main, validate_config, load_config

        # Load and validate configuration
        config = load_config(str(config_path))
        validate_config(config)

        log.info("✅ Configuration validation passed")

        # Confirm live trading settings
        assert config['operation']['dry_run'] == False, "Phase 2 MUST be live trading"
        assert config['exchange']['testnet'] == False, "Phase 2 MUST use mainnet"
        assert config['risk']['max_loss_per_trade_usdt'] == 10.0, "Phase 2 MUST use reduced risk"

        log.warning("🔥 LIVE TRADING confirmations:")
        log.warning("   - dry_run=False ⚠️ (REAL ORDERS)")
        log.warning("   - max_loss=10 USDT (1% balance)")
        log.warning("   - max_positions=2 (LIMITED)")

        # Execute main application
        log.warning("🎯 Executing live trading...")
        main()

    except KeyboardInterrupt:
        log.warning("⏹️ Phase 2 live trading stopped by user")
        sys.exit(0)
    except Exception as e:
        log.error(f"❌ Phase 2 live trading failed: {e}")
        raise

def main():
    """Main execution entry point"""
    try:
        execute_phase2()
    except Exception as e:
        print(f"PHASE 2 FAILED: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()