# T-003: Strateji Backtest + Görsel Validasyon

**Epic:** P-001
**Claimed by:** @claude (2026-06-11) — R1+R3 konsensüs + çoklu-sembol gate re-run şartı
**Tahmini süre:** 2-3 gün (R1+R3 patch'leri + gate re-run)
**Bağımlılık:** T-002 ✅ DONE (G-T2 PASS), T-001 ✅ DONE (G-T1 PASS)
**Branch:** `feat/p001-t003-strategy` (push edilmemiş, R1+R3 patch'leri bu branch'e eklenecek)
**PR:** PR #194 (draft, `pr-194-t003` HEAD `118a597`) — G-T4 FAIL nedeniyle merge EDİLMEYECEK, R1+R3 sonrası

## Hedef

`pine/u2algo/wave1_strategy.pine` (v1.0.0-draft) Pine v6 STRATEGY backtest mantığını TV Pine Editor'da doğrulamak; 7 kalite gate'inden (G-T1..G-T6, G-T3 Pine↔Python mapping) geçirmek. PR #194 (draft) merge-onayı için gate re-run PASS şart.

## Çıktılar (G-T4 FAIL sonrası revize)

- [x] `pine/u2algo/wave1_strategy.pine` — STRATEGY iskeleti v1.0.0-draft (622 satır, 5 patch: round-1 + limit-expiry + round-3 + alert + gate-raporu)
- [x] `pine/u2algo/WAVE1_SPEC.md` §7 — T-003 bölümü eklendi
- [x] Alert template (Telegram/Discord zengin format) — PR patch'le geldi
- [x] Round-1 review fix: 3 MAJOR (N3 parite, qty_percent=50, time-window) + limit-expiry + MINOR
- [x] Round-2 review (smc-reviewer REQUEST_CHANGES): F1-F6 bulguları
- [x] Round-3 review fix: F1+F2 qty semantigi, F3 risk-bazlı sizing, F5 karşı-yön cancel, F6 pending-gate, F4 spec caveat
- [x] Gate run 1 raporu (`LLTODO/reports/REPORT-T-003-gate-run-1.md`): G-T3 PASS, G-T4 FAIL (trade_count=0)
- [ ] **R1+R3 patch'leri** — Plan v1.4 §8a.2 (3 dosya SENKRON: `wave1_signals.pine` + `wave1_strategy.pine` + `WAVE1_SPEC.md`)
  - R1.a: OB-aktif pencere 5→15 bar
  - R1.b: `allow_ob_less` input (default OFF) — OB ön koşulu kaldırılır
  - R3.a: limit-expiry 20→40 bar
  - R3.b: `extended_expiry_in_trend` input (default OFF) — 1h bias aligned'da 80 bar
- [ ] **Çoklu-sembol agregasyonlu gate re-run** — BTC+ETH+SOL+BNB+XRP perp 15m, ~4.3 ay (Plan §6 kaçış)
- [ ] G-T4 PASS kanıtı (trade_count ≥ 100) → STATE.md `IMPL_READY` → FAZ 4 UR-001
- [ ] G-T5/G-T6 tetikleme (sub-min-RR, inverted SL/TP)

## Acceptance Kriterleri

- [x] **G-T3 PASS** — Pine v6 compile 0 hata 0 marker (f8ce5c2, 2026-06-11)
- [ ] **G-T4 PASS** — Çoklu-sembol agregasyonlu backtest'te trade_count ≥ 100, OOS Sharpe ≥ IS×0.7
- [ ] **G-T5 PASS** — Long'da SL>entry>TP veya short'ta SL<entry<TP olamaz (sıfır trade)
- [ ] **G-T6 PASS** — Realized RR < min_rr (1.5) trade olamaz (sıfır trade)
- [x] **SENKRON** — R1 patch'leri 3 dosyaya birlikte uygulanır (Plan v1.4 §8a.3)
- [x] **Python kapsamı korunur** — CLAUDE.md "Python kaynak mantığını değiştirme" istisnasız (Plan v1.4 §8a.4)
- [x] **PR #194 draft kalır** — G-T4 FAIL devam ettiği sürece merge YOK (operatör kararı 2026-06-11)
- [x] **LLTODO lint** — 8/8 yeşil (kart R6 parse edilebilir)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | STARTED | T-003 claimed by @claude — T-002 G-T2 PASS sonrası |
| 2026-06-11 | ROUND_1 | smc-reviewer round-1: 3 MAJOR (N3 parite, qty_percent=50, time-window) + limit-expiry fix + MINOR (slippage/sizing). Patch 60e6421. |
| 2026-06-11 | ROUND_2 | smc-reviewer round-2 REQUEST_CHANGES: F1-F6 (qty semantigi, risk-bazlı sizing, karşı-yön cancel, pending-gate, spec caveat). Patch 39df356 (limit-expiry) + log kaydı 6e9bc92. |
| 2026-06-11 | ROUND_3 | smc-reviewer round-3 fix: F1+F2 qty semantigi (TP1 %50, TP2 kalan TAMAMINIn kendi stop'uyla), F3 risk-bazlı sizing (qty = equity × risk_pct / |entry-SL|), F5 karşı-yön cancel, F6 pending-gate, F4 spec caveat. Patch f513b7c. |
| 2026-06-11 | IMPL_READY | T-003 strateji draft tamamlandı (alert template patch'iyle 9d27f81), 622 satır, 5 patch, Pine v6 compile-clean. R1+R3 konsensüs + çoklu-sembol gate kararı bekleniyordu. |
| 2026-06-11 | GATE_RUN_1 | G-T3 PASS, G-T4 FAIL (trade_count=0, BTC+ETH perp 15m ~4.3 ay). Kök neden: §2a 5-ardışık-ters-mum × 1.5×ATR × ≤5-bar pencere × bias × conf≥55 kombinasyonu 15m'de nadir. R-002 backtest-validasyon gate'i amacına ulaştı. |
| 2026-06-11 | DRAFT_HOLD | PR #194 (4 dosya 66+/0-) merge EDİLMEYECEK kararı — R1+R3 patch'leri + çoklu-sembol gate re-run PASS'a kadar draft. `feat/p001-t003-strategy` (5 dosya 664+/6-) push edilmemiş, R1+R3 eklenince operatör onayıyla push. |
| 2026-06-11 | R1+R3_PLAN | Plan v1.4 (LLTODO/plans/P-001-u2algo-wave1-tradingview.md) §8a: R1 sinyal mantığı gevşetme (R1.a pencere 5→15, R1.b `allow_ob_less`) + R3 fill güvenilirliği (R3.a expiry 20→40, R3.b `extended_expiry_in_trend`). SENKRON 3 dosya. Claude konsensüs + operatör onayı tamam. Patch'ler hazırlanacak (format-patch+sha256). |
