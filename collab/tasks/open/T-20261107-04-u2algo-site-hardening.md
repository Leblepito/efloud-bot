---
id: T-20261107-04
title: u2algo-site — statik servis allowlist, waitlist rate-limit, webhook body tavanı
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: T-20261106-06
created: 2026-11-07
touches_live: false
---

## Amaç
Güvenlik denetimi (T-20261106-06) fix PR'ı #2. `u2algo-site/server.js` (u2algo.com, Railway)
için internete açık yüzeyi daraltır. Trading koduna dokunmaz.

## Değişiklik
1. **Statik servis allowlist** — yalnız kökteki `*.html`, `favicon.ico`, `robots.txt`,
   `sitemap.xml`, `updates.json`, `premium_proof.json` ve `brand/`, `assets/`,
   `brand-kit/assets/` + yalnız `brand-kit/css/*.css` servis edilir. Diğer her şey (server kaynağı,
   package/config dosyaları, `scripts/`, `supabase/`, `web/`, dotfile'lar, `data/` altındaki
   waitlist DB-fallback'i) bilinmeyen yol gibi `index.html`'e düşer. Kök sınırı kontrolü
   `root + path.sep` ile düzeltildi.
2. **Waitlist rate-limit** — istemci başına 5 / 10 dk + global 200 / 10 dk → 429.
3. **Purchase webhook** — ham gövde 64 KB tavanı (aşan kısım tamponlanmaz, 413);
   500 yanıtında iç hata mesajı artık dönmüyor.

Bilinçli olarak değiştirilmeyen: waitlist fallback yolu (`data/waitlist_leads.jsonl`,
CLAUDE.md'de belgeli) — allowlist servis edilmesini engelliyor.

## Beklenen çıktı (Definition of Done)
- [x] Gerçek sunucuyu başlatan HTTP entegrasyon testi (`scripts/test_server_http.js`) — önce 17 FAIL
  (yerelde kaydedilen e-posta `/data/waitlist_leads.jsonl`'den indirilebiliyordu), sonra ALL PASS
- [x] Mevcut `test_consent_and_webhook.js` 15/15, `smoke.js` (Railway build gate) geçer
- [x] Sitemap + iç bağlantı yollarının hepsi allowlist'te
- [x] Review (security-reviewer: APPROVE_WITH_NITS — allowlist bypass yok, gereken asset engellenmiyor; nit'ler uygulandı: brand-kit/css yalnız .css, ölü `WAITLIST_MAX_TRACKED` kaldırıldı, testlere `%5c`/çift-kodlama/sahte-XFF/gerçek-bayt kontrolleri eklendi)

## Kısıtlar
- Yalnız `u2algo-site/server.js`, `u2algo-site/package.json` (`test` script), 2 yeni test dosyası, collab dosyaları.
- Not: CI site testlerini koşmuyor (yalnız Railway build'i `smoke`); `npm test` yerelde/elle.

## Log
- 2026-11-07 claude-code: RED 17 → GREEN; consent/webhook 15/15; smoke OK.
- 2026-11-07 claude-code: review nit'leri → `test_server_http.js` 45/45 PASS.
- Deploy sonrası doğrula: Railway edge'i `X-Forwarded-For`'a istemci IP'sini SAĞDAN ekliyor mu (eklemiyorsa limit tüm siteye 5/10dk olur); `/.well-known/*` artık servis edilmiyor (Railway TLS'i etkilemez).
- Takip (NIT, engelleyici değil): webhook'ta `content-length` ön-kontrolü + erken 413.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
