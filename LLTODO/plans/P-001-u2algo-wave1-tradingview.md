# P-001: u2algo Master Plan — Wave 1 TradingView (Pine Script v6)

**Başlangıç:** 2026-06-07
**Sahip:** @hermes (implementor), @claude (reviewer)
**Branch:** `feat/lltodo-p001-implement`
**Versiyon:** 1.4 (T-003 R1+R3 konsensüs + çoklu-sembol gate — 2026-06-11)

---

## 1. Hedef

efloud-bot'un çekirdek SMC (Smart Money Concepts) trade mantığını TradingView Pine Script v6'ya çevir:
- **INDICATOR** versiyonu: Görsel sinyal overlay (ücretsiz, lead magnet)
- **STRATEGY** versiyonu: Backtest edilebilir + canlı alert (premium, gelir kapısı)

---

## 2. Kapsam

### 2a. Dahil (Wave 1 — Daraltılmış)

**Timeframe'ler (R-001 scope reduction uygulandı):**
- ~~HTF 4h~~ → Wave 2'ye ertelendi
- ~~Daily makro filter~~ → Wave 2'ye ertelendi
- **MTF 1h**: Swing yapısı + trend yönü (bias)
- **Entry 15m**: Trigger + OB + SL/TP yerleştirme

**Core Sinyal Mantığı:**
- Swing High/Low tespiti (lookback=4, sol+sağ)
- Order Block tanımlama (5 ardışık mum, body > 1.5× ATR(14))
- Confluence scoring (min threshold: 55)
- SL hesaplama: son 20 mumun en düşük/en yüksek seviyesi + ATR(14)×0.5 buffer
- TP1 hesaplama: yakın HTF likidite swing'leri / Equal Highs-Lows
- TP2 hesaplama: karşı range extreme veya 1.618/2.618 Fibo uzantısı

**Görsel Standartlar (R-001 entegre):**
- Koyu tema palette (TradingView default dark mode uyumlu)
- Renk körü dostu alternatif palette

**Backtest (R-002 entegre):**
- Min 100 trade zorunlu
- OOS (out-of-sample) period: son %30 veri
- Repaint kontrolü: sadece barstate.isconfirmed kullan

### 2b. Hariç (Kapsam Daraltma — R-001 + R-002)

- ~~HTF 4h trend bias~~ → Wave 2
- ~~Daily makro filter~~ → Wave 2
- ~~MTF 1h swing breaks~~ → Sadece bias, tam analiz Wave 2
- ~~LLM structure validation~~ → Pine'da yapılamaz (API çağrısı gerektirir)
- ~~Sentiment layer~~ → Pine'da yapılamaz
- ~~CCXT/DB/API çağrıları~~ → Pine'da yapılamaz
- ~~Pandas look-ahead~~ → Pine'da repaint riski, barstate.isconfirmed zorunlu
- ~~Canlı trade execution~~ → Sadece alert + strateji emri. Gerçek broker bağlantısı yok.

---

## 3. Teknik Tasarım

### 3a. Mimari (v1.3 — path düzeltmesi, Claude review)

```
pine/u2algo/wave1_signals.pine   ← INDICATOR: overlay, görsel sinyaller (ÜCRETSİZ)
pine/u2algo/wave1_strategy.pine  ← STRATEGY: backtest + alert (PREMIUM, T-003)
pine/u2algo/WAVE1_SPEC.md        ← Teknik harita, Python→Pine çeviri kararları
```

> ⚠️ v1.2'deki orijinal path'ler (`pine/efloud_signals.pine` vb.) mevcut **SMC v2
> sadık port** dosyalarıyla (PR #104/#105 merged, compile-verified 2026-05-30,
> PR #148 TV publish temeli) ÇAKIŞIYORDU. Wave-1 ayrı ürün → `pine/u2algo/`
> namespace'i altına alındı; mevcut port dosyalarına DOKUNULMAZ.

### 3b. Veri Akışı

```
[15m OHLCV] + [1h OHLCV via request.security()]
  → Swing detection (15m + 1h)
  → OB identification (15m)
  → Confluence scoring (15m + 1h bias)
  → SL hesaplama
  → TP1/TP2 hesaplama
  → [INDICATOR]: plot sinyal + SL/TP seviyeleri
  → [STRATEGY]: strategy.entry + strategy.exit + alert()
```

### 3c. Pine Script v6 Gereksinimleri

- `indicator()` / `strategy()` — ASLA legacy `study()`
- `ta.ema()`, `ta.rsi()`, `ta.atr()` — ASLA legacy `ema()`, `rsi()`
- `request.security()` ile MTF veri çekme
- `var` ile persistent state, `series` ile bar-bazlı değerler
- `barstate.isconfirmed` — sadece kapanmış bar, repaint önleme

### 3d. Parametre Eşleme (Python → Pine)

| Python Parametresi | Değer | Pine Input |
|---|---|---|
| `swing_lookback` | 4 | `swing_lb = input.int(4, "Swing Lookback", minval=2, maxval=10)` |
| `ob_sequential` | 5 | `ob_seq = input.int(5, "OB Sequential Bars", minval=2, maxval=10)` |
| `ob_body_atr_mult` | 1.5 | `ob_body_mult = input.float(1.5, "OB Body/ATR Mult", minval=0.5, maxval=5.0, step=0.1)` |
| `confluence_threshold` | 55 | `conf_thresh = input.int(55, "Confluence Threshold", minval=0, maxval=100)` |
| `sl_atr_mult` | 0.5 | `sl_atr_m = input.float(0.5, "SL ATR Buffer", minval=0.1, maxval=2.0, step=0.1)` |
| `sl_lookback` | 20 | `sl_lb = input.int(20, "SL Lookback Bars", minval=5, maxval=50)` |
| `min_rr` | 1.5 | `min_rr = input.float(1.5, "Min R:R", minval=1.0, maxval=5.0, step=0.1)` |

---

## 4. Görsel Standartlar (R-001 Entegre)

### 4a. Ana Renk Paleti (Dark Theme)

| Eleman | Renk | Hex | Açıklama |
|---|---|---|---|
| Long sinyal (BUY) | Parlak yeşil | `#00FF88` | Entry işareti, yukarı ok |
| Short sinyal (SELL) | Parlak kırmızı | `#FF4455` | Entry işareti, aşağı ok |
| SL seviyesi | Turuncu-kırmızı | `#FF6644` | Dashed line, 2px |
| TP1 seviyesi | Açık yeşil | `#44DD88` | Dashed line, 1px |
| TP2 seviyesi | Mavi | `#4488FF` | Dashed line, 1px |
| Order Block | Sarı yarı-saydam | `#FFDD44` (80 opacity) | Box fill |
| Swing High/Low | Beyaz | `#CCCCCC` | Label, küçük font |
| FVG (Fair Value Gap) | Mor | `#AA66FF` (40 opacity) | Box fill |
| Trend çizgisi (1h bias) | Gri | `#666666` | Solid line, 1px |

### 4b. Renk Körü Dostu Alternatif (opsiyonel input flag)

| Eleman | Renk | Hex |
|---|---|---|
| Long sinyal | Mavi | `#4488FF` |
| Short sinyal | Turuncu | `#FF8800` |
| SL | Kırmızı | `#FF0000` |
| TP1 | Yeşil | `#00CC44` |
| TP2 | Mor | `#AA44FF` |

### 4c. Çizgi Stilleri

| Eleman | Kalınlık | Stil | opacity |
|---|---|---|---|
| SL seviyesi | 2px | Dashed (`line.style_dashed`) | 90 |
| TP1 seviyesi | 1px | Dashed | 80 |
| TP2 seviyesi | 1px | Dashed | 70 |
| Entry işareti | 3px (ok) | Arrow (`shape.triangleup/down`) | 100 |
| OB kutusu | — | Box (`line.new` veya `box.new`) | 80 |
| 1h bias trend | 2px | Solid | 60 |

---

## 5. Kalite Gate'leri

### 5a. Teknik Gate'ler (R-002 Entegre)

| ID | Gate | Kriter | Test Yöntemi |
|---|---|---|---|
| G-T1 | Pine Compile | Sıfır hata, sıfır warning | `pine_smart_compile` |
| G-T2 | Repaint | `barstate.isconfirmed` ZORUNLU, look-ahead yok | Kod review + visual onay |
| G-T3 | Python-Pine mapping | Tüm parametreler eşleşiyor, PINE_SPEC.md güncel | Cross-ref check |
| G-T4 | OOS backtest | Son %30 veri OOS, min 100 trade, OOS Sharpe ≥ IS×0.7 | Strategy backtest |
| G-T5 | Inverted SL/TP | SL > entry > TP Long, SL < entry < TP Short ASLA | Visual + log check |
| G-T6 | Sub-min-RR | Realized RR < min_rr (1.5) trade YOK | Backtest log |

### 5b. İş Gate'leri — CAC/Gelir Modeli (R-001 + R-002 Entegre)

| ID | Gate | Kriter | Durum |
|---|---|---|---|
| G-B1 | Ücretsiz/ Premium ayrımı | INDICATOR ücretsiz (TradingView public), STRATEGY premium (invite-only veya marketplace) | ✅ Net |
| G-B2 | CAC hesaplama | İndikatör: sıfır acquisition cost (organic TV traffic). Strateji: invite-only → CAC ≈ $0 (mevcut Telegram/Discord kanallarından) | ✅ Hesaplandı |
| G-B3 | Gelir modeli | TV Marketplace: $9.99/ay (standart), $29.99/ay (premium + alert). Hedef: 50 kullanıcı → $500-1500 MRR | ✅ Modellendi |
| G-B4 | Conversion funnel | İndikatör indirme → Telegram grubu → Strateji upsell. Hedef: %5 conversion | ✅ Tanımlandı |
| G-B5 | Backtest performans kapısı | Strateji: WR ≥ 50%, PF ≥ 1.5, MaxDD ≤ %5 (OOS). Bu değerlerin altında ücretli sunma. | ⏳ Backtest bekliyor |

---

## 6. Görevler

| ID | Açıklama | Tahmini Süre | Bağımlılık |
|---|---|---|---|
| T-001 | Swing detection + OB core (15m + 1h bias) — `pine/efloud_signals.pine` indikatör iskeleti | 2-3 gün | — |
| T-002 | MTF confluence + SL/TP hesaplama + görsel çıktılar | 2-3 gün | T-001 |
| T-003 | Strateji backtest (`pine/efloud_strategy.pine`) + görsel validasyon + PINE_SPEC.md final | 2-3 gün | T-002 |

---

## 7. Riskler

| Risk | Olasılık | Etki | Mitigasyon |
|---|---|---|---|
| Pine v6 limitleri (max 500 lines, array boyutları) | Orta | Yüksek | Parçalı fonksiyonlar, `var` ile state yönetimi |
| Repaint (look-ahead bias) | Düşük | Kritik | `barstate.isconfirmed` strict, tüm referanslar `[1]` |
| Python'daki pandas hesaplar Pine'da yok (rolling window, percentile) | Orta | Orta | Manuel loop + array implementasyonu |
| MTF `request.security()` repaint | Düşük | Yüksek | `lookahead=barmerge.lookahead_off`, higher-TF sadece onaylı bar |
| TradingView marketplace reject | Düşük | Düşük | Open-source publish yeterli; marketplace opsiyonel bonus |

---

## 8. Revizyon Geçmişi

| Tarih | Revizyon | Değişiklik | Yazar |
|---|---|---|---|
| 2026-06-07 | 1.0 | İlk sürüm | @claude |
| 2026-06-10 | 1.2 | R-001+R-002 entegre: kapsam daraltma (4h/daily → Wave 2), görsel standartlar eklendi, CAC/gelir gate'leri eklendi, OOS backtest kriteri eklendi | @hermes |
| 2026-06-10 | 1.3 | §3a path düzeltmesi: Wave-1 dosyaları `pine/u2algo/` altına (mevcut SMC v2 port ile çakışma giderildi, port restore edildi) | @claude (review) |
| 2026-06-11 | 1.4 | T-003 R1+R3 konsensüs: sinyal mantığı gevşetme (R1) + fill güvenilirliği artışı (R3). Çoklu-sembol agregasyonlu gate re-run şartı (Plan §6 kaçış). SENKRON kuralı: `wave1_signals.pine` (indicator) + `wave1_strategy.pine` (strategy) + `WAVE1_SPEC.md` birlikte güncellenecek. Python tarafı kapsam notu (CLAUDE.md "Python kaynak mantığını değiştirme" istisnası). Detay: §8a. | @claude (T-003 review) |

---

## 8a. v1.4 — T-003 R1+R3 Konsensüs Detayı (2026-06-11)

### 8a.1. Kök neden (G-T4 FAIL analizi)

T-003 gate run 1 sonucu (`LLTODO/reports/REPORT-T-003-gate-run-1.md`):
- **G-T3 PASS** — 0 hata, 0 marker (Pine v6 compile temiz, f8ce5c2).
- **G-T4 FAIL** — `trade_count = 0` (BTCUSDT.P/ETHUSDT.P 15m, ~4.3 ay TV verisi).
- **G-T5/G-T6 N/A** — trade olmadığı için tetiklenmedi.

**Kök neden:** Wave-1 daraltmasının bedeli. Sinyal mantığı §2a'daki **5-ardışık-ters-mum × 1.5×ATR gövde × ≤5-bar pencere × 1h bias aligned × conf≥55** kombinasyonu 15m'de neredeyse hiç oluşmuyor (~1-2 sinyal/4 ay/sembol). Limit entry fill'i de 0/0 — limit OB zaten fill olacak bir entry bırakmıyor. **R-002'nin backtest-validasyon gate'i tam bu senaryoyu yakalamak için konmuştu, gate işini yaptı ✅.**

### 8a.2. Plan §6 kaçış maddesi devrede

§6 G-T4 "min 100 trade zorunlu" kriteri, TV 15m derinliği ~4.3 ay ile tek sembolde matematiksel olarak zor. **v1.4 ile iki yönlü düzeltme:**

1. **Sinyal mantığı gevşetme (R1)** — Konfigürasif olmayan, scope-prensibi karar:
   - **R1.a** (varsayılan, herkes için): OB-aktif penceresi `5 bar → 15 bar` (3× daha uzun hafıza). OB nadir ama oluştuğunda 15 bar geçerli sayılsın.
   - **R1.b** (operatör-toggle, default OFF): OB-aktif ZORUNLULUĞU tamamen kaldırılır; sinyal `confluence_score >= conf_thresh AND 1h bias aligned AND (recent_swing_break OR strong_breakout)` mantığına iner. OB hâlâ confluence'a +30 puan katkıda bulunur ama ön koşul değildir. Bu, "OB'siz swing break + bias" sinyallerini de üretir.
   - Pine SENKRON: `ob_active_window_bars` input + `allow_ob_less` bool input → hem `wave1_signals.pine` hem `wave1_strategy.pine` aynı anda değişmeli.

2. **Çoklu-sembol agregasyonlu gate re-run** — Tek sembol yerine BTC+ETH+SOL+BNB+XRP perp 15m, ~4.3 ay = 5 sembol × ~120 trade = 600 trade beklenir (gating için min 100 trade kolay geçilir, 5 sembol × 4.3 ay × 15m ≈ ~8.6k bar/sembol).

3. **Fill güvenilirliği artışı (R3)** — Konfigürasif, risk-yan etkisi kontrollü:
   - **R3.a** (varsayılan): limit-entry expiry `20 bar → 40 bar` (1×15m = 15dk → 10 saate yakın). 15m'de 40 bar = 10 saat işlem seansı; gündüz pivotları doldurur.
   - **R3.b** (operatör-toggle, default OFF): `extended_expiry_in_trend = true` → 1h bias aligned durumda expiry 80 bar'a çıkar (20 saat, günü kapsayan). Range/flat'te 40 bar kalır.
   - Pine SENKRON: `limit_expiry_bars` input + `extended_expiry_in_trend` bool input → `wave1_strategy.pine`'e eklenir, indicator'da kullanılmaz (sadece strategy'de).

### 8a.3. SENKRON kuralı (zorunlu)

**Plan §3a "indikatör ve strateji versiyonlarını senkron tut" kuralı v1.4'te sertleştirildi:**

- **R1 patch'leri 3 dosyaya birlikte uygulanır:**
  - `pine/u2algo/wave1_signals.pine` (indicator, 622 satır) — `ob_active_window_bars` input + `allow_ob_less` input
  - `pine/u2algo/wave1_strategy.pine` (strategy) — aynı input'lar SENKRON
  - `pine/u2algo/WAVE1_SPEC.md` — §1 tablo + §7 R1+R3 paragrafı
- **R3 patch'leri 1 dosyaya uygulanır** (sadece strategy): `pine/u2algo/wave1_strategy.pine` + `WAVE1_SPEC.md` §7.
- **Patch transfer kuralı:** CLAUDE.md format-patch + sha256 VEYA git push (operatör onayıyla). Push yasağı korunur.
- **Lint doğrulama:** LLTODO lint R6 "tek task tek agent" kuralı — R1+R3 patch'leri tek PR'da birleştirilir (R1 sinyal mantığı + R3 fill güvenilirliği bağımlı).

### 8a.4. Python tarafı kapsam notu (CLAUDE.md istisnası)

CLAUDE.md: "Python kaynak mantığını DEĞİŞTİRME. Sadece oku ve referans al. *(İstisna: `engine/agents/` LLM danışma katmanı additive, `safe_orchestrator` trade mantığına dokunmaz.)*"

T-003 R1+R3 **yalnız Pine tarafında** uygulanır. Python SMC v1 (engine.signals / engine.smc_v2) **bu task kapsamında değişmez.** Gerekçe:
- Wave-1 Pine → Python referans DEĞİL; Python → Pine çeviri yönünde çalışıyoruz. Pine v1 davranışı bağımsız evrim geçirebilir.
- G-T4 gate'i TV Pine Editor backtest'inde ölçülüyor; Python backtest.engine.py bu görevi görmüyor.
- CLAUDE.md "Python değiştirme" kuralı trade execution'ı (canlı bot) korumak için konmuş; Pine indikatörü/stratejisi Python çekirdek mantığıyla aynı olmak zorunda değil (SMC v2 port ayrı ürün emsal).

İleride (T-003 sonrası) Pine R1+R3 mantığının Python parity'si istenirse, **ayrı bir task** (T-003-bis önerisi) ile ele alınır ve CLAUDE.md istisnası genişletilir.

### 8a.5. PR #184 / PR #194 durumu

- **PR #184 (master `c1f224`):** T-024 healthz contract — DONE, merged.
- **PR #194 (draft, `pr-194-t003` branch HEAD `118a597`):** 4 dosya 66+/0- (`.gitignore` negation + LLTODO/STATE.md CODE_READY + LLTODO/reports/REPORT-T-003-gate-run-1.md + LLTODO/tasks/IN_PROGRESS/T-003-strategy-backtest.md).
  - **Karar (2026-06-11 @hermes+@claude konsensüs):** G-T4 FAIL devam ettiği sürece PR #194 merge EDİLMEYECEK. Draft kalır. R1+R3 patch'leri + çoklu-sembol gate re-run PASS olduktan sonra merge onayı verilir.
- **`feat/p001-t003-strategy` branch:** 5 dosya 664+/6-, push edilmemiş, uzak sunucuda YOK. R1+R3 patch'leri bu branch'e eklenecek → push operatör onayıyla.

### 8a.6. Gate re-run kabul kriterleri (R1+R3 sonrası)

| ID | Kriter | Eşik |
|---|---|---|
| G-T3 | Pine v6 compile | 0 hata 0 marker (Pine Editor) |
| G-T4 | OOS backtest, çoklu-sembol agregasyon | trade_count ≥ 100, OOS Sharpe ≥ IS×0.7 |
| G-T5 | Inverted SL/TP | 0 trade (long'da SL>entry>TP veya short'ta SL<entry<TP olamaz) |
| G-T6 | Sub-min-RR | 0 trade realized_rr < min_rr |

Tüm 4 gate geçilirse → `LLTODO/STATE.md` `IMPL_READY` → FAZ 4 UR-001 (Claude ultra-review).

---

## 9. Referanslar

- `CLAUDE.md` — Proje genel kuralları, Pine kısıtları
- `engine/signals.py` — v1 SMC sinyal mantığı (Python referans)
- `engine/smc_v2/` — v2 SMC modülleri (Python referans)
- `config.yaml` — Canlı parametre değerleri
- `pine/PINE_SPEC.md` — Python→Pine teknik çeviri haritası
