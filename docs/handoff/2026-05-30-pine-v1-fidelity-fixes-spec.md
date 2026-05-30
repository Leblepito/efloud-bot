# Spec: Pine V1 Port Fidelity Fixes (Gemini iş paketi)

> **Yazan:** Opus (Architect). **Uygulayan:** Gemini (Engineer). **Review:** Opus.
> **Kapsam:** SADECE `pine/` dosyaları. Python kaynağı DEĞİŞMEZ (CLAUDE.md kuralı).
> **Bağlam:** Pine V2 portu yüksek fidelity (kritik sapma yok). V1 portunda 4 sapma var (fidelity denetimi 2026-05-30). Bu spec onları kapatır.

---

## Hedef

`pine/efloud_signals_v1.pine` ve `pine/efloud_strategy_v1.pine`'ı Python V1 kaynağına (`engine/signals.py`) ve **production config'e** (`configs/config.phase2_1k.yaml`) hizalamak. Pine V2 dosyalarına DOKUNMA (zaten uyumlu).

Her değişiklikten sonra TradingView Pine Editor'da derle (sıfır hata), `pine/PINE_SPEC.md`'yi güncelle.

---

## S3 (KRİTİK) — Target-Inversion Guard eksik

**Python referansı:** `engine/signals.py` `_enforce_tp2_beyond_tp1` (satır ~98-113):
```python
def _enforce_tp2_beyond_tp1(tp2, tp1, price, risk, is_long):
    if is_long:
        if tp2 <= tp1:
            tp2 = max(tp2, tp1 + risk * 0.5, price + risk * 2.618)
    else:
        if tp2 >= tp1:
            tp2 = min(tp2, tp1 - risk * 0.5, price - risk * 2.618)
    return tp2
```
Python her sinyalde TP2 hesabından SONRA bunu çağırır (`signals.py:633`). TP2, TP1'e eşit/yakın olursa TP2'yi TP1 ötesine zorlar → borsada -2021 "immediate trigger" reddi ve ters TP1/TP2 sırası önlenir.

**Sorun (Pine V1):** `efloud_signals_v1.pine` (TP2 bloğu ~satır 496-502) ve `efloud_strategy_v1.pine` (~446-453) bu guard'ı İÇERMİYOR. Strateji `strategy.exit("TP2", limit=curTp2)` ile ters TP2'yi canlı emir yapabilir.

**Uygulama:** Her iki V1 dosyasında, TP2 (`tp2`/`curTp2`) atandıktan SONRA, `rr2` hesabından ÖNCE şunu ekle (Pine v6):
```pine
// Target-inversion guard (Python _enforce_tp2_beyond_tp1 ile birebir)
risk_ti = math.abs(price - sl)   // mevcut risk değişkenini kullan; yeniden tanımlama, varsa onu kullan
if isLong
    if tp2 <= tp1
        tp2 := math.max(tp2, tp1 + risk_ti * 0.5, price + risk_ti * 2.618)
else
    if tp2 >= tp1
        tp2 := math.min(tp2, tp1 - risk_ti * 0.5, price - risk_ti * 2.618)
```
NOT: `risk`/`price`/`sl`/`tp1` için dosyadaki mevcut değişken isimlerini kullan (yeni hesap yapma). `risk` zaten tanımlıysa onu kullan.

**Kabul:** TP1 likidite seviyesi 1.618R'den uzakken üretilen sinyalde TP2 artık TP1'den daha uzakta (LONG'ta tp2>tp1, SHORT'ta tp2<tp1). Derleme sıfır hata.

---

## S1 (KRİTİK) — minConfluence default prod ile uyumsuz

**Python/config:** `configs/config.phase2_1k.yaml:96` → `min_confluence: 50` (production-active).
**Pine V1:** `minConfluence=55` (input default).

**Uygulama:** Her iki V1 dosyasında `minConfluence` input default'unu **50** yap:
```pine
minConfluence = input.int(50, "Min Confluence Score", minval=0, maxval=100)
```
(Mevcut input satırının default'unu 55→50 değiştir; başlık/minval/maxval aynı kalsın.)

**Kabul:** Pine V1, prod ile aynı sinyal eşiğini kullanır → backtest canlıyla kıyaslanabilir.

---

## S2 (KRİTİK) — recencyBars ve minRr default'ları prod ile uyumsuz

**Python/config (prod):** `recency_bars: 40`, `min_rr: 1.8` (`config.phase2_1k.yaml:95,97`).
**Pine V1:** `recencyBars=20`, `minRr=1.5`.

**Uygulama:** Her iki V1 dosyasında input default'larını prod'a çek:
```pine
recencyBars = input.int(40, "Recency Window (bars)", minval=1)
minRr       = input.float(1.8, "Min R:R", minval=0.1, step=0.1)
```
(Başlık/minval/step aynı kalsın, sadece default 20→40 ve 1.5→1.8.)

**Kabul:** Pine V1 backtest sonuçları prod davranışıyla hizalı.

> **Önemli not:** S1+S2 ile V1 artık root `config.yaml` yerine **prod config'e** hizalanıyor. `PINE_SPEC.md`'de "V1 defaults = config.phase2_1k.yaml (production-active)" notu ekle; eski "root config / CLAUDE.md" referansını düzelt.

---

## S4 (ORTA) — Deviation TP2 clamp eksik + useIntendedDeviation default açık

**Python referansı:** `engine/signals.py` `_resolve_deviation_tp2` (satır ~75-95): deviation TP2'ye (a) karlı-taraf clamp (min_tp eşiğine), (b) collapse→2.618R fallback uygular. AMA Python'da `has_dev` pratikte ölü kod (range deviation hiç tetiklenmez — spec EK A.7 #5).

**Sorun (Pine V1):** `useIntendedDeviation=true` DEFAULT açık (Python'da ölü olan dalı canlandırıyor) + deviation TP2'ye (`rngHi`/`rngLo`) clamp YOK → clamp'siz ham range ekstremi.

**Uygulama — İKİ seçenek (Gemini birini seç, gerekçeyle):**
- **Seçenek A (Python'a tam sadakat, ÖNERİLEN):** `useIntendedDeviation` input default'unu **false** yap. Böylece Python'daki ölü-kod davranışına birebir uyulur, deviation dalı hiç çalışmaz, clamp gereksiz olur. En düşük risk.
- **Seçenek B (niyet modu korunacaksa):** default `true` kalsın AMA deviation TP2 atamasına (`tp2 := isLong ? rngHi : rngLo`) hemen sonra clamp ekle: `_resolve_deviation_tp2` mantığı (min_tp clamp + tp2 collapse→2.618R). S3 guard'ı zaten sonradan koruma sağlıyorsa minimal ek gerekebilir.

**Kabul:** Ya deviation dalı kapalı (A), ya da clamp'li (B). Hibrit (açık + clamp'siz) KALMASIN.

---

## Genel kurallar (Gemini)
1. Sadece `pine/efloud_signals_v1.pine`, `pine/efloud_strategy_v1.pine`, `pine/PINE_SPEC.md`. V2 dosyalarına dokunma.
2. Pine Script v6 zorunlu (`indicator()`/`strategy()`, `ta.*`, doğru `var`/`:=`). Legacy yok.
3. İndikatör ve strateji V1 dosyalarını SENKRON tut (aynı input isimleri/default'ları).
4. TradingView Pine Editor'da derle → `pine_get_errors` sıfır olana kadar düzelt.
5. `PINE_SPEC.md`'ye her sapma için "FIXED 2026-05-30" notu + S1/S2 için prod-config referans düzeltmesi.
6. Repaint kuralını koru: yeni kod sadece kapanmış bar / `barstate.isconfirmed`.

## Review (Opus)
Tamamlanınca Opus: (a) her 4 sapmanın kapandığını Python'a karşı doğrular, (b) V1 indikatör↔strateji senkronunu kontrol eder, (c) repaint güvenliğini teyit eder, (d) PINE_SPEC güncelliğini denetler.
