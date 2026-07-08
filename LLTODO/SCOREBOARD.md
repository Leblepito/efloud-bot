# LLTODO — SCOREBOARD

| **Son güncelleme:** 2026-06-18 @hermes (T-025 DONE — P-002 M3 Manus REST client; gerçek API verified `request_id=92657...`, task `Bnk8FCrVYgZ6Kavx3eA332`; `urllib`→`requests` WAF-bypass bugfix; `MANUS_API_KEY` `.env.production` chmod 600 flag kapalı. T-026 claim — P-002 M1 xurl runbook; T-019 kart kapatma bookkeeping fix) |

## Genel Metrikler

| Metrik | Değer |
|---|---|
| Toplam epic | ~~1 (P-001)~~ → 3 (P-001, P-002, P-003) |
| Aktif epic | ~~1 (P-001)~~ → 3 (P-001 IN_PROGRESS, P-002 CONSENSUS_REACHED, P-003 CONSENSUS_REACHED) |
| Tamamlanan epic | 0 |
| Toplam görev | ~~3 (T-001, T-002, T-003)~~ → 18 (T-001..T-003, T-010..T-024) → 25 (T-025..T-031 eklendi: P-002 M3/M1/M6/M2) |
| Tamamlanan görev | 11 (T-001..T-014 ✅ mevcut + T-011 ✅ consent [15 Jun] + T-016 ✅ INERT DELIVERED [15 Jun]; T-017 ✅ runbook [15 Jun]) ~~önceki: 10~~ → 19 (T-019 ✅ quickstart 17 Jun merged [kart 18 Jun DONE]; T-018 ✅ müşteri telegram digest 16 Jun merged [kart 18 Jun DONE]; T-021 ✅ status page 18 Jun kod + runbook; T-025 ✅ Manus REST client 18 Jun; T-026 ✅ xurl facade [PR #228 merged 18 Jun]; T-029 ✅ M2 manifest consumer [19 Jun]; T-030 ✅ approval callback [19 Jun]; T-031 ✅ xurl publisher [19 Jun]) → 20 (T-028 ✅ Tier-2 renderers — kod zaten master'da 19 Jun'dan beri canlıydı, kart 2026-07-08 @claude tarafından DONE/'a taşındı [bookkeeping-only fix, fonksiyonel değişiklik yok]) |
| Claim edilmiş görev | 0 (T-028 DONE/'a taşındı, 2026-07-08 @claude) |

## P-001 Görev Skoru

| Görev | Açıklama | Durum | Claim |
|---|---|---|---|
| T-001 | Swing detection + OB core (Pine Script) | 🟢 DONE | @hermes (2026-06-10) |
| T-002 | MTF confluence + SL/TP hesaplama | 🟢 DONE (G-T2 PASS 2026-06-11) | @hermes (2026-06-11) |
| T-003 | Strateji backtest + görsel validasyon | ❌ NO-GO (4+ tur edge negatif; SMC sinyali tradeable edge yok) → 🔀 INDICATOR-ONLY SHIP (PR #198, v1.2.0). Strateji premium → R&D backlog; #194 parked/kapatıldı. | @hermes (2026-06-11) |

## Sprint Görünümü

**Sprint 1 (2026-06-10 → 2026-06-13):**
- [x] T-001: Swing detection + OB core ✅ IMPL_READY
- [ ] LLTODO scaffolding → master PR (GÖREV 2) — #177 merged ✅
- [x] Prod reconciliation runbook ✅
- [x] Strategy-opt re-verify report ✅

**Sprint 2 (2026-06-14 → 2026-06-17):**
- [x] T-002: MTF confluence + SL/TP ✅ DONE (erken bitti — G-T2 PASS 2026-06-11)
- [ ] T-003: Strateji backtest (R1+R3 patch'leri hazırlanıyor → çoklu-sembol gate re-run)

**Sprint 3 (2026-06-18 → ...):**
- [ ] UR-001 UltraReview
- [ ] Master merge

## P-002 (Marketing & Growth Pipeline)

| Alan | Durum |
|---|---|
| Durum | ~~ULTRA_PLAN (Claude review bekliyor)~~ → ~~REVIEW_OPEN~~ → CONSENSUS_REACHED (UR-003 oturumunda kapsandı; M11 dedup bulguları entegre, 2026-06-11 @claude) |
| Rekonstrükte plan | `LLTODO/plans/P-002-marketing-growth-pipeline.md` |
| Hermes v1 draft | `LLTODO/plans/P-002-marketing-growth-pipeline.v1-hermes-draft.md` |
| Claude prompt | `LLTODO/PROMPT-claude.md` + `LLTODO/plans/P-002-claude-ultraplan-prompt.md` |
| Sonraki | @hermes plan onayı + operatör OQ#1-#12 kararları → M1-M4 implementasyon |

| Agent | Rol |
|---|---|
| @hermes | v1 draft, implementasyon |
| @claude | UltraPlan rekonstrüksiyonu, security audit, UR-002 |

### P-002 Görev Skoru (append-only, 2026-06-19 @hermes)

> P-002 görevleri M1-M15 PR yapısına bağlı. Hermes implementasyonu başladı
> (M1 facade + M3 Manus client patch'leri hazır, operatör push'u bekliyor).
> T-025 placeholder DONE olarak işaretlendi (gerçek dosya `feat/p002-m3-manus-client`
> branch'inde; push sonrası R8 cross-ref için).

| Görev | Faz | Açıklama | Durum | Claim |
|---|---|---|---|---|
| T-025 | M3 | Manus API client + retry + key masking + 3 template + 41 test | 🟡 placeholder DONE (kod branch'te, push bekliyor; gerçek dosya feat/p002-m3-manus-client @ 53b0cc2, 3 commit, T-025 bookkeeping) | @hermes (2026-06-19) |
| T-026 | M1 | xurl CLI facade + runbook + config schema (default OFF) | 🟡 IN_PROGRESS (kod + 23 test + runbook hazır, commit + push bekliyor; feat/p002-m1-xurl-runbook) | @hermes (2026-06-19) |
| T-027 | M6 | Content Approval Queue skeleton (state machine + migration 009 + storage + runbook) | 🟡 IN_PROGRESS (29 test PASS, 8/8 lint PASS, commit + push bekliyor; feat/p002-m6-content-queue @ 4e6dc90; renderer PR'a merge edildi [19 Jun @hermes]) | @hermes (2026-06-19) |
| T-028 | M6.2 | Tier-2 Content Renderers (yaml → render → pre-gate → queue enqueue) | ✅ DONE (31 test PASS + 5 M2 integration, 8/8 lint PASS; master'a merge edilmiş [db03b5b/bbe32f6/3839659, PR #230]; kart bookkeeping fix 2026-07-08 @claude — kod zaten canlıydı, tracker dosyası IN_PROGRESS/'ta unutulmuştu) | @hermes (2026-06-19) |
| T-029 | M2 | Chart-Export Manifest Consumer (VPS-side, operatör-lokal manifest → renderer resolver) | ✅ DONE (26 test PASS; tv_manifest.py + tier2_renderers entegrasyonu + push fix + runbook; feat/p002-m6-templates HEAD @ 0056ef1+) | @hermes (2026-06-19) |

## Review Skoru

| Review | Epic | Reviewer | Sonuç | Conf |
|---|---|---|---|---|
| R-001 | P-001 | @claude | CHANGES_REQUESTED | 7/10 |
| R-002 | P-001 | @gemini | CHANGES_REQUESTED | 9/10 |

## Agent Katkıları

| Agent | Epic | Roller |
|---|---|---|
| @hermes | P-001 | Plan revizyonu, implementasyon |
| @claude | P-001 | R-001 review, UR-001 ultra review |
| @gemini | P-001 | R-002 review |

---

## P-003 Eki (2026-06-11 — append-only)

> P-003 "Commercial MVP" açıldı (epic ID çakışması nedeniyle P-002'den renumber edildi;
> P-002 = Marketing & Growth). Genel metrik tablosu rename commit'inde mutabıklandı:
> 3 epic, 18 görev (T-001..T-003 + T-010..T-019 + W-R eki T-020..T-024).

### P-003 Görev Skoru

| Görev | Dalga | Açıklama | Durum | Claim |
|---|---|---|---|---|
| T-010 | W0 | u2algo-site legal sayfaları + footer + sitemap | ✅ DONE (PR #208 → `c41fb15`; terms.html + footer Yasal + sitemap; smoke compliance PASS) — legal text refinement operatör follow-up'u | @hermes (2026-06-15) |
| T-011 | W0 | Waitlist consent checkbox + server.js payload (3 fallback zincirinde) + 13/13 test | ✅ DONE (consent gate strict===true + 3-fallback persist + index.html checkbox + privacy.html; 13/13 test; PR #204) | @hermes (2026-06-15) |
| T-012 | W1 | proof_export.py + snapshot şema + privacy testi | ✅ DONE (PR #185; baseline-referans kararı operatörden; VPS cron+baseline = runbook §5) | @claude (2026-06-11) |
| T-013 | W1 | monthly.py + /api/reports/monthly | ✅ DONE (PR #191; journal-first, DB-less equity "n/a", operatör-only İÇ) | @claude (2026-06-11) |
| T-014 | W1 | Uptime alanı + public CHANGELOG + site updates | ✅ DONE (PR #192; uptime schema 1.1.0, §3 ayrımı; changelog→updates.json statik) | @claude (2026-06-11) |
| T-015 | W2 | Supabase entitlements migration + RLS | ✅ DONE (entitlements tablosu + consent kolonları CANLI Supabase'e uygulandı [16 Jun]; RLS service-role-only doğrulandı — advisor INFO-only, permissive-policy hole'u yakalandı/önlendi) | @claude (2026-06-16) |
| T-016 | W2 | Lemon Squeezy webhook (HMAC) + onay e-postası | ✅ DONE (INERT DELIVERED, 13/13 test, B.1-B.4 onayı sonrası aktive) | @claude (2026-06-15) |
| T-017 | W2 | tv-access-grant runbook + kuyruk görünümü | ✅ DONE (runbook + list_pending script + 7 acceptance kriteri) | @hermes (2026-06-15) |
| T-018 | W3 | telegram_notifier (default-OFF) + regression test | ✅ DONE (PR #201 `d4bb169` merged 16 Jun; 32/32 test; default-OFF 2-katmanlı guard; G-P3-3 sağlam. Kart 18 Jun DONE'a taşındı) | @claude (2026-06-15, kart kapatma @hermes 2026-06-18) |
| T-019 | W3 | Müşteri quickstart + site FAQ/destek | ✅ DONE (PR #214 `2835bdb` merged 17 Jun; u2algo-site/quickstart.html — TV invite + setup + alert + 9 SSS; smoke compliance gate; premium.html hero+footer link; sitemap 0.7 priority. Kart 18 Jun DONE'a taşındı — bookkeeping fix) | @hermes (2026-06-16, kart kapatma 2026-06-18) |
| T-020 | W-R | Backup otomasyonu + restore tatbikatı (pre-UR-exempt) | ⬜ BACKLOG (kod merged, GÖREV F operatör tetiklemeli — backup provizyon + drill) | @claude (2026-06-11, parked) |
| T-021 | W-R | Public status page + uptime monitor | ✅ DONE (feat/p003-wr-t021-status-page @ 4c88c09 18 Jun; status.html + uptime_to_public.py + 8/8 test; runbook status-page-operations.md. Kart 18 Jun DONE'a taşındı) | @hermes (2026-06-18) |
| T-022 | W-R | SLA + DR + on-call dokümanları | ✅ DONE (PR #187; tabletop PASS 2. tur — breaker-reset.md bonus; G-P3-B2 paketi hazır) | @claude (2026-06-11) |
| T-023 | W-R | CI hardening: gitleaks + frontend + lint (pre-UR-exempt) | ✅ DONE (PR #182 → master `63b9872`, CI 4/4) | @claude (2026-06-11) |
| T-024 | W-R | Healthz kontrat dokümanı + uptime metriği | ✅ DONE (PR #184 — `docs/runbooks/healthz-contract.md`) | @claude (2026-06-11) |
| T-025 | P-002-M3 | Manus REST client (fail-safe, flag OFF) + task template şemaları | ✅ DONE (P-002 Faz A M3: `backend/social/manus_client.py` 460 satır — `ManusClient` + `requests.Session` transport + 3 task templates; `backend/social/templates/manus_{x_thread,youtube_short,weekly_snapshot}.json`; `docs/runbooks/manus-setup.md`; `config.yaml` notifications.manus.enabled=false şema; 41/41 unit test PASS — hermetic, network YOK, retry/backoff/max_log truncation/key maskeleme/compliance token validate. **Bugfix:** `urllib`→`requests` WAF-bypass (Hetzner IPv6 + AWS WAF). **Real API verified:** `request_id=92657...` (`task.list` side-effectsiz). **Env wired:** `MANUS_API_KEY` `.env.production`'a eklendi (chmod 600, flag kapalı default-OFF). Operatör: `MANUS_API_ENABLED=true` + recreate) | @hermes (2026-06-18) |
| T-026 | P-002-M1 | xurl CLI kurulum + auth runbook + facade | 🟡 IN_PROGRESS (P-002 Faz A M1: `backend/social/xurl_client.py` 580 satır — XurlClient + post/thread + dry-run + compliance gate integration; 23/23 unit test PASS — hermetic, network YOK, subprocess mock'lu. Operatör: xurl binary local machine'de kurulacak [VPS'te OAuth browser flow yapılamaz]; Twitter app + OAuth PIN flow; VPS'e SSH tunnel ile veya manuel post) | @hermes (2026-06-18) |

### P-003 Review Skoru

| Review | Epic | Reviewer | Sonuç | Conf |
|---|---|---|---|---|
| UR-003 | P-003 | @claude (lokal 4-lens; cloud /ultrareview 30dk timeout — PR #175 emsali fallback) | ✅ APPROVED_WITH_NITS (0 blocker; 14 should-fix → plan v1.1'e entegre) | 8.5/10 |

> UR-003 detayı: `LLTODO/reviews/R-003-claude-ur003-commercial-mvp.md`
> P-002 Marketing planı da aynı oturumda kapsandı (UR-002 işlevi) — dedup/M11 bulguları entegre.

### Agent Katkıları (ek)

| Agent | Epic | Roller |
|---|---|---|
| @claude | P-003 | Boşluk analizi, plan yazımı, UR-003 |
| @hermes | P-003 | Infra ön-işleri (Supabase/Railway), W0-W3 implementasyon |
