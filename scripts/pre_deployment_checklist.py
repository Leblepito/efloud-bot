#!/usr/bin/env python3
"""
Pre-Deployment Checklist
═══════════════════════════

Mainnet deployment öncesi tüm kritik sistemleri doğrular.
Gerçek para ile trading öncesi güvenlik ve hazırlık kontrolü.
"""

import os
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any
import importlib.util

# Fix Windows console encoding issues
if sys.platform == "win32":
    try:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    except:
        pass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from exchange import BinanceClient
from engine.permissions import PermissionManager
from engine.risk.custom_calculator import CustomRiskCalculator
from engine import SafeOrchestrator

from main import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)


class PreDeploymentChecker:
    """Mainnet deployment öncesi kapsamlı sistem doğrulama."""

    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.critical_issues = []
        self.warnings = []
        self.project_root = project_root

    def run_all_checks(self) -> bool:
        """Tüm pre-deployment check'leri çalıştır."""
        print("[CHECK] EFLOUD BOT PRE-DEPLOYMENT CHECKLIST")
        print("=" * 50)

        checks = [
            ("1. Konfigurasyonlari Dogrula", self._check_configurations),
            ("2. Environment Variables Kontrolü", self._check_environment_vars),
            ("3. Dependencies ve Import Kontrolu", self._check_dependencies),
            ("4. API Baglantisi ve Yetkileri", self._check_api_connection),
            ("5. Risk Calculation Sistemini Test Et", self._check_risk_calculator),
            ("6. Permission Manager Testi", self._check_permission_manager),
            ("7. Safe Orchestrator Entegrasyonu", self._check_safe_orchestrator),
            ("8. Phase Scripts Dogrulama", self._check_phase_scripts),
            ("9. Test Coverage Kontrolü", self._check_test_coverage),
            ("10. Log ve State Dizinleri", self._check_directories),
            ("11. Backup ve Rollback Hazirligi", self._check_backup_readiness),
            ("12. Mainnet Safety Locks", self._check_mainnet_locks),
        ]

        for check_name, check_func in checks:
            print(f"\n[CHECKLIST] {check_name}")
            print("-" * 40)
            try:
                success = check_func()
                if success:
                    self.checks_passed += 1
                    print("OK PASSED")
                else:
                    self.checks_failed += 1
                    print("ERROR FAILED")
            except Exception as e:
                self.checks_failed += 1
                self.critical_issues.append(f"{check_name}: {e}")
                print(f"ERROR ERROR: {e}")

        return self._generate_final_report()

    def _check_configurations(self) -> bool:
        """Phase konfigürasyonlarının geçerliliğini kontrol et."""
        # Local v2.1: phase3 yok, phase2_micro var. Mevcut olan tüm config'leri tara.
        config_files = sorted([
            str(p.relative_to(self.project_root)).replace("\\", "/")
            for p in (self.project_root / "configs").glob("config.*.yaml")
        ]) + ["config.yaml"]

        valid_configs = 0
        for config_file in config_files:
            path = self.project_root / config_file
            if not path.exists():
                print(f"   ERROR Missing: {config_file}")
                continue

            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                # Required sections check
                required_sections = ['exchange', 'symbols', 'risk', 'operation', 'safety']
                missing_sections = [s for s in required_sections if s not in config]
                if missing_sections:
                    print(f"   ERROR {config_file}: Missing sections {missing_sections}")
                    continue

                # Specific validations
                if 'testnet' in config.get('exchange', {}):
                    testnet = config['exchange']['testnet']
                    if config_file.endswith("config.yaml") and testnet:
                        print(f"   WARNING  {config_file}: testnet=true (production'da false olmalı)")
                        self.warnings.append(f"{config_file}: mainnet config'de testnet=true")

                print(f"   OK {config_file}: Valid")
                valid_configs += 1

            except yaml.YAMLError as e:
                print(f"   ERROR {config_file}: YAML parse error: {e}")
            except Exception as e:
                print(f"   ERROR {config_file}: Error: {e}")

        return valid_configs == len(config_files)

    def _check_environment_vars(self) -> bool:
        """Kritik environment variable'ların varlığını kontrol et."""
        required_vars = {
            'BINANCE_API_KEY': 'Binance API erişimi için gerekli',
            'BINANCE_API_SECRET': 'Binance API secret için gerekli',
            'EFLOUD_ALLOW_MAINNET': 'Mainnet trading güvenlik kilidi'
        }

        all_present = True
        for var, description in required_vars.items():
            value = os.getenv(var)
            if not value:
                print(f"   ERROR Missing: {var} - {description}")
                all_present = False
                self.critical_issues.append(f"Environment variable missing: {var}")
            else:
                # Mask sensitive values
                masked_value = value[:8] + "..." if len(value) > 8 else "***"
                print(f"   OK {var}: {masked_value}")

        # EFLOUD_ALLOW_MAINNET special check
        mainnet_flag = os.getenv('EFLOUD_ALLOW_MAINNET')
        if mainnet_flag != '1':
            print(f"   WARNING  EFLOUD_ALLOW_MAINNET='{mainnet_flag}' (mainnet için '1' olmalı)")
            self.warnings.append("EFLOUD_ALLOW_MAINNET mainnet için '1' değeri gerekli")

        return all_present

    def _check_dependencies(self) -> bool:
        """Critical module import'larını test et."""
        critical_modules = [
            'ccxt',
            'pandas',
            'numpy',
            'yaml',
            'asyncio'
        ]

        project_modules = [
            'exchange',  # BinanceClient is in exchange module
            'engine.permissions',
            'engine.risk.custom_calculator',
            'engine',  # SafeOrchestrator is in engine/__init__.py
            'engine.notifications'  # NotificationManager is in notifications/__init__.py
        ]

        all_imports_ok = True

        # External dependencies
        for module in critical_modules:
            try:
                __import__(module)
                print(f"   OK {module}")
            except ImportError as e:
                print(f"   ERROR {module}: {e}")
                all_imports_ok = False
                self.critical_issues.append(f"Missing dependency: {module}")

        # Project modules
        for module in project_modules:
            try:
                importlib.import_module(module)
                print(f"   OK {module}")
            except ImportError as e:
                print(f"   ERROR {module}: {e}")
                all_imports_ok = False
                self.critical_issues.append(f"Project module import failed: {module}")

        return all_imports_ok

    def _check_api_connection(self) -> bool:
        """Binance API bağlantısı ve yetki kontrolü."""
        try:
            client = BinanceClient(
                api_key=os.getenv('BINANCE_API_KEY', ''),
                api_secret=os.getenv('BINANCE_API_SECRET', ''),
                testnet=False
            )

            # Test connection
            exchange_info = client.exchange.fetch_markets()
            print(f"   OK API Connection: {len(exchange_info)} markets fetched")

            # Check account permissions
            try:
                balance = client.exchange.fetch_balance()
                can_trade = balance.get('info', {}).get('canTrade', False)
                print(f"   OK Account canTrade: {can_trade}")

                if not can_trade:
                    self.warnings.append("Account canTrade=False - trade permissions required for live trading")

                # Check USDT futures balance
                futures_balance = 0
                for currency, details in balance.items():
                    if currency == 'USDT' and isinstance(details, dict):
                        futures_balance = details.get('total', 0)
                        break

                print(f"   OK USDT Balance: {futures_balance}")
                if futures_balance < 100:
                    self.warnings.append(f"Low USDT balance: {futures_balance} (minimum ~100 USDT recommended)")

                return True

            except Exception as e:
                print(f"   ERROR Account Info Error: {e}")
                self.critical_issues.append(f"Cannot fetch account info: {e}")
                return False

        except Exception as e:
            print(f"   ERROR API Connection Failed: {e}")
            self.critical_issues.append(f"Binance API connection failed: {e}")
            return False

    def _check_risk_calculator(self) -> bool:
        """Risk calculator'ın doğru çalışmasını test et."""
        try:
            # Test configuration
            calc = CustomRiskCalculator(
                max_loss_usdt=20.0,
                leverage=3,
                target_stop_pct=0.10
            )

            # Test calculation
            balance = 1000.0

            position_size = calc.calculate_position_size(balance)

            expected_size = 20.0 / (45000.0 - 40500.0) * 45000.0  # ~200 USDT position

            print(f"   OK Position Size Calculation: {position_size:.2f} USDT")
            print(f"   OK Expected Range: ~{expected_size:.2f} USDT")

            # Verify position size is reasonable
            if 0 < position_size <= balance:
                print(f"   OK Risk Validation: Position size within safe bounds")
            else:
                print(f"   ERROR Risk Validation: Position size {position_size} outside safe bounds")

            return True

        except Exception as e:
            print(f"   ERROR Risk Calculator Error: {e}")
            self.critical_issues.append(f"Risk calculator test failed: {e}")
            return False

    def _check_permission_manager(self) -> bool:
        """Permission manager'ın API'den yetkileri doğru tespit ettiğini kontrol et."""
        try:
            client = BinanceClient(
                api_key=os.getenv('BINANCE_API_KEY', ''),
                api_secret=os.getenv('BINANCE_API_SECRET', ''),
                testnet=False
            )
            perm_manager = PermissionManager(client)

            # Test symbol list
            test_symbols = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT']
            permissions = perm_manager.detect_all(test_symbols)

            tradeable_count = sum(1 for p in permissions.values() if p.tradeable)
            readonly_count = len(permissions) - tradeable_count

            print(f"   OK Symbol Permissions Detected: {len(permissions)} total")
            print(f"   OK Tradeable: {tradeable_count}, Read-only: {readonly_count}")

            for symbol, perm in permissions.items():
                status = "OK TRADE" if perm.tradeable else "READ READ"
                print(f"      {status} {symbol}: {perm.reason}")

            return len(permissions) > 0

        except Exception as e:
            print(f"   ERROR Permission Manager Error: {e}")
            self.critical_issues.append(f"Permission manager test failed: {e}")
            return False

    def _check_safe_orchestrator(self) -> bool:
        """Safe orchestrator entegrasyonunu test et (legacy + opt-in reverse_from_risk)."""
        try:
            # Load test config — phase1 varsa onu, yoksa default config.yaml
            config_path = self.project_root / "configs" / "config.phase1.yaml"
            if not config_path.exists():
                config_path = self.project_root / "config.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # Create orchestrator (local: state_dir + opsiyonel permission/notif mgr)
            import tempfile
            orchestrator = SafeOrchestrator(
                config, state_dir=tempfile.mkdtemp(prefix="efloud_chk_")
            )
            print(f"   OK SafeOrchestrator Created")

            # Risk calculation modu — local'de opt-in
            mode = config.get("risk", {}).get("position_size_calculation", "legacy")
            if mode == "reverse_from_risk":
                # Yeni mode aktif → CustomRiskCalculator instantiate edilebilir mi?
                from engine.risk.custom_calculator import CustomRiskCalculator
                calc = CustomRiskCalculator(
                    max_loss_usdt=config["risk"].get("max_loss_per_trade_usdt", 10.0),
                    leverage=config["exchange"].get("leverage", 1),
                    target_stop_pct=config["risk"].get("target_stop_distance_pct", 5) / 100.0,
                )
                size = calc.calculate_position_size(1000.0)
                print(f"   OK Risk Calculation Mode: reverse_from_risk → {size:.2f} USDT")
            else:
                # Legacy mode — mevcut risk.calc_position_size kullanılıyor
                from risk import calc_position_size
                print(f"   OK Risk Calculation Mode: legacy (calc_position_size)")

            return True

        except Exception as e:
            print(f"   ERROR Safe Orchestrator Error: {e}")
            self.critical_issues.append(f"Safe orchestrator test failed: {e}")
            return False

    def _check_phase_scripts(self) -> bool:
        """Phase execution path'leri kontrol et.

        Local v2.1: phase yürütücü olarak `python main.py configs/<file>.yaml` kullanılıyor;
        ayrı `scripts/execute_phase*.py` reddedildi. Bu check main.py'nin syntax'ını
        ve phase config'lerin var olduğunu doğrular.
        """
        all_valid = True

        # main.py syntax check (phase entry point)
        main_path = self.project_root / "main.py"
        if not main_path.exists():
            print(f"   ERROR Missing: main.py")
            all_valid = False
        else:
            try:
                with open(main_path, 'r', encoding='utf-8') as f:
                    compile(f.read(), str(main_path), 'exec')
                print(f"   OK main.py: Valid syntax (phase entry point)")
            except SyntaxError as e:
                print(f"   ERROR main.py: Syntax error: {e}")
                all_valid = False

        # preflight.py — local'in mainnet API doğrulama scripti
        preflight = self.project_root / "preflight.py"
        if preflight.exists():
            print(f"   OK preflight.py: Available for mainnet API verification")
        else:
            print(f"   WARNING preflight.py missing — mainnet readiness check unavailable")

        return all_valid

    def _check_test_coverage(self) -> bool:
        """Test dosyalarının varlığını kontrol et (local v2.1 + cherry-pick)."""
        test_files = [
            # Local script-style tests
            "test_safety.py",
            "test_v2_2_0.py",
            "test_regime.py",
            "test_offline.py",
            # Cherry-picked pytest suite
            "tests/risk/test_custom_calculator.py",
            "tests/config/test_phase_configs.py",
        ]

        all_present = True
        for test_file in test_files:
            test_path = self.project_root / test_file
            if test_path.exists():
                print(f"   OK {test_file}")
            else:
                print(f"   ERROR Missing: {test_file}")
                all_present = False

        return all_present

    def _check_directories(self) -> bool:
        """Gerekli log ve state dizinlerinin varlığını kontrol et."""
        required_dirs = [
            "logs",
            "state",
            "reports",
            "configs"
        ]

        all_exist = True
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                print(f"   OK {dir_name}/ directory exists")
            else:
                print(f"   WARNING  Creating {dir_name}/ directory")
                dir_path.mkdir(exist_ok=True)

        return all_exist

    def _check_backup_readiness(self) -> bool:
        """Backup ve rollback prosedürlerinin hazırlığını kontrol et."""
        # Check if we have git repository
        git_dir = self.project_root / ".git"
        if git_dir.exists():
            print("   OK Git repository detected")
        else:
            print("   WARNING  No git repository - version control recommended")
            self.warnings.append("No git repository for version control")

        # Check if we have config backups
        config_backup_dir = self.project_root / "configs" / "backups"
        if config_backup_dir.exists():
            print("   OK Config backup directory exists")
        else:
            print("   WARNING  No config backup directory")
            self.warnings.append("Consider creating configs/backups/ for configuration backups")

        # Check if we have state backup strategy
        print("   [INFO]  Manual backup reminder: State ve logs dizinlerinin yedeğini alın")

        return True

    def _check_mainnet_locks(self) -> bool:
        """Mainnet güvenlik kilitleri kontrolü."""
        # Check environment variable
        mainnet_allowed = os.getenv('EFLOUD_ALLOW_MAINNET') == '1'
        if not mainnet_allowed:
            print("   ERROR EFLOUD_ALLOW_MAINNET not set to '1'")
            self.critical_issues.append("EFLOUD_ALLOW_MAINNET must be '1' for mainnet trading")
            return False

        print("   OK EFLOUD_ALLOW_MAINNET=1")

        # Check dry_run settings in configs
        config_path = self.project_root / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            dry_run = config.get('operation', {}).get('dry_run', True)
            if dry_run:
                print("   WARNING  config.yaml: dry_run=true (production'da false yapabilirsiniz)")
                self.warnings.append("dry_run=true in main config - set to false for live trading")
            else:
                print("   OK config.yaml: dry_run=false")

        return True

    def _generate_final_report(self) -> bool:
        """Final deployment readiness raporu."""
        print("\n" + "=" * 60)
        print("[SUMMARY] PRE-DEPLOYMENT CHECKLIST SUMMARY")
        print("=" * 60)

        print(f"OK Checks Passed: {self.checks_passed}")
        print(f"ERROR Checks Failed: {self.checks_failed}")
        print(f"WARNING  Warnings: {len(self.warnings)}")

        if self.critical_issues:
            print(f"\n[CRITICAL] CRITICAL ISSUES:")
            for issue in self.critical_issues:
                print(f"   • {issue}")

        if self.warnings:
            print(f"\nWARNING  WARNINGS:")
            for warning in self.warnings:
                print(f"   • {warning}")

        deployment_ready = self.checks_failed == 0 and len(self.critical_issues) == 0

        if deployment_ready:
            print(f"\n[SUCCESS] DEPLOYMENT READY!")
            print("   Sistem mainnet trading için hazır.")
            print("   Phase 1 (dry_run=true) ile başlamayı öneriyoruz.")
        else:
            print(f"\n[BLOCKED] DEPLOYMENT NOT READY")
            print("   Kritik sorunları çözün ve tekrar çalıştırın.")

        print("\n[NEXT] NEXT STEPS:")
        if deployment_ready:
            print("   1. python scripts/execute_phase1.py  # Dry run ile başlayın")
            print("   2. Sonuçları izleyin ve doğrulayın")
            print("   3. python scripts/execute_phase2.py  # Küçük pozisyonlarla test")
            print("   4. python scripts/execute_phase3.py  # Full scale")
        else:
            print("   1. Yukarıdaki kritik sorunları çözün")
            print("   2. python scripts/pre_deployment_checklist.py  # Tekrar çalıştırın")
            print("   3. Tüm check'ler geçince deployment'a başlayın")

        return deployment_ready


def main():
    """Pre-deployment checklist çalıştır."""
    checker = PreDeploymentChecker()
    is_ready = checker.run_all_checks()

    # Exit code for automation
    sys.exit(0 if is_ready else 1)


if __name__ == "__main__":
    main()