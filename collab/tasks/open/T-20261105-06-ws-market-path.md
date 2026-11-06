---
id: T-20261105-06
title: "Fix: WS kline akışı /market/stream yoluna (gölge akış veri almıyordu)"
from: operator
to: claude-code
status: claimed
claimed_by: claude-code
reviewer: abacus
parent: T-20261104-11
created: 2026-11-05
touches_live: true
---

## Amaç
EF-20261105-03 deploy'undan sonra (`042c3a3`) WS gölge akışı bağlanıyor ama veri almıyordu: 16:00/16:15 UTC kapanışlarında
29/29 `[ws shadow] … WS'te yok (age_ms=None)`. Operatör: "Yes, fix WS URL".

## Kanıt (VPS container içinden, salt-okuma public market data)
- `wss://fstream.binance.com/stream?streams=…@kline_*` → 8 sn'de 0 mesaj (bağlantı kabul, veri yok).
- `wss://fstream.binance.com/market/stream?…` → 8 sn'de 56 mesaj; prod'un tam 30 akışlık URL'si 10 sn'de 739 mesaj, 30/30 akış.
- Testnet `wss://stream.binancefuture.com`: `/stream` ve `/market/stream` ikisi de veri veriyor → ikisi için `/market/stream`.

## Beklenen çıktı (Definition of Done)
- [x] `exchange/ws_klines.py` `build_url`: `/stream` → `/market/stream` (tek satır + docstring).
- [x] Test: `backend/tests/test_ws_klines.py` mainnet + testnet yol assert'leri (önce kırmızı, sonra yeşil).
- [x] Merge + deploy ticket + operatör onayı (claude-code uygular; EF-20261105-04, `6d70ae0`, 16:47 UTC). Deploy sonrası: sonraki 15m kapanışta `[ws shadow] parity=OK`.
- [ ] 3 gün: `parity=MISMATCH` = 0 (T-20261105-04 ölçümü).

## Kısıtlar
- Emir/karar yolu REST'te; bu modülü kullanmaz. `risk:`/`safety:`/config değişmez.
- Geri alma: commit'i revert → deploy (ya da `data_feed.ws.enabled: false`).

## Log
- 2026-11-05 claude-code: fix + test; `backend/tests/test_ws_klines.py backend/tests/test_audit_journal.py tests/engine/test_touch_entry.py tests/config` 87 passed.
- 2026-11-05 claude-code: deploy `6d70ae0`; 17:00 UTC 10/10 `parity=OK`, 0 MISMATCH. Kalan: 3 gün MISMATCH=0 takibi (T-20261105-04 ile birlikte).

## Review
