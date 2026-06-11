# T-002: MTF Confluence + SL/TP Hesaplama

**Epic:** P-001
**Claimed by:** @hermes (2026-06-11)
**Tahmini süre:** 2-3 gün
**Bağımlılık:** T-001

## Hedef

15m + 1h confluence scoring, SL hesaplama (son 20 mum + ATR buffer), TP1 (likidite swing'leri), TP2 (range extreme / fibo) — `pine/efloud_signals.pine`'e ekle.

## Çıktılar

- [x] Confluence scoring fonksiyonu (min threshold: 55) — 7-faktör, max 100
- [x] SL hesaplama: son 20 mum low/high + ATR(14)×0.5 buffer (`f_calc_sl`, %0.1 taban + 5×ATR clamp)
- [x] TP1 hesaplama: yakın HTF likidite / equal highs-lows (1h gecikmeli-pivot swing; min-RR fallback)
- [x] TP2 hesaplama: karşı range extreme / fibo uzantısı (swing range × 1.618 default)
- [x] SL/TP seviyelerini plot et (renkli dashed line'lar)
- [x] PINE_SPEC.md güncelle (Wave-1 için `pine/u2algo/WAVE1_SPEC.md` — PR #188)

## Acceptance Kriterleri

- [x] Pine Compile: sıfır hata, sıfır warning (`pine_smart_compile` + `pine_get_errors` → 0 marker, 2026-06-11 @claude, G-T2)
- [x] SL her zaman entry'nin altında (LONG) / üstünde (SHORT) — sinyal `valid` kontrolü zorunlu kılar
- [x] TP1 > SL (LONG), TP1 < SL (SHORT) — `valid`: TP1 entry'nin doğru tarafında, SL karşı tarafta
- [x] min_rr kontrolü: (TP1 - entry) / (entry - SL) ≥ 1.5 — `f_calc_tp` fallback'i min_rr altını yükseltir
- [x] Görsel standartlar §4a-4c'ye uygun (T-002 review'da doğrulandı; B2 visual_group fix dahil)

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | IMPL_READY | T-002 implemente edildi: confluence scoring + SL/TP + sinyal + plot. 608 satır, Pine v6. |
| 2026-06-11 | REVIEW_FIXES | @claude review REQUEST_CHANGES → fix: B1 repaint (1h pivot gelecek-bar → gecikmeli-pivot) + B2 visual_group forward-ref + N1 var + N3 %0.1 SL tabanı. PR #188 → master `eb5af4f`. |
| 2026-06-11 | DONE ✅ | G-T2 PASS: TradingView Pine Editor compile **0 hata, 0 marker** (pine_smart_compile + pine_get_errors). `eb5af4f` hali 2 compile hatası verdi → minimal fix (v1.1.1): (1) satır 315/317 `\` satır devamı Pine'da geçersiz → girintili satır sarma; (2) `f_calc_tp` içinde `tp1/tp2 = na` → `float tp1/tp2 = na` (tip anahtar kelimesi zorunlu). Mantık değişikliği YOK. → T-003 başlayabilir |
