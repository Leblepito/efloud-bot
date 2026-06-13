# REPORT — T-003 GATE_RUN_4-prelim (Round-6 / Round-6b — faithful zone-pullback)

**Tarih:** 2026-06-13 · **Koşan:** @claude (TV MCP, izole worktree) · **Branch:** `feat/p001-t003-strategy` (PR #194 DRAFT)
**Spec/Plan:** `docs/superpowers/specs/2026-06-13-wave1-round6-faithful-smc-design.md` + `plans/2026-06-13-wave1-round6-faithful-smc.md`
**Build:** round-6 prototip (FVG/EQH-EQL/Breaker detektörler + engine-faithful TP + near-edge zone-pullback entry). G-T3 compile **PASS** (0 hata 0 marker, ~580 satır array-yoğun Pine).

---

## NET SONUÇ: ❌ NO-GO — Wave-1 sinyalinin tradeable edge'i yok (entry mekanizması değil)

Validation-first prototip 2 varyantta koşuldu:

### Round-6 (OB-only zone-pullback, strict signal — allow_ob_less yok)
5 sembol Full: **toplam 15 closed-leg** (BTC 2, ETH 0, SOL 2, BNB 5, XRP 6), fill **~%12**.
→ **Frekans çöktü** (conf≥55 ≈ OB-zorunlu = GATE_RUN_1 seyrekliği) + near-edge limit trend'de dolmuyor. 15 trade = istatistiksel anlamsız.

### Round-6b (OB|BB+FVG+OTE zone-pullback, gevşetilmiş signal)
`f_nearest_zone`'a FVG (engine primary) + OTE (fallback) eklendi; sinyal `bias + (structure-break OR conf)`'a gevşetildi (operatör onaylı yön).
- **BTC:** closed 69, orders 182, fill ~%38, **PF 0.66**, net −%6.9, maxDD %8.6, Sharpe −0.16
- **ETH:** closed 110, orders 188, fill ~%58, **PF 0.84**, net −%4.1, maxDD %8.8, Sharpe −0.07
→ **Frekans + fill ÇÖZÜLDÜ** (ETH 0→110!) AMA **edge negatif** (her iki sembol PF<1, kaybeden).

> Engine-TP doğru çalışıyor: t1src=0 (LIQUIDITY), t2src=1/2 (FIB / single-target — TP1/TP2 yapışıklığı çözüldü). Detektörler (FVG/EQH-EQL/Breaker) compile + çalışıyor.

---

## 🔑 Kapsamlı bulgu — 4+ tur sentezi

| Tur | Entry mekaniği | Frekans/Fill | Edge (agg PF) |
|---|---|---|---|
| Round-4 | limit @ ob_bot (derin) | 168 trade / %41 | **1.44** (en iyi; marjinal + az fill) |
| Round-5 | market @ close | 270 / %100 | 0.71 (kaybeden) |
| Round-6 | zone-pullback OB-only | 15 / %12 | — (örneklem yok) |
| Round-6b | zone-pullback FVG/OTE + gevşek | ~180 / %38-58 | 0.66-0.84 (kaybeden) |

**Temel gerçek (fill ↔ edge takası):** Strateji **yeterli trade ürettiğinde edge HEP negatif** (round-5, round-6b); pozitif edge SADECE round-4'ün seçici + derin-limit config'inde belirdi (PF 1.44) ama o da fill yetersiz + WR/PF gate'lerinde marjinaldi. **Sorun entry mekanizması değil — Wave-1 SMC sinyalinin (1h EMA bias + OB/confluence, simplified) kendisi robust tradeable edge taşımıyor.**

Entry mekanizması uzayı **tükendi:** limit-deep (round-4), market-close (round-5), zone-pullback-near-edge OB (round-6), zone-pullback FVG/OTE+OB (round-6b). Hiçbiri "yeterli trade + pozitif edge" ikilisini sağlamıyor.

---

## Öneri — stratejik karar (operatör/konsensüs)

**#194 DRAFT/BLOCKED kalır.** Hızlı-düzeltme uzayı (entry mekanizması + sinyal gevşetme) tüketildi. İki gerçekçi yol:

1. **Wave-2 tam redesign** — engine'in TAM mantığını port et: CHoCH/BOS structure-break trigger (mevcut 1h-EMA-bias + OB yerine), tam FVG/OTE pullback, confirmation candle. Bu Wave-1'i aşar, büyük iş, kendi spec'i. Engine'in canlı edge'i bile mütevazı (Gemini backtest PF 1.15) — premium-satılabilir backtest garantisi yok.
2. **Indicator-only ship** — `wave1_signals.pine` (ücretsiz lead-magnet, sinyal+zone+TP görsel) ship edilir; premium STRATEGY backtest-gate'i geçene kadar (belki Wave-2) rafa kaldırılır. P-003 ticari baskısı için pragmatik; "proof ≠ ürün" zaten kabul edilmiş.

**Korunan değerli iş (her iki yolda kullanılır):** FVG + EQH/EQL + Breaker Pine detektörleri + engine-faithful TP (likidite/FVG, min_rr-gate, single-target) + bt_date fix + OOS-split — hepsi derleniyor ve çalışıyor.

---

## Not
- Round-6/6b prototipi `wave1_strategy.pine`'da (diagnostik tablo dahil; Faz-1'e geçilmedi — NO-GO).
- İzole worktree; ana repo (Gemini) + `pine/efloud_signals.pine` (SMC v2) DOKUNULMADI.
- Validation-first kill-switch çalıştı: 600+ satır finalize/SENKRON/spec yazılmadan edge yokluğu yakalandı.
