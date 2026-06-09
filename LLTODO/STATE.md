# LLTODO STATE — Epic Registry (heartbeat)

Last Updated: 2026-06-09T14:30:00+03:00

> Her agent girişte **İLK** bunu okur. `[M]` global dosyalar master'da yaşar; her epic'in
> çalışma dosyaları (plans/reviews/tasks/tests/reports) kendi **epic branch**'inde, kodla
> birlikte yaşar. Bu registry hangi epic'in hangi branch'te olduğunu eşler.

## 📒 Active Epics (Registry)
| Epic | Title | Branch | Phase | Ball-holder | Faz-4 SLA | Last update |
|------|-------|--------|-------|-------------|-----------|-------------|
| E-000 | Bootstrap LLTODO v2 (upgrade → spec v1.1) | feat/zone-touch-confirmation (merged) | DONE ✅ | — | — | 2026-06-09 |
| P-001 | u2algo Master Plan (Wave 1: TradingView) | feat/zone-touch-confirmation | CONSENSUS | claude & gemini | 24h | 2026-06-09 |

## 🎯 Active Epic Detail — P-001
- **Current Phase:** CONSENSUS
- **Next Action / Ball Holder:** @gemini (R-002 tie-breaker review; önce Claude'un R-001'ini oku)

### Phase Roadmap
- [x] FAZ 1: PLAN (P-001 by @hermes)
- [/] FAZ 2: CONSENSUS — R-001 (claude) ✅ DONE [CHANGES_REQUESTED, conf 7]; R-002 (gemini) PENDING (tie-breaker). Dağıtım teyit-2 ✅ (claude APPROVE).
- [ ] FAZ 3: IMPLEMENT (T-001, T-002, T-003)
- [ ] FAZ 4: ULTRAREVIEW (UR-001 by @claude; SLA 24h aşılırsa proxy mümkün)
- [ ] FAZ 5: CROSSTEST (TEST-001 rotasyon; BUGS_FOUND → `confirmed_by` gerekir)

### Task Matrix Summary
- **PENDING:** R-002 (gemini)
- **IN_PROGRESS:** None
- **DONE:** R-001 (claude — CHANGES_REQUESTED, conf 7)

## 🧭 Conventions
- Fazlar: PLAN → CONSENSUS → IMPLEMENT → ULTRAREVIEW → CROSSTEST → DONE
- Consensus: 2/3 APPROVE, **en az 1 gerçek (non-author) APPROVE** şart (proxy tek başına geçmez).
- **3 consensus noktası:** plan onayı + dağıtım onayı (plan içi, teyit-2) + crosstest verdict teyidi (`confirmed_by`).
- Faz-4 proxy SLA: default 24h (ball-holder bu süreyi aşarsa proxy UltraReview pipeline'ı açabilir).
- Branch modeli (R1): per-epic iş kodla aynı branch'te; bu registry epic→branch eşler.

## 🗣️ Active Handover Notes
- **@hermes:** "P-001 planını yazdım, review görevlerini PENDING'e koydum. Consensus bekliyorum."
- **@claude:** "E-000 KAPANDI ✅. R-001 (P-001 review) DONE → **CHANGES_REQUESTED** (conf 7): Wave-1 GO ama 12-ürün scope daraltılmalı + müşteri-edinme/gelir-gate'leri ekle (6 bulgu, 2 HIGH). Dağıtım APPROVE. Ball → @gemini R-002."
- **@gemini:** "SIRA SENDE → R-002: Claude'un `reviews/R-001-claude.md`'ini oku, P-001'i pazar + görsel açıdan değerlendir, tie-breaker verdict ver (APPROVE/CHANGES_REQUESTED/REJECT). `PROMPT-gemini.md` + `R-template.md` kullan, `reviews/R-002-gemini.md` yaz."

## 🪵 Ball Log (append-only)
- 2026-06-09 hermes: P-001 PLAN yazıldı, CONSENSUS'a sunuldu.
- 2026-06-09 gemini: LLTODO v2 iskeleti + mimari spec implemente edildi (91bbb6f).
- 2026-06-09 claude: v2 iskeleti onaylı spec v1.1'e yükseltildi (E-000, feat/lltodo-v2).
- 2026-06-09 claude: E-000 DONE — upgrade + 3-agent adversarial review + reports-gitignore bug fix merged → feat/zone-touch-confirmation; worktree kaldırıldı, feat/lltodo-v2 silindi.
- 2026-06-09 claude: R-001 DONE (CHANGES_REQUESTED, conf 7) — P-001 CEO+Eng review; ball → gemini (R-002 tie-breaker).
