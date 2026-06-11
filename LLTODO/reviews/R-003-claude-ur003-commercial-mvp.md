# R-003: P-003 UltraReview (UR-003) — @claude

**Confidence:** 8.5/10 (lens'ler: süreç 9, risk 9, iş 8, fizibilite 8)
**Sonuç:** APPROVED_WITH_NITS — 0 blocker; 14 should-fix **plan v1.1'e entegre edildi** (bu PR'da)
**Yöntem:** Lokal 4-lens adversarial review (cloud `/ultrareview` 30dk timeout — PR #175 emsali
fallback). Lens'ler: LLTODO süreç uyumu, canlı-bot risk/safety, ticari tutarlılık, teknik
fizibilite (reuse iddiaları repo ground-truth'uyla tek tek doğrulandı). Kapsam: PR #181'in
tamamı — P-003 Commercial MVP + W-R dalgası + P-002 Marketing reconcile (UR-002 işlevi dahil).

## Bulgular

### Kritik (Blocker)

YOK. Diff doğrulandı: 25 dosya, tamamı `LLTODO/` + `docs/` — kod/config/compose/.env/workflow
teması SIFIR; merge anında canlı mainnet bota hiçbir etki yok. Lint 8/8; renumber (P-002→P-003)
tam; append-only disiplini korunmuş; tüm çapraz referanslar çözülüyor.

### Önemli (Should-Fix) — TAMAMI v1.1'e entegre edildi

| # | Lens | Bulgu | Entegrasyon |
|---|---|---|---|
| 1 | risk | T-020/GÖREV F: "anahtar yalnız VPS'te" kuralı DR amacını boşa çıkarır (VPS total-loss anahtarı da götürür) | T-020 + GÖREV F'ye operatör password-manager escrow zorunluluğu |
| 2 | risk | Proof snapshot cadence/granularity sınırsız → fiilî sinyal beslemesi riski | G-P3-1'e ≥günlük cadence + günlük-kapanış granularity + yalnız kapanmış trade sınırı |
| 3 | risk | G-P3-5 ↔ T-018 config çelişkisi (root config.yaml inert, prod configs/config.phase2_1k.yaml) | G-P3-5'e açık dokunulmaz dosya listesi + root-config şema istisnası |
| 4 | iş | Gelir modeli şekli (tek-seferlik vs abonelik) tanımsız; P-001 G-B3 ile çelişki | Yeni gate G-P3-B5 (operatör kararı, W2 öncesi) + GÖREV A DDL'e expires_at |
| 5 | iş | T-016'da refund/chargeback event'leri yok → refund-sonrası-erişim-devam riski | T-016'ya order_refunded/dispute → revoked + T-017 kuyruk tetiği |
| 6 | iş | "Proof ≠ ürün" ifşası eksik; W1→W2 bağı 3 dokümanda 3 farklı | G-P3-B4'e zorunlu disclaimer + §3c duruş netleştirmesi (sert gate = G-P3-B3 backtest) |
| 7 | iş | Lemon Squeezy fizibilitesi doğrulanmadan tek ray (TR payout, trading-AUP, vergi) | GÖREV B'ye md.4-6 + §7 risk satırı + Paddle fallback notu |
| 8 | iş | Transactional e-posta altyapısı görevsiz | GÖREV B md.7 (sağlayıcı + SPF/DKIM, M12'ye bağımlı) |
| 9 | fizibilite | max_dd_pct/% equity eğrisi journal'dan baseline'sız türetilemez | T-012'ye çözüm-pinleme bölümü (baseline-equity girdisi veya R-multiple eğri) |
| 10 | fizibilite | Tek-timestamp heartbeat'ten uptime % çıkmaz; alerter≠bot canlılığı | T-014 + T-024'e healthz-türevi sampling tasarımı |
| 11 | fizibilite | Gap-analizi G4 olgusal hata: gerçek NotificationManager var, seam canlıda dolu | Audit doc'a ERRATUM + T-018'e composition kararı (channel ekleme; operatör bildirimleri korunur) |
| 12 | fizibilite | T-013 veri kaynağı pinlenmemiş (compute_summary DB-anahtarları ↔ journal alanları) | T-013'e adapter + DB-less davranış bölümü |
| 13 | fizibilite | u2algo-site kaynak-of-truth belirsiz (vendored kopya vs ayrı repo) | §3c not + GÖREV B md.8 deploy-kaynağı teyidi |
| 14 | süreç | M11 SUPERSEDED işareti P-002 §4/§5/§6'ya yayılmamış; SCOREBOARD metrik satırları üstü-çizilisiz | P-002 S2/S3/S6/G7/OQ#10/OQ#12 annotasyonları + SCOREBOARD strikethrough formatı |

### İyileştirme (Nice-to-Have) — FAZ 3'e devredilenler

- T-023 lint genişletmesi: R1 vakum fix'i (geçersiz state asla yakalanmıyor), R6'nın BACKLOG
  kartlarını da taraması, R7'nin "Toplam görev" sayısını da doğrulaması, G-P3-5 path-guard CI job'ı.
- T-021 healthz public-exposure mekaniği (port publish edilmiyor; probe için routing kararı GÖREV E'ye).
- T-017'ye entitlements ↔ TV erişim listesi periyodik drift-audit adımı.
- Satış-sonrası KPI (waitlist→paid dönüşüm, refund oranı, churn) — M15 genişletmesi veya W3.
- G-P3-B3'e P-001 G-B5 ticari performans tabanı (WR≥50%, PF≥1.5, MaxDD≤%5 OOS) referansı.
- TV vendor house-rules doğrulaması (çalışan site, açık fiyat, refund policy) — W0/T-019 eşleşmesi.
- T-023 sonrası: PR #182 merge edilince T-023 kartı DONE'a taşınır + Log satırı (claim akışı
  bypass edildi — pre-UR-exempt istisnası, kayda geçirildi).

## Kapsam Değerlendirmesi

W0→W1→W2→W3 + W-R dalga yapısı doğru; kapsam-dışı listesi (multi-tenant SaaS, API key vault,
gerçek-zamanlı sinyal, TV tam otomasyonu) 2026-05-05 roadmap kararıyla tutarlı. W-R eklemesi
"kurumsal firma" iddiasının gerçek önkoşullarını (backup, status, SLA/DR, CI) kapatıyor.

## Teknik Doğruluk

Reuse iddialarının çoğu ground-truth'la doğrulandı (routines kalıbı, compute_summary,
notification seam, server.js fallback, require_auth, healthz docstring). 4 fizibilite
düzeltmesi (#9-#12) karta işlendi — implementasyon bunlarla başlamalı.

## İş Modeli Uyumu

Kritik yol doğru: P-001 T-002→T-003 (G-P3-B3) satışın sert gate'i; takvim riski dürüstçe
kabul edilmiş. G-P3-B5 (model şekli) + LS fizibilitesi (GÖREV B md.4-6) W2 öncesi operatör
kararları olarak netleştirildi.

## Karar

**APPROVED_WITH_NITS → nits entegre → CONSENSUS_REACHED.** PR #181 (+ #182) merge edilebilir;
FAZ 3 implementasyonu merge sonrası dalga sırasıyla başlar. Satış açılışı G-P3-B2/B3/B5 +
T-022 paketi arkasında kilitli kalır (satış-öncesi ikinci UltraReview checkpoint'i korunur).
