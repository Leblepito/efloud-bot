# v3.2 Entry-Anchored TP — 48 Saat Gözlem Raporu (2026-07-14, otomatik)

> Kaynak: bot.ualgotrade.com canlı API (healthz/status/positions/history/equity/orders) + repo kod incelemesi.
> Kısıt gereği hiçbir config/kod değiştirilmedi, push yapılmadı, canlı trade'e müdahale edilmedi.

## Özet (TL;DR)

Bot sağlıklı çalışıyor (cycle 18740, crash 0, breaker OPEN = normal akış) ve haftalık equity +%32.5
(1097 → 1454 USDT, unrealized dahil). **Ancak v3.2'nin ana hedefi canlıda gerçekleşmiyor:**
deploy sonrası açılan tek trade'in TP1 etiketi `RR_PROJECTION` @ tam 1.8R — beklenen
`RANGE_EQ / LIQ_MTF / LIQ_SWING` etiketlerinden hiçbiri hiç görülmedi (0/12 tüm zamanlar).
Kod incelemesi nedeni netleştiriyor: canlı config `smc_version: v2` ve v2 setup yolu TP'yi
`engine/smc_v2/tp_calc.py` ile hesaplıyor; bu dosya `smc_tp_targeting/min_rr_tp1/blended_rr_target`
parametrelerini **hiç okumuyor**, legacy `min_rr: 1.8` projeksiyonunu kullanıyor. v3.2 havuzu
(`_select_tp_from_smc_blocks`) yalnız v1 `generate_signal` yolunda yaşıyor ve o yoldan 48 saatte
0 trade geldi. **Ek olarak iki risk bulgusu:** (1) lifecycle 12 açık pozisyon sayıyor ama borsada
2 gerçek pozisyon var — 10 hayalet/duplike journal kaydı `max_open_positions: 10` limitini doyurmuş
olabilir; (2) `/api/orders` canlı Binance sorgusu **boş** dönüyor — iki açık short için borsada
bekleyen SL/TP emri görünmüyor.

## Bulgular

### 1. Git durumu ✅
- v3.2 batch (`410d81b` … `86e9297`) origin/master'da mevcut — push yapılmış.
- Lokal master origin'den **1 commit ileride**: `7e632bf test(statement): skipif'ler kaldirildi`.
  Push Windows'tan yapılmalı (sandbox'tan push yasak — hafıza kuralı).
- Working tree'de 446 modified dosya görünüyor (büyük olasılıkla Cowork mount/CRLF gürültüsü,
  ayrıca `backend/bot_runner.py`, `main.py` bilinen unstaged değişiklikler).

### 2. Canlılık ✅
| Metrik | Değer |
|---|---|
| running | true (mainnet, dry_run: false) |
| cycle_count | 18740, son cycle 2026-07-14T02:03:30Z (taze) |
| breaker_state | OPEN (bu repo semantiğinde = normal akış, breaker.py:36) |
| healthz | ok — fatal_exception yok, crash_count 0 |
| config | configs/config.phase2_1k.yaml |

### 3. tp1_source etiketleri ❌ (ana bulgu)
- Journal'da `tp1_target_type` dolu olan **12 kayıt var, 12'si de `RR_PROJECTION`**, tamamı
  `entry_setup_source=OTE_RETRACE`, `tp2_target_type=NONE`, TP1_R **tam 1.80** (sabit).
- Deploy (07-12) sonrası tek yeni trade: **LINK/USDT SHORT** 2026-07-12T23:00Z —
  entry 7.957 / SL 8.229 / TP1 7.467 → TP1_R = 1.80, TP2 yok. Yine `RR_PROJECTION`.
- Beklenen `RANGE_EQ / LIQ_MTF / LIQ_SWING`: **0 adet**.
- Kök neden (kod okuması):
  - `configs/config.phase2_1k.yaml:68` → `smc_version: v2`.
  - v2 setup yolu: `engine/safe_orchestrator.py:2223` → `engine/smc_v2/tp_calc.py` →
    havuz yalnız LIQUIDITY/FVG_NEAR; aday yoksa `entry ± min_rr(1.8) × risk` = RR_PROJECTION.
    `smc_tp_targeting` bu dosyada okunmuyor.
  - v3.2 havuzu: `engine/signals.py:922-984` (`_select_tp_from_smc_blocks`) — yalnız v1
    `generate_signal` yolunda; `safe_orchestrator.py:1215` parametreyi oraya geçiriyor.
  - Yani `smc_tp_targeting: true` config'de açık ama canlı trade üreten v2 yolunda **etkisiz**.
  - Ayrıca 12/12 kayıtta smc_v2 havuzunun kendi LIQUIDITY/FVG_NEAR adayları da hiç seçilmemiş
    (hep "aday yok" fallback'i) — v2 yoluna boş `htf_swings/eq_levels` gidiyor olabilir, ayrıca
    incelenmeli.

### 4. TP1 fill / SL→BE ⏸ (veri yok)
- 48 saatte TP1 fill **0** (tek yeni trade hâlâ açık, `tp1_hit: false`; BNB eski pozisyon da false).
- Journal kapanış nedenleri (son 60): RECONCILED 35, MAX_HOLD 14 — açık `TP1/SL` nedeni yok
  (TP/SL fill'leri RECONCILED altında toplanıyor olabilir). SL→BE geçişi gözlemlenemedi.

### 5. Sinyal/trade sayısı ⚠️
- Deploy sonrası 48 saatte **1 trade** (öncesinde ~5-8/gün). Kalite filtresiyle düşüş beklenendi
  ama bu seviye şüpheli; aşağıdaki hayalet pozisyon bulgusuyla birleşince guard-bloğu ihtimali var.

### 6. Hayalet pozisyonlar / max_open doygunluğu ⚠️ (yeni bulgu)
- `/api/status` ve `/api/equity` → **open_positions: 12**; `/api/positions` (borsa gerçeği) → **2**
  (BNB/USDT SHORT 07-10, LINK/USDT SHORT 07-12).
- Journal'da hiç kapanmamış 12 kayıt birebir eşleşiyor: 8× BNB SHORT aynı entry 585.68
  (07-07 17:00→18:45, 15dk aralıklarla duplike!) + 3× BNB (07-10 08:00/13:45/19:30) + 1× LINK.
- `max_open_positions: 10` (config:119) — lifecycle 12 sayıyorsa duplicate/exposure/max_open
  guard'ları **doymuş** olabilir → yeni girişleri sessizce engelliyor olabilir (madde 5'i açıklar).
  Duplike kayıtlar F2 (v2 lifecycle mirror) fix'i ÖNCESİ döneme ait; RECONCILE bunları temizlememiş.

### 7. Borsada bekleyen emir yok ⚠️ (doğrulanmalı)
- `/api/orders` canlı `fetch_open_orders()` → **[]**. İki açık short için borsada SL/TP emri
  görünmüyor (endpoint CCXT hatasında da [] döner — Binance panelinden teyit şart).
  Bot çökerse pozisyonlar çıplak kalır; F3-F7 sentinel-SL fix'lerinin amacına aykırı durum.

### 8. Kritik log event'leri (uzaktan erişilemedi)
`be_sl_unreachable_closing`, `sl_repair_unreachable_closing`, `fallback_close_failed` VPS loglarında
aranmalı — dashboard API'sinde log endpoint'i yok.

## VPS Manuel Kontrol Listesi (Utku)

```bash
cd /opt/efloud-bot
# 1. Kritik fail-closed event'leri + TP1/BE akışı
docker compose logs --since 48h | grep -E "tp1_source|TP1 HIT|SL → BE|Signal:|be_sl_unreachable|sl_repair_unreachable|fallback_close_failed"
# 2. Guard bloğu var mı (hayalet pozisyon hipotezi)
docker compose logs --since 48h | grep -iE "max_open|duplicate|exposure|guard|skip"
# 3. Deploy edilen kod v3.2 mi
docker compose exec bot git log --oneline -3
# 4. Borsada SL/TP emirleri gerçekten yok mu → Binance Futures > Open Orders (BNB, LINK)
```

## Tuning Kararı: min_rr_tp1 0.5 → 0.8?

**HAYIR — şimdilik değiştirme.** Gerekçe: TP1'ler 0.5R'ye yığılmıyor (tam tersi, tek post-deploy
örnek 1.8R fallback'te); yapısal havuz canlı yolda hiç devreye girmediği için min_rr_tp1'in
etkisini ölçecek veri yok. Parametre tuning'i anlamsız — önce entegrasyon sorunu çözülmeli.

## Önerilen Sonraki Adımlar (öncelik sırasıyla — bu run'da uygulanmadı)

1. **v2 TP entegrasyonu:** `smc_v2/tp_calc.py`'ye entry-anchored havuzu taşı veya v2 setup yolunu
   `_select_tp_from_smc_blocks`'a bağla (TDD + risk-ops review + backtest gate ile).
2. **Hayalet pozisyon temizliği:** 10 duplike journal-open kaydını reconcile/kapat; duplike
   journaling'in kök nedenini bul (F9 dedup davranışıyla ilişkili olabilir).
3. **Borsa SL/TP teyidi:** Binance'te emir yoksa acil — sentinel SL yerleştirme yolunu incele.
4. LINK trade'i TP1(7.467)/SL(8.229) gerçekleşince TP1-sonrası %50 kısmi + SL→BE zincirini logdan doğrula.
