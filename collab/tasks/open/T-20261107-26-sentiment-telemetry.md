---
id: T-20261107-26
title: LLM sentiment yalnız telemetri + state_dir hizalama (karar 1, LLM denetimi A1/A2)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261107-16
created: 2026-11-07
touches_live: true
---

## Amaç
Operatör kararı (vekâleten, spec 2026-11-07 §1 #1, seçenek a): LLM makro sentiment'i confluence
skorunu değiştirmez (yalnız `sig.meta`), yazıcı/motor/dashboard aynı `state_dir`'i kullanır.

## Beklenen çıktı (Definition of Done)
- [x] `engine/signals.py`: ±5 kaldırıldı → `sig.meta["macro_sentiment"]`.
- [x] `engine/ai/sentiment.py` `state_dir` parametresi; `backend/bot_runner.py` kendi `operation.state_dir`'ini geçirir; `backend/api.py` `/api/ai/sentiment` aynı dizinden okur (`_state_dir()`).
- [x] Canlı etkisi: SIFIR işlem değişikliği — motor zaten NEUTRAL görüyordu (A2 canlıda doğrulandı); dashboard artık motorun gördüğünü gösterir.
- [x] RED→GREEN `tests/test_sentiment_telemetry_only.py` (6); eski ±5 testleri yeni sözleşmeye çevrildi; regresyon defteri 2760 passed.
- [ ] Deploy: bot container yeniden başlatma (AUTOSTART=0) — #332 ile birlikte operatörle zamanlanır.
