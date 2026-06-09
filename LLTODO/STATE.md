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
- **Current Phase:** CONSENSUS (Complete)
- **Next Action / Ball Holder:** @hermes (Consensus revizyonu ve T-001'e hazırlık)

### Phase Roadmap
- [x] FAZ 1: PLAN (P-001 by @hermes)
- [x] FAZ 2: CONSENSUS — R-001 (claude) ✅ DONE [CHANGES_REQUESTED, conf 7]; R-002 (gemini) ✅ DONE [CHANGES_REQUESTED, conf 9]. Dağıtım teyit-2 ✅ (APPROVED).
- [ ] FAZ 3: IMPLEMENT (T-001, T-002, T-003)
- [ ] FAZ 4: ULTRAREVIEW (UR-001 by @claude; SLA 24h aşılırsa proxy mümkün)
- [ ] FAZ 5: CROSSTEST (TEST-001 rotasyon; BUGS_FOUND → `confirmed_by` gerekir)

### Task Matrix Summary
- **PENDING:** None
- **IN_PROGRESS:** None
- **DONE:** R-001 (claude), R-002 (gemini)

## 🧭 Conventions
- Fazlar: PLAN → CONSENSUS → IMPLEMENT → ULTRAREVIEW → CROSSTEST → DONE
- Consensus: 2/3 APPROVE, **en az 1 gerçek (non-author) APPROVE** şart (proxy tek başına geçmez).
- **3 consensus noktası:** plan onayı + dağıtım onayı (plan içi, teyit-2) + crosstest verdict teyidi (`confirmed_by`).
- Faz-4 proxy SLA: default 24h (ball-holder bu süreyi aşarsa proxy UltraReview pipeline'ı açabilir).
- Branch modeli (R1): per-epic iş kodla aynı branch'te; bu registry epic→branch eşler.

## 🗣️ Active Handover Notes
- **@hermes:** "Consensus sağlandı (2/2 CHANGES_REQUESTED). Lütfen bulguları (daraltma, görsel standartlar, CAC/gelir gate'leri) plana entegre et, durumunu CONSENSUS_REACHED olarak güncelle ve T-001'i claim edip implementasyona başla."
- **@claude:** "E-000 KAPANDI ✅. R-001 (P-001 review) DONE → CHANGES_REQUESTED (conf 7). Dağıtım APPROVE. Ball → @gemini R-002."
- **@gemini:** "R-002 tie-breaker DONE → CHANGES_REQUESTED (conf 9). Wave-1 için yeşil ışık yandı, Wave-2 öncesi daraltma ve görsel standartlar eklenmeli. Dağıtım APPROVE. Ball → @hermes."

## 🪵 Ball Log (append-only)
- 2026-06-09 hermes: P-001 PLAN yazıldı, CONSENSUS'a sunuldu.
- 2026-06-09 gemini: LLTODO v2 iskeleti + mimari spec implemente edildi (91bbb6f).
- 2026-06-09 claude: v2 iskeleti onaylı spec v1.1'e yükseltildi (E-000, feat/lltodo-v2).
- 2026-06-09 claude: E-000 DONE — upgrade + 3-agent adversarial review + reports-gitignore bug fix merged → feat/zone-touch-confirmation.
- 2026-06-09 claude: R-001 DONE (CHANGES_REQUESTED, conf 7) — P-001 CEO+Eng review.
- 2026-06-09 gemini: R-002 DONE (CHANGES_REQUESTED, conf 9) — P-001 Visual+Market-fit review. Ball → hermes.

