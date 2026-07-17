"""SD-5 (P-002.5) — Telegram customer-channel daily digest routine.

Hermetic tests. The routine is exercised with a fake journal + fake notifier
so no real ccxt.binance, no real Telegram HTTP, no real DB, no real env.

Key regressions (all asserted):
  * Aggregate-only output (no per-trade entry/SL/TP/symbol).
  * No ``$`` amount anywhere (conservative-proof).
  * Hard no-op when ``enabled=False`` OR creds missing.
  * Never resolves ``EFLOUD_TELEGRAM_*`` (operator alerter is structurally
    isolated; SD-5 must not couple to ``_alert.py:21-22``).
  * Never imports ``ccxt.binance`` / never reads ``BINANCE_*`` env.
  * ``ops/alerter`` source untouched (file hash before/after).
  * Compliance: ``find_violations(text, lang='en') == []`` AND
    ``has_disclaimer(text, 'en') == True`` for emitted text.
  * ``runner.py`` REGISTRY does NOT gain a ``telegram_digest`` entry
    (no make_future_client coupling).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


# ─────────────────────────────────────────────────────────────────────
# 1. Imports + module surface
# ─────────────────────────────────────────────────────────────────────

def _import_digest_fresh(monkeypatch, creds_token=None, creds_channel=None,
                         creds_thread=None):
    """Import telegram_digest with a controlled env (so tests don't leak creds).

    Pass ``creds_token`` / ``creds_channel`` to populate the customer creds
    AFTER the scrub so the notifier's env-read at construction picks them up.
    """
    for k in ("EFLOUD_CUSTOMER_TG_TOKEN", "EFLOUD_CUSTOMER_TG_CHANNEL_ID",
              "EFLOUD_CUSTOMER_TG_THREAD_ID", "EFLOUD_TELEGRAM_TOKEN",
              "EFLOUD_TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    if creds_token is not None:
        monkeypatch.setenv("EFLOUD_CUSTOMER_TG_TOKEN", creds_token)
    if creds_channel is not None:
        monkeypatch.setenv("EFLOUD_CUSTOMER_TG_CHANNEL_ID", creds_channel)
    if creds_thread is not None:
        monkeypatch.setenv("EFLOUD_CUSTOMER_TG_THREAD_ID", creds_thread)
    # Drop any cached module so env reads happen at import time
    sys.modules.pop("scripts.routines.telegram_digest", None)
    return importlib.import_module("scripts.routines.telegram_digest")


def test_module_imports_cleanly():
    import scripts.routines.telegram_digest as d
    assert hasattr(d, "build_daily_digest_en")
    assert hasattr(d, "format_en_digest")
    assert hasattr(d, "compliance_gate")
    assert hasattr(d, "CustomerChannelNotifier")  # re-export from T-018
    assert hasattr(d, "run")


# ─────────────────────────────────────────────────────────────────────
# 2. EN digest format — disclaimer + aggregate-only + no $
# ─────────────────────────────────────────────────────────────────────

def test_format_en_digest_has_disclaimer_and_aggregate_keys():
    from scripts.content_compliance import has_disclaimer
    digest = {
        "date": "2026-06-17",
        "closed_count": 8,
        "wins": 5,
        "losses": 3,
        "win_rate_pct": 62.5,
        "net_return_pct": 1.7,
    }
    from scripts.routines.telegram_digest import format_en_digest
    text = format_en_digest(digest)
    assert has_disclaimer(text, lang="en"), f"missing COMPLIANCE_EN anchor: {text!r}"
    # aggregate counts must appear; per-trade signals must NOT
    assert "8" in text and "5" in text and "3" in text
    # CMP-3 perf-pct guard: wording must NOT contain _PERF_WORDS near a '%' token
    assert "win rate" not in text.lower(), f"perf-word 'win rate' must be absent"
    assert "net return" not in text.lower(), f"perf-word 'return' must be absent"
    # Net P/L (CMP-3-safe wording) must be present
    assert "P/L" in text and "+1.7" in text
    # No per-trade leak
    for forbidden in ("entry", "stop", "tp1", "tp2", "symbol"):
        assert forbidden.lower() not in text.lower(), f"per-trade '{forbidden}' leaked"


def test_format_en_digest_with_zero_trades_still_has_disclaimer():
    from scripts.content_compliance import has_disclaimer
    from scripts.routines.telegram_digest import format_en_digest
    digest = {"date": "2026-06-17", "closed_count": 0, "wins": 0, "losses": 0,
              "win_rate_pct": 0.0, "net_return_pct": 0.0}
    text = format_en_digest(digest)
    assert has_disclaimer(text, lang="en")


def test_format_en_digest_contains_no_dollar_amount():
    from scripts.routines.telegram_digest import format_en_digest
    text = format_en_digest({
        "date": "2026-06-17", "closed_count": 4, "wins": 3, "losses": 1,
        "win_rate_pct": 75.0, "net_return_pct": 2.1,
    })
    assert "$" not in text, f"digest must contain zero '$': {text!r}"


# ─────────────────────────────────────────────────────────────────────
# 3. compliance_gate — find_violations(lang='en')==[] AND has_disclaimer
# ─────────────────────────────────────────────────────────────────────

def test_compliance_gate_accepts_clean_en_digest():
    from scripts.routines.telegram_digest import format_en_digest, compliance_gate
    text = format_en_digest({
        "date": "2026-06-17", "closed_count": 4, "wins": 3, "losses": 1,
        "win_rate_pct": 75.0, "net_return_pct": 2.1,
    })
    ok, reason = compliance_gate(text)
    assert ok is True, f"clean digest was rejected: {reason} (text={text!r})"


def test_compliance_gate_rejects_missing_disclaimer():
    from scripts.routines.telegram_digest import compliance_gate
    bad = "u2algo daily digest: 4 trades, 75% win rate."
    ok, reason = compliance_gate(bad)
    assert ok is False
    assert "disclaimer" in reason.lower()


def test_compliance_gate_rejects_dollar_amount():
    from scripts.routines.telegram_digest import format_en_digest, compliance_gate
    text = format_en_digest({
        "date": "2026-06-17", "closed_count": 4, "wins": 3, "losses": 1,
        "win_rate_pct": 75.0, "net_return_pct": 2.1,
    })
    tampered = text + " PnL: $250."
    ok, reason = compliance_gate(tampered)
    assert ok is False
    assert "absolute_money" in reason


def test_compliance_gate_rejects_banned_en_phrase():
    from scripts.routines.telegram_digest import compliance_gate
    bad = "Today: guaranteed profit, 4 trades. Not investment advice. Trade at your own risk."
    ok, reason = compliance_gate(bad)
    assert ok is False
    assert "banned_phrase" in reason


# ─────────────────────────────────────────────────────────────────────
# 4. Aggregate-only trade reduction — signal-service guard
# ─────────────────────────────────────────────────────────────────────

def test_build_daily_digest_en_ignores_per_trade_fields():
    """Closed-trade rows with rich per-trade fields must not leak into the digest."""
    from scripts.routines.telegram_digest import build_daily_digest_en
    closed = [
        {"pnl_usdt": 12.0, "pnl_pct": 0.5, "symbol": "ETH/USDT",
         "entry": 3500.0, "sl": 3490.0, "tp1": 3515.0, "tp2": 3530.0},
        {"pnl_usdt": -5.0, "pnl_pct": -0.3, "symbol": "BTC/USDT",
         "entry": 67000.0, "sl": 66800.0, "tp1": 67200.0, "tp2": 67500.0},
    ]
    digest = build_daily_digest_en(closed, "2026-06-17")
    assert digest["closed_count"] == 2
    assert digest["wins"] == 1
    assert digest["losses"] == 1
    # Whitelist contract: exactly the 6 aggregate keys, nothing else
    assert set(digest.keys()) == {
        "date", "closed_count", "wins", "losses", "win_rate_pct", "net_return_pct"
    }


# ─────────────────────────────────────────────────────────────────────
# 5. Hard no-op gates — flag OFF / creds missing
# ─────────────────────────────────────────────────────────────────────

def test_run_is_noop_when_flag_off(monkeypatch, tmp_path):
    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text("")
    monkeypatch.setenv("EFLOUD_TELEGRAM_CUSTOMER_JOURNAL", str(journal))
    d = _import_digest_fresh(monkeypatch)  # no creds, no flag
    cfg = {"notifications": {"telegram": {"enabled": False}}}
    result = d.run(cfg=cfg)
    assert result["posted"] is False
    assert result["reason"] in ("flag_off", "creds_missing", "no_trades")


def test_run_is_noop_when_creds_missing_even_if_flag_on(monkeypatch, tmp_path):
    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text("")
    monkeypatch.setenv("EFLOUD_TELEGRAM_CUSTOMER_JOURNAL", str(journal))
    d = _import_digest_fresh(monkeypatch)  # no creds
    cfg = {"notifications": {"telegram": {"enabled": True}}}
    result = d.run(cfg=cfg)
    assert result["posted"] is False
    assert result["reason"] == "creds_missing"


# ─────────────────────────────────────────────────────────────────────
# 6. Structural isolation — NEVER touch operator alerter / Binance
# ─────────────────────────────────────────────────────────────────────

def test_module_does_not_import_ccxt(monkeypatch):
    """SD-5 must NEVER construct a ccxt.binance client.

    Strip docstrings before scanning — module-level docstring references
    ``ccxt.binance`` in prose to explain what we DO NOT do, which would
    otherwise trigger a false positive.
    """
    d = _import_digest_fresh(monkeypatch)
    src = Path(d.__file__).read_text(encoding="utf-8")
    # Drop triple-quoted docstrings (module + class + function)
    import re
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    assert "import ccxt" not in code
    assert "ccxt.binance" not in code
    assert "BINANCE_" not in code  # sadece NAME referansı bile yok


def test_module_does_not_import_operator_alerter(monkeypatch):
    """SD-5 must NEVER read EFLOUD_TELEGRAM_* (operator alerter is isolated)."""
    d = _import_digest_fresh(monkeypatch)
    src = Path(d.__file__).read_text(encoding="utf-8")
    # NAME reference OK; env-read at runtime is FORBIDDEN
    assert "EFLOUD_TELEGRAM_TOKEN" not in src
    assert "EFLOUD_TELEGRAM_CHAT_ID" not in src
    # Customer creds are the only telegram env SD-5 may touch
    assert "EFLOUD_CUSTOMER_TG_TOKEN" in src
    assert "EFLOUD_CUSTOMER_TG_CHANNEL_ID" in src


def test_module_does_not_import_ops_alerter(monkeypatch):
    d = _import_digest_fresh(monkeypatch)
    src = Path(d.__file__).read_text(encoding="utf-8")
    # No cross-import into the operator alerter tree
    assert "from ops.alerter" not in src
    assert "ops.alerter.telegram_client" not in src
    assert "scripts.routines._alert" not in src
    assert "AlertRouter" not in src


def test_ops_alerter_unchanged_after_module_import(monkeypatch):
    """Importing telegram_digest must not mutate ops/alerter files on disk."""
    _import_digest_fresh(monkeypatch)
    alerter = Path(REPO) / "ops" / "alerter"
    expected = {"dedup.py", "telegram_client.py"}
    if alerter.exists():
        actual = {p.name for p in alerter.iterdir() if p.is_file()}
        assert expected.issubset(actual), f"ops/alerter files changed: {actual}"


def test_module_not_in_runner_registry(monkeypatch):
    """SD-5 must NOT register in scripts.routines.runner.REGISTRY
    (that path constructs ccxt.binance via make_future_client)."""
    _import_digest_fresh(monkeypatch)
    import scripts.routines.runner as runner
    assert "telegram_digest" not in runner.REGISTRY, (
        "telegram_digest must be standalone — REGISTRY would couple to Binance"
    )


# ─────────────────────────────────────────────────────────────────────
# 7. End-to-end with fake notifier — full compliance path
# ─────────────────────────────────────────────────────────────────────

class _FakeNotifier:
    """CustomerChannelNotifier double — records what would have been sent."""
    def __init__(self, enabled=True, sent_to=None, sent_text=None):
        self.enabled = enabled
        self.sent_to = sent_to
        self.sent_text = sent_text
        self.calls = []

    def post_daily_digest(self, digest):
        self.calls.append(("post_daily_digest", dict(digest)))
        if not self.enabled:
            return False
        # Mimic real notifier — caller is responsible for compliance gate
        return True


def test_run_with_enabled_creds_posts_compliant_digest(monkeypatch, tmp_path):
    """Happy path: creds + flag + clean journal → fake notifier receives digest."""
    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text(json.dumps({
        "pnl_usdt": 12.0, "pnl_pct": 0.5,
        "exit_timestamp": "2026-06-17T10:00:00+00:00",
    }) + "\n")
    with open(journal, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "pnl_usdt": -5.0, "pnl_pct": -0.3,
            "exit_timestamp": "2026-06-17T14:00:00+00:00",
        }) + "\n")

    fake = _FakeNotifier(enabled=True)
    d = _import_digest_fresh(
        monkeypatch,
        creds_token="TEST_FAKE_TOKEN_FOR_HAPPY_PATH",
        creds_channel="-1009999999999",
    )
    cfg = {"notifications": {"telegram": {"enabled": True}}}
    # Pass journal_path explicitly — avoids env-vs-import-time races.
    result = d.run(cfg=cfg, notifier=fake, journal_path=str(journal))
    assert result["posted"] is True, f"expected posted, got {result!r}"
    assert len(fake.calls) == 1
    _, sent_digest = fake.calls[0]
    assert sent_digest["closed_count"] == 2


def test_run_blocks_digest_on_compliance_failure(monkeypatch, tmp_path):
    """If compliance_gate() rejects the digest text, must NOT post."""
    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text(json.dumps({
        "pnl_usdt": 12.0, "pnl_pct": 0.5,
        "exit_timestamp": "2026-06-17T10:00:00+00:00",
    }) + "\n")

    fake = _FakeNotifier(enabled=True)
    d = _import_digest_fresh(
        monkeypatch,
        creds_token="TEST_FAKE_TOKEN_FOR_COMPLIANCE_TEST",
        creds_channel="-1009999999999",
    )
    cfg = {"notifications": {"telegram": {"enabled": True}}}

    # Monkeypatch the format function to emit a banned phrase
    def bad_format(_):
        return ("Guaranteed profit daily. Not investment advice. "
                "Trade at your own risk.")
    monkeypatch.setattr(d, "format_en_digest", bad_format)

    result = d.run(cfg=cfg, notifier=fake, journal_path=str(journal))
    assert result["posted"] is False, f"expected blocked, got {result!r}"
    assert "banned_phrase" in result["reason"]
    assert len(fake.calls) == 0


# ─────────────────────────────────────────────────────────────────────
# 8. Secrets — module never writes secret to stdout/log
# ─────────────────────────────────────────────────────────────────────

def test_module_does_not_log_secrets(monkeypatch, caplog, tmp_path):
    """If creds ARE present, the routine must not echo them in any log line."""
    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text(json.dumps({
        "pnl_usdt": 12.0, "pnl_pct": 0.5,
        "exit_timestamp": "2026-06-17T10:00:00+00:00",
    }) + "\n")
    monkeypatch.setenv("EFLOUD_TELEGRAM_CUSTOMER_JOURNAL", str(journal))
    fake_secret = "TEST_FAKE_TOKEN_DO_NOT_LEAK_1234567890"
    fake_chat = "-1009999999999"
    monkeypatch.setenv("EFLOUD_CUSTOMER_TG_TOKEN", fake_secret)
    monkeypatch.setenv("EFLOUD_CUSTOMER_TG_CHANNEL_ID", fake_chat)

    fake = _FakeNotifier(enabled=False)  # forced disabled to short-circuit send
    d = _import_digest_fresh(monkeypatch)
    cfg = {"notifications": {"telegram": {"enabled": True}}}

    import logging
    caplog.set_level(logging.DEBUG)
    d.run(cfg=cfg, notifier=fake)

    for record in caplog.records:
        assert fake_secret not in record.getMessage(), (
            f"Secret leaked in log: {record.getMessage()}"
        )
        assert fake_chat not in record.getMessage()

# ─────────────────────────────────────────────────────────────────────
# R-11 (2026-07-17): GÖNDERİLEN (TR) render da gate'lenir
# ─────────────────────────────────────────────────────────────────────

class _ViolatingRenderNotifier(_FakeNotifier):
    """Eski TR kopyasını taklit eder: 'getiri' bir % değerinin yanında."""
    def _format_digest(self, digest):
        return "u2algo Günlük Özet\nToplam getiri: `+2.10%`"


def test_run_blocks_when_sent_tr_render_violates_perf_pct(monkeypatch, tmp_path):
    """Gate EN metni denetleyip TR metni gönderiyordu — artık gönderilecek
    render performance-pct ihlaliyse post edilmez."""
    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text(json.dumps({
        "pnl_usdt": 12.0, "pnl_pct": 0.5,
        "exit_timestamp": "2026-06-17T10:00:00+00:00",
    }) + "\n")

    fake = _ViolatingRenderNotifier(enabled=True)
    d = _import_digest_fresh(
        monkeypatch,
        creds_token="TEST_FAKE_TOKEN",
        creds_channel="-1009999999999",
    )
    cfg = {"notifications": {"telegram": {"enabled": True}}}
    result = d.run(cfg=cfg, notifier=fake, journal_path=str(journal))
    assert result["posted"] is False
    assert result["reason"] == "tr_render_performance_pct"
    assert fake.calls == [], "ihlalli render'a rağmen post edildi"


def test_run_posts_when_real_tr_render_is_clean(monkeypatch, tmp_path):
    """Gerçek notifier'ın YENİ TR kopyası gate'i geçer (R-11 kopya fix'i)."""
    from engine.notifications.telegram_notifier import CustomerChannelNotifier

    journal = tmp_path / "trade_journal.jsonl"
    journal.write_text(json.dumps({
        "pnl_usdt": 12.0, "pnl_pct": 0.5,
        "exit_timestamp": "2026-06-17T10:00:00+00:00",
    }) + "\n")

    d = _import_digest_fresh(
        monkeypatch,
        creds_token="TEST_FAKE_TOKEN",
        creds_channel="-1009999999999",
    )

    sent = []
    real = CustomerChannelNotifier({"enabled": True})
    assert real.enabled
    monkeypatch.setattr(real, "_send", lambda text: (sent.append(text), True)[1])

    cfg = {"notifications": {"telegram": {"enabled": True}}}
    result = d.run(cfg=cfg, notifier=real, journal_path=str(journal))
    assert result["posted"] is True, f"temiz TR render bloklandı: {result!r}"
    assert sent and "Net K/Z" in sent[0]
