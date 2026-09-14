"""Safety layer — crash recovery, circuit breakers, position guards, mainnet guards."""

from .breaker import BreakerState, BreakerStatus, CircuitBreaker
from .guard import (
    MainnetGuard,
    RateLimiter,
    RetryExhausted,
    StaleDataError,
    mask_secret,
    retry_with_backoff,
    validate_kline_freshness,
    validate_kline_integrity,
)
from .orphan_protection import (
    CoverageStatus,
    OrphanProtectionConfig,
    OrphanProtector,
    ProtectionAction,
    load_orphan_protection_config,
)
from .position_guard import (
    PauseConfig,
    PauseGateDecision,
    PositionCheckResult,
    PositionGuard,
    cleanup_orphan_hedges,
    load_pause_config,
)
from .state import ReconciliationError, StateStore, reconcile_positions

__all__ = [
    "BreakerState",
    "BreakerStatus",
    "CircuitBreaker",
    "CoverageStatus",
    "MainnetGuard",
    "OrphanProtectionConfig",
    "OrphanProtector",
    "PauseConfig",
    "PauseGateDecision",
    "PositionCheckResult",
    "PositionGuard",
    "ProtectionAction",
    "RateLimiter",
    "ReconciliationError",
    "RetryExhausted",
    "StaleDataError",
    "StateStore",
    "cleanup_orphan_hedges",
    "load_orphan_protection_config",
    "load_pause_config",
    "mask_secret",
    "reconcile_positions",
    "retry_with_backoff",
    "validate_kline_freshness",
    "validate_kline_integrity",
]
