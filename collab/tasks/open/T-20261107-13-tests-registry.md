---
id: T-20261107-13
title: TESTS.md TEST-ID kaydı (backlog madde 4)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261106-04
created: 2026-11-07
touches_live: false
---

## Amaç
Korunması gereken kuralları (audit C/H/M, bughunt #1–#12, olaylar, alerter, güvenlik
denetimi) kalıcı TEST-ID'lere ve çalıştırılabilir kanıta bağlamak (skill: test-collaboration,
ai-regression-testing).

## Beklenen çıktı (Definition of Done)
- [x] `TESTS.md`: giriş noktaları, varlık haritası, sınır-ötesi sözleşmeler, 46 TEST-ID (kaynak → kanıt → prod'da aktif mi).
- [x] CI kilidi `tests/ci/test_tests_registry.py`: TESTS.md'deki her `path::node` var olmalı; TEST-ID'ler tekil.
- [x] Kayıt sırasında bulunan boşluk kapatıldı: TEST-SEC-06 MCP pin testi (`tests/ci/test_mcp_pins.py`).
- [x] Kanıt koşusu: §4'teki tüm Python dosyaları 388 passed; u2algo-site `ALL PASS`; Windows tam suite 3091 passed.
- [ ] Açık: frontend/panel ↔ `/api/*` için makine-okunur sözleşme yok (madde 11); H7/M1 bayrakları config'e bağlı değil (backtest kapısı gerekir).

## Kısıtlar
- Üretim koduna dokunuş yok; yalnız doküman + test.
