# REPORT — T-003 Gate Run 1 (G-T3 + G-T4..G-T6)

**Tarih:** 2026-06-11 · **Koşan:** @claude (TV Desktop MCP, lokal)
**Kod:** `feat/p001-t003-strategy` @ `f8ce5c2` (round-3, smc-reviewer APPROVE_WITH_NITS)
**Ortam:** TradingView Strategy Tester · BINANCE:BTCUSDT.P + ETHUSDT.P @ 15m
**Veri derinliği:** ~2026-02-01 → 2026-06-11 (~4.3 ay, ~12.5k bar/sembol — TV 15m limiti)

## Sonuçlar

| Gate | Kriter | Sonuç | Değer |
|---|---|---|---|
| **G-T3** | Compile 0 hata 0 warning | ✅ **PASS** | 0 hata, 0 marker (`pine_smart_compile` + `pine_get_errors`) |
| **G-T4** | min 100 trade, WR ≥ %50, PF ≥ 1.5 | ❌ **FAIL** | **trade_count = 0** (BTC ve ETH, tüm pencere) |
| **G-T5** | MaxDD ≤ %5 | ⬜ değerlendirilemedi | trade yok |
| **G-T6** | OOS Sharpe ≥ 0.7×IS | ⬜ değerlendirilemedi | trade yok |

## Bulgu zinciri (kanıtlı)

1. İlk koşuda 0 trade'in sebebi **pencere tuzağıydı**: chart instance'ı eski input
   değerlerini (default 2025 penceresi) tutuyordu; TV script güncellense de instance
   input'ları persist eder. Instance kaldırılıp 2026-penceresi default'lu v9 ile
   yeniden eklendi.
2. Yeni instance'ta da **0 trade** — bu noktada sebep stratejinin kendisi:
   - `data_get_pine_labels`: son 500 label'da **tek bir distinct sinyal**
     (SHORT @ 70402.5, ~Şubat-Mart bölgesi). Sinyal frekansı ≈ **1-2 / 4 ay / sembol**.
   - O tek sinyal de hiç **fill olmamış** (OB-üstü limit retrace bekledi, 20-bar
     expiry'de iptal).
   - ETHUSDT.P 15m: aynı tablo, 0 trade.

## Kök neden analizi

| # | Etken | Etki |
|---|---|---|
| 1 | **OB-aktif = ZORUNLU ön koşul** (`bullish_ob_active and conf ≥ 55 and bias`) — Python bot'ta OB bir *confluence faktörü*, sinyal kaynağı yapı kırılımları (BoS/CHoCH). Wave-1 daraltması sinyal evrenini çökertiyor. | BÜYÜK |
| 2 | **5-ardışık ters mum + 1.5×ATR gövde** birleşimi 15m kriptoda nadir; üstüne ≤5-bar OB-aktif penceresi + bias hizası + conf≥55. | BÜYÜK |
| 3 | **OB kenarına limit entry** (retrace şartı) + 20-bar expiry → nadir sinyallerin de çoğu dolmadan ölüyor. | ORTA |
| 4 | Görsel yan bug: `not na(sig_entry_*)` kalıcı olduğundan label/line HER bar yeniden çiziliyor (label bütçesini yutuyor; kozmetik). | KÜÇÜK |

## Öneri (revizyon — plan §6 kaçış maddesi: "T-003 backtest'i bozarsa revize edilir")

R-002'nin backtest-validasyon gate'i tam bu senaryo için kondu; gate işini yaptı.
Revizyon seçenekleri (Hermes + Claude konsensüsü, plan v1.4 dokunuşu gerekir):

- **R1 (önerilen):** OB'yi ön koşul olmaktan çıkar → +30'luk confluence faktörü olarak
  kalsın; sinyal tetiği bot'taki gibi yapı kırılımı (recent_higher_high/lower_low veya
  breakout mumu) + conf ≥ threshold olsun.
- **R2:** `ob_seq` 5→3 + OB-aktif penceresi 5→10 bar (parametre gevşetme; parite notu
  spec'e yazılır).
- **R3:** Limit-at-OB yerine sinyal barı kapanışında market entry (bot'un
  market+drift-guard davranışına daha yakın; intrabar-fill iyimserliği de azalır).
- Re-run'da **çoklu-sembol agregasyonu** (BTC/ETH/SOL/BNB/XRP perp) — TV 15m veri
  derinliği ~4.3 ay olduğundan tek sembolde 100 trade zaten zor.

## Not

- G-T3 kanıtı nihai repo içeriğiyle alındı; gate-run varyantı yalnız `bt_date_*`
  default timestamp'lerinde farklıydı (2026 penceresi).
- TV internal-api strateji okuma tool'ları (`data_get_strategy_results/trades/equity`)
  bu kurulumda strateji handle'ını görmüyor — sonuçlar Strategy Tester UI
  (screenshot) + pine_labels üzerinden doğrulandı.
