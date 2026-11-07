---
id: T-20261107-11
title: Orphan (takip edilmeyen) pozisyon varken tekrarlayan Telegram uyarısı
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261107-05
created: 2026-11-07
touches_live: false
---

## Amaç
#314 risk review M3 follow-up'ı: `entry_rollback_failed` uyarısı tek seferliktir; Telegram
gönderimi başarısız olursa kaybolur ve borsada botun takip etmediği canlı bir pozisyon fark
edilmeden kalabilir. Reconcile her döngüde `ORPHAN POSITION DETECTED` satırını logladığı
için, alerter bu satırdan pozisyon durdukça tekrarlayan bir uyarı üretir.

## Girdi
- `exchange/__init__.py` `OrderManager.reconcile()` orphan tespiti (serbest metin WARNING, logger `efloud.exchange`).
- `ops/alerter/rules.py` (#314 üstüne stacked).

## Beklenen çıktı (Definition of Done)
- [x] `OrphanPositionRule`: (sembol, yön) başına saatte 1 mesaj; detaysız satır da eşlenir; HTML-escape; `ai_format=False`.
- [x] Bayrak: `EFLOUD_ALERTER_SL_ALERTS` (aynı aile: "canlı pozisyon bot koruması dışında olabilir"); yeni compose satırı yok.
- [x] Testler: birim + gerçek yol sözleşme testi (open → SL hatası → rollback hatası → 2 reconcile döngüsünde orphan satırı kurala eşleniyor).
- [ ] Operatör: #308 → #314 → bu PR merge sırası.

## Kısıtlar
- Trading kodu (exchange/engine/configs/backend) DEĞİŞMEDİ; compose değişmedi.
- Yalnız mid bot.

## Log
- 2026-11-07 claude-code: orphan kuralı + testler; #314 üstüne stacked PR açıldı.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
