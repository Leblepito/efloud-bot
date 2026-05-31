"""Timeframe utilities shared across data layer and engine."""
from __future__ import annotations


def tf_to_minutes(tf: str) -> int:
    """Normalize a Binance/CCXT TF string to minutes.

    Per spec §6.6: must handle '1m', '15m', '1h', '4h', '1d', '1w'. ValueError on unknown.
    """
    tf_map = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if not tf or tf[-1] not in tf_map:
        raise ValueError(f"Unsupported timeframe: {tf!r}")
    try:
        n = int(tf[:-1])
    except ValueError as e:
        raise ValueError(f"Bad timeframe number: {tf!r}") from e
    return n * tf_map[tf[-1]]


# ── Trade-Horizon Profiles ───────────────────────────────────────────────────
# Canonical (entry, mtf, htf) bundles. Single source of truth so operators pick
# a name, not a raw triple. Chains are strictly monotonically increasing.
# Spec: docs/superpowers/specs/2026-05-31-trade-horizon-profiles-design-spec.md
PROFILES: dict[str, tuple[str, str, str]] = {
    "scalp": ("5m", "1h", "12h"),
    "mid":   ("15m", "1h", "4h"),
    "long":  ("1h", "8h", "1w"),
}

_WEEKLY_MIN = tf_to_minutes("1w")


def resolve_timeframes(cfg: dict) -> dict:
    """Resolve the active timeframe chain from config, fail-fast on errors.

    A named ``profile`` (scalp|mid|long) expands to its canonical triple. A
    missing profile or ``profile: custom`` falls back to the explicit
    entry/mtf/htf keys (backward compatible with pre-profile configs). The
    resolved values are written back into ``cfg["timeframes"]`` IN PLACE so
    every consumer that reads ``cfg["timeframes"]`` directly (main.py,
    bot_runner.py daemon, backtest CLI) sees the same resolved chain.

    Raises ValueError on unknown profile, missing explicit TFs, or a chain that
    is not strictly increasing (entry < mtf < htf) — preventing target-inversion
    and repaint issues, and avoiding silently trading the wrong timeframe.
    """
    tf_cfg = cfg.setdefault("timeframes", {})
    profile = tf_cfg.get("profile")
    kline_limit = tf_cfg.get("kline_limit", 500)

    if not profile or profile == "custom":
        entry = tf_cfg.get("entry")
        mtf = tf_cfg.get("mtf")
        htf = tf_cfg.get("htf")
        resolved_profile = "custom"
    elif profile in PROFILES:
        entry, mtf, htf = PROFILES[profile]
        resolved_profile = profile
    else:
        raise ValueError(
            f"Unknown timeframe profile: {profile!r} "
            f"(valid: {sorted(PROFILES)} or 'custom')"
        )

    if entry is None or mtf is None or htf is None:
        raise ValueError(
            "timeframes must define entry/mtf/htf (set a named profile or all three)"
        )

    e_min, m_min, h_min = tf_to_minutes(entry), tf_to_minutes(mtf), tf_to_minutes(htf)
    if not (e_min < m_min < h_min):
        raise ValueError(
            "Timeframe chain must be strictly increasing entry<mtf<htf: "
            f"{entry}({e_min}m) / {mtf}({m_min}m) / {htf}({h_min}m)"
        )

    # Cap history for weekly+ HTF: 250 weekly bars ≈ 4.8y, plenty of context
    # without fetching bars Binance won't return anyway.
    if h_min >= _WEEKLY_MIN and kline_limit > 250:
        kline_limit = 250

    tf_cfg["entry"] = entry
    tf_cfg["mtf"] = mtf
    tf_cfg["htf"] = htf
    tf_cfg["kline_limit"] = kline_limit
    tf_cfg["profile"] = resolved_profile

    return {
        "entry": entry,
        "mtf": mtf,
        "htf": htf,
        "kline_limit": kline_limit,
        "profile": resolved_profile,
    }
