---
id: T-20261107-14
title: main.py import'u Windows'ta pytest capture'ını kapatıyordu
from: claude-code
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261107-13
created: 2026-11-07
touches_live: false
---

## Amaç
Windows'ta `main.py`'yi import eden her pytest koşusu (tam suite dahil) hiç test çalışmadan
`ValueError: I/O operation on closed file` ile çöküyordu: `main.py` import anında
`sys.stdout/stderr`'i yeni `TextIOWrapper` ile değiştiriyor, eski capture akışı kapanıyordu.
CI (Linux) ve prod (Linux container) etkilenmiyor; yerel test kanıtı (TESTS.md) üretilemiyordu.

## Beklenen çıktı (Definition of Done)
- [x] UTF-8 konsol sarmalayıcısı `_force_utf8_console()`'a taşındı, yalnız `__main__`'de çağrılıyor (preflight.py ile aynı desen). Davranış: Windows'ta doğrudan çalıştırınca aynı; Linux'ta no-op (değişmedi).
- [x] RED→GREEN: `tests/test_main_import_keeps_stdout.py`.
- [x] Windows'ta tam suite artık koşuyor: 3091 passed, 1 flaky (`test_persist_crash_safety` eşzamanlılık testi; tek başına 5/5 geçiyor — Windows dosya kilidi, bu değişiklikle ilgisiz).
