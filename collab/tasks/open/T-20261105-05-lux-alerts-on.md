---
id: T-20261105-05
title: "Config PR: Telegram LuxAlgo bölge uyarılarını aç (#275, yalnız bildirim)"
from: operator
to: claude-code
status: claimed
claimed_by: claude-code
reviewer: abacus
parent: T-20261104-08
created: 2026-11-05
touches_live: true
---

## Amaç
Operatör (2026-11-05): "Yeni özellikleri açmak: Telegram bölge uyarıları (#275) … ayrı config PR'ı ve ayrı ticket."
#275 kodu master'da ve VPS'te (`b39751a`) ama kapalı. Bu PR iki anahtarı açar; emir yolu değişmez.

## Beklenen çıktı (Definition of Done)
- [x] `configs/config.phase2_1k.yaml` → `smc_v2.luxalgo.near_alert_atr: 1.0` (motor yalnız `[lux] near` log satırı basar).
- [x] `docker-compose.prod.yml` → yalnız `alerter` servisine `EFLOUD_ALERTER_LUX_ALERTS=1` (git'te görünür, git'le geri alınır;
      VPS `.env.production` elle değişmez).
- [x] Test: `tests/config/test_live_lux_alert_flags.py` (bayraklar + bayrak trading servislerinde yok).
- [x] Merge + deploy ticket + Risk PASS + operatör onayı (claude-code uygular). → EF-20261105-02, `042c3a3`, 2026-11-05 15:48 UTC.
- [ ] Deploy sonrası 24 saat: Telegram mesaj sayısı ve içerik operatörce kontrol; spam ise `near_alert_atr` küçült / kapat.

## Hacim tahmini
Son 3 gün mid log'u bu kurallarla 18 mesaj üretirdi (8 dokunma, 9 pos_guard reddi, 1 breaker reddi; olay başına dedup
dokunma 6 sa, red 1 sa). `near` buna eklenir (dokunuş öncesi en fazla aday başına bir mesaj).

## Kısıtlar
- `risk:` / `safety:` değişmez; scalp/long config'leri değişmez. Telegram metni "bilgi amaçlı — işlem sinyali değil" notu taşır.
- Geri alma: iki satırı sil → deploy (ya da yalnız alerter için `docker compose up -d alerter`).

## Log
- 2026-11-05 claude-code: config + compose + test; `tests/config tests/test_alerter_lux_rules.py tests/test_lux_transition_logs.py tests/collab` 139 passed.
- 2026-11-05 claude-code: deploy edildi (`042c3a3`); 16:00 UTC ilk `[lux] near`/`touch` satırları. 24 sa hacim kontrolü açık.

## Review
