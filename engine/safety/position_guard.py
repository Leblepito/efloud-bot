"""
Position Guards — Pozisyon bazlı güvenlik kuralları
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Check'ler:
  - Size cap (tek trade max %20 notional)
  - Total exposure (tüm pozisyonlar < 5x equity)
  - Max holding time (default 48h)
  - Max pyramid adds (default 2)
  - Duplicate direction (same sym + same dir = reject)
  - Opposite direction (sym + opposite dir = reject; orchestrator
    re-checks via can_reverse_position to decide reverse-on-profit)
  - Minimum SL distance (ATR tabanlı, whipsaw'dan kaçınmak için)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional, List
from datetime import datetime, timedelta, timezone

log = logging.getLogger("efloud.posguard")


@dataclass(frozen=True)
class PauseGateDecision:
    """Result of the pause_new_entries hard gate for new market entries."""
    allowed: bool
    reason: Optional[str] = None
    source: Optional[str] = None


@dataclass(frozen=True)
class PauseConfig:
    """Resolved pause configuration loaded once at process start.

    Env changes require container recreation (`docker compose up -d`), not
    `docker restart`. True runtime hot-flip belongs to a later API/state PR.
    """
    enabled: bool
    source: str
    config_value: Optional[bool]
    env_override: Optional[str]


_ENV_VAR_NAME = "EFLOUD_PAUSE_NEW_ENTRIES"
_ENV_TRUE = {"1", "true", "yes", "on"}
_ENV_FALSE = {"0", "false", "no", "off", ""}


def _parse_env_bool(raw: Optional[str]) -> Optional[bool]:
    if raw is None:
        return None
    norm = raw.strip().lower()
    if norm in _ENV_TRUE:
        return True
    if norm in _ENV_FALSE:
        return False
    return None


def load_pause_config(safety_cfg: Mapping[str, Any]) -> PauseConfig:
    """Resolve pause_new_entries from env + config.

    Precedence: EFLOUD_PAUSE_NEW_ENTRIES > safety.pause_new_entries > false.
    Unknown env values are ignored with a warning and fall back to config.
    """
    config_raw = safety_cfg.get("pause_new_entries", None)
    if config_raw is None:
        config_value: Optional[bool] = None
    elif isinstance(config_raw, bool):
        config_value = config_raw
    else:
        log.warning(
            "safety.pause_new_entries has unexpected type %s (value=%r); "
            "treating as missing (default false).",
            type(config_raw).__name__, config_raw,
        )
        config_value = None

    env_raw = os.environ.get(_ENV_VAR_NAME)
    env_parsed = _parse_env_bool(env_raw)
    if env_raw is not None and env_parsed is None:
        log.warning(
            "%s has unrecognized value %r; expected true values %s or false values %s. "
            "Ignoring env, falling back to config.",
            _ENV_VAR_NAME, env_raw, sorted(_ENV_TRUE), sorted(_ENV_FALSE - {""}),
        )

    if env_parsed is not None:
        enabled = env_parsed
        source = "env"
    elif config_value is not None:
        enabled = config_value
        source = "config"
    else:
        enabled = False
        source = "default"

    cfg = PauseConfig(
        enabled=enabled,
        source=source,
        config_value=config_value,
        env_override=env_raw,
    )
    log.info(
        "pause_new_entries config loaded: effective=%s source=%s (config=%r, env=%r)",
        enabled, source, config_value, env_raw,
        extra={
            "event": "position_guard.pause_config_loaded",
            "effective": enabled,
            "source": source,
            "config_value": config_value,
            "env_override": env_raw,
        },
    )
    return cfg


@dataclass
class PositionCheckResult:
    allowed: bool
    reason: str = ""
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class PositionGuard:
    """
    Her pozisyon açma/ekleme öncesi sorulan guard.
    """

    def __init__(self,
                 max_notional_pct_of_balance: float = 20.0,
                 max_total_exposure_multiplier: float = 5.0,
                 max_holding_hours: float = 48.0,
                 max_pyramid_adds: int = 2,
                 min_sl_distance_atr: float = 0.5,
                 max_sl_distance_atr: float = 5.0,
                 reserve_balance: float = 0.0,
                 max_open_positions: int = 999,
                 reverse_min_profit_pct: float = 0.2,
                 pause_config: PauseConfig | None = None,
                 hedge_mode: bool = False):
        self.max_size_pct = max_notional_pct_of_balance / 100
        self.max_exposure = max_total_exposure_multiplier
        self.max_hold = max_holding_hours
        self.max_adds = max_pyramid_adds
        self.min_sl_atr = min_sl_distance_atr
        self.max_sl_atr = max_sl_distance_atr
        self.reserve_balance = reserve_balance
        # Default 999 = effectively unlimited (back-compat for tests/configs that
        # don't set this). Real configs cap at 1-10.
        self.max_open_positions = max_open_positions
        # Reverse-on-profit threshold: only allow flipping LONG↔SHORT on the
        # same symbol when current unrealized PnL exceeds this % (fee+slippage
        # buffer, default 0.2% net). Below threshold the opposite signal is
        # rejected — TP or SL must fire first.
        self.reverse_min_profit_pct = reverse_min_profit_pct
        self.hedge_mode = hedge_mode
        self._pause = pause_config or PauseConfig(
            enabled=False,
            source="default",
            config_value=None,
            env_override=None,
        )

    def is_new_entry_allowed(self, signal) -> PauseGateDecision:
        """Return whether a new market entry may proceed past pause gate.

        This gate only blocks new entries. Reconcile, lifecycle, SL/TP
        management, breaker updates, and notifications remain independent.
        """
        if not self._pause.enabled:
            return PauseGateDecision(allowed=True)

        source_attribution = (
            "EFLOUD_PAUSE_NEW_ENTRIES"
            if self._pause.source == "env"
            else "safety.pause_new_entries"
        )
        symbol = getattr(signal, "symbol", None)
        side = getattr(signal, "side", None)
        is_pyramid = bool(getattr(signal, "is_pyramid", False) is True)
        log.info(
            "gate blocked: pause_new_entries active",
            extra={
                "event": "position_guard.gate_blocked",
                "symbol": symbol,
                "side": side,
                "is_pyramid": is_pyramid,
                "reason": "pause_new_entries",
                "source": source_attribution,
            },
        )
        return PauseGateDecision(
            allowed=False,
            reason="pause_new_entries",
            source=source_attribution,
        )

    def can_open_position(self,
                            balance: float,
                            entry: float,
                            size: float,
                            sl: float,
                            atr: float,
                            direction: str,
                            symbol: str,
                            existing_positions: list,
                            leverage: int = 1) -> PositionCheckResult:
        """Yeni pozisyon açılabilir mi?"""
        warnings = []

        # 0. Max simultaneous open positions (parallel exposure cap)
        # Counted on `is_open` only — closed positions don't count toward the cap.
        open_count = sum(1 for p in existing_positions if p.is_open)
        if open_count >= self.max_open_positions:
            return PositionCheckResult(
                False,
                f"max_open_positions reached: {open_count}/{self.max_open_positions} "
                f"already open"
            )

        # 1. Size > 0
        if size <= 0:
            return PositionCheckResult(False, "Size is zero or negative")

        # 2. Size cap
        notional = entry * size
        if leverage > 1:
            notional = notional / leverage  # Margin değeri

        # 2.5 Reserve balance check — bakiye - margin - reserve > 0 olmalı
        if self.reserve_balance > 0:
            free_after_trade = balance - notional - self.reserve_balance
            if free_after_trade < 0:
                return PositionCheckResult(
                    False,
                    f"Reserve violated: balance ${balance:.2f} - "
                    f"margin ${notional:.2f} - reserve ${self.reserve_balance:.2f} = "
                    f"${free_after_trade:.2f} (negatif)"
                )

        max_notional = balance * self.max_size_pct
        # Float tolerance: 1e-2 USDT (1¢, far below any Binance min order increment).
        # Real-world residue from chained float multiplications in legacy SMC sizing
        # (entry × size / leverage with realistic prices) can reach ~1e-3 magnitude.
        # The original 1e-6 was too tight — backtest validation showed many false
        # rejections like "Size 40.15 exceeds max 40.15" (formatted-equal, ~1e-3 apart).
        if notional > max_notional + 1e-2:
            return PositionCheckResult(
                False,
                f"Size {notional:.2f} exceeds max {max_notional:.2f} "
                f"({self.max_size_pct*100:.2f}% of balance)"
            )

        # 3. Total exposure (tüm pozisyonların notional/balance oranı)
        total_notional = sum(
            p.avg_entry_price * p.remaining_size
            for p in existing_positions
            if p.is_open
        )
        new_total = total_notional + notional
        exposure_multiple = new_total / balance if balance > 0 else 0
        if exposure_multiple > self.max_exposure:
            return PositionCheckResult(
                False,
                f"Total exposure {exposure_multiple:.2f}x exceeds max {self.max_exposure}x"
            )

        # 4. Duplicate direction check
        for p in existing_positions:
            if (p.is_open and p.symbol == symbol and p.direction == direction
                and p.scenario_id is None):  # hedge değil
                return PositionCheckResult(
                    False,
                    f"Already {direction} open on {symbol} (pos {p.id})"
                )

        # 4b. Opposite direction check — orchestrator re-evaluates via
        # can_reverse_position to decide whether to flip on profit.
        # Without this branch Binance auto-flip (isolated + hedge off)
        # would close the existing position whenever the bot sent an
        # opposite-side order — bypassing the bot's TP/SL discipline.
        # Bypass this check if hedge_mode is enabled (allows dual-sided LONG/SHORT positions).
        if not self.hedge_mode:
            for p in existing_positions:
                if (p.is_open and p.symbol == symbol and p.direction != direction
                    and p.scenario_id is None):
                    return PositionCheckResult(
                        False,
                        f"OPPOSITE_DIRECTION_EXISTS: {p.direction} open on {symbol} (pos {p.id})"
                    )

        # 5. SL distance sanity (ATR tabanlı)
        if atr > 0:
            sl_dist = abs(entry - sl)
            sl_atr_mult = sl_dist / atr
            if sl_atr_mult < self.min_sl_atr:
                return PositionCheckResult(
                    False,
                    f"SL too tight: {sl_atr_mult:.2f} ATR < min {self.min_sl_atr}. "
                    f"Whipsaw risk — reject."
                )
            if sl_atr_mult > self.max_sl_atr:
                warnings.append(
                    f"SL very wide: {sl_atr_mult:.2f} ATR > {self.max_sl_atr}. "
                    f"Consider smaller size."
                )

        # 5b. SL must fire BEFORE isolated-margin liquidation (P3-4). For
        # ISOLATED Nx the position liquidates at ~(1/leverage) adverse move
        # (minus maintenance margin). An SL wider than that NEVER triggers — the
        # exchange liquidates first at a worse price. Reject with a 0.9 safety
        # factor covering maintenance margin + buffer (e.g. 5x → reject ≥ 18%).
        if leverage > 1 and entry > 0:
            sl_dist_pct = abs(entry - sl) / entry
            liq_dist_pct = 1.0 / leverage
            if sl_dist_pct >= liq_dist_pct * 0.90:
                return PositionCheckResult(
                    False,
                    f"SL distance {sl_dist_pct*100:.1f}% >= liquidation distance "
                    f"{liq_dist_pct*100:.1f}% (ISOLATED {leverage}x) — SL would never "
                    f"fire (liquidation first). Reject."
                )

        # 6. Risk per trade sanity
        risk_amount = abs(entry - sl) * size
        risk_pct = (risk_amount / balance) * 100 if balance > 0 else 0
        if risk_pct > 5:
            return PositionCheckResult(
                False,
                f"Risk per trade {risk_pct:.2f}% exceeds hard cap 5%"
            )

        return PositionCheckResult(True, warnings=warnings)

    def can_reverse_position(self,
                              existing_position,
                              current_price: float,
                              min_profit_pct: Optional[float] = None
                              ) -> PositionCheckResult:
        """Karda olan açık pozisyonun ters yöne çevrilmesine izin var mı?

        Çağrılması beklenen yer: orchestrator can_open_position
        OPPOSITE_DIRECTION_EXISTS reddi aldıktan sonra. Onay verirse caller
        eski pozisyonu close + yeni yönde open zinciri yürütür.

        Reddetme şartları:
          - Pozisyon zaten kapalıysa.
          - Partial close olmuşsa (exits listesi dolu) — TP1 sonrası trail
            risksiz, dokunma.
          - Unrealized PnL eşiğin altındaysa (default 0.2%, fee+slippage buffer).
        """
        threshold = self.reverse_min_profit_pct if min_profit_pct is None else min_profit_pct

        if not existing_position.is_open:
            return PositionCheckResult(False, "REVERSE_BLOCKED_POSITION_CLOSED")

        if existing_position.exits:
            return PositionCheckResult(False, "REVERSE_BLOCKED_PARTIAL_CLOSED")

        avg = existing_position.avg_entry_price
        if avg <= 0 or current_price <= 0:
            return PositionCheckResult(False, "REVERSE_BLOCKED_INVALID_PRICE")

        if existing_position.direction == "LONG":
            pnl_pct = (current_price - avg) / avg * 100.0
        else:  # SHORT
            pnl_pct = (avg - current_price) / avg * 100.0

        if pnl_pct < threshold:
            return PositionCheckResult(
                False,
                f"REVERSE_BLOCKED_NOT_PROFITABLE pnl={pnl_pct:.3f}% < min {threshold:.3f}%"
            )

        return PositionCheckResult(
            True,
            f"REVERSE_OK pnl={pnl_pct:.3f}% >= min {threshold:.3f}%"
        )

    def can_add_to_position(self,
                              position,
                              add_size: float,
                              current_price: float) -> PositionCheckResult:
        """Piramit ekleme yapılabilir mi?"""
        warnings = []

        if not position.is_open:
            return PositionCheckResult(False, "Position is closed")

        # Max adds count
        non_initial_entries = [e for e in position.entries if e.reason != "initial"]
        if len(non_initial_entries) >= self.max_adds:
            return PositionCheckResult(
                False,
                f"Max {self.max_adds} pyramid adds reached"
            )

        # Total size sonrası initial'ın 2 katını geçmemeli
        initial_size = position.entries[0].size
        new_total = position.total_size_entered + add_size
        if new_total > initial_size * 2:
            return PositionCheckResult(
                False,
                f"Total size after add ({new_total:.4f}) exceeds 2× initial ({initial_size*2:.4f})"
            )

        # Pozisyon tekrar kârda olmalı (TP1 hit veya current price > avg for long)
        if position.direction == "LONG":
            in_profit = current_price > position.avg_entry_price or position.tp1_hit
        else:
            in_profit = current_price < position.avg_entry_price or position.tp1_hit

        if not in_profit and not position.tp1_hit:
            warnings.append("Adding to losing position — higher risk")

        return PositionCheckResult(True, warnings=warnings)

    def check_holding_time(self, position) -> PositionCheckResult:
        """Pozisyon çok uzun süredir açık mı?

        Tolerates both TZ-naive ('2026-05-08T10:14:12') and TZ-aware
        ('2026-05-08T10:14:12+00:00' / '...Z') opened_at formats. Mixing
        the two used to raise TypeError on subtraction, silently bypassing
        the force-close protection (2026-05-08 incident).
        """
        if not position.opened_at:
            return PositionCheckResult(True)

        raw = position.opened_at
        # Strip trailing Z; fromisoformat handles it natively on 3.11+, but
        # the slice keeps us safe on older interpreters and is a no-op otherwise.
        if raw.endswith("Z"):
            raw = raw[:-1]

        try:
            opened = datetime.fromisoformat(raw)
        except Exception:
            return PositionCheckResult(True)

        # Convert any TZ-aware value to UTC before dropping tzinfo, so a hand-
        # edited non-UTC offset (e.g. "+03:00") is normalized rather than
        # silently distorted by hours. Subtracting against datetime.utcnow()
        # below requires a naive datetime.
        if opened.tzinfo is not None:
            opened = opened.astimezone(timezone.utc).replace(tzinfo=None)

        age = datetime.utcnow() - opened
        hours = age.total_seconds() / 3600

        if hours > self.max_hold:
            return PositionCheckResult(
                False,
                f"Position age {hours:.1f}h exceeds max {self.max_hold}h — force close recommended"
            )

        if hours > self.max_hold * 0.8:
            return PositionCheckResult(
                True,
                warnings=[f"Position aging: {hours:.1f}h / {self.max_hold}h"]
            )

        return PositionCheckResult(True)


def cleanup_orphan_hedges(positions: list, logger=None) -> list:
    """
    Ana pozisyon kapanmış ama hedge hâlâ açık — orphan hedge tespiti.

    Returns: orphan hedge listesi (manual review için)
    """
    orphans = []
    for p in positions:
        if not p.is_open:
            continue
        # Hedge'ler scenario_id "hedge_of_X" formatında
        if p.scenario_id and "hedge_of_" in p.scenario_id:
            parent_id = p.scenario_id.replace("hedge_of_", "")
            parent = next((pp for pp in positions if pp.id == parent_id), None)
            if parent is None or not parent.is_open:
                orphans.append(p)
                if logger:
                    logger.warning(f"🔓 Orphan hedge detected: {p.id} (parent {parent_id} closed)")
    return orphans
