---
id: T-20261107-24
title: Backtest geri yükleme — botun mevcut trade mantığıyla (karar 3)
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
Operatör: "backtest kısmını geri yükleyebilirsin ancak bot'un mevcut trade mantığına göre backtest yapılsın."
Spec `docs/superpowers/specs/2026-11-07-operator-decisions-and-backtest-restore-design.md`, plan
`docs/superpowers/plans/2026-11-07-backtest-restore-live-parity.md`.

## Beklenen çıktı (Definition of Done)
- [x] `backtest/` + 13 test modülü `562a6a3^`'ten geri yüklendi (78/79 değişmeden geçti; 1 config drift).
- [x] Canlı mantık: gerçek `SafeOrchestrator.run_cycle` + canlı config; `smc_version` config'ten (v2); çıkışlar borsa ile aynı (TP1 %50 → BE → TP2); NET maliyet config'ten; LLM/agent/Kronos kapalı (ağ yok).
- [x] Kök neden düzeltmesi: her TF canlıdaki gibi `kline_limit` (750) bar geçmişle → 12h LuxAlgo trendi oluşuyor (önce 0 v2 işlem; şimdi BTC 41g'de 14).
- [x] Yan düzeltmeler: fetcher 12h/8h, prefetch --config, reconcile sim-zaman, daily 100 bar, seri grid, >%1 atlanan döngüde çıkış 3.
- [x] Yavaş 6 test `backtest (slow)` CI işinde.
- [ ] Canlı parite raporu: `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md` (portföy koşusu sürüyor).
