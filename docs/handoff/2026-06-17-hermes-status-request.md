# 🟧 Hermes — Durum Raporu İsteği + State Sync (2026-06-17)

> Hazırlayan: Claude (backend orchestrator). Bu bir **DURUM RAPORU** isteğidir —
> state-sync'i oku, açık işlerini raporla. İlerlemeyi raporuna göre planlayacağız.

## State sync — ÇÖZÜLEN / tabağından kalkanlar (master = `8fb874e`)

- **T-015 entitlements — DONE ✅** (canlı doğrulandı, prod `kjaicqpqfwnfbioofdib`):
  tablo tüm kolonlarıyla (`id, email, product, status, source, tv_username, order_ref,
  granted_at, expires_at, created_at, updated_at`) + **RLS service-role-only** (enable, 0 policy)
  + status enum check (`pending|granted|revoked|expired`) + `set_updated_at` trigger. Güvenlik
  advisor entitlements'ta yalnız INFO `rls_enabled_no_policy` (= doğru tasarım), `rls_policy_always_true`
  **YOK**. **Yeniden uygulama gerekmez.**
- **T-010 legal — DONE ✅:** `terms.html` + `privacy.html` + `sitemap.xml` + `robots.txt` master'da,
  `scripts/smoke.js` compliance gate geçiyor.
- **CHoCH/BOS reconcile (launch-content §B'de sana atanmıştı) — Claude #221 ile YAPILDI.**
  `premium.html` + `quickstart.html` "CHoCH/BOS" → gerçek **Breaker Block**; quickstart 4 uydurma
  alert tipi → gerçek 2 (`u2algo SMC LONG`/`SMC SHORT`). **Senin tabağından kalktı.**
- ℹ️ `.env.supabase` (lokal) **stale**: token geçersiz (401) + yanlış proje ref (`trytjrtqdpmeekgxhhdb`,
  gerçek prod `kjaicqpqfwnfbioofdib`). Operatöre temizleme/yenileme önerildi.

## Senden rapor istediğim konular (operatör-gated kalanlar)

1. **T-016** Lemon Squeezy webhook aktivasyon (B.1-B.4 + secret): mevcut durum? Hâlâ default-OFF
   inert mi? B.1-B.4 (LS AUP / payout / legal-entity / domain) kararları bekliyor mu?
2. **T-020** backup drill (GÖREV F): VPS'te backup/restore drill koşuldu mu? PASS → kart DONE +
   `G-P3-6` açılır.
3. privacy/terms **legal-rafine** (operatör elemesi): durum?
4. Başka VPS-tarafı in-flight iş var mı?

## Bonus — Supabase güvenlik advisor bulguları (T-015 DIŞI, pre-existing — senin değerlendirmen için)

Prod advisor taramasında şunlar çıktı (entitlements TEMİZ, bunlar ayrı):
- **WARN `anon_security_definer_function_executable`:** `public.rls_auto_enable()` SECURITY DEFINER
  fonksiyonu **anon + authenticated** tarafından `/rest/v1/rpc/rls_auto_enable` ile çağrılabilir →
  privilege-escalation yüzeyi. Kasıtlı mı? Değilse `REVOKE EXECUTE` / `SECURITY INVOKER`.
- **WARN `rls_policy_always_true`:** `waitlist_leads` "Allow public insert" INSERT policy
  `WITH CHECK (true)` — public signup formu için **muhtemelen kasıtlı**; teyit et.
- **WARN `function_search_path_mutable`:** `set_updated_at()` search_path set değil — minör hardening
  (`alter function ... set search_path = ''`).

> Bunlar canlı bot davranışını etkilemiyor; değerlendirip gerekirse ayrı atomic PR. CANLI bot
> tablolarına (trades/equity/breaker_state RLS) **dokunma** — onlar kasıtlı service-role-only.

## Kurallar (değişmedi)
**G-P3-5 dokunulmaz:** bot config/compose/`.env`/`EFLOUD_*`. Yalnız ilgili yüzeye dokun, atomic,
secrets repo'ya **ASLA**. Transfer: `git format-patch origin/master --stdout` + sha256 → operatör
relay → Claude `git am` → review → PR → merge.
