# LLTODO — Epic State

> Append-only. Her durum geçişi yeni satır olarak eklenir. Eski satır silinmez.
> Son güncelleme: 2026-06-10 @hermes

---

## P-001: u2algo Master Plan — Wave 1 TradingView (Pine Script v6)

**Başlangıç:** 2026-06-07
**Sahip:** @hermes (implementor), @claude (reviewer)
**Branch:** `feat/lltodo-p001-implement`

### Durum Geçmişi

```
2026-06-07  DRAFT            @claude  Plan yazıldı
2026-06-08  REVIEW_OPEN      @claude  R-001 (claude) + R-002 (gemini) review'a açıldı
2026-06-09  CHANGES_REQUESTED @claude  R-001 conf7: kapsam daraltma, görsel standartlar, CAC gate
2026-06-09  CHANGES_REQUESTED @gemini  R-002 conf9: gelir gate'leri, backtest validasyonu, repaint risk
2026-06-10  CONSENSUS_REACHED @hermes  İki review bulguları plana entegre edildi. Plan revize.
```

### Aktif Durum

**Durum:** `CONSENSUS_REACHED` (2026-06-10)
**Sonraki adım:** T-001 IMPL_READY → compile-verify (G-T1 gate) → T-002 başlat

### Heartbeat

```
2026-06-10  IN_PROGRESS      @hermes  T-001 IMPL_READY: pine/efloud_signals.pine (259 satır) + PINE_SPEC.md. Branch: feat/p001-t001-pine-indicator. Swing detection (manuel pivot lb=4), OB (seq=5, body>1.5×ATR), 1h bias (EMA20 overlay). G-T1 compile gate BEKLİYOR (VPS'te TV yok).
```

### Review Özeti

| Review | Reviewer | Sonuç | Confidence | Ana Bulgular |
|---|---|---|---|---|
| R-001 | @claude | CHANGES_REQUESTED | 7/10 | Kapsam daraltma (tüm MTF zincirini tek seferde değil, önce 15m+1h), görsel standartlar (renk paleti, çizgi kalınlıkları), CAC hesaplama gate'i |
| R-002 | @gemini | CHANGES_REQUESTED | 9/10 | Gelir modeli gate'i (indikatör ücretsiz, strateji premium), backtest validasyon kriterleri (min 100 trade, repaint kontrolü), OOS period zorunlu |

### Faz Planı

| Faz | İçerik | Durum |
|---|---|---|
| FAZ 0 | Spec + plan yazımı | ✅ DONE |
| FAZ 1 | External review (R-001, R-002) | ✅ DONE |
| FAZ 2 | Consensus + plan revizyonu | ✅ CONSENSUS_REACHED |
| FAZ 3 | Implementasyon (T-001 ✅ IMPL_READY, T-002, T-003) | 🟡 IN_PROGRESS |
| FAZ 4 | UltraReview (UR-001 @claude) | ⬜ BEKLİYOR |
| FAZ 5 | Master merge + deploy | ⬜ BEKLİYOR |

---

## P-002: (Gelecek — henüz açılmadı)

---

### Handover Notları (Aktif)

> **@hermes için (2026-06-10):**
> 1. P-001 CONSENSUS_REACHED — plan revize edildi, review bulguları entegre.
> 2. T-001 claim et (`LLTODO/tasks/IN_PROGRESS/T-001-swing-detection-core.md`) ve implementasyona başla.
> 3. Append-only kuralına uy: STATE.md'de eski satırları silme, yeni satır ekle.
> 4. FAZ 3 bitince FAZ 4 UltraReview (UR-001) için Claude'a bildir.
