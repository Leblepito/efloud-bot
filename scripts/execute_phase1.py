#!/usr/bin/env python3
"""
Phase 1 Execution Script: Mainnet Dry Run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Executes Phase 1 of mainnet migration:
- Connect to real market data (mainnet)
- Execute with dry_run=True (zero financial risk)
- Validate all safety systems
- Confirm API permissions
- Test risk calculations

SAFETY: This phase uses real market data but places NO real orders.
"""

import sys
import os
import logging
import time
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def setup_phase1_logging():
    """Setup enhanced logging for Phase 1 validation"""
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"phase1_execution_{timestamp}.log"

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(name)-25s | %(levelname)-5s | %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger("phase1")

def validate_phase1_requirements():
    """Validate Phase 1 execution requirements"""
    log = logging.getLogger("phase1")

    # Check config file exists
    config_path = project_root / "configs" / "config.phase1.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Phase 1 config not found: {config_path}")

    # Check API credentials
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError(
            "Phase 1 requires BINANCE_API_KEY and BINANCE_API_SECRET environment variables. "
            "These are needed to connect to mainnet for real market data."
        )

    log.info("✅ Phase 1 requirements validated")
    return config_path, api_key[:10] + "..." + api_key[-4:]

def execute_phase1():
    """Execute Phase 1 dry run"""
    log = setup_phase1_logging()

    log.info("🚀 Starting Phase 1: Mainnet Dry Run Execution")
    log.info("📊 Real market data, ZERO financial risk")

    try:
        # Validate requirements
        config_path, masked_key = validate_phase1_requirements()
        log.info(f"🔑 Using API key: {masked_key}")

        # Import and run main with Phase 1 config
        sys.argv = ["main.py", str(config_path)]

        from main import main, validate_config, load_config

        # Load and validate configuration
        config = load_config(str(config_path))
        validate_config(config)

        log.info("✅ Configuration validation passed")

        # Confirm safety settings
        assert config['operation']['dry_run'] == True, "Phase 1 MUST be dry run"
        assert config['exchange']['testnet'] == False, "Phase 1 MUST use mainnet data"

        log.info("🔒 Safety confirmations:")
        log.info("   - dry_run=True ✅ (No real orders)")
        log.info("   - testnet=False ✅ (Real market data)")

        # Execute main application
        log.info("🎯 Executing main application...")
        main()

    except KeyboardInterrupt:
        log.info("⏹️ Phase 1 execution stopped by user")
        sys.exit(0)
    except Exception as e:
        log.error(f"❌ Phase 1 execution failed: {e}")
        raise

def main():
    """Main execution entry point"""
    try:
        execute_phase1()
    except Exception as e:
        print(f"PHASE 1 FAILED: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()