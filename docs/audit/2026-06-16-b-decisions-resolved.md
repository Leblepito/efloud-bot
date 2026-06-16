# P-003 W2 — B-Decisions RESOLVED (operatör, 2026-06-16)

> Supersedes the open items in `docs/audit/2026-06-15-p003-task-b-checklist.md`.
> All **decision** gates for T-016 (Lemon Squeezy webhook activation) are now closed.
> Remaining blockers are operator **actions** (external account/domain setup), not decisions.

## Decisions (operatör kararı, 2026-06-16)

| # | Madde | KARAR | Etki / not |
|---|---|---|---|
| 1 | **Tüzel kişilik** | ✅ **Türkiye'de Anonim Şirket (A.Ş.) zaten mevcut** | LS identity verification güçlü zeminde — kayıtlı şirket + vergi levhası mevcut. Ltd/şahıs kuruluşuna gerek yok. |
| 2 | **Domain** | ✅ **u2algo.com** (ayrı marka) | Site kodu ZATEN u2algo.com varsayıyor — `SITE_URL`, canonical (index/privacy/terms), `RESEND_FROM_EMAIL=noreply@u2algo.com`, `SUPPORT_EMAIL=support@u2algo.com`. **Kod değişikliği gerekmez.** Bot dashboard ayrı kalır (`bot.ualgotrade.com`). |
| 3 | **Gelir modeli (G-P3-B5)** | ✅ **Tek-seferlik / lifetime** | `entitlements.expires_at = NULL`; webhook `order_created→pending/granted`, `order_refunded→revoked`. Subscription event handler'ları INERT iskelet kalır (gerekmez). Mevcut şema + webhook bunu zaten varsayıyor — kod değişikliği gerekmez. |
| 4 | **LS AUP** | ✅ Uygun | "Analiz aracı / TradingView indicator", "yatırım tavsiyesi değildir" disclaimer'ları terms.html + privacy.html + index.html'de mevcut. |
| 5 | **TR payout** | ✅ Mümkün | A.Ş. kurumsal Wise Business / TR banka rayı. |
| 6 | **B.5 Deploy kaynağı** | ✅ **efloud-bot reposu, `u2algo-site/` alt dizini** (vendored) | `u2algo-site/railway.json` + `nixpacks.toml` bu repoda; tek remote `Leblepito/efloud-bot`; start=`node server.js`. T-010/T-011/T-016 PR'ları zaten bu repoya açıldı (#204/#208). |

## Kalan OPERATÖR AKSİYONLARI (karar değil — gerçek dünya kurulumu)

T-016 webhook'u CANLI aktive etmeden önce:

- [ ] **Lemon Squeezy hesabı aç** (A.Ş. ile) → identity verification (vergi levhası).
- [ ] **İlk ürün oluştur:** "u2algo — TradingView indicator (analiz aracı, yatırım tavsiyesi değildir)". MVP'de ücretsiz/test ürün → sonra ücretli. Tek-seferlik fiyatlama.
- [ ] **Webhook secret al:** LS dashboard → webhook ekle → `LEMONSQUEEZY_WEBHOOK_SECRET` (Railway env'e manuel, repo'ya ASLA).
- [ ] **LS product_id → internal product** eşlemesini `server.js` `LS_PRODUCT_MAP`'e ekle (B.1 sonrası, ayrı küçük PR).
- [ ] **Payout rayı:** Wise Business (veya A.Ş. TR banka) → LS payout bağla.
- [ ] **u2algo.com domain** sahipliği + DNS (Railway custom domain) + Resend için SPF/DKIM/DMARC.
- [ ] **Resend hesabı** (transactional email) → `RESEND_API_KEY` (Railway env).
- [ ] **`SUPABASE_SERVICE_ROLE_KEY`** Railway env'de set (entitlements yazımı için; T-015 tablosu CANLI hazır).

## T-016 AKTİVASYON RUNBOOK (operatör hazır olunca)

Kod + entitlements tablosu (T-015, CANLI) HAZIR ve INERT. Aktivasyon:

1. Railway `u2algo-site` env'e ekle (dashboard, manuel — repo'ya değer girmez):
   - `LEMONSQUEEZY_WEBHOOK_SECRET=<LS panelden>`
   - `LS_WEBHOOK_ENABLED=true`
   - `SUPABASE_SERVICE_ROLE_KEY=<set değilse>`
2. `server.js` `LS_PRODUCT_MAP`'e LS `product_id` → `'wave1-premium'` eşlemesi (küçük PR, Claude review).
3. LS dashboard → webhook URL = `https://u2algo.com/api/purchase-webhook` (veya Railway URL), event'ler: `order_created`, `order_refunded`.
4. Test: LS test-mode order → webhook 200 + `entitlements` satırı `status=pending` → operatör TV invite grant (T-017 runbook `docs/runbooks/tv-access-grant.md`) → `granted`.
5. `scripts/list_pending_entitlements.py --status pending` ile kuyruğu izle.

**⚠️ Aktivasyon = CANLI ödeme alma. Operatör son onayı + LS test-mode doğrulaması olmadan production webhook açılmaz.**
