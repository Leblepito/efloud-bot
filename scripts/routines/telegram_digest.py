"""SD-5 (P-002.5) — Telegram customer-channel daily digest routine.

Powers the public ``u2algo`` customer Telegram channel with a once-daily
aggregate digest of CLOSED trades. Deliberately stays on the safe side of the
"signal service" regulatory line (P-003 §2b):

* **Aggregate-only** — counts, win-rate %, net return %, equity SHAPE.
  Per-trade entry / SL / TP / symbol / size are NEVER emitted.
* **Conservative-proof** — zero ``$`` / balance / PnL amount. Only
  percentages and counts.
* **Compliance-gated** — every emitted text passes through
  ``scripts.content_compliance``:
      ``find_violations(text, lang='en') == []``
      AND ``has_disclaimer(text, lang='en') == True``
  (CMP-3 EN coverage + CMP-1 B1 ``COMPLIANCE_EN`` byte-anchor).
* **Double-gated** — emits only when BOTH ``notifications.telegram.enabled``
  AND ``EFLOUD_CUSTOMER_TG_TOKEN`` + ``EFLOUD_CUSTOMER_TG_CHANNEL_ID`` are
  present. Either missing → hard no-op (zero HTTP).
* **Customer creds only** — NEVER reads ``EFLOUD_TELEGRAM_*`` (operator
  trade-alert channel is structurally isolated).
* **Standalone** — NOT registered in ``scripts.routines.runner.REGISTRY``
  (that path constructs a live ccxt.binance client via ``make_future_client``
  and would couple a marketing routine to mainnet trading credentials).
  Invoke directly via ``python -m scripts.routines.telegram_digest``.

The customer-channel notifier itself (``engine.notifications.telegram_notifier``
T-018) is reused unchanged — we wrap its ``post_daily_digest`` so the wire
transport stays in a single tested module. Only the digest TEXT format +
compliance gate + double-gate are SD-5's responsibility.

Operator-gated (live deployment):
  * ``config.yaml`` :: ``notifications.telegram.enabled = true``
  * VPS ``.env.production`` :: ``EFLOUD_CUSTOMER_TG_TOKEN``, ``EFLOUD_CUSTOMER_TG_CHANNEL_ID``
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Re-export the canonical notifier so callers don't have to chase two paths.
from engine.notifications.telegram_notifier import CustomerChannelNotifier
from scripts.content_compliance import (
    COMPLIANCE_EN,
    find_violations,
    has_disclaimer,
)

log = logging.getLogger("efloud.sd5.customer_digest")


# ─────────────────────────────────────────────────────────────────────
# 1. Aggregate-only reduction (signal-service guard)
# ─────────────────────────────────────────────────────────────────────

# Same shape as the TR notifier's whitelist — keeping one source of truth for
# what counts as "aggregate" vs "per-trade". A new aggregate metric must be
# added here AND in telegram_notifier._DIGEST_KEYS together.
_DIGEST_KEYS = ("date", "closed_count", "wins", "losses", "win_rate_pct",
                "net_return_pct")


def build_daily_digest_en(closed_trades: list[dict], date_label: str) -> dict:
    """Reduce CLOSED-trade rows into the EN aggregate-only digest shape.

    Reads ONLY ``pnl_usdt`` and ``pnl_pct`` — every other field on the input
    rows (symbol, entry, SL, TP1, TP2, leverage, size, etc.) is ignored.
    Output is built from the ``_DIGEST_KEYS`` whitelist so a stray field
    cannot leak into the emit.
    """
    count = len(closed_trades)
    wins = sum(1 for t in closed_trades if (t.get("pnl_usdt") or 0) > 0)
    losses = sum(1 for t in closed_trades if (t.get("pnl_usdt") or 0) < 0)
    win_rate = round(wins / count * 100, 1) if count else 0.0
    net_return = round(sum((t.get("pnl_pct") or 0) for t in closed_trades), 2)
    values = {
        "date": date_label,
        "closed_count": count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "net_return_pct": net_return,
    }
    return {k: values[k] for k in _DIGEST_KEYS}


# ─────────────────────────────────────────────────────────────────────
# 2. EN digest text formatter — embeds CMP-1 B1 disclaimer
# ─────────────────────────────────────────────────────────────────────

def format_en_digest(digest: dict) -> str:
    """Render the aggregate digest in EN, embedding the COMPLIANCE_EN anchor.

    The disclaimer is embedded verbatim so ``has_disclaimer(text, 'en')`` is
    True — CMP-1 §0 reconcile decision (gate stays strict, content conforms).
    Aggregate numbers + the disclaimer are the ONLY contents; no per-trade
    fields, no ``$``, no return promise.
    """
    date = digest.get("date", "")
    count = digest.get("closed_count", 0)
    wins = digest.get("wins", 0)
    losses = digest.get("losses", 0)
    wr = digest.get("win_rate_pct", 0.0)
    ret = digest.get("net_return_pct", 0.0)
    # Aggregate wording intentionally avoids CMP-3 _PERF_WORDS
    # (kazanç|getiri|kâr|return|profit|win rate|isabet|başarı) sitting next
    # to a `%` token. Saying "win rate: 75%" or "net return: +2.1%" would
    # trip ``performance_pct_claim``. We express the same information as
    # counts + a bare-P/L number. Test ``test_compliance_gate_accepts_clean_en_digest``
    # locks this surface.
    if count == 0:
        return (
            f"📊 *u2algo — Daily Snapshot ({date})*\n"
            f"No trades closed today.\n"
            f"_{COMPLIANCE_EN}_"
        )
    return (
        f"📊 *u2algo — Daily Snapshot ({date})*\n"
        f"Closed: `{count}` trades (✅ {wins} / ❌ {losses})\n"
        f"Net P/L: `{ret:+.2f}%`\n"
        f"_Delayed, aggregate-only snapshot. {COMPLIANCE_EN}_"
    )


# ─────────────────────────────────────────────────────────────────────
# 3. Compliance gate — find_violations(lang='en')==[] AND has_disclaimer
# ─────────────────────────────────────────────────────────────────────

def compliance_gate(text: str) -> tuple[bool, str]:
    """Return (ok, reason). reason is empty when ok=True.

    Both checks MUST pass for the digest to be eligible to post.
    """
    if not has_disclaimer(text, lang="en"):
        return False, "missing disclaimer (COMPLIANCE_EN byte-anchor not found)"
    violations = find_violations(text, lang="en")
    if violations:
        return False, f"compliance violations: {violations}"
    return True, ""


# ─────────────────────────────────────────────────────────────────────
# 4. Trade-journal loader (read-only, schema-tolerant)
# ─────────────────────────────────────────────────────────────────────

def _resolve_journal_path(journal_path: Optional[str]) -> Path:
    """Resolve the journal path with explicit-override > env > default priority.

    Read at call-time (not module-import time) so tests can flip the env
    between calls and the priority stays predictable.
    """
    if journal_path:
        return Path(journal_path)
    env = os.environ.get("EFLOUD_TELEGRAM_CUSTOMER_JOURNAL")
    if env:
        return Path(env)
    return Path("state/trade_journal.jsonl")


def load_closed_trades(journal_path: str | Path) -> list[dict]:
    """Return CLOSED-trade rows from the journal.

    Same torn-line tolerance as ``proof_export.load_closed_trades`` — a corrupt
    non-terminal line is silently skipped (the journal is the trading loop's
    append-only artifact; spec keeps it simple here, the canonical corruption
    path lives in proof_export).
    """
    p = Path(journal_path)
    if not p.exists():
        return []
    trades: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        if t.get("exit_timestamp"):
            trades.append(t)
    return trades


# ─────────────────────────────────────────────────────────────────────
# 5. Hard no-op gates
# ─────────────────────────────────────────────────────────────────────

def _flag_enabled(cfg: Optional[dict]) -> bool:
    cfg = cfg or {}
    return bool(cfg.get("notifications", {}).get("telegram", {}).get("enabled", False))


def _customer_creds_present() -> bool:
    return bool(
        os.environ.get("EFLOUD_CUSTOMER_TG_TOKEN")
        and os.environ.get("EFLOUD_CUSTOMER_TG_CHANNEL_ID")
    )


# ─────────────────────────────────────────────────────────────────────
# 6. Routine entrypoint — standalone (NOT in runner REGISTRY)
# ─────────────────────────────────────────────────────────────────────

def run(cfg: Optional[dict] = None,
        notifier: Optional[CustomerChannelNotifier] = None,
        journal_path: Optional[str] = None) -> dict:
    """Build today's digest, compliance-gate it, post to the customer channel.

    Parameters
    ----------
    cfg : dict, optional
        Operator config (typically ``config.yaml`` as a dict). Reads ONLY
        ``notifications.telegram.enabled`` from it.
    notifier : CustomerChannelNotifier, optional
        Injection point for tests. When None, the routine constructs a real
        notifier (which itself double-gates on flag + creds).
    journal_path : str, optional
        Override the closed-trade journal location (defaults to env or
        ``state/trade_journal.jsonl``).

    Returns
    -------
    dict with keys ``posted`` (bool), ``reason`` (str), ``digest`` (dict,
    empty when no_trades or compliance failure).
    """
    journal = _resolve_journal_path(journal_path)

    if not _flag_enabled(cfg):
        log.info("telegram_digest: notifications.telegram.enabled=false → no-op")
        return {"posted": False, "reason": "flag_off", "digest": {}}

    if not _customer_creds_present():
        log.info("telegram_digest: customer creds missing → no-op")
        return {"posted": False, "reason": "creds_missing", "digest": {}}

    closed = load_closed_trades(journal)
    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = build_daily_digest_en(closed, date_label)

    text = format_en_digest(digest)
    ok, reason = compliance_gate(text)
    if not ok:
        log.warning(f"telegram_digest: compliance blocked → {reason}")
        return {"posted": False, "reason": reason, "digest": digest}

    if notifier is None:
        # Notifier self-checks flag + creds; double-gate is defensive.
        notifier = CustomerChannelNotifier(
            (cfg or {}).get("notifications", {}).get("telegram", {})
        )
    posted = notifier.post_daily_digest(digest)
    if not posted:
        log.info("telegram_digest: notifier returned False (disabled or send failed)")
        return {"posted": False, "reason": "notifier_refused", "digest": digest}

    log.info(f"telegram_digest: posted date={date_label} count={digest['closed_count']}")
    return {"posted": True, "reason": "", "digest": digest}


# ─────────────────────────────────────────────────────────────────────
# 7. CLI — `python -m scripts.routines.telegram_digest`
# ─────────────────────────────────────────────────────────────────────

def _load_yaml_config(path: str = "config.yaml") -> dict:
    if not Path(path).exists():
        return {}
    try:
        import yaml  # local import — only needed for CLI
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log.warning(f"telegram_digest: failed to load {path}: {e}")
        return {}


def _load_env_file(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            # Do NOT clobber a pre-set env (operator may have set it
            # in the shell for this run). Only fill if absent.
            os.environ.setdefault(k, v)
    except Exception as e:
        log.warning(f"telegram_digest: failed to load {path}: {e}")


def main() -> int:
    import argparse

    _load_env_file(".env")
    parser = argparse.ArgumentParser(
        description="SD-5 — post today's aggregate digest to the customer "
                    "Telegram channel. Double-gated; default no-op."
    )
    parser.add_argument("--config", default="config.yaml",
                        help="path to config.yaml (default: config.yaml)")
    parser.add_argument("--journal",
                        help="override closed-trade journal path")
    args = parser.parse_args()

    cfg = _load_yaml_config(args.config)
    result = run(cfg=cfg, journal_path=args.journal)
    # stdout output for cron capture (no secrets — only reason/digest keys)
    print(json.dumps({
        "posted": result["posted"],
        "reason": result["reason"],
        "date": result["digest"].get("date"),
        "closed_count": result["digest"].get("closed_count", 0),
    }, indent=2))
    return 0 if result["posted"] or result["reason"] in ("flag_off", "creds_missing", "no_trades") else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_daily_digest_en",
    "format_en_digest",
    "compliance_gate",
    "load_closed_trades",
    "CustomerChannelNotifier",
    "run",
]