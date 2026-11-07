---
id: T-20261107-17
title: CRITICAL uyarılar LLM'siz + Telegram HTML kaçışı (LLM denetimi A3/A4)
from: claude-code
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261107-16
created: 2026-11-07
touches_live: false
---

## Amaç
LLM katmanı denetiminin A3/A4 bulguları: CRITICAL güvenlik uyarıları (breaker HALT, crash loop,
unhealthy, overseer heartbeat) LLM formatlayıcıyla yeniden yazılıyor ve ham metin kayboluyordu;
Telegram'a HTML kaçışsız gidiyordu (`<` → mesaj reddi → uyarı kaybı).

## Beklenen çıktı (Definition of Done)
- [x] `ops/alerter/alerter.py`: severity CRITICAL ise LLM formatlayıcı atlanır (ham, kural metni gider).
- [x] `ops/alerter/rules.py`: breaker log metni `_esc()` ile kaçışlı.
- [x] `ops/alerter/formatter.py`: LLM'in yazdığı tüm alanlar HTML-escape.
- [x] `ops/alerter/telegram_client.py`: 400 "can't parse entities" → bir kez düz metin olarak yeniden gönder.
- [x] RED→GREEN: `tests/test_alerter_critical_formatting.py` (7); alerter + downstream (overseer, routines) 457 passed.
- [ ] Deploy: alerter-only (`build efloud-bot` + `up -d --no-deps alerter`) — merge sonrası.
