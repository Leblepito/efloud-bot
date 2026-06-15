# 🟧 Hermes — Backend/Infra Açık Görevler (2026-06-15)

> Hazırlayan: Claude (Architect/Backend-orchestrator). Bitince Claude review edecek.
> Kurallar: canlı mainnet bot → feature-branch + PR, atomic commit, secrets sadece
> VPS `.env.production` / Railway env (repo'ya ASLA), destructive-op yok.
> Transfer: VPS deploy key read-only ise → `git format-patch` + her patch'in **sha256**'sı
> (Telegram'a dosya İÇERİĞİ yapıştırma — 2026-06-11'de orta-bölüm kaybı yaşandı).

---

## 0. Bağlam & Operatör Kararları (2026-06-15)

master tip = `eebe42b` (PR #198 merged: indicator-only ship `wave1_signals.pine` v1.2.0
+ #199 sb_vars.json gitignore fix). Bu oturumda 3 stratejik karar verildi:

1. **Premium ürün = INDICATOR** (operatör kararı). Wave-1 STRATEGY 4+ tur NO-GO
   (tradeable edge yok) → strateji redesign (Wave-2 CHoCH/BOS engine port) **düşük-öncelik
   R&D backlog**'a alındı. Ship'lenen round-6 indicator (`pine/u2algo/wave1_signals.pine`,
   render-verified) **premium ürün** olarak konumlanıyor.
   - 🔑 **W2 etkisi:** Satılacak şey artık bir **strateji script'i değil, karar-destek
     indicator'ı** (TradingView invite-only erişim). Bu, P-003 §3c'deki **G-P3-B3
     backtest gate'ini moot/yeniden-tanımlar** — indicator getiri vaadiyle satılmıyor;
     proof≠ürün disclaimer'ı (G-P3-B4) zaten kapsıyor. **W2 monetizasyon hattı AÇIK** —
     premium ürünle eşleşti, T-003'e bağımlılık kalktı.
2. **Gelir modeli ERTELENDİ** → şema **forward-compatible** olacak (`expires_at NULL`);
   tek-seferlik vs abonelik kararı T-016 webhook implementasyonundan önceye bırakıldı.
3. Gemini → entry-slippage validation backtest resume (senin işin değil; ayrı dosya).

İmplementasyon görevleri (T-010..T-024) UR-003 onaylı (4×APPROVED_WITH_NITS, 0 blocker).
Aşağıdaki görevler P-003'ün **infra ön-işleri** — `2026-06-11-hermes-commercial-mvp-tasks.md`
detaylı versiyondur; bu dosya o görevleri güncel kararlarla **re-task** eder + öncelik verir.

---

## GÖREV F — Backup hedefi provizyonu ⚠️ EN KRİTİK (T-020 girdisi)

**Neden #1:** Prod state volume backup'ı SIFIR. 2026-05-15 VPS-rebuild emsali (tüm state
kaybı) tekrarlanırsa kurtarma yok. T-020 scriptleri + runbook PR'da hazır
(`docs/runbooks/backup-restore.md`), tek eksik **off-VPS şifreli hedef**.

1. Off-VPS şifreli hedef provizyon: Hetzner Storage Box (VPS DC avantajı) veya S3-uyumlu.
2. **ESCROW ZORUNLU (UR-003):** şifreleme anahtarının offline kopyası operatör
   password-manager'ında. VPS total-loss'ta anahtar veriyle yok olursa backup açılamaz.
   Repo'ya ASLA girmez.
3. Kısıt: backup script canlı volume'lara **read-only** dokunur (`-v efloud_state:/src:ro`).
   Restore tatbikatı YALNIZ scratch volume; restore-to-live operatör-gated.

**Acceptance:** hedef hazır + erişim testi (1 dosya yaz/oku/sil) + T-020'ye haber →
Claude T-020 drill PASS işaretler → G-P3-6 açılır (ilk public proof yayını gate'i).

---

## GÖREV A — Supabase şema ön-hazırlığı (entitlements + waitlist consent)

**Karar-2 etkisi:** Şema **forward-compatible** olacak — `expires_at timestamptz NULL`
kolonu DAHIL et (tek-seferlik VE abonelik ikisini de kaldırır; kesin karar ertelendi).

1. `waitlist_leads` tablosu canlıda hazır değilse (`PGRST205`) → `ensure_waitlist_leads`
   ile oluştur; JSONL fallback kayıtlarını migrate etmeyi değerlendir.
2. `entitlements` DDL taslağı (UYGULAMA değil, taslak): `id, email, product, status
   (pending|granted|revoked), source (lemonsqueezy|manual), tv_username, order_ref,
   granted_at, created_at, expires_at timestamptz NULL` + RLS (service-role-only yazma).
   - **Not:** `product` alanı artık indicator-erişimi taşıyacak (premium = indicator).
3. `waitlist_leads`'e `consent boolean` + `consent_at timestamptz` migration taslağı
   (mevcut kayıtlar `consent=null`, geriye dönük varsayım yok).

**Acceptance:** waitlist tablosu canlıda çalışıyor + iki migration taslağı
`u2algo-site/supabase/` altında PR. → Claude review. (T-015'in temeli.)

---

## GÖREV B — Lemon Squeezy fizibilite + Railway env (W2 ön-koşulu, ZORUNLU)

**Karar-1 etkisi:** Satılan ürün artık **indicator** (dijital araç/decision-support) —
"trading strategy"den **AUP-açısından daha güvenli**; LS AUP reddi riski düşer. Yine de
teyit ZORUNLU (W2'ye girmeden):

1. LS AUP/store-aktivasyon: trading-indicator (dijital ürün) kabul ediliyor mu? Red
   riskinde fallback (Paddle) not.
2. Türkiye satıcı **payout rayı** teyidi (LS → TR satıcıya ödeme yolu).
3. Tüzel kişilik + vergi (hizmet ihracı faturası/KDV istisnası) → operatör-gate maddesi.
4. **Transactional e-posta altyapısı:** sağlayıcı seçimi + domain SPF/DKIM (M12 domain
   kararına bağımlı). T-016 onay e-postası + T-019 support adresi bunu kullanacak.
5. **Deploy kaynağı teyidi:** u2algo-site ayrı repo mu, bu repodaki vendored
   `u2algo-site/` dizini mi Railway'e deploy ediliyor? T-010/T-011/T-016 PR'ları doğru
   hedefe açılacak (yanlış repoya açılırsa deploy'a yansımaz).
6. Railway `u2algo-site` servisine `LEMONSQUEEZY_WEBHOOK_SECRET` placeholder env (değer
   yalnız Railway'de). Webhook URL planı: `…/api/purchase-webhook` (kod T-016'da).

**Acceptance:** fizibilite (1-4) + deploy-kaynağı (5) **yazılı rapor** + env hazır.
Teyit olmadan W2 (T-015/T-016) implementasyonuna GİRİLMEZ.

---

## GÖREV E — Status page sağlayıcı seçimi (T-021 girdisi)

1. Sağlayıcı: UptimeRobot / BetterStack / benzeri — ücretsiz tier yeterli mi?
2. **KRİTİK kısıt:** probe `/healthz`'nin JSON `status` alanını **parse edebilmeli** —
   HTTP 200 + `status:"suspended"` = trading durdu (breaker) ama servis ayakta. Yalnız
   HTTP koduna bakan sağlayıcı YANLIŞ "operational" gösterir (T-024 healthz-contract.md).
3. Public görünürlük kapsamı operatörle netleş (incident geçmişi kamuya açık mı?).

**Acceptance:** sağlayıcı önerisi + JSON-parse yeteneği doğrulaması → operatöre/Claude'a.
(Status page'in kendi frontend sayfası başka Claude oturumunda — sen sadece sağlayıcı/
monitör infra'sını seç; seam'i PR notunda belirt.)

---

## GÖREV D — prod ↔ master reconciliation (W2 PR'larından ÖNCE)

**Durum:** prod = `feat/pr1-identity-tokens` (+fix), master'dan çatallı. W0/W2 u2algo-site
değişiklikleri prod'daki token-sync ile çakışabilir. **Operatör-gated** (canlı hizalama).

**Yapılacak:** prod↔master topolojisini netleştir; W2 site PR'ları açılmadan
reconciliation planını belgele VEYA ayrı-tutma gerekçesini yaz. Canlı config/compose
DOKUNULMAZ (`configs/config.phase2_1k.yaml`, `docker-compose.prod.yml`, `.env*`).

**Acceptance:** topoloji + karar belgeli → Claude/operatör onayı.

---

## Öncelik Sırası

1. **GÖREV F** (backup — kritik, T-020 drill'i açar)
2. **GÖREV A** + **GÖREV B** (paralel — W2 temelini ve fizibiliteyi kurar)
3. **GÖREV E** (status sağlayıcı)
4. **GÖREV D** (operatör-gated, W2 PR'larından önce)

### Bitince
Her görev: branch + PR (master base) + test/rapor. Claude'a "review" sinyali ver.
W2 implementasyonu (T-015/T-016/T-017) GÖREV A+B teyitlerinden sonra başlar.
