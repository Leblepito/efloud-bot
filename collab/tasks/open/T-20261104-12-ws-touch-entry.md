---
id: T-20261104-12
title: "WS Faz 2: olay tetiklemeli tarama + fitil/temas girişi (varsayılan KAPALI)"
from: operator
to: abacus
status: claimed
claimed_by: abacus
reviewer: claude-code
parent: T-20261104-11
created: 2026-11-04
touches_live: true
---

## Amaç
Operatör: "mum kapanışı beklemeyelim, fitil ve temas ile işleme girilsin; işlemleri kaçırmayalım."
Faz 1 (#278) WS kline akışını gölgede getirdi. Faz 2 bu akışı iki yerde kullanır:
(a) entry mumu WS'te kapanınca taramayı 30 sn döngü + 2 sn tampon beklemeden başlatır;
(b) bekleyen v2/LuxAlgo adayının hedef bölgesine oluşan barın fitili ya da anlık fiyat
değdiği an, engulfing kapanışını beklemeden girişi mevcut emir kapılarından geçirir.

## Girdi
- #278 (`exchange/ws_klines.py`, `backend/bot_runner.py` gölge parite) — bu PR onun üstüne kurulu.
- `engine/safe_orchestrator.py` `_advance_setup_state_tick`, `_place_v2_entry_order`.
- T-09 (#277) NET-cost raporu: teyitsiz bölge-kenarı girişi 60 günlük veride NET daha iyi değil.

## Beklenen çıktı (Definition of Done)
- [x] `data_feed.ws.event_scan` (varsayılan false): WS entry kapanışı → döngü erken uyanır, tampon 0.
- [x] `smc_v2.touch_entry: off|shadow|live` (varsayılan off): `on_intrabar_touch` + `_touch_loop`.
- [x] Kapılar korunur: whitelist, breaker, SL/TP, pos_guard, smc_v2_shadow, OrderManager drift,
      po3, lease; bayat kapanış taraması (> 2 bar) → giriş yok; bölge ters delinmişse giriş yok.
- [x] Kapanış taraması ile dokunuş yolu RLock ile serileşir; çift giriş yok (test: 8 thread → 1 emir).
- [x] Testler: `tests/engine/test_touch_entry.py` (12), `backend/tests/test_ws_klines.py` (+5).
- [ ] Canlıya alma: ayrı config PR (`data_feed.ws.enabled/event_scan`, önce `touch_entry: shadow`)
      + claude-code deploy ticket + Risk PASS + operatör onayı.

## Kısıtlar
- `risk:` / `safety:` blokları, `engine/smc_v2/`, `pine/` değişmez. Config dosyası bu PR'da değişmez.
- Deploy/VPS yazma yok (claude-code ticket ile).

## Log
- 2026-11-04 abacus: claim; #278 üstüne stacked PR. Kod + 17 test; varsayılan davranış birebir aynı.

## Review
