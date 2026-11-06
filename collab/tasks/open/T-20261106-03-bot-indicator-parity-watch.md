---
id: T-20261106-03
title: Bot işlemleri ↔ u2algo Price Action sinyalleri günlük eşleşme raporu
from: claude-code
to: hermes
status: open
claimed_by: null
reviewer: claude-code
parent: T-20261106-01
created: 2026-11-06
touches_live: false
---

## Amaç
Operatör sosyal medyada "bot bu indicator'ün sinyalleriyle işlem yapıyor" diyebilmek için ikisinin aynı işlemleri ürettiğini sürekli görmek istiyor. Pine indicator (`pine/efloud_lab.pine`, "u2algo Price Action") canlı botun SMC v2 LuxAlgo mantığını aynalıyor (parity: `docs/pine-lab/2026-11-06-ilk-tur.md` §4c–4d, BTC 42/42, ETH 33/33, SOL 49/49 pozisyon). Fark beklenen yerler: bot ayrıca risk kapıları, pozisyon limiti, 10 sembol listesi ve breaker uygular → her indicator sinyali bot işlemi olmaz; ama her bot işlemi bir indicator sinyaline karşılık gelmeli.

## Girdi
- Bot işlemleri: VPS trade journal / ops Telegram log'u (salt okuma).
- Indicator sinyalleri: topluluk kanalına TradingView alarmı ile düşen mesajlar (`docs/telegram/tradingview-to-telegram.md`) veya `scripts/pine_lab_parity.py replay` çıktısı.
- Araç: `scripts/pine_lab_parity.py compare --since …` (pozisyon bazlı eşleşme).

## Beklenen çıktı (Definition of Done)
- [ ] Günlük (00:15 cron turunda) kısa rapor: son 24 saatte bot işlemi sayısı, eşleşen indicator sinyali sayısı, eşleşmeyen bot işlemleri (sembol, zaman, neden tahmini).
- [ ] Eşleşmeyen bot işlemi varsa `inbox:claude-code` etiketiyle PR/issue + `STATUS.md` notu.
- [ ] Rapor `collab/outputs/hermes/parity-YYYYMMDD.md` (kişisel/hesap verisi yok).

## Kısıtlar
- Salt okuma; canlı sisteme yazma, restart, config değişikliği YOK.
- TradingView MCP `indicator set` kullanılmaz ("Can't parse pine" çökmesi; `docs/pine-lab/README.md` §5).

## Log
- 2026-11-06 claude-code: görev açıldı.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
