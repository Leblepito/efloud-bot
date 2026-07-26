"""R-13 (2026-07-18): overseer ölü kuralları — bot tarafı yapısal event emisyonu
+ compose kablolaması.

Üç ölü nokta kapatılıyor:
  1. `cycle_start` yalnız bus.publish'e (WS) gidiyordu — log dosyasına hiç
     düşmüyordu → rule_cycle_gap ölüydü. bot_runner artık log_event de atar.
  2. `regime_change` HİÇBİR yerde emit edilmiyordu → rule_regime_flipflop
     ölüydü. Orchestrator per-symbol rejim değişimini log_event'le yayar.
  3. `REVERSE_BLOCKED_NOT_PROFITABLE` yalnız düz-metin reason içinde geçiyordu
     (line.get("event") eşleşmez) → rule_reverse_block_streak ölüydü.
Ek: compose'ta overseer'ın journal path'i emekli aggressive instance'a
bakıyordu (canlı bot state_1k'ya yazar) ve bot servisi log dosyasını hiç
yazmıyordu (EFLOUD_LOG_FILE yalnız overseer'da — okuyan var, yazan yoktu).
"""
from __future__ import annotations

import logging

import yaml


# ─────────────────────────────────────────────────────────────────────
# regime_change emisyonu — modül-seviyesi helper (orchestrator inline çağırır)
# ─────────────────────────────────────────────────────────────────────


def test_emit_regime_change_on_transition(caplog):
    from engine.safe_orchestrator import _emit_regime_change
    last: dict = {"BTC/USDT": "TREND"}
    with caplog.at_level(logging.INFO):
        _emit_regime_change(last, "BTC/USDT", "RANGE")
    recs = [r for r in caplog.records if getattr(r, "event", None) == "regime_change"]
    assert len(recs) == 1
    assert recs[0].symbol == "BTC/USDT"
    assert recs[0].old == "TREND"
    assert recs[0].new == "RANGE"
    assert last["BTC/USDT"] == "RANGE", "helper son rejimi güncellemeli"


def test_emit_regime_change_silent_on_first_observation(caplog):
    """İlk gözlem = değişim değil — cold-boot'ta flipflop false-positive olmasın."""
    from engine.safe_orchestrator import _emit_regime_change
    last: dict = {}
    with caplog.at_level(logging.INFO):
        _emit_regime_change(last, "ETH/USDT", "TREND")
    assert not [r for r in caplog.records if getattr(r, "event", None) == "regime_change"]
    assert last["ETH/USDT"] == "TREND"


def test_emit_regime_change_silent_on_same_regime(caplog):
    from engine.safe_orchestrator import _emit_regime_change
    last: dict = {"BTC/USDT": "RANGE"}
    with caplog.at_level(logging.INFO):
        _emit_regime_change(last, "BTC/USDT", "RANGE")
    assert not [r for r in caplog.records if getattr(r, "event", None) == "regime_change"]


# ─────────────────────────────────────────────────────────────────────
# REVERSE_BLOCKED_NOT_PROFITABLE emisyonu
# ─────────────────────────────────────────────────────────────────────


def test_emit_reverse_block_fires_on_marker(caplog):
    from engine.safe_orchestrator import _emit_reverse_block
    with caplog.at_level(logging.INFO):
        _emit_reverse_block("BTC/USDT", "REVERSE_BLOCKED_NOT_PROFITABLE pnl=0.010% < min 0.150%")
    recs = [r for r in caplog.records
            if getattr(r, "event", None) == "REVERSE_BLOCKED_NOT_PROFITABLE"]
    assert len(recs) == 1
    assert recs[0].symbol == "BTC/USDT"


def test_emit_reverse_block_silent_on_other_reasons(caplog):
    """Reverse başka sebeple reddedildiyse (cooldown vb.) bu event ATILMAZ —
    kural adı spesifik, sinyal kirlenmesin."""
    from engine.safe_orchestrator import _emit_reverse_block
    with caplog.at_level(logging.INFO):
        _emit_reverse_block("BTC/USDT", "reverse cooldown active (120s left)")
    assert not [r for r in caplog.records
                if getattr(r, "event", None) == "REVERSE_BLOCKED_NOT_PROFITABLE"]


# ─────────────────────────────────────────────────────────────────────
# docker-compose.prod.yml kablolaması
# ─────────────────────────────────────────────────────────────────────


def _compose():
    with open("docker-compose.prod.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_compose_overseer_journal_points_to_live_state_1k():
    """Emekli aggressive instance yerine CANLI bot'un journal'ı (state_1k —
    bot_runner TradeJournal(state_dir/trade_journal.jsonl), config phase2_1k)."""
    svc = _compose()["services"]["overseer"]
    env = svc.get("environment", [])
    assert "EFLOUD_OVERSEER_JOURNAL_PATH=/app/state_1k/trade_journal.jsonl" in env, \
        f"journal path canlı state_1k'ya bakmalı; environment: {env}"
    vols = svc.get("volumes", [])
    assert any(v.startswith("efloud_state_1k:/app/state_1k") for v in vols), \
        f"state_1k volume mount edilmeli (ro); volumes: {vols}"


def test_compose_bot_writes_the_log_file_overseer_reads():
    """Overseer EFLOUD_LOG_FILE'ı OKUR ama hiçbir servis YAZMIYORDU
    (configure_json_logging stdout-only). Bot servisi artık env ile dosyayı
    yazar; utils.logging.attach_json_file_handler backend/main.py'de devreye
    girer (env yoksa no-op — default-OFF)."""
    svc = _compose()["services"]["efloud-bot"]
    env = svc.get("environment", []) or []
    assert "EFLOUD_LOG_FILE=/app/logs/efloud_bot.log" in env, \
        f"bot servisi log dosyasını yazacak env'i taşımalı; environment: {env}"
