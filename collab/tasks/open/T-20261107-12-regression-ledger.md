---
id: T-20261107-12
title: REGRESSION.md modül regresyon defteri (backlog madde 3)
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
"A'yı değiştirdim, B kırıldı" sınıfı hataları yakalamak: her değişiklikte değişen modülü ve
bütün downstream tüketicilerini çalıştıran, çıkış koduyla karar veren bir regresyon defteri
(skill: module-regression, change-impact).

## Girdi
- Mevcut test varlıkları (`tests/`, `backend/tests/`, `scripts/lane_e/tests/`), CI (`.github/workflows/ci.yml`).
- Runtime bağları: alerter/overseer bot logunu ve `trade_journal.jsonl`'i okuyor, panel/frontend bot API'sini HTTP ile çağırıyor.

## Beklenen çıktı (Definition of Done)
- [x] `scripts/regression_ledger.py`: modül tablosu + takip edilen dosyaların AST import taraması (tekrar üretilebilir kanıt), runtime bağları `git grep` kanıtıyla `unverified` olarak.
- [x] `REGRESSION.md` bu betikten üretiliyor (29 modül; her biri için downstream, kabul komutu, eşlenen testler).
- [x] `run --base origin/master`: diff (commit + staged + unstaged + untracked) → modüller → transitif downstream → komutlar; karar = çıkış kodu.
- [x] CI kilidi: `tests/ci/test_regression_ledger.py` (defter güncel mi, her kod dosyası bir modülde mi, yayılım doğru mu).
- [x] Defter boşluğu kapatıldı: `risk/` (pozisyon boyutu) doğrudan testsizdi → karakterizasyon testleri (`tests/risk/test_position_size.py`, davranış değişikliği yok).
- [ ] TEST-ID bağlantıları: madde 4 (`TESTS.md`) ile.

## Kısıtlar
- Trading koduna dokunuş yok. `risk/` için yalnız mevcut davranışı sabitleyen test.
