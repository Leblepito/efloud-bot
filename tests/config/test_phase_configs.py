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


def test_prod_config_breaker_calibration_consistent():
    """C2: the PRODUCTION live config (config.phase2_1k.yaml — the active
    EFLOUD_CONFIG_PATH) must have an internally consistent breaker calibration.
    The breaker computes daily-loss% as daily_pnl/starting_balance (static) and
    HALTs when live balance < emergency_balance_threshold — so a half-reconciled
    config (e.g. starting_balance lowered to 1000 but emergency left at 1800) is
    the dangerous intermediate this gate forbids.

    Scoped to the production config on purpose: other LIVE configs (e.g.
    config.aggressive_v1.yaml) carry a PRE-EXISTING emergency/daily mismatch that
    is out of scope for the C2 audit — flagged here, not fixed (not the prod path).
    """
    cfg = _load(CONFIGS_DIR / "config.phase2_1k.yaml")
    sb = cfg.get("safety", {})
    start = sb["starting_balance"]
    emerg = sb["emergency_balance_threshold"]
    daily = sb["daily_loss_limit_pct"]
    # (a) emergency must sit BELOW starting_balance — else the breaker HALTs on the
    #     first balance-fetch cycle (emerg 1800 vs a $1000 wallet => instant halt).
    assert emerg < start, (
        f"emergency {emerg} >= starting_balance {start} -> instant HALT risk"
    )
    # (b) the emergency drawdown (start-emerg)/start must match daily_loss_limit_pct
    #     within tolerance, so the absolute USDT halt and the % daily trip are
    #     calibrated to the SAME wallet (real ~$2070 → $2000/$1800/10% is coherent).
    implied_emerg_dd_pct = (start - emerg) / start * 100.0
    assert abs(implied_emerg_dd_pct - daily) <= 1.0, (
        f"emergency implies {implied_emerg_dd_pct:.1f}% DD but "
        f"daily_loss_limit_pct={daily}% — mismatched wallet calibration"
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
