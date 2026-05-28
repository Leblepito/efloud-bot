"""Deterministic doctrine extraction from Efloud social posts.

The extractor intentionally uses transparent regex/keyword rules. Its output is
research metadata only; it must not be interpreted as a live trade signal.
"""
from __future__ import annotations

import re
from typing import Any

_SYMBOL_ALIASES = {
    "BTC": "BTC/USDT",
    "BTCUSDT": "BTC/USDT",
    "ETH": "ETH/USDT",
    "ETHUSDT": "ETH/USDT",
    "SOL": "SOL/USDT",
    "SOLUSDT": "SOL/USDT",
    "BNB": "BNB/USDT",
    "BNBUSDT": "BNB/USDT",
    "ADA": "ADA/USDT",
    "ADAUSDT": "ADA/USDT",
    "LINK": "LINK/USDT",
    "LINKUSDT": "LINK/USDT",
    "AVAX": "AVAX/USDT",
    "AVAXUSDT": "AVAX/USDT",
}

_TIMEFRAME_MAP = {
    "1D": "1d",
    "1G": "1d",
    "4H": "4h",
    "1H": "1h",
    "15M": "15m",
    "5M": "5m",
}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _extract_symbols(text: str) -> list[str]:
    found: list[str] = []
    upper = text.upper()

    for match in re.findall(r"\b([A-Z]{2,10})\s*/\s*USDT\b", upper):
        found.append(f"{match}/USDT")

    for alias, canonical in _SYMBOL_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", upper):
            found.append(canonical)

    return _unique(found)


def _extract_timeframes(text: str) -> list[str]:
    upper = text.upper()
    found = []
    for raw, normalized in _TIMEFRAME_MAP.items():
        if re.search(rf"\b{re.escape(raw)}\b", upper):
            found.append(normalized)
    return _unique(found)


def _extract_levels(text: str) -> list[float]:
    levels: list[float] = []
    # Handles 93200, 94100, 103k, 2.5k. Keeps insertion order.
    for raw, suffix in re.findall(r"(?<![A-Za-z0-9])([0-9]+(?:[.,][0-9]+)?)(\s*[kK])?", text):
        normalized = raw.replace(",", ".")
        try:
            value = float(normalized)
        except ValueError:
            continue
        if suffix.strip().lower() == "k":
            value *= 1000.0
        # Avoid matching timeframe numbers such as 1D/4H as levels.
        if value < 10:
            continue
        if value not in levels:
            levels.append(value)
    return levels


def _bias(text: str, symbols: list[str]) -> str:
    lower = text.lower()
    if not symbols and any(term in lower for term in ("notu", "mpa", "öğren", "egit", "eğit")):
        return "educational"
    if any(term in lower for term in ("bearish", "düşüş", "short", "alt likidite")):
        return "bearish"
    if any(term in lower for term in ("bullish", "yükseliş", "long", "üst likidite", "hedefine doğru")):
        return "bullish"
    return "neutral"


def extract_doctrine(feed_item: dict[str, Any]) -> dict[str, Any]:
    """Extract SMC/MPA doctrine tags from one social feed item."""
    text = str(feed_item.get("content", ""))
    upper = text.upper()
    lower = text.lower()

    symbols = _extract_symbols(text)
    timeframes = _extract_timeframes(text)

    structure_terms: list[str] = []
    for term in ("MSB", "BOS", "CHOCH", "HH", "HL", "LH", "LL", "MPA"):
        if re.search(rf"\b{term}\b", upper):
            structure_terms.append(term)

    zones: list[str] = []
    for term in ("FVG", "OTE"):
        if re.search(rf"\b{term}\b", upper):
            zones.append(term)
    if "order block" in lower:
        zones.append("Order Block")

    liquidity_terms: list[str] = []
    if any(term in lower for term in ("likidite temiz", "liquidity sweep", "sweep", "stop hunt")):
        liquidity_terms.append("liquidity_sweep")
    if "likidite" in lower and "hedef" in lower:
        liquidity_terms.append("liquidity_target")

    risk_terms: list[str] = []
    if any(term in lower for term in ("risk yönet", "sermayeyi kor", "stop", "sl", "tp1", "break-even", "breakeven")):
        risk_terms.append("risk_management")

    recipe: list[str] = []
    if any(term in structure_terms for term in ("MSB", "BOS", "CHOCH")):
        recipe.append("market_structure_shift")
    if "OTE" in zones or "pullback" in lower:
        recipe.append("pullback")
    if "FVG" in zones:
        recipe.append("fvg_reaction")
    if "liquidity_target" in liquidity_terms:
        recipe.append("liquidity_target")
    if "liquidity_sweep" in liquidity_terms and not symbols:
        recipe.append("reversal_zone")
    if risk_terms:
        recipe.append("risk_first")

    signal_count = sum(
        bool(bucket)
        for bucket in (symbols, timeframes, structure_terms, zones, liquidity_terms, risk_terms, recipe)
    )
    confidence = min(0.95, 0.2 + signal_count * 0.1)

    return {
        "feed_id": str(feed_item.get("id", "")),
        "source": feed_item.get("source"),
        "symbols": symbols,
        "timeframes": timeframes,
        "bias": _bias(text, symbols),
        "structure_terms": _unique(structure_terms),
        "zones": _unique(zones),
        "liquidity_terms": _unique(liquidity_terms),
        "risk_terms": _unique(risk_terms),
        "levels": _extract_levels(text),
        "setup_recipe": _unique(recipe),
        "confidence": round(confidence, 2),
    }
