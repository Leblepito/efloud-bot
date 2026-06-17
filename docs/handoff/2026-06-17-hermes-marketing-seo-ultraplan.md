# Hermes Handoff — u2algo Marketing + SEO Ultraplan (P-002.5 Growth Layer)

| Field | Value |
|---|---|
| Date | 2026-06-17 |
| From | @claude (orchestration/review/Pine/risk) |
| To | @hermes (impl/backend/content ops, VPS) |
| Epic | P-002.5 "Manus+Higgsfield Growth Layer" |
| Full spec | `docs/superpowers/specs/2026-06-17-u2algo-marketing-seo-ultraplan-design.md` (READ THIS FIRST — 63 tasks, 6 depts, 21 CRIT/HIGH resolutions, phase gates) |
| Your queued tasks | **26 @hermes tasks** across 4 phases |
| Branch convention | `feat/p0025-<task-id>-<slug>` per task; doc-only PRs may batch |

---

## 1. Mission (oku, sonra spec'e geç)

u2algo, ücretsiz TradingView SMC indikatörünü tepe-huni varlığı yapan **EN-first global** bir content + SEO büyüme hunisi kurar: content → u2algo.com → waitlist → 90-gün canlı kanıt → premium. HYBRID bütçe (Higgsfield PAID, Manus+X FREE-start), tüm çıktı **additive · flag-OFF default · draft-only · `content_compliance.py`+disclaimer-gated · conservative-proof (90-güne kadar SHAPE+aggregate% only, sıfır $)** ve **canlı MAINNET trade path'e (`configs/config.phase2_1k.yaml`, `dry_run:false`) sıfır dokunuş**. İş 4 faza bölünür — Foundation / QuickWins / ContentMachine / Scale — aralarında HARD gate'ler (CAC gate, 90-gün proof gate, operatör sign-off). Full mimari, dept tabloları, governance çözümleri ve ground-truth düzeltmeleri spec dosyasındadır. **Bu handoff yalnızca SENİN (@hermes) kuyruğun + protokoldür.** @claude (SEO-1/2/5/6/8, CON-1..7/9/10, SD-1/2/7, WEB-1/4/7/9/10, CMP-1/2/6/8/9, GROW-1/5/7/8/9, PROD-0) ve @operator (bloklar) ayrı çalışır.

---

## 2. Model-to-Model Transfer Protocol (DEĞİŞMEZ — Telegram BANNED)

Her @hermes işi şu akışla teslim edilir. Telegram dosya transferi YASAK (geçmişte patch'leri bozdu).

```
VPS (Hermes)                          Local (Claude)
────────────                          ──────────────
1. work on isolated branch
2. git format-patch --stdout \
     origin/master..HEAD > NNNN.patch
3. sha256sum NNNN.patch  ───────────► (sha paste edilir)
4. scp NNNN.patch  local:/tmp/  ────►
                                       5. sha256sum /tmp/NNNN.patch
                                          → MUST match Hermes's sha (mismatch=abort, re-scp)
                                       6. git worktree add /tmp/wt-<task> -b review/<task> origin/master
                                       7. cd /tmp/wt-<task> && git am --3way /tmp/NNNN.patch
                                       8. Claude review (see §5)
                                       9. PASS → push + PR → master ; FAIL → fix-notes back to Hermes
```

KURALLAR:
- `git format-patch` kullan (raw diff DEĞİL) — commit mesajı + author + sırayı korur.
- sha256 **her iki tarafta** doğrulanır; eşleşmezse uygula**MA**, yeniden scp.
- Çok-commit'li iş → `git format-patch -N` ile numaralı seri; sırayla `git am`.
- Çakışma olursa `--3way` resolve; origin/master = source of truth.
- `git add -A` YASAK (LLTODO append-only kuralı); spesifik dosya stage et.
- İki AI oturumu aynı repo'da: branch state repo-global → kendi izole worktree'nde kal, origin/PR'ı kaynak-of-truth tut, destructive-op YOK.

---

## 3. Prioritized @hermes Task Queue (dependency order, by phase)

Legend: **[EXEMPT]** = doc/runbook/infra-only, pre-UltraReview-exempt (yine de Claude göz-geçirir ama risk-ops gerekmez). **[REVIEW]** = kod/site PR → Claude review zorunlu, risk paths varsa risk-ops escalation. Her task'tan önce §6 invariant checklist'ini kendin doğrula.

> ⚠️ **Foundation bloklarını (SITE-SOT, MANUS-CAP, LS-FLIP, PROD-0, CMP-3) GEÇMEDEN ilgili task'lara başlama** — §4'e bak. Özellikle **CMP-3 her EN-copy task'ının HARD blocker'ı**.

---

### PHASE 1 — Foundation

#### CMP-3 — Extend `content_compliance.py`: BANNED_EN + price-whitelist + testnet-label (TDD)  **[REVIEW]**
- **Why first:** EN-first pivot'un en yüksek-değer compliance task'ı. **Bugün gate TR-only** — empirik doğrulandı: `find_violations('Guaranteed profit, risk-free returns, double your money')` → `[]` (PASS = leak). Bu, SD-3/SD-4/CON-8/GROW-2 dahil her EN-copy task'ını bloklar. **Foundation'a çekildi (QuickWins değil).**
- **Files:** `scripts/content_compliance.py` (EXTEND, don't rebuild) + `backend/tests/test_content_compliance.py`
- **Do:**
  1. `BANNED_EN_PHRASES` ekle — **CMP-2 matrisinin tamamı** (≥12: guaranteed profit, risk-free / risk free, no loss / no-loss, can't lose, double your money, passive income machine, signal and earn, get rich, + EN %-return-promise). `_norm()` ile aynı normalizasyon, `banned_phrase` tag.
  2. `PRICE_WHITELIST` ekle — tek ürün-fiyat token'ı (`$39 lifetime` / one-time / tek seferlik) GEÇER, ama per-trade/account-balance/$-PnL hâlâ REDDEDİLİR. (Verified: `find_violations('Founding member - $39 lifetime')` → bugün `['absolute_money']` = false-reject.)
  3. `unlabeled_simulation` tag — metin backtest/shadow/testnet/simulated/replay içerip `[BACKTEST]`/`[TESTNET]`/`[SIMULATED]` label token'ı yoksa → violation. EN+TR keyword.
  4. **Optional `lang` param SADECE `find_violations()`'a.** `has_disclaimer()`'a DOKUNMA — zaten `lang='en'/'both'` destekliyor (verified lines 85-92); değiştirirsen CMP-1'in COMPLIANCE_EN byte-match'ini kırarsın.
- **Acceptance:** Yeni testler: EN banned reddedilir (her phrase için per-phrase regression), TR hâlâ reddedilir, `lang='both'` iki listeyi de koşar, `$39 lifetime` GEÇER, `$250 trade`/`balance $1000` REDDEDİLİR, simulated-without-label → `unlabeled_simulation`, clean labeled text geçer. Full suite green CI py3.11. **Mevcut tag'lar değişmez (backward-compat regression test).**
- **Safety:** scripts-only/additive, flag-flip yok, pure-function (no I/O/network/secrets), backward-compatible = clean revert. Hermes→Claude format-patch+sha256.

#### WEB-2 — Stand up u2algo.com on Railway + DNS + TLS  **[REVIEW]** (runbook [EXEMPT], env/binding op-gated)
- **Blocked by:** SITE-SOT (operatör). **Tek gerçek marketing prerequisite** — sıfır trade-path coupling.
- **Files:** `docs/runbooks/u2algo-com-binding.md` (yeni) + Railway env `SITE_URL=https://u2algo.com` (op uygular DNS)
- **Do:** apex (ALIAS/ANAME veya Railway A/AAAA) + www CNAME → mevcut `u2algo-site` Railway servisi; otomatik TLS; www→apex 301; curl/Lighthouse smoke. **Operatör DNS kaydını oluşturur; sen tam kayıt değerlerini + doğrulama komutlarını verirsin.**
- **Acceptance:** `https://u2algo.com/` 200 + valid TLS; www 301→apex; sitemap.xml+robots.txt apex'te ulaşılır; Railway `SITE_URL` doğrulanmış; served HTML'de `railway.app` leak yok (grep). Runbook merged.
- **Safety:** Marketing servisi botla AYRI Railway servisi = sıfır trade-path. `SITE_URL` non-secret config. Clean revert = custom domain kaldır.

#### GROW-2 — UTM scheme + waitlist source capture (server.js:280 fix)  **[REVIEW]**
- **Blocked by:** GROW-1 (claude doc), **WEB-6** (event layer owner — consume etme, re-implement etme).
- **Why:** `server.js` `source`'u hardcode `'u2algo-site'` yazıyor (verified :280) → kanal atribüsyonu YOK → CAC uncomputable. Bu gerçek bug.
- **Files:** `u2algo-site/index.html` (waitlist form: gizli alanlar) + `u2algo-site/server.js` (POST /api/waitlist persist) + Supabase additive nullable column `landing_ref`
- **Do:** UTM convention (`utm_source=x|youtube|telegram|tradingview|manus`, `utm_medium=organic|paid`, `utm_campaign=<slug>`, `utm_content=<variant|lang>`); first-party snippet UTM+referrer'ı gizli form alanlarına okur (3rd-party tracker YOK, KVKK-friendly); server.js gerçek `source/utm`'i `waitlist_leads.source`'a yazar (hardcoded literal yerine) + nullable `landing_ref`. **3-fallback (Supabase REST→PG→JSONL) + T-011 consent gate AYNEN korunur.**
- **Acceptance:** `?utm_source=x&utm_medium=organic&utm_content=en`'den gelen signup `source='x'` ile düşer; consent gate hâlâ `consent!=true` reddeder; 3 fallback da 200; mevcut server.js test pattern green; secret-scan green; migration additive (nullable, default eski satırları korur). **Supabase MCP ile prod `kjaicqpqfwnfbioofdib` waitlist_leads'e additive nullable column'un RLS/migration conflict çıkarmadığını DOĞRULA.**
- **Safety:** u2algo-site only; sıfır efloud-bot trade-path. Additive nullable + default-preserving = clean revert. First-party only, consent gate korunur. Hermes→Claude format-patch+sha256.

---

### PHASE 2 — QuickWins (thin spine that proves the funnel)

#### WEB-5 — Analytics Plausible + GA4 consent-gated loader (flag-OFF)  **[REVIEW]**  ← *SOLE analytics owner*
- **Blocked by:** WEB-2. **Bu katmanın TEK sahibi sensin** — GROW-3 buraya consume eder, SD-9 buraya bağlanır. Çift-planlama yok.
- **Files:** `u2algo-site/` 5 sayfa (index/premium/quickstart/privacy/terms.html) `<head>` + `privacy.html` disclosure
- **Do:** Plausible (cookieless EU) primary + GA4 (gtag) secondary; **`ANALYTICS_ENABLED` env flag default-OFF**; GA4 SADECE consent sonrası yüklenir (privacy.html T-011 KVKK consent click); ID'ler env-driven (literal değil); privacy.html her iki tool'u + opt-out'u açıklar.
- **Acceptance:** Flag-OFF iken sıfır analytics isteği (verified page load); GA4 consent-öncesi gtag network call YOK; ID'ler env'den; `u2algo-site/scripts/smoke.js` green.
- **Safety:** Marketing site only; authed dashboard hariç + noindex kalır. Flag-OFF default = clean revert. GA4 post-consent (T-011 KVKK). ID'ler env, repo literal'da değil. INV-1 marketing-only.

#### WEB-6 — Funnel events incl. checkout/purchase  **[REVIEW]**
- **Blocked by:** WEB-5. **GROW-2 + SD-9 buna depend eder (consumer).** T-015/T-016 orphan'ını kapatır.
- **Files:** `u2algo-site/assets/analytics.js` (yeni, flag-OFF no-op) + `docs/marketing/funnel-events.md` + event hook'ları 5 sayfada
- **Do:** 4-stage funnel named events (Plausible goals + GA4 events): `visit` (auto), `cta_click` (waitlist/premium CTA), `waitlist_submit` (success path, network call'da DEĞİL — double-count önle), `proof_view` (premium_proof block viewport'a girince). **+ `checkout_click` + `purchase_complete` (server.js:247 LS webhook'u server-side join et)** — DevEx/recon HIGH, T-015/T-016 orphan fix. `analytics.js` flag-OFF iken no-op.
- **Acceptance:** Tüm 6 event flag-ON manuel browser testinde doğru fire (Plausible realtime + GA4 DebugView); `waitlist_submit` success başına tam 1× (no double-count); `analytics.js` flag-OFF no-op; `funnel-events.md` merged event dictionary ile; smoke.js green.
- **Safety:** Events `ANALYTICS_ENABLED` arkasında, additive helper, clean revert. Read-only telemetry, publish path yok. `proof_view` engagement izler, conservative %-only proof içeriğini değiştirmez.

#### WEB-3a — Webhook URL + waitlist origin rebind  **[REVIEW]**
- **Blocked by:** WEB-2, **LS-FLIP (operatör `LS_WEBHOOK_ENABLED=true` + LS test-purchase)**. ⚠️ Webhook bugün default-INERT (verified 503 `disabled_by_config`); operatör flip etmeden acceptance geçemez.
- **Files:** `docs/runbooks/integration-rebind.md` (yeni, 3a slice) + Lemon Squeezy dashboard webhook URL (op) + re-run `u2algo-site/scripts/test_consent_and_webhook.js`
- **Do:** LS webhook URL → `https://u2algo.com/api/purchase-webhook` (server.js:247 HMAC endpoint); `LEMONSQUEEZY_WEBHOOK_SECRET` HMAC path hâlâ bad-sig'de 401 döner doğrula; Supabase REST origin host-agnostic onayla, yeni apex Origin'den waitlist POST CORS doğrula.
- **Acceptance:** LS webhook u2algo.com/api/purchase-webhook'a fire eder + valid-sig accept + invalid-sig 401 loglar (test_consent_and_webhook.js green); waitlist POST yeni apex'ten persist (200). Runbook merged.
- **Safety:** `LEMONSQUEEZY_WEBHOOK_SECRET` VPS/Railway env-only, repo'da asla — sadece key NAME'leri. server.js (marketing) only, bot engine yok. Customer-protection: silent webhook break = müşteri öder entitlement almaz → LS test-purchase ŞART.

#### WEB-3b — Email domain auth SPF/DKIM/DMARC + live send  **[REVIEW]** (runbook [EXEMPT], DNS op-gated)
- **Blocked by:** WEB-2. (WEB-3a'dan AYRI — yeni-domain email deliverability "rebind" değil, çok-günlük DNS+warmup.)
- **Files:** `docs/runbooks/integration-rebind.md` (3b slice) + DNS TXT set (op uygular) + Railway `RESEND_FROM_EMAIL=noreply@u2algo.com` `SUPPORT_EMAIL=support@u2algo.com` `DASHBOARD_URL=https://bot.u2algo.com`
- **Do:** u2algo.com için SPF+DKIM+DMARC TXT kayıt seti (Manus.im registrar'da, op); **canlı test-send Gmail/Outlook'a (sadece mail-tester değil)**; T-016 transactional email (confirmation) + T-019 support gönderebilir hale gelir.
- **Acceptance:** SPF+DKIM+DMARC published + mail-tester pass + **gerçek inbox placement (Gmail/Outlook live send)**; `DASHBOARD_URL=https://bot.u2algo.com` Railway'de. **T-016 email go-live bu task'a gate'lenir** (WEB-3a cutover'a değil).
- **Safety:** `RESEND_API_KEY` VPS/Railway env-only. No auto-publish; email = transactional. DNS TXT public by design.

#### WEB-3c — Harden /api/waitlist (CORS + rate-limit + honeypot)  **[REVIEW]**
- **Blocked by:** WEB-2. (CSO MED — CAC atribüsyon bütünlüğünü korur.)
- **Files:** `u2algo-site/server.js` (/api/waitlist CORS + rate-limit + honeypot)
- **Do:** `access-control-allow-origin` wildcard `*` → bilinen apex'lere kısıtla SADECE /api/waitlist için (webhook server-to-server kalır); per-IP token-bucket rate-limit; honeypot/timestamp alan; server-side referer sanity bound (GROW-2 utm_source client-spoofable).
- **Acceptance:** /api/waitlist sadece bilinen apex Origin kabul; rate-limit aktif; honeypot reddeder; webhook etkilenmez (HMAC korunur). smoke.js green.
- **Safety:** Marketing server.js only, trade-path yok. Additive, clean revert. CAC-data integrity hardening.

#### WEB-8 — Rebind STATUS_PAGE_URL + uptime monitor  **[REVIEW]** (runbook [EXEMPT])
- **Blocked by:** WEB-3a, WEB-4 (op-gated staging).
- **Files:** `docs/runbooks/uptime-monitor.md` (yeni) + `u2algo-site/.env.example` `STATUS_PAGE_URL` default + monitor config
- **Do:** Uptime monitor target → `bot.u2algo.com/healthz` (prod) + ayrı staging probe `bot.ualgotrade.com/healthz`; **healthz JSON `status` alanını parse et (T-024 contract)** — 503 breaker-state'i hard-down false-alarm sayma; `.env.example` u2algo-branded status page.
- **Acceptance:** Monitor prod+staging healthz prob eder; `STATUS_PAGE_URL` u2algo-branded; 200-healthy vs 503-breaker doğru ayrılır (bilinen breaker-open'da false page YOK); .env.example güncel; runbook merged.
- **Safety:** Monitor SADECE /healthz READ eder, bota yazmaz; breaker/guard dokunulmaz. UptimeRobot/statuspage key env-only. T-024 healthz contract'a saygı (operatör-gated 503 false alarm değil).

#### CMP-5 — Wire disclaimer library into live pages + risk-disclosure.html  **[REVIEW]**
- **Blocked by:** CMP-1 (claude doc). **PR body canonical Railway source belirtmeli (SITE-SOT).** Operatör publish sign-off (G-P3-B2/B4).
- **Files:** `u2algo-site/{index,premium,quickstart,terms,privacy}.html` + yeni `u2algo-site/risk-disclosure.html` + footer + `sitemap.xml`
- **Do:** premium.html+quickstart.html her biri NFA+Risk+Proof≠Product (G-P3-B4) blokları taşır; index.html'e EN risk bloğu ekle (mevcut TR'yi koru); terms/privacy A.S. jurisdiction note adlandırır; eksik `risk-disclosure.html` oluştur + footer+sitemap+robots'a bağla. **Disclaimer string'leri CMP-1 library'ye fidelity** — live drift'i (`Yatırım tavsiyesi değildir` short-form ≠ COMPLIANCE_TR long-form) CMP-1 reconcile kararına göre çöz.
- **Acceptance:** premium+quickstart NFA+Risk+Proof≠Product render; risk-disclosure.html oluşturuldu+footer+sitemap+robots-allowed; EN risk bloğu index'te; terms/privacy A.S. note; PR body canonical source + two-copy sync. @claude disclaimer-text fidelity review; @operator publish sign-off.
- **Safety:** Static HTML only, ayrı u2algo-site repo, sıfır trade-path. Draft PR → operatör sign-off before publish (HARD-3/6). HTML'de secret yok.

#### SD-3 — Manus REST client + IG/FB templates (fail-safe, flag-OFF)  **[REVIEW]**
- **Blocked by:** SD-2 (claude doc), **MANUS-CAP (operatör — Manus auto-publish/auto-head + free-tier doğrulanmadan başlama)**.
- **Files:** `backend/social/manus_client.py` (yeni) + `backend/social/templates/` (yeni dir — IG post/carousel/FB post/Reel Pydantic schemas) + tests
- **Do:** `manus_client.py` fail-safe: `MANUS_API_KEY` yoksa hard no-op (None, sıfır HTTP) — `content_jobs.py _enabled()` disiplini. `backend/social/templates/` 4 Pydantic schema, her biri zorunlu disclaimer alanı + `content_compliance.py` validation. Submit = Manus'ta DRAFT; KODDA publish call YOK. (Reuse `docs/handoff/2026-05-31_manus-connectors-task-distribution.md` Lanes E/F, manual-gated.)
- **Acceptance:** key-absent → no-op test green; schemas banned-phrase/$ payload'ı content_compliance ile reddeder (hermetik unit test); auto-publish path YOK (grep `publish`/`post-live` → sadece draft-queue); `backend/social/templates/` 4 schema ile; full suite green py3.11.
- **Safety:** Additive `backend/social/` only; engine/safety/lifecycle/order/breaker dokunulmaz. Flag-OFF (no key = no-op). Draft-only. `MANUS_API_KEY` VPS .env-only; secret-scan green. Her template compliance+disclaimer-gated.

#### SD-4 — X build-in-public draft→approve→manual  **[REVIEW]**
- **Blocked by:** SD-3. (M5 result-emitter named upstream dep — repurpose-from-signal yolu.)
- **Files:** `backend/social/templates/x_thread.py` (yeni) + draft generator + `state/social_drafts/x/*.json`
- **Do:** X lane xurl runbook üstüne (M1); `x_thread.py` 4-pillar EN thread skeletons; draft generator `content_jobs.py` event'lerinden çeker (CLOSED-trade aggregate event → build-in-public thread, **per-trade entry/SL/TP SIZINTI YOK** — telegram_notifier.py aggregate-only kuralı). Çıktı `state/social_drafts/x/`; Hermes/operatör review → MANUEL post. İlk 10 EN draft seed. (M13 implementasyonu.)
- **Acceptance:** 10 EN draft thread `state/social_drafts/x/`'e; her biri content_compliance geçer (disclaimer, no $, no perf-% promise); repurpose-from-signal SADECE aggregate count/win-rate/R:R sızdırır (test assert); auto-post code path YOK (manuel/xurl-after-signoff); **X free tier'da SADECE manual-post (xurl write-automation YOK — budget MED)**; regression suite green.
- **Safety:** `content_jobs.py` emitter (flag-OFF) read-only okur; trade path'e yazmaz. Draft-queue file only. Repurpose aggregate-only (signal-service guard P-003 2b). xurl creds VPS .env-only. Thread templates $ yasak.

#### SD-5 — Telegram community + snapshot (separate customer token)  **[REVIEW]**
- **Blocked by:** SD-2 (claude doc).
- **Files:** `scripts/routines/telegram_digest.py` (yeni) + `docs/marketing/telegram-community.md` (yeni)
- **Do:** Mevcut `engine/notifications/telegram_notifier.py` (T-018) aktive et: günlük routine aggregate CLOSED-trade digest (count, win-rate, aggregate return, equity SHAPE) kurar + notifier çağırır. **AYRI `EFLOUD_CUSTOMER_TG_*` token/channel — ASLA operatör alerter `EFLOUD_TELEGRAM_*` / ops/alerter.** Double-gated: `notifications.telegram.enabled` (default False) AND customer creds present, yoksa hard no-op. + community-growth playbook (pinned welcome EN, waitlist CTA, weekly snapshot cadence, anti-signal-service kuralları). (M8+T-018 connect.)
- **Acceptance:** `telegram_digest.py` aggregate-only digest (no per-trade entry/SL/TP, no $) kurar + flag-OFF/creds-missing'de hard no-op (**regression test: operatör alerter ops/alerter yapısal olarak DOKUNULMAMIŞ — G-P3-3**); digest content_compliance geçer + disclaimer; playbook present (EN-first, waitlist CTA, signal-service guard); full suite green.
- **Safety:** Additive `scripts/routines/` + mevcut telegram_notifier.py; ASLA ops/alerter dokunmaz — ayrı `EFLOUD_CUSTOMER_TG_*` token/channel. Double-gated default-OFF (G-P3-3 regression). Aggregate/delayed only. Customer TG token VPS .env-only. Digest'te $ yok.

#### SD-8 — Manual-approval queue (no auto-publish)  **[REVIEW]**
- **Blocked by:** SD-3. **Tüm kanalların (SD-3/4/5/6) tek sink'i.** Governance CRIT/HIGH: approve action HARD compliance gate.
- **Files:** `scripts/social_queue.py` (yeni) + `state/social_drafts/<channel>/<id>.json` store + `docs/runbooks/social-approval-queue.md`
- **Do:** Flat-file draft store `status (draft|approved|posted|rejected)` + compliance-gate result snapshot. `social_queue.py` CLI: list pending / show / approve (reviewer kaydeder) / reject. **Approve = HUMAN action; posting hâlâ manuel.** Hiçbir kod draft'ı otomatik `posted`'a geçirmez. **`approve` action HARD-calls `find_violations()==[]` AND `has_disclaimer(<lang>)` — reject not warn** (advisory değil, mandatory).
- **Acceptance:** CLI list/show/approve/reject; **draft hiçbir code path'ten `posted`'a geçemez (test assert no auto-transition)**; her draft compliance snapshot ile saklanır; rejected asla emit edilmez; approve compliance-fail'de reject eder; full suite green; runbook yazıldı.
- **Safety:** Additive `scripts/` + flat-file; trade-path yok. Draft-only invariant'ı KODDA enforce eder (no auto-publish transition). Tüm draft'lar queue-entry'de compliance+disclaimer-gated. Store'da secret yok. Clean revert (dir+script sil).

---

### PHASE 3 — ContentMachine (gated: GATE 2 CAC `gate_open=true` + non-zero conversion)

> ⚠️ **GATE 2'yi geçmeden bu faza başlama.** `cac_gate.json gate_open=true` = ≥14 gün AND ≥300 organic session AND ölçülmüş non-zero visit→waitlist conversion. Tüm ContentMachine/Scale BLOCKED until first non-zero conversion (CEO HIGH — boil the lake, don't build it upfront).

#### CON-8 — Video-script compliance harness (extend, don't rebuild)  **[REVIEW]**
- **Blocked by:** CON-1, CON-4 (claude docs), **CMP-3** (EN enforcement zaten merged olmalı).
- **Files:** `scripts/video_script_compliance.py` (yeni, thin wrapper) + `tests/test_video_script_compliance.py`
- **Do:** Brief'in VO+on-screen+caption blob'unu alır → violations list (`find_violations` reuse), disclaimer presence (`has_disclaimer`), + ekstra forbidden visual-claim string check (`CHoCH`, `BOS label`, `$`, `guaranteed`, `win rate`). **Regex logic'i DUPLICATE ETME — `content_compliance`'tan import et.** Hermetic clean+dirty fixtures. **Queue label "compliance PASS" → "script-text PASS"** (CSO HIGH — text gate burned-in pixel göremez).
- **Acceptance:** `find_violations/has_disclaimer`'ı import eder (kopyalamaz); test green (clean brief geçer, `$500`/`CHoCH`/`80% win rate` fixture fail); full suite green; CI py3.11 geçer.
- **Safety:** Scripts-only/additive, engine/safety dokunulmaz. content_compliance EXTENDS (rebuild değil). Pure-Python, hermetic, no network/secrets. Hermes→Claude format-patch+sha256.

#### CMP-4 — Conservative-proof rule + code enforcement + return_pct decision  **[REVIEW]**
- **Blocked by:** CMP-3.
- **Files:** `docs/compliance/conservative-proof-rule.md` (yeni) + `scripts/content_compliance.py` (proof_mode)
- **Do:** Whitelist (win-rate%/R:R/profit-factor/max-DD%) + equity-curve normalization (100-indexed, no $ axis). **Signed `return_pct` durumunu KARARLA — live `premium_proof.json` -5.3% yayınlıyor; bu gate'i tetikler (`find_violations('return -5.3%')`→`performance_pct_claim`) VE whitelist dışında (VERIFY).** `proof_mode` flag (`pre_track_record` default = safest): per-trade/non-aggregate language reddeder. **`proof_mode`'u GROW-8 `proof_milestone.json` single-source-of-truth'a BAĞLA** — checker `milestone_reached` okur, `false` iken dollar-PnL copy reddeder (manuel proof_mode arg'a bakmaksızın). Ties P-003 G-P3-1.
- **Acceptance:** Rule doc whitelist+normalization belirtir; gate per-trade/non-aggregate'i `pre_track_record`'da reddeder; testler allowed-aggregates geçer + per-trade fail + equity-shape geçer + `milestone_reached==false` iken $-PnL fail (manuel arg'a bakmaksızın); return_pct kararı dokümante. @operator metric whitelist onayı.
- **Safety:** scripts+docs; P-003 G-P3-1 proof whitelist'i mirror eder (gate'ler diverge edemez). Conservative-proof (HARD-6) literal konu. Additive flag default=safest. Trade-path yok.

#### KPI-ROUTINE (was GROW-4; absorbs SD-9 + WEB-11) — Single weekly KPI routine  **[REVIEW]**
- **Blocked by:** GROW-2, WEB-6. ⚠️ **İki kritik düzeltme (verified bugs):**
- **Files:** `scripts/growth/kpi_report.py` (yeni STANDALONE runner) + `state/kpi_weekly.json` + customer-token digest
- **Do:** Haftalık funnel KPI'ları 3 kaynaktan toplar: (a) Supabase `waitlist_leads` source/utm-grouped (signups/channel, EN vs TR), (b) `entitlements` (granted/revoked), (c) analytics provider stats API (sessions, CTR, visit→waitlist). Çıktı `state/kpi_weekly.json` (whitelisted schema, **proof-milestone OFF iken sıfır $**) + markdown digest.
  - 🔴 **`AlertRouter.from_env()` KULLANMA** — `_alert.py:21-22` SADECE `EFLOUD_TELEGRAM_TOKEN/CHAT_ID` (operatör trade-alert channel!) okur. **Ayrı `EFLOUD_CUSTOMER_TG_*` (SD-5 ile aynı convention) kullan.** Regression test: digest asla `EFLOUD_TELEGRAM_CHAT_ID`'ye resolve etmez.
  - 🔴 **`scripts/routines/runner.py REGISTRY`'ye KAYDETME** — `runner.run_one()` → `make_future_client()` (`_base.py:20-26`) her çağrıda `BINANCE_API_KEY/SECRET`'ten CANLI ccxt.binance futures client kurar. Marketing cron'unu mainnet trading cred'lerine coupling = INV-1 ihlali. **Standalone `scripts/growth/` runner, `make_future_client` import ETMEZ.** Test: no ccxt.binance constructed + no `BINANCE_*` read.
- **Acceptance:** `state/kpi_weekly.json` per-channel signups + conversion% + CAC=null (no spend); draft markdown digest **growth/customer Telegram channel'a** (trade-alert DEĞİL); proof-milestone OFF iken sıfır $ (test-enforced); routine ok=True; flag OFF = no-op; full suite green CI py3.11; **test asserts no ccxt.binance + no BINANCE_* read + no resolve to EFLOUD_TELEGRAM_CHAT_ID.**
- **Safety:** Read-only aggregation; standalone runner (no make_future_client, no engine/safety). Flag-OFF default. Ayrı customer TG token VPS .env-only. Draft/info message, no auto-publish. $-suppression test-enforced. **SD-9 + WEB-11 buna absorbe edildi — onları ayrı yazma.**

#### SD-6 — YouTube 2/wk structure + Shorts  **[REVIEW]** (structure doc [EXEMPT])
- **Blocked by:** SD-3, SD-2 (claude doc).
- **Files:** `docs/marketing/youtube-structure.md` (yeni) + `backend/social/templates/youtube.py` (yeni) + ilk 3 EN video brief
- **Do:** YouTube structure youtube_upload.py draft-mode (M4) üstüne: 2 video/hafta = (A) backtest/methodology walkthrough, (B) live-trade explainer, her biri 2 Short. EN title/desc/tag templates her açıklamada zorunlu disclaimer + UTM-tagged u2algo.com link. İlk 3 edu brief EN. **YT longs = screen-record, $0 Higgsfield** (budget MED — Higgsfield 15s cap, longs onun bütçesine girmez). (M14.)
- **Acceptance:** structure 2/hafta + Short mapping; youtube.py EN title/desc/tags disclaimer+UTM, content_compliance valid; ilk 3 brief EN; upload path draft-mode only (public-publish call YOK); youtube_upload.py dry-run test green.
- **Safety:** M4 draft-mode üstüne; trade-path yok. Draft/private only, manuel publish operatör sign-off sonrası. YouTube API key VPS .env-only. Her desc'te disclaimer, no $/perf-%.

#### CMP-7 — Compliance gate hook into draft queue  **[REVIEW]**
- **Blocked by:** CMP-3, CMP-4.
- **Files:** `engine/content_jobs.py` path (gate function) veya `scripts/` + `scripts/check_draft.py` (yeni CLI)
- **Do:** Gating point: hiçbir draft `find_violations()==[]` AND `has_disclaimer(lang)==True` geçmeden Hermes/human queue'ya ulaşmaz. Thin gate function content-job emitter (M5/M6) draft queue-öncesi çağırır; violation'da `draft.status='rejected_compliance'` + tag list, asla auto-publish. `check_draft.py` CLI: Hermes pasted draft'ı lokal lint. Flag-OFF default. **Manual path'te MANDATORY (SD-8/CON-9), advisory değil** (governance HIGH).
- **Acceptance:** Gate violation/missing-disclaimer draft'ı queue-öncesi reddeder; `check_draft.py` PASS/FAIL+tags yazar; regression: flag-OFF → sıfır behavior change; auto-publish path yok. @claude review.
- **Safety:** Additive, flag-OFF default; mevcut flag-gated content_jobs (PR #173) reuse. Draft-only mandatory queue (HARD-3). Trade-path yok, config-flip yok. Hermes→Claude format-patch+sha256.

#### GROW-6 — KPI dashboard schema + operator read-out  **[REVIEW]** (schema doc [EXEMPT])
- **Blocked by:** KPI-ROUTINE, GROW-5 (claude).
- **Files:** `docs/marketing/kpi-dashboard-schema.md` (yeni) + operator read-out (Google Sheet append VEYA `u2algo-site/ops/kpi.html` noindex static)
- **Do:** Schema columns (week, channel, lang, impressions, clicks, ctr_pct, sessions, waitlist_signups, visit_to_waitlist_pct, new_customers, churned, mrr_or_null, cac_or_null, cac_gate_open, ab_test_active). Read-out `state/kpi_weekly.json`'ı render eder, `cac_gate_open` görünür; **$ columns milestone-OFF iken null**; static ise robots noindex + sitemap dışı + operator-gated. (T-012 static-serve pattern mirror.)
- **Acceptance:** Schema tüm columns+types; read-out latest `state/kpi_weekly.json` render eder cac_gate_open ile; $ columns milestone-OFF null; static page noindex+sitemap dışı; smoke test green.
- **Safety:** Operator-only read-out, noindex, NOT public. Static-serve, bot API exposure yok. Flag-gated $ columns. u2algo-site only, trade-path yok.

---

### PHASE 4 — Scale (gated: GATE 3 90-day proof + CAC justifies paid)

#### SD-10 — Content-calendar engine  **[REVIEW]** (calendar doc [EXEMPT])
- **Blocked by:** SD-8, SD-2 (claude doc).
- **Files:** `docs/marketing/content-calendar.md` (yeni) + `scripts/social_calendar.py` (yeni)
- **Do:** Steady-state calendar: SD-2 repurposing matrix verilince haftanın draft slot'larını (3-5 post/hafta: X thread×2, Telegram snapshot×1, IG carousel×1, YT A/B+Shorts) SD-8 approval queue'ya önceden üretir — hâlâ draft-only, human-approved. EN-primary/TR-derivative split per slot + Higgsfield/TV asset dependency per pillar.
- **Acceptance:** Calendar haftalık slot template (3-5 post, channel+pillar+language+source asset); `social_calendar.py` bir hafta DRAFT slot SD-8 queue'ya emit eder (compliance-gated, none auto-posted); EN/TR split explicit; ilk production week proof; suite green.
- **Safety:** Additive `scripts/` SD-8 draft queue'ya yazar only; no auto-publish, human approval mandatory. Trade-path yok. Her slot compliance+disclaimer. Conservative proof (no $). Clean revert.

---

### Collapsed / absorbed @hermes items (ayrı YAZMA — yukarıya katlandı)
- **GROW-3** → WEB-5'i consume eder; sadece `docs/marketing/analytics-vs-manus-seo.md` slice yazar (SEO-1 RACI'ye reference). Ayrı analytics standup YOK.
- **GROW-4 / SD-9 / WEB-11** → tek **KPI-ROUTINE**'a katlandı.
- **SEO-7 GSC/Bing** → WEB-10'a (operatör) katlandı; SEO-7 sadece rank-sheet (operatör).

---

## 4. Operator-Gated Blockers — Hermes BUNLARI GEÇEMEZ

Aşağıdakiler @operator domain'i. **İlgili task'a, blocker yeşil olana kadar BAŞLAMA** (veya doc-spec kısmını yaz, exec kısmını bekle).

| Blocker | Ne | Bloklar |
|---|---|---|
| **SITE-SOT** | u2algo-site Railway deploy source-of-truth (repo mu vendored copy mu?) | **HER site PR** (WEB-2/3/5/6/3c, GROW-2, SD-3 değil ama CMP-5/SEO-3/4) |
| **MANUS-CAP** | Manus auto-publish YOK + `<head>` yazıyor mu? Free-tier IG/FB+SEO+DNS kotaları | SD-3, GROW-3 |
| **LS-FLIP** | `LS_WEBHOOK_ENABLED=true` + LS test-purchase (webhook bugün 503-inert) | WEB-3a |
| **PROD-0** | `$39` premium farklılaşması tanımı VEYA "free+waitlist" reframe | SEO-3 (claude) — ama SD/CON copy'de $ kullanımını da etkiler |
| **DNS records** | apex/www/SPF/DKIM/DMARC/CNAME — operatör Manus.im registrar'da uygular | WEB-2, WEB-3b |
| **Secrets** | `MANUS_API_KEY`, X/xurl, YouTube API, GA4 ID, `EFLOUD_CUSTOMER_TG_*`, Plausible — operatör VPS .env'e koyar | SD-3/4/5/6, WEB-5/6, KPI-ROUTINE |
| **Higgsfield paid-tier** | Plus/887cr; Kling-only first batch; Ultra upgrade CAC-gated | CON-9 (claude) |
| **Publish sign-off** | Hiçbir content yayınlanmaz; operatör/Hermes approval queue | SD-8 approve→post adımı; CMP-5 live publish |
| **Bot migration cutover** | WEB-1/4/8 STANDALONE ops change — efloud-risk-ops sign-off + flat-book/quiet window + LS test-purchase | WEB-8 (staging probe kısmı) |
| **Proof posture** | Negatif proof (-5.3%) ne gösterir? (hide/research-log) | CMP-4 return_pct kararı, GROW-8 |
| **CAC GATE 2** | `gate_open=true` (≥14gün, ≥300 session, non-zero conv) | TÜM ContentMachine/Scale task'ları |
| **90-day GATE 3** | `milestone_reached=true` (≥90gün + ≥N trade) | dollar-PnL claims, paid scale, SD-10 |

Kural: secret yapıştırılınca SADECE VPS `.env.production` / Railway env'e; repo/config/commit/memory/log'a ASLA; çıktıda gösterme; doğrulamayı dosyadan okuyarak yap.

---

## 5. Review Gates

| Gate | Ne zaman | Kim |
|---|---|---|
| **efloud-code-reviewer** | Her kod/site PR (CMP-3, GROW-2, WEB-2/3/5/6/3c/8, SD-3/4/5/6/8/10, CON-8, CMP-4/5/7, KPI-ROUTINE, GROW-6) | @claude — `/review` skill |
| **efloud-risk-ops-reviewer** (escalation) | Risk/safety path'i dokunan PR'lar (KPI-ROUTINE Binance-coupling kontrolü, WEB-8 healthz, herhangi bir engine-adjacent) | @claude — auto-escalate |
| **Design/Brand lens** | Herhangi u2algo-site PR (brand-token, efloud-leak, cross-surface) | gstack role-review |
| **SEO review gate (SEO-8)** | SEO-3/SEO-4 merge öncesi: JSON-LD valid, hreflang valid, canonical present, no $-claim, dashboard noindex, Lighthouse ≥95 | @claude + gstack |
| **CSO/Compliance lens** | Foundation→QuickWins gate: CMP-3 EN coverage, price-whitelist, disclaimer reconcile, MANUS-CAP | gstack role-review |
| **/ultrareview** | **Tüm initiative sonunda** (cloud multi-agent) | @operator tetikler |

Akış: Hermes format-patch → sha256 → Claude izole worktree `git am --3way` → Claude review (yukarıdaki gate'ler) → PASS: push+PR→master / FAIL: fix-notes geri Hermes'e. CI 4/4 yeşil olmadan merge yok.

---

## 6. Invariant Self-Checklist (HER PR'dan önce Hermes doğrular)

Her patch'i format-patch etmeden önce bu 7 maddeyi kendin geç. Bir madde bile düşerse PR REDDEDİLİR.

- [ ] **INV-1 Trade path untouchable** — `engine/safety/`, `engine/lifecycle.py`, order path, breaker/guard, `configs/config.phase2_1k.yaml` SIFIR değişiklik. Bot LIVE MAINNET `dry_run:false`. (KPI-ROUTINE: `make_future_client` import etmedim, ccxt.binance kurmadım, `BINANCE_*` okumadım — test ile assert.)
- [ ] **INV-2 Flag-OFF default + additive + clean revert** — yeni davranış env/config flag arkasında default-OFF; mevcut path değişmez; revert = dosya/blok sil.
- [ ] **INV-3 Draft-only** — sıfır auto-publish path; çıktı approval queue'ya. Hiçbir kod draft→posted otomatik geçirmez.
- [ ] **INV-4 Compliance gate** — copy `content_compliance.find_violations()==[]` AND `has_disclaimer(<surface-lang>)`==True geçer. EN asset → `lang='en'` (asla `'both'`). (CMP-3 merged değilse EN-copy task'a başlama.)
- [ ] **INV-5 Secrets VPS .env-only** — repo/config/commit/log'da key yok; key-absent → no-op; `MANUS_API_KEY`/`EFLOUD_CUSTOMER_TG_*`/X/YouTube/GA4/Plausible sadece NAME ile referans. gitleaks (ci.yml:109-119) yeşil.
- [ ] **INV-6 Conservative proof** — 90-güne kadar SHAPE + aggregate % only, sıfır $/per-trade/balance. `$39` ürün-fiyatı PRICE_WHITELIST ile OK ama PnL-$ değil.
- [ ] **INV-7 sha256 handoff** — format-patch + sha256, iki tarafta eşleşir; Telegram YASAK; `git am --3way` izole worktree.

Ek davranış kuralları: `git add -A` yasak (spesifik stage); aynı 5 HTML dosyasına çakışan PR yok (@hermes serializes u2algo-site merge queue); `efloud`/`efloud-bot` internal-name public copy'ye sızmaz (launch-assets 6× leak scrub edilir).

---

*End of Hermes handoff. Spec: `docs/superpowers/specs/2026-06-17-u2algo-marketing-seo-ultraplan-design.md`. Sıra: Foundation blokları → CMP-3 (her şeyin önü) → QuickWins spine → CAC gate → ContentMachine → 90-day gate → Scale. Trade path untouched, all additive, all draft-only.*
