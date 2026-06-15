# GÖREV B: Operatör Checklist (LS Fizibilite + Railway Env)

> **Kaynak audit:** `docs/audit/2026-06-11-lemonsqueezy-feasibility.md` (5 madde analiz).
> **Bu doküman:** 5 operatör kararı + zaman planı + W2'ye giriş gate'i.

## Fizibilite Özeti (11 Jun'dan)

| # | Madde | Durum | Aksiyon |
|---|---|---|---|
| B.1 | LS AUP (trading yazılım) | ✅ Uygun | "Analiz aracı" pozisyonu, "yatırım tavsiyesi değildir" disclaimer |
| B.2 | TR satıcı payout | ✅ Mümkün | Wise Business hesabı önerilir |
| B.3 | Tüzel kişilik | ⚠️ **OPERATÖR KARARI** | Şahıs mı, ltd şirket mi? (1 hafta) |
| B.4 | E-posta sağlayıcı | ✅ Resend önerildi | Domain + SPF/DKIM (M12'ye bağlı) |
| B.5 | Railway deploy kaynağı | ❓ **OPERATÖR CEVABI** | Hangi repo? (1 gün, kritik) |

---

## Operatör Karar Listesi

### B.3 — Tüzel kişilik kararı (1 hafta, sırası önemli)
**Sorular:**
- [ ] Şahıs şirketi mi (düşük ciroda yeterli, basit muhasebe)?
- [ ] Ltd şirket mi (vergi avantajı, daha ciddi görünüm)?
- [ ] Vergi levhası hazır mı (LS identity verification ister)?
- [ ] Wise Business hesabı açıldı mı (TR payout için)?

**Operatör kararı:** _______________ (tarih: ____-__-__)

**LS'ye etkisi:** Identity verification bu karara bağlı; hesap açılışı için vergi levhası zorunlu.

### B.5 — Deploy kaynağı teyidi (1 gün, KRİTİK)
**Sorular:**
- [ ] Railway `u2algo-site` servisi hangi repodan deploy ediliyor?
  - [ ] Bu repo (`efloud-bot/`) → `u2algo-site/` alt dizini (vendored)
  - [ ] Ayrı `u2algo-site` reposu → URL: _______________
- [ ] `railway.json` / `railway.toml` hangi repoda?
- [ ] T-010/T-011/T-016 PR'ları nereye açılacak?

**Operatör cevabı:** _______________ (tarih: ____-__-__)

**Etkisi:** GÖREV A'nın (Supabase entitlements) PR'ı doğru hedefe açılacak. Yanlış hedefe PR = merge conflict + zaman kaybı.

### B.4 — Domain + e-posta (M12 kararına bağlı)
**Sorular:**
- [ ] Domain: `ualgotrade.com` (mevcut) üzerinden mi git, yoksa ayrı `u2algo.com` mu?
  - [ ] Mevcut: `bot.ualgotrade.com` (dashboard), `ualgotrade.com` zaten alınmış
  - [ ] Yeni: `u2algo.com` (satış/marketing için ayrı) — ek maliyet
- [ ] Müşteri destek e-postası: `support@ualgotrade.com` mi, `support@u2algo.com` mu?
- [ ] Resend hesabı açıldı mı (ücretsiz tier: 100 email/gün)?

**Operatör kararı:** _______________ (tarih: ____-__-__)

### B.1 + B.2 (zaten ✅ — hatırlatma)
- **B.1**: LS ürün taslağı oluştur → "TradingView indicator — analiz aracı, yatırım tavsiyesi değildir"
- **B.2**: Wise Business hesabı aç (USD/TRY hesabı, LS → Wise → TR banka)

---

## Railway Env Placeholder (Hermes işi — 5dk)

`u2algo-site/` (veya uygun repo — B.5'e göre) `.env.example`'a eklenecek:

```bash
# Lemon Squeezy webhook secret (T-016)
# GÖREV B.6 — operatör tarafından Railway dashboard'dan manuel eklenir
# ASLA repo'ya/değer olarak commit edilmez
LEMONSQUEEZY_WEBHOOK_SECRET=

# Resend transactional email (T-016, T-019)
# B.4 kararına göre domain + API key
RESEND_API_KEY=
SUPPORT_EMAIL=support@ualgotrade.com

# Supabase service role key (T-015 entitlements write)
# T-015 implementasyonunda eklenecek
SUPABASE_SERVICE_ROLE_KEY=
```

**Önemli:** Değerler Railway dashboard'dan manuel eklenir. `.env.example` sadece KEY ADLARINI içerir.

---

## W2'ye Giriş Gate'i (UR-003 eki)

> ⚠️ **Aşağıdaki OLMADAN T-016 (LS webhook implementasyonu) BAŞLATILAMAZ:**

- [ ] B.1 (LS ürün taslağı oluşturuldu)
- [ ] B.3 (tüzel kişilik kararı verildi, vergi levhası hazır)
- [ ] TR payout rayı teyit edildi (Wise hesabı açık)
- [ ] G-P3-B5 (gelir modeli kararı — tek-seferlik vs abonelik)

G-P3-B5 operatör kararı ayrı bir gate (SCOREBOARD.md'de izleniyor).

---

## Zaman Planı (Önerilen)

| Hafta | Aksiyon | Çıktı |
|---|---|---|
| **15-21 Haziran** | B.5 (deploy kaynağı cevabı) | A/B/E PR'ları doğru hedefe açılır |
| **15-21 Haziran** | B.3 (tüzel kişilik kararı) | Vergi levhası hazır, LS'ye başvuru |
| **22-28 Haziran** | B.4 (domain kararı) | Resend hesabı + DNS ayarları |
| **29 Haz-5 Tem** | B.1 (LS ürün taslağı) | LS hesabı açık, ücretsiz indicator yayında |
| **6-12 Tem** | G-P3-B5 (gelir modeli kararı) | W2'ye girilebilir |
| **13+ Tem** | T-016 implementasyonu başlar | Webhook + onay e-postası |

---

## İlgili Dokümanlar
- Fizibilite audit: `docs/audit/2026-06-11-lemonsqueezy-feasibility.md`
- Operatör handoff: `docs/handoff/2026-06-15-hermes-backend-tasks.md` (GÖREV B bölümü)
- T-016 task: `LLTODO/tasks/BACKLOG/T-016-lemonsqueezy-webhook.md`
- P-003 plan: `LLTODO/plans/P-003-commercial-mvp.md`
