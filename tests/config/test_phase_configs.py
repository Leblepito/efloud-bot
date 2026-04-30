"""
Generic phase config sanity tests.

Local v2.1 + cherry-pick (2026-04-30): Remote'un test_phase_configs.py'si remote'un
mevcut value'larıyla sıkı bağlıydı (max_loss_per_trade_usdt=20 hardcoded vs.). Local'in
config setiyle uyumlu hale getirildi — value-spesifik assertion yerine YAPISAL sağlamlık
test ediliyor.
"""
from pathlib import Path
import pytest
import yaml

CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"
REQUIRED_SECTIONS = ["exchange", "operation", "risk", "safety", "timeframes"]


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_phase_configs():
    return sorted(CONFIGS_DIR.glob("config.*.yaml"))


def test_phase_configs_directory_exists():
    assert CONFIGS_DIR.is_dir(), f"configs dir missing: {CONFIGS_DIR}"
    files = _all_phase_configs()
    assert len(files) >= 2, f"expected at least 2 phase configs, got {len(files)}"


@pytest.mark.parametrize("path", _all_phase_configs(), ids=lambda p: p.name)
def test_config_is_valid_yaml(path: Path):
    cfg = _load(path)
    assert isinstance(cfg, dict), f"{path.name}: top level must be dict"


@pytest.mark.parametrize("path", _all_phase_configs(), ids=lambda p: p.name)
def test_config_has_required_sections(path: Path):
    cfg = _load(path)
    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    assert not missing, f"{path.name}: missing sections {missing}"


@pytest.mark.parametrize("path", _all_phase_configs(), ids=lambda p: p.name)
def test_config_safety_invariants(path: Path):
    """Live + non-testnet kombinasyonu en azından emergency_balance_threshold ister."""
    cfg = _load(path)
    op = cfg.get("operation", {})
    ex = cfg.get("exchange", {})

    if not op.get("dry_run", True) and not ex.get("testnet", True):
        # Live mainnet config — emergency threshold zorunlu
        threshold = cfg.get("safety", {}).get("emergency_balance_threshold")
        assert threshold is not None, (
            f"{path.name}: live mainnet config without emergency_balance_threshold"
        )


@pytest.mark.parametrize("path", _all_phase_configs(), ids=lambda p: p.name)
def test_config_leverage_within_sane_bounds(path: Path):
    cfg = _load(path)
    leverage = cfg.get("exchange", {}).get("leverage", 1)
    assert 1 <= leverage <= 20, f"{path.name}: leverage {leverage}x outside sane bounds [1,20]"


@pytest.mark.parametrize("path", _all_phase_configs(), ids=lambda p: p.name)
def test_config_risk_pct_within_sane_bounds(path: Path):
    cfg = _load(path)
    risk_pct = cfg.get("risk", {}).get("risk_per_trade_pct", 1.0)
    assert 0 < risk_pct <= 5.0, f"{path.name}: risk_per_trade_pct {risk_pct}% outside [0,5]"
