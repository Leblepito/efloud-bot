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

**Durum:** `IN_PROGRESS` — FAZ 3 (2026-06-10)
**Sonraki adım:** T-002 (MTF confluence + SL/TP) — @hermes claim edebilir

### Heartbeat

```
2026-06-10  IN_PROGRESS      @hermes  T-001 IMPL_READY: pine/efloud_signals.pine (259 satır) + PINE_SPEC.md. Branch: feat/p001-t001-pine-indicator. Swing detection (manuel pivot lb=4), OB (seq=5, body>1.5×ATR), 1h bias (EMA20 overlay). G-T1 compile gate BEKLİYOR (VPS'te TV yok).
2026-06-10  REVIEW_FIXES     @claude  Path çakışması düzeltildi: Wave-1 dosyaları pine/u2algo/ altına (mevcut SMC v2 port restore). OB 5-ardışık fidelity fix + ölü kod temizliği. Plan v1.3 (§3a path'leri güncellendi).
2026-06-10  T-001 DONE ✅    @claude  G-T1 PASS: TV Pine Editor compile 0 hata 0 marker (pine_smart_compile + pine_get_errors). T-001 → tasks/DONE/. Sıra T-002'de.
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
| FAZ 3 | Implementasyon (T-001 ✅ DONE [G-T1 PASS], T-002, T-003) | 🟡 IN_PROGRESS |
| FAZ 4 | UltraReview (UR-001 @claude) | ⬜ BEKLİYOR |
| FAZ 5 | Master merge + deploy | ⬜ BEKLİYOR |

---

## P-002: Marketing & Growth Pipeline

**Başlangıç:** 2026-06-10
**Sahip:** @hermes (v1 draft, implementasyon), @claude (UltraPlan rekonstrüksiyonu, security audit, UR-002)
**Branch:** `feat/marketing-growth-pipeline` (şemsiye — her PR kendi branch'inde)

### Durum Geçmişi

```
2026-06-10  DRAFT             @hermes  v1 draft + UltraPlan prompt yazıldı (VPS; read-only key → telegram transfer)
2026-06-11  TRANSFERRED       @claude  Dosyalar LLTODO/plans/'a işlendi; v1 orta bölümü transferde kayıp (işaretli)
2026-06-11  ULTRA_PLAN_DONE   @claude  UltraPlan rekonstrüksiyonu: 10 ground-truth + 9 gap + 15 PR (M1-M15) + security audit (S1-S7) + G1-G8 checklist
2026-06-11  REVIEW_OPEN       @claude  Plan Hermes + operatör onayına açıldı (özellikle OQ#1-#12 operatör kararları)
```

### Aktif Durum

**Durum:** `REVIEW_OPEN` — rekonstrükte plan onay bekliyor (2026-06-11)
**Plan:** `LLTODO/plans/P-002-marketing-growth-pipeline.md` (v1 backup: `.v1-hermes-draft.md`)
**Sonraki adım:** @hermes plan onayı + operatör OQ kararları → M1-M4 (Faz A) implementasyon

---

## P-003: Commercial MVP — u2algo Satış Altyapısı

**Başlangıç:** 2026-06-11
**Sahip:** @hermes (implementor/infra), @claude (architect/reviewer)
**Branch:** `claude/trading-bot-mvp-plan-l83v5s` (plan), implementasyon dalga başına ayrı branch
**Plan:** `LLTODO/plans/P-003-commercial-mvp.md`
**Dayanak:** `docs/audit/2026-06-11-commercial-mvp-gap-analysis.md`

### Durum Geçmişi

```
2026-06-11  DRAFT            @claude  Kurumsal MVP boşluk analizi + tek parça plan yazıldı (W0 legal → W1 kanıt → W2 monetizasyon → W3 müşteri deneyimi)
2026-06-11  REVIEW_OPEN      @claude  UltraReview (UR-003) için açıldı — operatör /ultrareview tetikleyecek
2026-06-11  RENUMBERED       @claude  Epic ID çakışması çözüldü: P-002→P-003, UR-002→UR-003, G-P2→G-P3 (P-002 = Marketing & Growth, Hermes scoreboard precedent'i)
```

### Aktif Durum

**Durum:** `REVIEW_OPEN` — UR-003 UltraReview bekliyor (2026-06-11)
**Sonraki adım:** Operatör `/ultrareview` çalıştırır → bulgular plana entegre → FAZ 3 implementasyon (T-010..T-019, dalga sırasıyla)

### Faz Planı

| Faz | İçerik | Durum |
|---|---|---|
| FAZ 0 | Boşluk analizi + plan yazımı | ✅ DONE (2026-06-11) |
| FAZ 1-2 | UltraReview (UR-003) + consensus/revizyon | ⬜ BEKLİYOR |
| FAZ 3 | İmplementasyon W0→W1→W2→W3 (T-010..T-019) | ⬜ BEKLİYOR |
| FAZ 4 | Dalga başına review + master merge | ⬜ BEKLİYOR |

---

### Handover Notları (Aktif)

> **@hermes için (2026-06-10):**
> 1. P-001 CONSENSUS_REACHED — plan revize edildi, review bulguları entegre.
> 2. T-001 claim et (`LLTODO/tasks/IN_PROGRESS/T-001-swing-detection-core.md`) ve implementasyona başla.
> 3. Append-only kuralına uy: STATE.md'de eski satırları silme, yeni satır ekle.
> 4. FAZ 3 bitince FAZ 4 UltraReview (UR-001) için Claude'a bildir.
