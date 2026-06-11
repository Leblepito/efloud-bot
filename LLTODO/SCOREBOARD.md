# LLTODO — SCOREBOARD

> Son güncelleme: 2026-06-10 @hermes

## Genel Metrikler

| Metrik | Değer |
|---|---|
| Toplam epic | 3 (P-001, P-002, P-003) |
| Aktif epic | 3 (P-001 IN_PROGRESS, P-002 REVIEW_OPEN, P-003 REVIEW_OPEN) |
| Tamamlanan epic | 0 |
| Toplam görev | 13 (T-001..T-003, T-010..T-019) |
| Tamamlanan görev | 1 (T-001 ✅ 2026-06-10, G-T1 compile PASS) |
| Claim edilmiş görev | 0 |

## P-001 Görev Skoru

| Görev | Açıklama | Durum | Claim |
|---|---|---|---|
| T-001 | Swing detection + OB core (Pine Script) | ✅ DONE (G-T1 PASS, @claude compile-verify) | @hermes (2026-06-10) |
| T-002 | MTF confluence + SL/TP hesaplama | ⬜ BACKLOG | — |
| T-003 | Strateji backtest + görsel validasyon | ⬜ BACKLOG | — |

## Sprint Görünümü

**Sprint 1 (2026-06-10 → 2026-06-13):**
- [x] T-001: Swing detection + OB core ✅ IMPL_READY
- [ ] LLTODO scaffolding → master PR (GÖREV 2) — #177 merged ✅
- [x] Prod reconciliation runbook ✅
- [x] Strategy-opt re-verify report ✅

**Sprint 2 (2026-06-14 → 2026-06-17):**
- [ ] T-002: MTF confluence + SL/TP
- [ ] T-003: Strateji backtest

**Sprint 3 (2026-06-18 → ...):**
- [ ] UR-001 UltraReview
- [ ] Master merge

## P-002 (Marketing & Growth Pipeline)

| Alan | Durum |
|---|---|
| Durum | ~~ULTRA_PLAN (Claude review bekliyor)~~ → REVIEW_OPEN (rekonstrüksiyon TAMAM 2026-06-11 @claude) |
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
> 3 epic, 13 görev (T-001..T-003 + T-010..T-019).

### P-003 Görev Skoru

| Görev | Dalga | Açıklama | Durum | Claim |
|---|---|---|---|---|
| T-010 | W0 | u2algo-site legal sayfaları + footer + sitemap | ⬜ BACKLOG | — |
| T-011 | W0 | Waitlist consent checkbox + server.js alanı | ⬜ BACKLOG | — |
| T-012 | W1 | proof_export.py + snapshot şema + privacy testi | ⬜ BACKLOG | — |
| T-013 | W1 | monthly.py + /api/reports/monthly | ⬜ BACKLOG | — |
| T-014 | W1 | Uptime alanı + public CHANGELOG + site updates | ⬜ BACKLOG | — |
| T-015 | W2 | Supabase entitlements migration + RLS | ⬜ BACKLOG | — |
| T-016 | W2 | Lemon Squeezy webhook (HMAC) + onay e-postası | ⬜ BACKLOG | — |
| T-017 | W2 | tv-access-grant runbook + kuyruk görünümü | ⬜ BACKLOG | — |
| T-018 | W3 | telegram_notifier (default-OFF) + regression test | ⬜ BACKLOG | — |
| T-019 | W3 | Müşteri quickstart + site FAQ/destek | ⬜ BACKLOG | — |

### P-003 Review Skoru

| Review | Epic | Reviewer | Sonuç | Conf |
|---|---|---|---|---|
| UR-003 | P-003 | @claude (operatör /ultrareview) | ⬜ BEKLİYOR | — |

### Agent Katkıları (ek)

| Agent | Epic | Roller |
|---|---|---|
| @claude | P-003 | Boşluk analizi, plan yazımı, UR-003 |
| @hermes | P-003 | Infra ön-işleri (Supabase/Railway), W0-W3 implementasyon |
