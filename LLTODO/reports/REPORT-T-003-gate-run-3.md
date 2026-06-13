# REPORT — T-003 Gate Run 3 (ROUND-5 Market Entry)

**Tarih:** 2026-06-13 · **Koşan:** @claude (TV Desktop MCP, izole worktree `C:/tmp/wt-t003`)
**Kod:** `feat/p001-t003-strategy` round-5 (market entry) · diagnostik instrumented build
**Ortam:** TV Strategy Tester · BTC/ETH/SOL/BNB/XRP USDT.P @ 15m · `allow_ob_less=true`, `bt_segment=Full`
**Önceki:** GATE_RUN_2 (round-4 limit) → FAIL (limit-fill ~%41, F-01). Round-5 = §6 eskalasyonu (market entry).
**Review:** smc-strategy-reviewer **APPROVE_WITH_NITS** — market-entry mantığı doğru/repaint-safe; B-01 (WAVE1_SPEC senkronu) + H-01 (unused-var) düzeltildi.

---

## NET SONUÇ: ❌ **FAIL (DECISIVE)** — market entry edge'i yok ediyor

Market entry fill sorununu çözdü (~%100, count 270 ≥ 100 PASS) **ama stratejinin edge'ini YOK ETTİ**:
agregat PF **0.71** (<1, kaybeden), net **−%14.3** (5 hesap), **4/5 sembol kaybeden**, çoğu MaxDD>%5, Sharpe negatif.

**🔑 KRİTİK BULGU:** Stratejinin (sınırlı) edge'i **tamamen OB-retrace limit girişine bağlıymış.**
Round-4'te limit-at-OB iyi fiyattan giriyordu (BTC PF 1.57, BNB 2.59) ama az fill oluyordu (~%41).
Round-5'te market-at-close her sinyali dolduruyor ama **kötü fiyattan** (breakout sonrası, geç) →
negatif edge. **Yani round-4 yaklaşımı "daha doğru"ydu; sorun sadece fill oranıydı, edge değil.**

---

## G-T3 Compile

EXACT committed round-5 `wave1_strategy.pine` (617 satır) → `pine_smart_compile` + `pine_get_errors`
→ **0 hata, 0 marker. ✅ PASS** (H-01 unused-var temizliği sonrası teyit).

## Per-Sembol Sonuçlar (Full segment, ~3-4.5 ay 15m, 5×10k)

| Sembol | closedlegs | orders | win% | PF | net% | maxDD% | Sharpe(trade) |
|---|---|---|---|---|---|---|---|
| BTCUSDT.P | 50 | 26 | 28.0 | 0.70 | −2.7 | 6.6 | −0.164 |
| ETHUSDT.P | 46 | 24 | 43.5 | **1.32** | **+2.2** | 2.1 | +0.132 |
| SOLUSDT.P | 35 | 18 | 17.1 | 0.37 | −4.7 | 5.2 | −0.482 |
| BNBUSDT.P | 54 | 28 | 25.9 | 0.60 | −4.1 | 5.0 | −0.241 |
| XRPUSDT.P | 85 | 43 | 28.2 | 0.68 | −5.0 | 8.3 | −0.185 |
| **TOPLAM** | **270** | **139** | — | **0.71** | **−14.3** | — | neg |

> Sharpe = per-trade `strategy.closedtrades.profit()` mean/std (annualize edilmemiş; IS/OOS oran
> karşılaştırması için). orders=market entry sayısı (=pozisyon); closedlegs≈2×orders (TP1-kısmi+runner).
> gprofit toplam 3469 / gloss toplam 4904 → agregat PF 0.707.

## Round-4 (limit) vs Round-5 (market) — PF karşılaştırması

| Sembol | Round-4 PF (limit) | Round-5 PF (market) | Δ |
|---|---|---|---|
| BTC | 1.57 | 0.70 | ⬇ −0.87 |
| ETH | 3.97 | 1.32 | ⬇ −2.65 |
| SOL | 1.29 | 0.37 | ⬇ −0.92 |
| BNB | 2.59 | 0.60 | ⬇ −1.99 |
| XRP | 0.38 | 0.68 | ⬆ +0.30 (hâlâ <1) |
| **Agg** | **1.44** | **0.71** | ⬇ **−0.73** |

**4/5 sembolde market entry PF'i düşürdü** (genelde 2-3× kötüleşme). Limit girişin iyi fiyatı load-bearing.

## Gate Değerlendirmesi

| Gate | Kriter | Sonuç |
|---|---|---|
| G-T3 | compile 0 hata/marker | ✅ PASS |
| G-T4a | trade_count ≥ 100 | ✅ PASS (270; market fill ~%100) |
| G-T5 / G-T6 | inverted=0 / sub-RR=0 | ✅ PASS (5/5) |
| WR ≥ %50 | — | ❌ FAIL (17-43%) |
| **PF ≥ 1.5** | — | ❌ **FAIL HARD** (agg 0.71; en iyi ETH 1.32 < 1.5) |
| MaxDD ≤ %5 | — | ❌ FAIL (3-4/5 breach: BTC 6.6, SOL 5.2, XRP 8.3, BNB 5.0) |
| Sharpe | OOS ≥ IS×0.7 | ❌ MOOT — base Sharpe negatif (4/5); kaybeden stratejide OOS-split anlamsız |

## Sonuç & Öneri

**Hem round-4 (limit) hem round-5 (market) FULL gate'i geçemiyor — ZIT sebeplerle:**
- **Round-4 (limit):** İyi per-trade edge (agg PF 1.44) AMA fill ~%41 → sinyallerin yarıdan fazlası gerçekleşmiyor; realize edilen sonuç marjinal.
- **Round-5 (market):** Fill ~%100 AMA edge negatif (agg PF 0.71) → kötü giriş fiyatı.

**Wave-1 STRATEGY mevcut tasarımıyla shippable değil.** Entry-mekanizması ayarı (limit↔market) sorunu çözmüyor; bu daha derin bir tasarım sorunu. **#194 MERGE EDİLMEZ.**

**Seçenekler (operatör/konsensüs kararı — FAZ 4 UR-001 kapsamı):**
1. **Hibrit/akıllı limit** — OB'ye daha yakın/gerçekçi limit yerleşimi veya kısmi-retrace ile fill↑ + iyi fiyat korunur (round-4'ün edge'i + round-5'in fill'i arası).
2. **Düşük-frekans limit kabulü** — limit modelini koru, gate eşiklerini (min 100 trade) gerçekçi frekansa göre revize et (limit edge'i gerçek, az ama öz).
3. **Indicator-only ship** — `wave1_signals.pine` (ücretsiz lead-magnet) sinyal gösterir; premium STRATEGY redesign'a kadar rafa kaldırılır.
4. **Sinyal kalitesi redesign** — conf_thresh↑, daha seçici setup'lar, farklı SL/TP — düşük WR (%17-43) + nadir-büyük-winner profili kırılgan.

**Korunan iyileştirmeler (entry-mekanizmasından bağımsız, değerli):** `bt_date_end` latent bug fix + `bt_segment` OOS-split infrastructure — redesign hangisi olursa olsun gerekli.

---

## Notlar

- Metrik: ölçüm-amaçlı diagnostik build (committed trade mantığı değişmeden + sayaç/Sharpe/`table.new`),
  `data_get_pine_tables` ile okundu (TV internal-api kırık). G-T3 EXACT committed'da ayrıca doğrulandı.
- İzole worktree `C:/tmp/wt-t003`; ana repo (Gemini) + `pine/efloud_signals.pine` (SMC v2) DOKUNULMADI.
- Veri derinliği sembol başına değişir (TV 15m lazy-load); count'lar bundan etkilenir ama PF/WR/Sharpe edge ölçümü derinlikten bağımsız negatif.
