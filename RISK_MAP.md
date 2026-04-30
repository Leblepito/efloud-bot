# RISK HARITASI — TÜM ARIZA MODLARI VE ÇÖZÜMLERİ
# Efloud Bot v2.1 — "What Can Go Wrong?" Analizi

Bu doküman, botun başına gelebilecek HER ŞEYİ ve çözüm yollarını listeler.
Kod yazmadan önce bu tablodaki her satır için bir yanıtımız olması gerekir.

## KATEGORİ 1: PİYASA REJİMLERİ (Market Regimes)

Bot "trending" piyasada iyi çalışır. Diğer rejimler sorun yaratır:

### 1.1 CHOPPY / SIDEWAYS (Yatay piyasa)
**Sorun:** CHoCH/BOS sinyalleri sürekli tetiklenir ama yön tutmaz.
Whipsaw — SL vurup duruyor, art arda zarar.
**Tespit:** ATR azalıyor + son N bar'daki range daralıyor + swing'ler üst üste.
**Çözüm:**
- Regime detector: ADX < 20 VE bollinger band daralması → "RANGING"
- Ranging'de: sadece range uç noktalarında reversal ara, CHoCH yoksay
- Veya: tamamen işlem yapma, "watch only" moda geç

### 1.2 HIGH VOLATILITY BLOW-OFF (Ani patlama)
**Sorun:** 1-2 saat içinde %10+ hareket. SL bile gap'le geçilir.
**Tespit:** Son bar ATR > 3x ortalama ATR, volume > 5x ortalama.
**Çözüm:**
- "Volatility circuit breaker": yeni pozisyon açma
- Mevcut pozisyonları market order ile kapat (stop'u beklememe)
- 30 dk soğuma periyodu

### 1.3 LOW LIQUIDITY (Likidite çöküşü)
**Sorun:** Spread çok genişler, slippage büyür, orderlar dolmaz.
**Tespit:** Orderbook depth azaldı, spread > normal × 3.
**Çözüm:**
- Spread kontrolü her order öncesi
- Max slippage tolerance (0.1% gibi)
- Aşılırsa order iptal, cycle atla

### 1.4 TREND REVERSAL (Yapısal dönüş)
**Sorun:** Bot bullish bias ile long, ama günler süren bearish phase başladı.
**Tespit:** HTF CHoCH yeni yönde + MTF de aynı yönde + son N bar'ın eğimi ters.
**Çözüm:**
- Trend regime takibi — bias değiştiğinde mevcut pozisyonların review'ı
- Bias flip durumunda mevcut pozisyonlarda SL'yi agresif sıkılaştır
- Yeni yönde pozisyon açmadan önce 3 bar confirmation

### 1.5 NEWS SPIKE (Haber / event)
**Sorun:** FOMC, CPI, ETF onayı gibi olaylar teknik analizi geçersiz kılar.
**Tespit:** Önceden bilinebilir — economic calendar.
**Çözüm:**
- Calendar feed entegrasyonu (opsiyonel)
- Veya: ani volume/volatility spike tespit edince "news mode" → dur

---

## KATEGORİ 2: TEKNİK SISTEM ARIZALARI

### 2.1 API ERRORS
**Sorun:** Binance 503, 429 rate limit, 5xx server error, timeout.
**Çözüm:**
- Exponential backoff retry (1s, 2s, 4s, 8s)
- Rate limit tracking (per minute, per order)
- Network fail → pozisyonları OKUYABILMEK kritik, bu yüzden read cache
- 3 kez fail → sleep 5 dakika, loglara "degraded mode"

### 2.2 DATA GAPS / STALE DATA
**Sorun:** Binance bazen 1-2 mum eksik döndürür veya son mum tam değil.
**Çözüm:**
- Her fetch sonrası: son timestamp bugüne yakın mı? (delta < 2 × timeframe)
- Stale → skip this cycle, don't trade on stale data
- Eksik mum varsa forward-fill yapma — skip et

### 2.3 ORDER REJECTION
**Sorun:** Minimum notional altında, lot size precision hatası, leverage limit.
**Çözüm:**
- Exchange rules cache (market info preload)
- Her order öncesi: min_notional, max_size, step_size kontrolü
- Round to step_size
- Reject → log + skip (retry ETMEZ — muhtemelen parametre hatası)

### 2.4 PARTIAL FILLS
**Sorun:** Büyük order'ın yarısı fill oldu, yarısı pending.
**Çözüm:**
- fetch_order ile status check
- 60 saniye sonra hâlâ partial → iptal et, kalan için yeni order
- Position tracking'de gerçek fill miktarını kaydet (order size değil)

### 2.5 CLOCK DRIFT
**Sorun:** Bot saati sunucu saatinden kayık → "timestamp outside recv window".
**Çözüm:**
- Startup'ta NTP sync kontrolü
- Binance server time ile karşılaştır, > 500ms fark varsa uyar
- ccxt'nin `adjustForTimeDifference` opsiyonunu aç

### 2.6 PROCESS CRASH / RESTART
**Sorun:** Bot crash oldu, pozisyonlar açık, state kayboldu.
**Çözüm:**
- **State persistence**: her pozisyon/senaryo değişikliğinde JSON'a yaz
- Startup'ta: önce state yükle, exchange'den pozisyonları reconcile et
- Discrepancy varsa (bot'un bildiği pozisyon exchange'de yok) → uyar, manual intervention iste
- Tersi de (exchange'de pozisyon var bot bilmiyor) → önemli, trade etme

### 2.7 CONCURRENT TRADE LOCK
**Sorun:** Aynı sembol için iki cycle eşzamanlı trade açmaya kalkar.
**Çözüm:**
- Per-symbol lock (threading.Lock)
- Lock alınamazsa cycle skip
- Async context'te asyncio.Lock

---

## KATEGORİ 3: POZİSYON YÖNETİMİ RİSKLERİ

### 3.1 RUNAWAY LOSS (Sürekli zarar)
**Sorun:** Piyasa rejimi değişti, bot eski mantıkla trade etmeye devam.
Art arda 5-6 SL hit.
**Çözüm:**
- **Daily loss limit**: günlük -%3 zarar → günün geri kalanı pause
- **Consecutive loss limit**: 3 ardışık SL → 2 saat pause, sonraki sinyali 1 bar bekle
- **Weekly drawdown**: -%8 → durdur, manual review

### 3.2 OVER-LEVERAGE (Aşırı kaldıraç)
**Sorun:** Birden fazla pozisyon + kaldıraç = hesap patlama riski.
**Çözüm:**
- Total exposure check: tüm pozisyonların notional/equity < 5x
- Aynı sembolde aynı yönde pozisyon açma
- Hedge pozisyonlar ayrı limit

### 3.3 WRONG SIZE (Yanlış pozisyon boyutu)
**Sorun:** Risk hesabı yanlış, hesabın %50'si tek trade'de.
**Çözüm:**
- Position sizer'da HARD CAP: size * price < balance × 0.2 (tek trade max %20 notional)
- SL distance < %0.5 ise size hesabı patlar → minimum SL distance kuralı
- Size 0 veya negatif → kesin reject

### 3.4 STALE POSITION (Unutulmuş pozisyon)
**Sorun:** Pozisyon açıldı ama SL/TP olmadı, saatlerdir duruyor.
**Çözüm:**
- Her pozisyon için "max holding time" (örn 48 saat)
- Aşılırsa: zorunlu market close
- Pozisyon SL/TP orderları fetch ile doğrula (hepsi yerli yerinde mi)

### 3.5 HEDGE MISMANAGEMENT
**Sorun:** Hedge açıldı ama ana pozisyon kapandı, hedge kaldı.
**Çözüm:**
- Ana pozisyon kapanırken otomatik hedge değerlendirmesi
- Eğer hedge kârda → kapat; zararda → SL'ye yaklaştır
- "Orphan hedge" detector: ana pozisyon yoksa hedge uyarı ver

### 3.6 PYRAMID ABUSE (Kontrolsüz ekleme)
**Sorun:** Bot sürekli dip alımı yapıyor, ortalama fiyat düşüyor ama pozisyon çok büyüdü.
**Çözüm:**
- Max pyramid adds: 2 (ilk giriş + 2 add)
- Her ekleme: total size < initial × 2
- Adds only if first entry in profit at some point (momentum check)

---

## KATEGORİ 4: VERİ KALİTESİ

### 4.1 WRONG TIMEZONE
**Sorun:** Monday H/L tespiti yanlış timezone'da yapılır.
**Çözüm:**
- Tüm timestamp'ler UTC
- User preference'e göre display'de TZ dönüşümü
- Binance default UTC döndürür — doğrula

### 4.2 MISSING VOLUME
**Sorun:** Bazı sembollerde volume 0 veya NaN.
**Çözüm:**
- Volume NaN → intent engine'de fallback (sadece body + streak skorla)
- Volume tamamen yoksa → uyar, düşük güvenle devam

### 4.3 INCONSISTENT TIMEFRAMES
**Sorun:** HTF data 4h ama son mum yarım saatlik — henüz kapanmamış.
**Çözüm:**
- Last candle completeness check: `now - candle_close_time > candle_duration * 0.95`
- Değilse son mum'u HARIÇ tut (sadece kapanmış mumlarla analiz)

### 4.4 ROUNDING ERRORS
**Sorun:** Float precision — 2300.0000001 != 2300
**Çözüm:**
- Seviye karşılaştırmalarında tolerans (epsilon): 0.01%
- Fiyatları exchange precision'a yuvarla (BTC: 2 decimal, ETH: 2 decimal)

---

## KATEGORİ 5: STRATEJİ EDGE CASES

### 5.1 NO CLEAR BIAS
**Sorun:** HTF undefined, ne bullish ne bearish.
**Çözüm:**
- Bias "UNDEF" → sadece scenario planı (watch only), pozisyon açma
- 3 bar sonra hâlâ undef → alternatif TF dene (4h yerine 1d)

### 5.2 NO SIGNAL FOR DAYS
**Sorun:** Sinyal üretmiyor — parametreler mi yanlış, piyasa mı sakin?
**Çözüm:**
- Heartbeat log: "N cycles since last signal"
- > 24h signal yok → confluence eşiğini geçici düşür (50 → 40) "dry spell mode"
- 48h hâlâ yok → kullanıcıya uyar

### 5.3 CONFLICTING SIGNALS
**Sorun:** Entry TF long diyor, MTF short diyor.
**Çözüm:**
- Hiyerarşi: HTF > MTF > Entry. Çelişki varsa HTF kazanır.
- Entry sinyalinin MTF onayı yoksa reddet.

### 5.4 OVERLAPPING SCENARIOS
**Sorun:** Main scenario long, invalidation da long ama farklı seviyeden.
**Çözüm:**
- Scenarios sınıflandırması: aynı yön × farklı seviye = "additive", ayrı ayrı yönetilebilir
- Ama toplam risk limitini aşamaz

### 5.5 ZOMBIE SCENARIOS
**Sorun:** Eski senaryolar listede kalıyor, yenileri üretilmiyor.
**Çözüm:**
- Scenario TTL: 100 bar geçti tetiklenmediyse → EXPIRED
- Her cycle'da cleanup: expired/invalidated'ları arşive taşı
- Active scenario count > 20 → reset

---

## KATEGORİ 6: OPERASYONEL RİSKLER

### 6.1 SECRET LEAK
**Sorun:** API key git'e commit edildi veya log'a yazıldı.
**Çözüm:**
- Config'de API key ASLA plaintext değil — env var zorunlu
- Log'da key mask (sadece son 4 karakter)
- .gitignore'da config.local.yaml

### 6.2 ACCIDENTAL MAINNET
**Sorun:** testnet=false yanlışlıkla, gerçek para ile test.
**Çözüm:**
- Mainnet'te startup'ta "DANGER: MAINNET" uyarısı + 5 saniye beklet
- İlk defa mainnet açılırken dry_run=true zorla
- ENV variable `EFLOUD_ALLOW_MAINNET=1` olmadan mainnet çalışmaz

### 6.3 LOG EXPLOSION
**Sorun:** Debug mode açık, her tick'te 100 satır log → disk dolar.
**Çözüm:**
- Log rotation (günlük, max 100MB)
- Production'da INFO, development'ta DEBUG
- Her tick'te log yazma — sadece STATE CHANGE log

### 6.4 CONFIG DRIFT
**Sorun:** Canlı config değişti, backtest'te kullanılan farklıydı.
**Çözüm:**
- Her cycle başında config hash log'a
- State dosyasında aktif config snapshot'ı
- Değişiklikte eski state invalidate

### 6.5 DEPENDENCY BREAKAGE
**Sorun:** ccxt yeni sürüm çıktı, API signature değişti.
**Çözüm:**
- requirements.txt'de version pin: `ccxt==4.4.0`
- Startup'ta sürüm kontrolü
- Major version atlama → manual upgrade required

---

## ÖNCELİK LİSTESİ (İlk ne kodlamalı?)

**P0 — Bot'u güvenli hale getiren (şimdi):**
1. State persistence (crash recovery)
2. Daily loss limit + circuit breaker
3. API retry + rate limit
4. Mainnet guard
5. Stale data detection

**P1 — Strateji kalitesini artıran (hemen sonra):**
6. Regime detector (trending/ranging/volatile)
7. Consecutive loss pause
8. Signal drought handling
9. Volatility circuit breaker

**P2 — İleri düzey güvenlik (sonra):**
10. News calendar integration
11. Position reconciliation
12. Concurrent lock
13. Max pyramid/holding time
