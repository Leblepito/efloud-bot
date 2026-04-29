#!/usr/bin/env python3
"""
Environment Variables Setup Guide
═══════════════════════════════════

Mainnet deployment için gerekli environment variable'ları ayarlar.
"""

import os
import sys
from pathlib import Path

def check_current_env():
    """Mevcut environment variable'ları kontrol et."""
    print("[CHECK] Current Environment Status:")
    print("-" * 40)

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    mainnet_flag = os.getenv('EFLOUD_ALLOW_MAINNET')

    if api_key:
        masked_key = api_key[:8] + "..." if len(api_key) > 8 else "***"
        print(f"OK BINANCE_API_KEY: {masked_key}")
    else:
        print("ERROR BINANCE_API_KEY: NOT SET")

    if api_secret:
        print("OK BINANCE_API_SECRET: ***SET***")
    else:
        print("ERROR BINANCE_API_SECRET: NOT SET")

    if mainnet_flag == '1':
        print("OK EFLOUD_ALLOW_MAINNET: 1 (mainnet enabled)")
    elif mainnet_flag:
        print(f"WARNING  EFLOUD_ALLOW_MAINNET: {mainnet_flag} (should be '1')")
    else:
        print("ERROR EFLOUD_ALLOW_MAINNET: NOT SET")

    return bool(api_key and api_secret and mainnet_flag == '1')

def create_env_template():
    """Environment variable template oluştur."""
    env_file = Path(".env.template")

    content = """# Efloud Bot Environment Variables
# Bu dosyayi kopyalayip .env olarak kaydedin ve degerleri doldurun

# Binance API Credentials (REQUIRED for live trading)
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here

# Mainnet Safety Lock (REQUIRED - set to '1' for live trading)
EFLOUD_ALLOW_MAINNET=1

# Optional: Log level
LOG_LEVEL=INFO
"""

    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[FILE] Created template: {env_file}")
    print("   Next: Copy to .env and fill with your API credentials")

def show_setup_instructions():
    """Kurulum talimatlarını göster."""
    print("\n[CONFIG] ENVIRONMENT SETUP INSTRUCTIONS")
    print("=" * 50)

    print("\n1. GET BINANCE API CREDENTIALS:")
    print("   • Login to Binance")
    print("   • Go to: Account > API Management")
    print("   • Create New Key with these permissions:")
    print("     OK Enable Futures")
    print("     OK Enable Reading")
    print("     OK Enable Trading (for live trading)")
    print("   • Copy API Key and Secret Key")

    print("\n2. SET ENVIRONMENT VARIABLES:")

    if sys.platform == "win32":
        print("   Windows PowerShell:")
        print('   $env:BINANCE_API_KEY="your_api_key_here"')
        print('   $env:BINANCE_API_SECRET="your_secret_here"')
        print('   $env:EFLOUD_ALLOW_MAINNET="1"')
        print("\n   Windows CMD:")
        print('   set BINANCE_API_KEY=your_api_key_here')
        print('   set BINANCE_API_SECRET=your_secret_here')
        print('   set EFLOUD_ALLOW_MAINNET=1')
    else:
        print("   Linux/Mac Terminal:")
        print('   export BINANCE_API_KEY="your_api_key_here"')
        print('   export BINANCE_API_SECRET="your_secret_here"')
        print('   export EFLOUD_ALLOW_MAINNET="1"')

    print("\n3. ALTERNATIVE: Use .env file")
    print("   • Copy .env.template to .env")
    print("   • Fill in your credentials")
    print("   • Bot will auto-load from .env file")

    print("\nWARNING  SECURITY WARNINGS:")
    print("   • Keep API credentials SECRET")
    print("   • Use IP restrictions on Binance API")
    print("   • Start with testnet/paper trading first")
    print("   • Never commit .env to git")

def load_env_file():
    """Try to load .env file if it exists."""
    env_file = Path(".env")
    if env_file.exists():
        print(f"[FILE] Loading environment from {env_file}")
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
            print("OK Environment loaded from .env file")
            return True
        except Exception as e:
            print(f"ERROR Error loading .env: {e}")
            return False
    return False

def main():
    """Ana kurulum rehberi."""
    print("[SETUP] EFLOUD BOT ENVIRONMENT SETUP")
    print("=" * 50)

    # Try to load .env file
    load_env_file()

    # Check current status
    is_ready = check_current_env()

    if is_ready:
        print("\n[SUCCESS] ENVIRONMENT READY!")
        print("   All required variables are set")
        print("   You can now run: python scripts/pre_deployment_checklist.py")
    else:
        print("\nERROR ENVIRONMENT NOT READY")
        print("   Missing required environment variables")

        create_env_template()
        show_setup_instructions()

        print(f"\n[NEXT] NEXT STEPS:")
        print("   1. Set environment variables (see instructions above)")
        print("   2. Run this script again to verify: python scripts/setup_environment.py")
        print("   3. Run pre-deployment check: python scripts/pre_deployment_checklist.py")

    return is_ready

if __name__ == "__main__":
    ready = main()
    sys.exit(0 if ready else 1)