---
id: T-20261104-03
title: Review'lar sonrası Telegram metodolojisini tek skill olarak skills/'e promote et
from: claude-code
to: claude-code
status: blocked
claimed_by: claude-code
reviewer: abacus
created: 2026-11-04
touches_live: false
---

## Amaç
T-01 (laptop rulebook) + T-02 (Abacus review) + T-06 (Hermes skill v2) bitince 5 taslaktan 2'sini birleştir:
`skills/efloud-telegram-methodology/` (Telegram terimi ↔ motor kodu sözlüğü + fark/hipotez
listesi). risk-management → `agents/risk-manager.md`'ye "kaynak = canlı config" notu;
tradingview-integration → `skills/tradingview-mcp`'ye bölüm; master-orchestrator → REJECT
(ikinci emir yolu).

## Girdi
- T-20261104-01, T-20261104-02, T-20261104-06 çıktıları

## Beklenen çıktı
- [ ] PR: yeni skill (Hermes v2 taslaklarından) + incubator REVIEW.md `status: promoted` + `tests/collab` ve `tests/hooks/test_desk_plugin.py` yeşil
- [ ] Hipotez kartları (motor değişikliği YOK): H-TG1 teyit tipi (LuxAlgo setup + engulfing vs mLTF BOS/CHoCH), H-TG3 kademeli TP (motor bugün 50/50: `exchange/__init__.py:1065`). TP1 sonrası BE ZATEN VAR (`_move_sl_to_breakeven`, `exchange/__init__.py:1642`) → hipotez değil. Her kart: default-OFF flag + NET-cost kanıt planı.

## Kısıtlar
- Motor/config'e dokunma; yalnız skill/doküman.

## Log
- 2026-11-04 claude-code: blocked — T-01, T-02, T-06 bekleniyor.

## Review
