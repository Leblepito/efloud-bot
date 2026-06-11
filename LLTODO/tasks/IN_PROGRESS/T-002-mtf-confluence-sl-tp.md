# T-002: MTF Confluence + SL/TP Hesaplama

**Epic:** P-001
**Claimed by:** @hermes (2026-06-11)
**Tahmini süre:** 2-3 gün
**Bağımlılık:** T-001

## Hedef

15m + 1h confluence scoring, SL hesaplama (son 20 mum + ATR buffer), TP1 (likidite swing'leri), TP2 (range extreme / fibo) — `pine/efloud_signals.pine`'e ekle.

## Çıktılar

- [ ] Confluence scoring fonksiyonu (min threshold: 55)
- [ ] SL hesaplama: son 20 mum low/high + ATR(14)×0.5 buffer
- [ ] TP1 hesaplama: yakın HTF likidite / equal highs-lows
- [ ] TP2 hesaplama: karşı range extreme / fibo uzantısı
- [ ] SL/TP seviyelerini plot et (renkli dashed line'lar)
- [ ] PINE_SPEC.md güncelle

## Acceptance Kriterleri

- [ ] Pine Compile: sıfır hata, sıfır warning
- [ ] SL her zaman entry'nin altında (LONG) / üstünde (SHORT)
- [ ] TP1 > SL (LONG), TP1 < SL (SHORT)
- [ ] min_rr kontrolü: (TP1 - entry) / (entry - SL) ≥ 1.5
- [ ] Görsel standartlar §4a-4c'ye uygun

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | IMPL_READY | T-002 implemente edildi: confluence scoring + SL/TP + sinyal + plot. 608 satır, Pine v6. |
