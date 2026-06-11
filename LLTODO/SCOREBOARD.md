# LLTODO — SCOREBOARD

> Son güncelleme: 2026-06-11 @claude (önceki: 2026-06-10 @hermes)

## Genel Metrikler

| Metrik | Değer |
|---|---|
| Toplam epic | ~~1 (P-001)~~ → 3 (P-001, P-002, P-003) |
| Aktif epic | ~~1 (P-001)~~ → 3 (P-001 IN_PROGRESS, P-002 CONSENSUS_REACHED, P-003 CONSENSUS_REACHED) |
| Tamamlanan epic | 0 |
| Toplam görev | ~~3 (T-001, T-002, T-003)~~ → 18 (T-001..T-003, T-010..T-024) |
| Tamamlanan görev | 7 (T-001 ✅; T-002 ✅ G-T2; T-023 ✅ #182; T-024 ✅ #184; T-012 ✅ #185; T-022 ✅ #187; T-013 ✅ #191) ~~önceki: 6~~ |
| Claim edilmiş görev | 1 (T-020 @claude) ~~önceki: 2~~ |

## P-001 Görev Skoru

| Görev | Açıklama | Durum | Claim |
|---|---|---|---|
| T-001 | Swing detection + OB core (Pine Script) | 🟢 DONE | @hermes (2026-06-10) |
| T-002 | MTF confluence + SL/TP hesaplama | 🟢 DONE (G-T2 PASS 2026-06-11) | @hermes (2026-06-11) |
| T-003 | Strateji backtest + görsel validasyon | ⬜ BACKLOG | — |

## Sprint Görünümü

**Sprint 1 (2026-06-10 → 2026-06-13):**
- [x] T-001: Swing detection + OB core ✅ IMPL_READY
- [ ] LLTODO scaffolding → master PR (GÖREV 2) — #177 merged ✅
- [x] Prod reconciliation runbook ✅
- [x] Strategy-opt re-verify report ✅

**Sprint 2 (2026-06-14 → 2026-06-17):**
- [x] T-002: MTF confluence + SL/TP ✅ DONE (erken bitti — G-T2 PASS 2026-06-11)
- [ ] T-003: Strateji backtest

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
| T-010 | W0 | u2algo-site legal sayfaları + footer + sitemap | ⬜ BACKLOG | — |
| T-011 | W0 | Waitlist consent checkbox + server.js alanı | ⬜ BACKLOG | — |
| T-012 | W1 | proof_export.py + snapshot şema + privacy testi | ✅ DONE (PR #185; baseline-referans kararı operatörden; VPS cron+baseline = runbook §5) | @claude (2026-06-11) |
| T-013 | W1 | monthly.py + /api/reports/monthly | ✅ DONE (PR #191; journal-first, DB-less equity "n/a", operatör-only İÇ) | @claude (2026-06-11) |
| T-014 | W1 | Uptime alanı + public CHANGELOG + site updates | ⬜ BACKLOG | — |
| T-015 | W2 | Supabase entitlements migration + RLS | ⬜ BACKLOG | — |
| T-016 | W2 | Lemon Squeezy webhook (HMAC) + onay e-postası | ⬜ BACKLOG | — |
| T-017 | W2 | tv-access-grant runbook + kuyruk görünümü | ⬜ BACKLOG | — |
| T-018 | W3 | telegram_notifier (default-OFF) + regression test | ⬜ BACKLOG | — |
| T-019 | W3 | Müşteri quickstart + site FAQ/destek | ⬜ BACKLOG | — |
| T-020 | W-R | Backup otomasyonu + restore tatbikatı (pre-UR-exempt) | 🟡 IN_PROGRESS (scriptler+runbook PR'da; VPS kurulum+drill GÖREV F sonrası) | @claude (2026-06-11) |
| T-021 | W-R | Public status page + uptime monitor | ⬜ BACKLOG | — |
| T-022 | W-R | SLA + DR + on-call dokümanları | ✅ DONE (PR #187; tabletop PASS 2. tur — breaker-reset.md bonus; G-P3-B2 paketi hazır) | @claude (2026-06-11) |
| T-023 | W-R | CI hardening: gitleaks + frontend + lint (pre-UR-exempt) | ✅ DONE (PR #182 → master `63b9872`, CI 4/4) | @claude (2026-06-11) |
| T-024 | W-R | Healthz kontrat dokümanı + uptime metriği | ✅ DONE (PR #184 — `docs/runbooks/healthz-contract.md`) | @claude (2026-06-11) |

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
