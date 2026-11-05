---
id: T-20261105-04
title: "Config PR: WS gölge + touch_entry shadow bayrakları (mid, emir yolu yok)"
from: operator
to: abacus
status: claimed
claimed_by: abacus
reviewer: claude-code
parent: T-20261105-03
created: 2026-11-05
touches_live: true
---

## Amaç
Deploy (b39751a) sonrası kalan işler: WS veri katmanını (#283) ve touch gölgesini (#280) açmak için ayrı config PR.
Yalnız gözlem: tarama davranışı ve emir yolu değişmez.

## Beklenen çıktı (Definition of Done)
- [x] `configs/config.phase2_1k.yaml`: `data_feed.ws.enabled: true`, `event_scan: false`, `smc_v2.touch_entry: shadow`.
- [x] `risk:` / `safety:` dokunulmadı; scalp/long config'leri dokunulmadı.
- [ ] Merge + deploy ticket + Risk PASS + operatör onayı (abacus deploy etmez). Sonra 3 gün: `[ws shadow] parity=MISMATCH` = 0,
      `[touch shadow]` satırları T-09 harness'iyle NET ölçülür (n≥30, IS+OOS NET>0, bazdan iyi) → ancak o zaman `live` tartışılır.
- [ ] Ayrı karar: Telegram bölge uyarısı (#275) — `.env` `EFLOUD_ALERTER_LUX_ALERTS=1` (+ isteğe bağlı `near_alert_atr`; eşik operatörün).

## Kısıtlar
- `event_scan` bu PR'da KAPALI (2 sn tamponlu tarama davranışı değişmez). Deploy/VPS yazma yok.
- Geri alma: iki bloğu sil → `docker compose up -d` (claude-code).

## Log
- 2026-11-05 abacus: claim + config diff; `tests/config tests/engine tests/collab` 249 passed.

## Review
