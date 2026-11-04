---
id: T-20261104-08
title: "İstek: LuxAlgo bölge erken-uyarı (Telegram, salt-okunur) — alerter kuralı"
from: claude-code
to: claude-code
status: claimed
claimed_by: claude-code
reviewer: hermes
parent: null
created: 2026-11-04
touches_live: false
---

## Amaç
Operatör, motorun izlediği bölgeye fiyat yaklaşırken ve motor bir bölgeyi reddederken bunu
anında görmek istiyor. Emir yoluna dokunmadan, mevcut `efloud-alerter` (bot log'unu tail eden ayrı
container) üzerine kural ekle: (1) bekleyen bir v2 adayının bölgesine fiyat N×ATR yaklaştı,
(2) `[lux] touch|reentry|confirmed|expired` geçişleri, (3) `[v2 reject] …` / `[v2 gate] …` satırları
reddetme sebebiyle birlikte. Teşhis raporundaki öneri (a).

## Girdi
- `collab/outputs/claude-code/2026-11-04-ob-entry-gap.md` §4 (öneri a).
- `ops/alerter/` (kural motoru, dedup, formatter), `scripts/lux_monitor.py` (regex'ler, #265).
- `engine/safe_orchestrator.py` `_lux_trace` / `_lux_log_scan` log satırları.

## Beklenen çıktı (Definition of Done)
- [ ] TDD: önce kural testleri (`tests/` altında alerter için), sonra kural.
- [ ] Bayrak default OFF (alerter config/env); kapalıyken davranış birebir aynı.
- [ ] Yaklaşma uyarısı için motor tarafına gerekiyorsa yalnız **log satırı** eklenir (karar/kapı değişmez);
      bu durumda PR "risk-ops review" ister.
- [ ] Dedup: aday başına olay başına 1 mesaj; saatlik üst sınır.
- [ ] PR + başka modelden review; deploy operatör kararı.

## Kısıtlar
- Emir/size/SL/TP/kapı mantığına dokunma. TradingView'den motora girdi YOK (öneri b reddedildi, rapor §4).
- `engine/smc_v2/**` mantığı değişmez; yalnız log eklenebilir.

## Log
- 2026-11-04 claude-code: task açıldı (OB-entry-gap teşhisinin takibi).
- 2026-11-04 claude-code: claim — operatör (a) seçeneğini onayladı; branch `collab/claude-code/T-20261104-08-lux-zone-alert`. Alerter prod'da dry-run → T-20261104-10.

## Review
