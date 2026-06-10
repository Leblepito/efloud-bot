# T-001: Swing Detection + OB Core (15m + 1h bias)

**Epic:** P-001
**Claimed by:** @hermes @ 2026-06-10
**Tahmini süre:** 2-3 gün
**Bağımlılık:** —

## Hedef

`pine/u2algo/wave1_signals.pine` indikatör iskeletini oluştur: 15m timeframe'de swing high/low tespiti, order block tanımlama, ve 1h bias göstergesi.

> ⚠️ Path düzeltmesi (Claude review): orijinal hedef `pine/efloud_signals.pine` idi,
> ama o dosya mevcut SMC v2 sadık portu (compile-verified 2026-05-30, PR #148 publish
> temeli). Wave-1 ayrı ürün → `pine/u2algo/` altına taşındı, mevcut port restore edildi.

## Çıktılar

- [x] `pine/u2algo/wave1_signals.pine` — INDICATOR iskeleti (v6 syntax, koyu tema palette)
- [x] `pine/u2algo/WAVE1_SPEC.md` — Python→Pine teknik çeviri haritası (başlangıç)
- [x] Swing detection fonksiyonu: lookback=4, sol+sağ pivot (manuel)
- [x] Order Block tanımlama: 5 ardışık mum, body > 1.5× ATR(14)
- [x] 1h bias overlay: `request.security()` ile higher-TF trend yönü
- [x] Görsel çıktılar: swing label'ları, OB box'ları, 1h trend çizgisi + bias table

## Acceptance Kriterleri

- [x] Pine Compile: sıfır hata (`pine_smart_compile` + `pine_get_errors` → 0 marker, 2026-06-10 @claude)
- [x] Repaint kontrolü: tüm referanslar `barstate.isconfirmed` veya `[1]`
- [x] Görsel standartlar: renk paleti §4a'ya uygun
- [x] Python parametreleriyle eşleme: `pine/u2algo/WAVE1_SPEC.md`'de belgelenmiş
- [x] LLTODO lint: 8/8 yeşil

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
| 2026-06-10 | REVIEW_FIXES | @claude review: (1) DOSYA ÇAKIŞMASI — efloud_signals.pine/PINE_SPEC.md mevcut SMC v2 portunu eziyordu → `pine/u2algo/wave1_signals.pine` + `WAVE1_SPEC.md`'ye taşındı, port restore; (2) OB fidelity: `cnt >= 1` → `cnt == ob_seq` (plan §2a "5 ardışık mum"); (3) ölü `ns` → persistent var (T-002 confluence); (4) kullanılmayan HTF OHLC fetch'leri kaldırıldı; (5) indicator title "u2algo SMC — Wave 1" (TV'de yayınlı portla isim çakışması önlendi) |
| 2026-06-10 | DONE ✅ | G-T1 PASS: TradingView Pine Editor compile **0 hata, 0 marker** (pine_smart_compile + pine_get_errors, BTCUSDT.P @15m). Tüm acceptance kriterleri karşılandı. → T-002 başlayabilir |
