"""Content-pipeline compliance checker — Phase 4a, shared by Lane C (#12) and the
multi-TF commentary generator (#13).

Growth-OS guardrails on generated copy (no live config / risk touched):
- **Banned promise-phrases** — the REAL Turkish list from
  ``docs/marketing/GO_TO_MARKET_2026-05-28.md:16-22`` (ultrareview C1).
- **No absolute-$ amounts** — decision #5: result/PnL copy shows ratio/risk
  metrics only (R:R, %, risk); absolute dollar profit/loss is never shown.
- **No performance-% claims** — win-rate / return promises (e.g. "73.2% win
  rate", "%80 kazanç") are banned; risk-% (e.g. "2% risk") and R:R are allowed.

The mandated disclaimer reuses ``engine.content_jobs`` COMPLIANCE_TR/EN.
"""
from __future__ import annotations

import re

from engine.content_jobs import COMPLIANCE_EN, COMPLIANCE_TR

# GO_TO_MARKET_2026-05-28.md:16-22 — verbatim (curly quotes stripped).
BANNED_TR_PHRASES = [
    "Kesin kazanç",
    "Garantili getiri",
    "Her gün kâr",
    "Pasif gelir makinesi",
    "Sinyal al, kazan",
    "Fonumuza para yatır",
]

# CMP-3 — EN-first growth requires parity coverage for the same compliance
# surface. Source: P-002.5 CMP-2 phrase matrix (12 entries, all lowercase).
# All entries are kept lowercase + comma-free so ``_norm`` substring match
# behaves identically to the Turkish side. Add to this list (not modify) to
# keep the banned-phrase tag shape stable for downstream consumers.
BANNED_EN_PHRASES = [
    "guaranteed profit",
    "guaranteed returns",
    "risk-free",
    "risk free",
    "no loss",
    "no-loss",
    "can't lose",
    "cannot lose",
    "double your money",
    "passive income machine",
    "get rich",
    "get-rich-quick",
    "signal and earn",
    "guaranteed win",
]


def _norm(s: str) -> str:
    """Lowercase, drop commas, collapse whitespace — for tolerant matching.

    Turkish ``İ`` (U+0130) lowercases to ``i`` + combining dot above; map it to a
    plain ``i`` first (and strip any stray combining dot) so phrases match
    regardless of the writer's casing.
    """
    s = (s or "").replace("İ", "i").replace(",", " ").lower().replace("\u0307", "")
    return re.sub(r"\s+", " ", s).strip()


_BANNED_TR_NORM = [(p, _norm(p)) for p in BANNED_TR_PHRASES]
_BANNED_EN_NORM = [(p, _norm(p)) for p in BANNED_EN_PHRASES]


# CMP-3 — single product price token (the $39 founding-member / lifetime /
# one-time offer) is the ONLY dollar amount allowed in marketing copy. All
# other $-amounts (per-trade PnL, account balance, $250 trade, etc.) remain
# rejected by the regular absolute_money gate. Keep this scope tight: only
# matches the canonical price string + the cadence suffix list.
PRODUCT_PRICE_USD = 39
_PRICE_WHITELIST = re.compile(
    rf"\$\s*{PRODUCT_PRICE_USD}\b"
    rf"(?:\s*(?:lifetime|one[- ]?time|once|tek\s+seferlik|ömür\s+boyu))?",
    re.IGNORECASE,
)

# Absolute money amount: $/₺ either side of a number, or a currency-tagged number.
_MONEY = re.compile(
    r"\$\s*\d[\d.,]*"                              # $250, $1,000
    r"|\d[\d.,]*\s*\$"                             # 250$
    r"|₺\s*\d[\d.,]*|\d[\d.,]*\s*₺"                # ₺ amounts
    r"|\b\d[\d.,]*\s*(?:usd|usdt|dolar|tl)\b",     # 250 USD, 1000 TL
    re.IGNORECASE,
)

# Any percentage token, and the performance words that make one a *promise*.
_PCT = re.compile(r"%\s*\d[\d.,]*|\b\d[\d.,]*\s*%|yüzde\s+\d", re.IGNORECASE)
_PERF_WORDS = re.compile(
    r"kazanç|kazan\b|getiri|kâr\b|kar\b|win\s*rate|isabet|başarı|return|profit",
    re.IGNORECASE,
)


def _has_performance_pct(text: str) -> bool:
    """A percentage is a violation only when it sits next to a performance word."""
    for m in _PCT.finditer(text):
        lo, hi = max(0, m.start() - 30), min(len(text), m.end() + 30)
        if _PERF_WORDS.search(text[lo:hi]):
            return True
    return False


# CMP-3 — unlabeled simulation: backtest/shadow/testnet/replay/hypothetical
# copy MUST carry an explicit [BACKTEST]/[TESTNET]/[SIMULATED]/[SIM]/[REPLAY]
# label token; otherwise it leaks as if it were live. Single label per emit
# (deduped at call site).
_SIM_WORDS = re.compile(
    r"backtest|simulated|simülasyon|simulasyon|shadow|testnet|replay|hypothetical",
    re.IGNORECASE,
)
_SIM_LABEL = re.compile(
    r"\[(BACKTEST|TESTNET|SIMULATED|SIM|REPLAY)\]",
    re.IGNORECASE,
)


def find_violations(text: str, lang: str = "all") -> list[str]:
    """Return a list of compliance violation tags; empty == clean.

    CMP-3 ``lang`` parameter (additive, default ``"all"`` preserves backward
    compat):
      - ``"tr"``   → scan Turkish banned list only.
      - ``"en"``   → scan English banned list only.
      - ``"all"``  → scan both lists (default — recommended for EN-first funnel).
    Money / performance-pct / unlabeled-simulation checks always run regardless
    of ``lang`` (they are language-agnostic gates).
    """
    t = text or ""
    tn = _norm(t)
    out: list[str] = []
    scan_tr = lang in ("tr", "all")
    scan_en = lang in ("en", "all")
    if scan_tr:
        for original, norm in _BANNED_TR_NORM:
            if norm in tn:
                out.append(f"banned_phrase:{original}")
    if scan_en:
        for original, norm in _BANNED_EN_NORM:
            if norm in tn:
                out.append(f"banned_phrase:{original}")
    # Money gate: any $-amount that is not EXACTLY the whitelisted $39 product
    # price (e.g. "$39", "$39 lifetime") is a violation. Prefix/partial matches
    # such as "$39,000", "$39.99" or "$390" are NOT the price and stay banned
    # (fullmatch only — a non-anchored prefix match would leak them).
    if any(not _PRICE_WHITELIST.fullmatch(m.group(0)) for m in _MONEY.finditer(t)):
        out.append("absolute_money")
    if _has_performance_pct(t):
        out.append("performance_pct_claim")
    # Unlabeled simulation gate: presence of any sim-word without an explicit
    # bracketed label token is a violation.
    if _SIM_WORDS.search(t) and not _SIM_LABEL.search(t):
        out.append("unlabeled_simulation")
    return out


def has_disclaimer(text: str, lang: str = "tr") -> bool:
    """True if the mandated disclaimer for ``lang`` is present in ``text``."""
    t = text or ""
    if lang == "en":
        return COMPLIANCE_EN in t
    if lang == "both":
        return COMPLIANCE_TR in t and COMPLIANCE_EN in t
    return COMPLIANCE_TR in t


__all__ = [
    "BANNED_TR_PHRASES",
    "BANNED_EN_PHRASES",
    "PRODUCT_PRICE_USD",
    "find_violations",
    "has_disclaimer",
    "COMPLIANCE_TR",
    "COMPLIANCE_EN",
]
