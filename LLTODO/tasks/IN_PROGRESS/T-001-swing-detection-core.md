# T-001: Swing Detection + OB Core (15m + 1h bias)

**Epic:** P-001
**Claimed by:** @hermes @ 2026-06-10
**Tahmini süre:** 2-3 gün
**Bağımlılık:** —

## Hedef

`pine/efloud_signals.pine` indikatör iskeletini oluştur: 15m timeframe'de swing high/low tespiti, order block tanımlama, ve 1h bias göstergesi.

## Çıktılar

- [x] `pine/efloud_signals.pine` — INDICATOR iskeleti (v6 syntax, koyu tema palette)
- [x] `pine/PINE_SPEC.md` — Python→Pine teknik çeviri haritası (başlangıç)
- [x] Swing detection fonksiyonu: lookback=4, sol+sağ pivot (manuel)
- [x] Order Block tanımlama: 5 ardışık mum, body > 1.5× ATR(14)
- [x] 1h bias overlay: `request.security()` ile higher-TF trend yönü
- [x] Görsel çıktılar: swing label'ları, OB box'ları, 1h trend çizgisi + bias table

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
| 2026-06-10 | IMPL_READY | pine/efloud_signals.pine (259 satır, 11.9KB) + PINE_SPEC.md yazıldı. Swing manuel pivot, OB box, 1h bias table. awaiting compile-verify (G-T1 gate). Branch: feat/p001-t001-pine-indicator |
