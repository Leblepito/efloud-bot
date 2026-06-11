# 🟧 Hermes — Commercial MVP (P-003) Açık Görevler (2026-06-11)

> Hazırlayan: Claude (Architect/Review). Bitince Claude review edecek.
> Kurallar: canlı mainnet → feature-branch + PR, atomic, secrets sadece VPS/Railway,
> destructive-op yok. Bu dosyadaki görevler P-003 planının **infra ön-işleri** —
> implementasyon görevleri (T-010..T-024; istisna T-020/T-023 pre-UR-exempt) UR-003
> UltraReview onayından SONRA başlar. **UR-003 2026-06-11'de KOŞTU: 4×APPROVED_WITH_NITS,
> 0 blocker — nits plan v1.1'e entegre. Operatör merge sonrası FAZ 3 açık.**

Bağlam: P-003 "Commercial MVP" epic'i açıldı (`LLTODO/plans/P-003-commercial-mvp.md`,
durum REVIEW_OPEN). Ticari çapa: u2algo ürün hattı (TradingView indicator ücretsiz /
strategy premium). Boşluk analizi: `docs/audit/2026-06-11-commercial-mvp-gap-analysis.md`.

---

## GÖREV A — Supabase şema ön-hazırlığı (entitlements + waitlist consent)

**Durum:** P-003 W2 (T-015) ve W0 (T-011) için Supabase tarafı hazırlık gerekiyor.
Hermes'te `supabase_postgres` MCP araçları kurulu (health, list_tables,
ensure_waitlist_leads, waitlist_*).

**Yapılacak:**
1. `waitlist_leads` tablosu hâlâ hazır değilse (canlıda health check `PGRST205`
   dönüyordu) önce `ensure_waitlist_leads` ile tabloyu oluştur — JSONL fallback'teki
   kayıtları migrate etmeyi değerlendir.
2. `entitlements` tablosu için DDL taslağı hazırla (henüz UYGULAMA, taslak):
   `id, email, product, status (pending|granted|revoked), source (lemonsqueezy|manual),
   tv_username, order_ref, granted_at, created_at` + RLS (service-role-only yazma).
   **UR-003 eki:** `expires_at timestamptz NULL` kolonu da taslağa ekle — G-P3-B5 gelir-modeli
   kararı (tek-seferlik vs abonelik) ne çıkarsa çıksın şema hazır olsun; abonelikse
   cancel/expire/payment_failed event'leri T-016'da işlenecek.
3. `waitlist_leads`'e `consent boolean` + `consent_at timestamptz` kolonları için
   migration taslağı (mevcut kayıtlar `consent=null` kalır, geriye dönük varsayım yok).

**Acceptance:** waitlist tablosu canlıda çalışıyor (PGRST205 yok) + iki migration
taslağı `u2algo-site/supabase/` altında PR olarak. → Claude review.

---

## GÖREV B — Railway env hazırlığı (ödeme webhook)

**Durum:** W2 (T-016) Lemon Squeezy webhook'u `LEMONSQUEEZY_WEBHOOK_SECRET` isteyecek.

**Yapılacak:**
1. Lemon Squeezy hesabı/ürün taslağı operatörle birlikte aç (fiyat YAYINLANMAZ —
   G-P3-B2 gate'i operatör onayı ister).
2. Railway `u2algo-site` servisine `LEMONSQUEEZY_WEBHOOK_SECRET` placeholder env'ini
   ekle (değer yalnız Railway'de; repo'ya girmez).
3. Webhook URL planı: `https://u2algo-site-production.up.railway.app/api/purchase-webhook`
   — endpoint kodu T-016'da gelecek, şimdi sadece LS panel tarafını not et.

**UR-003 ekleri (fizibilite doğrulaması — W2'ye girmeden ZORUNLU):**
4. LS AUP/store-aktivasyon kontrolü: trading/finans-ilişkili ürün kabul ediliyor mu?
   Red riski varsa fallback (Paddle) değerlendirmesi not edilir.
5. Türkiye satıcı payout rayı teyidi (PayPal TR'de yok — LS'nin TR satıcıya ödeme yolu
   teyit edilmeden W2 implementasyonuna girilmez).
6. Tüzel kişilik + vergi (LS'ye hizmet ihracı faturası/KDV istisnası) → operatör-gate maddesi.
7. Transactional e-posta altyapısı: sağlayıcı seçimi + domain SPF/DKIM (M12 domain kararına
   bağımlı) — T-016 onay e-postası + T-019 support adresi bunu kullanacak.
8. Railway deploy kaynağı teyidi: u2algo-site ayrı repo mu, bu repodaki vendored `u2algo-site/`
   dizini mi deploy ediliyor? T-010/T-011/T-016 PR'ları doğru hedefe açılacak.

**Acceptance:** env hazır + LS ürün taslağı linki operatöre iletildi + fizibilite (md.4-6)
ve deploy-kaynağı (md.8) bulguları yazılı raporlandı.

---

## GÖREV C — P-001 T-002/T-003 devamı (W2'nin satış konusu)

**Durum:** P-003 W2'nin satışa açılma gate'i (G-P3-B3) P-001 T-003 backtest
validasyonuna bağlı. T-001 DONE; T-002 (MTF confluence + SL/TP) backlog'da seni bekliyor.

**Yapılacak:** Önceki handoff'taki (2026-06-10 GÖREV 1) akışla T-002'yi claim et ve
implementasyona devam et. P-003 bu hattı HIZLANDIRIR, değiştirmez.

**Acceptance:** T-002 claim + ilk implement commit. → FAZ 4 UR-001.

---

## GÖREV D — Çakışma notu: prod/master reconciliation (2026-06-10 GÖREV 4)

**Durum:** Önceki handoff'taki GÖREV 4 (prod `feat/pr1-identity-tokens` ↔ master
hizalaması) hâlâ açık. P-003 implementasyonu master'dan branch alacağı için bu
reconciliation P-003 FAZ 3'ten ÖNCE bitmeli — yoksa u2algo-site değişiklikleri
(W0/W2) prod'daki `bebcc8c` token-sync ile çakışabilir.

**Yapılacak:** GÖREV 4'ü P-003 FAZ 3 başlamadan kapat veya ayrı tutma gerekçesini
belgele.

**Acceptance:** prod↔master topolojisi net + karar belgeli.

---

## GÖREV E — Status page sağlayıcı seçimi (T-021 girdisi) *(2026-06-11 eki)*

**Durum:** W-R dalgası (T-021) public status page + harici uptime monitör istiyor.

**Yapılacak:**
1. Sağlayıcı değerlendir: UptimeRobot / BetterStack / benzeri — ücretsiz tier yeterli mi?
2. KRİTİK kısıt: probe `/healthz`'nin **JSON `status` alanını parse edebilmeli** —
   HTTP 200 + `status:"suspended"` = trading durdu (breaker), servis ayakta.
   Yalnız HTTP koduna bakan sağlayıcı YANLIŞ "operational" gösterir (T-024 kontratı).
3. Public görünürlük kapsamını operatörle netleştir (incident geçmişi kamuya açık mı?).

**Acceptance:** sağlayıcı önerisi + JSON-parse yeteneği doğrulaması operatöre iletildi.

---

## GÖREV F — Backup hedefi provizyonu (T-020 girdisi) *(2026-06-11 eki)*

**Durum:** Prod state volume'larının (`efloud_state*`, `trade_journal.jsonl`) backup'ı
SIFIR — W-R'nin en kritik işi T-020 bunun üstüne kurulacak.

**Yapılacak:**
1. Off-VPS şifreli hedef provizyon et: Hetzner Storage Box (VPS'le aynı DC avantajı)
   veya S3-uyumlu alternatif. Anahtar/credential VPS'te + **operatör password-manager'ında
   offline escrow kopyası ZORUNLU (UR-003):** VPS total-loss senaryosunda (2026-05-15 rebuild
   emsali) anahtar veriyle birlikte yok olursa şifreli backup açılamaz. Repo'ya ASLA girmez.
2. Kısıt: backup script'i canlı volume'lara **asla read-write dokunmaz** — snapshot
   `docker run --rm -v efloud_state:/src:ro ...` kalıbıyla alınır.
3. Restore tatbikatı YALNIZ scratch volume'da; restore-to-live operatör-gated.

**Acceptance:** hedef hazır + erişim test edildi (1 dosya yaz/oku/sil) + T-020'ye haber.

---

## Transfer Workflow'u (GAP9 dersi — Telegram'la dosya YOK) *(2026-06-11 eki)*

VPS deploy key read-only olduğu sürece (OQ#11 operatör kararı bekliyor):

1. Hermes: commit'leri lokal branch'e al → `git format-patch origin/master --stdout > seri.patch`
2. Transfer mesajına ekle: `git diff --stat` çıktısı + **her patch'in sha256'sı**
3. Claude: sha256 doğrula → `git am` (Hermes authorship korunur) → PR açar
4. Telegram'a dosya İÇERİĞİ yapıştırılmaz (2026-06-11'de orta bölüm kaybı yaşandı)

---

## Sahiplik Matrisi (P-002 + P-003)

| Agent | Sorumluluk |
|---|---|
| @hermes | u2algo-site/infra/VPS işleri (GÖREV A/B/E/F; T-010/T-011/T-015/T-016 site tarafı; M9/M10/M12) + **P-001 T-002/T-003 (gelir kritik yolu — içerik işlerinden ÖNCELİKLİ)** |
| @claude | Architect/review (UR-002/UR-003, dalga review'leri) + bot-repo Python (T-012/T-013/T-018 adayı) + T-020/T-023 pre-UR işleri |
| @gemini | P-003 external review (sıradaki boş ID: R-003) + frontend/test desteği |

---

### Bitince

Her görev: branch + PR (master) + test. Claude'a "review" sinyali ver.
P-003 implementasyonu (T-010..T-019 + T-021/T-022/T-024) UR-003 onayı olmadan BAŞLAMAZ;
**istisna: T-020 ve T-023 pre-UR-exempt** (CI-only / read-only-snapshot).
