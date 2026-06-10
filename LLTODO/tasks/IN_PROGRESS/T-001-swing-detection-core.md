# T-001: Swing Detection + OB Core (15m + 1h bias)

**Epic:** P-001
**Claimed by:** @hermes @ 2026-06-10
**Tahmini süre:** 2-3 gün
**Bağımlılık:** —

## Hedef

`pine/efloud_signals.pine` indikatör iskeletini oluştur: 15m timeframe'de swing high/low tespiti, order block tanımlama, ve 1h bias göstergesi.

## Çıktılar

- [ ] `pine/efloud_signals.pine` — INDICATOR iskeleti (v6 syntax, koyu tema palette)
- [ ] `pine/PINE_SPEC.md` — Python→Pine teknik çeviri haritası (başlangıç)
- [ ] Swing detection fonksiyonu: lookback=4, sol+sağ pivot
- [ ] Order Block tanımlama: 5 ardışık mum, body > 1.5× ATR(14)
- [ ] 1h bias overlay: `request.security()` ile higher-TF trend yönü
- [ ] Görsel çıktılar: swing label'ları, OB box'ları, 1h trend çizgisi

## Acceptance Kriterleri

- [ ] Pine Compile: sıfır hata, sıfır warning (`pine_smart_compile`)
- [ ] Repaint kontrolü: tüm referanslar `barstate.isconfirmed` veya `[1]`
- [ ] Görsel standartlar: renk paleti §4a'ya uygun
- [ ] Python parametreleriyle eşleme: PINE_SPEC.md'de belgelenmiş
- [ ] LLTODO lint: 8/8 yeşil

## Implementasyon Notları

- v6 syntax ZORUNLU: `indicator()`, `ta.atr()`, `request.security()`
- `request.security()` için `lookahead=barmerge.lookahead_off` kullan (repaint önleme)
- OB body hesaplama: `math.abs(close - open) > 1.5 * ta.atr(14)`
- Swing pivot: `ta.pivothigh(4, 4)` ve `ta.pivotlow(4, 4)` Pine'da built-in — test et
- Renkler: `#00FF88` long, `#FF4455` short, `#FFDD44` OB (80 opacity), `#CCCCCC` swing labels

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-10 | STARTED | T-001 claimed by @hermes |
