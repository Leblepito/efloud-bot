---
id: T-20261107-03
title: TP emri yerleştirilemediğinde Telegram uyarısı (alerter log kuralı)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261106-05
created: 2026-11-07
touches_live: false
---

## Amaç
Operatör, TP emri yerleştirilemediğinde (retry tükendi / kalıcı hata / -2021)
Telegram'dan haber almak istiyor. Bu, trading koduna dokunmadan, alerter'ın zaten
tail'lediği bot JSON loguna bir kural eklenerek yapılır.

## Girdi
- `exchange/__init__.py` `_retry_tp_order`: yapısal event'ler `order_manager.tp_placement_failed_after_sl` (WARNING) ve `order_manager.tp_unreachable` (CRITICAL); extras JSON satırına düşer (`utils/logging.py` JsonFormatter).
- `ops/alerter/rules.py`, `docker-compose.prod.yml` `alerter` servisi.

## Beklenen çıktı (Definition of Done)
- [x] `TpPlacementFailedRule` (`ops/alerter/rules.py`): TP1/TP2/TP1_REPAIR/TP2_REPAIR bacakları; SL bacakları hariç; HTML-escape; dedup (tür, sembol, yön, TP1|TP2) başına 1 saat; `ai_format=False`.
- [x] Kodda default OFF: `EFLOUD_ALERTER_TP_ALERTS`.
- [x] Prod açma satırı (yalnız alerter env, trading etkisi yok): `docker-compose.prod.yml` alerter → `EFLOUD_ALERTER_TP_ALERTS=1` (PR'da ayrı commit, operatör onayına).
- [x] Testler: kural birim testleri + gerçek `OrderManager` log çıktısıyla sözleşme testi + compose flag testi.
- [ ] Operatör: merge + `docker compose up -d alerter` (yalnız alerter yeniden başlar; bot/emir yolu etkilenmez).

## Kısıtlar
- Trading kodu (exchange/engine/configs) DEĞİŞMEDİ.
- Alerter yalnız mid bot logunu (`efloud_logs` → `/app/logs/efloud_bot.log`) okur → long/scalp KAPSANMIYOR.

## Log
- 2026-11-07 claude-code: alerter kuralı + testler + compose flag; PR açıldı.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
