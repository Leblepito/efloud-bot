# P-001: u2algo Master Plan — Wave 1 TradingView (Pine Script v6)

**Başlangıç:** 2026-06-07
**Sahip:** @hermes (implementor), @claude (reviewer)
**Branch:** `feat/lltodo-p001-implement`
**Versiyon:** 1.2 (post-consensus revize — 2026-06-10)

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

---

## 9. Referanslar

- `CLAUDE.md` — Proje genel kuralları, Pine kısıtları
- `engine/signals.py` — v1 SMC sinyal mantığı (Python referans)
- `engine/smc_v2/` — v2 SMC modülleri (Python referans)
- `config.yaml` — Canlı parametre değerleri
- `pine/PINE_SPEC.md` — Python→Pine teknik çeviri haritası
