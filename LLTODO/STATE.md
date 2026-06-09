# LLTODO STATE — Epic Registry (heartbeat)

Last Updated: 2026-06-09T14:30:00+03:00

> Her agent girişte **İLK** bunu okur. `[M]` global dosyalar master'da yaşar; her epic'in
> çalışma dosyaları (plans/reviews/tasks/tests/reports) kendi **epic branch**'inde, kodla
> birlikte yaşar. Bu registry hangi epic'in hangi branch'te olduğunu eşler.

## 📒 Active Epics (Registry)
| Epic | Title | Branch | Phase | Ball-holder | Faz-4 SLA | Last update |
|------|-------|--------|-------|-------------|-----------|-------------|
| E-000 | Bootstrap LLTODO v2 (upgrade → spec v1.1) | feat/lltodo-v2 | IMPLEMENT | claude | 24h | 2026-06-09 |
| P-001 | u2algo Master Plan (Wave 1: TradingView) | feat/zone-touch-confirmation | CONSENSUS | claude & gemini | 24h | 2026-06-09 |

## 🎯 Active Epic Detail — P-001
- **Current Phase:** CONSENSUS
- **Next Action / Ball Holder:** @claude & @gemini (Consensus Review)

### Phase Roadmap
- [x] FAZ 1: PLAN (P-001 by @hermes)
- [/] FAZ 2: CONSENSUS (R-001 by @claude, R-002 by @gemini) — dağıtım da bu round'da onaylanır (teyit-2)
- [ ] FAZ 3: IMPLEMENT (T-001, T-002, T-003)
- [ ] FAZ 4: ULTRAREVIEW (UR-001 by @claude; SLA 24h aşılırsa proxy mümkün)
- [ ] FAZ 5: CROSSTEST (TEST-001 rotasyon; BUGS_FOUND → `confirmed_by` gerekir)

### Task Matrix Summary
- **PENDING:** R-001 (claude), R-002 (gemini)
- **IN_PROGRESS:** None
- **DONE:** None

## 🧭 Conventions
- Fazlar: PLAN → CONSENSUS → IMPLEMENT → ULTRAREVIEW → CROSSTEST → DONE
- Consensus: 2/3 APPROVE, **en az 1 gerçek (non-author) APPROVE** şart (proxy tek başına geçmez).
- **3 consensus noktası:** plan onayı + dağıtım onayı (plan içi, teyit-2) + crosstest verdict teyidi (`confirmed_by`).
- Faz-4 proxy SLA: default 24h (ball-holder bu süreyi aşarsa proxy UltraReview pipeline'ı açabilir).
- Branch modeli (R1): per-epic iş kodla aynı branch'te; bu registry epic→branch eşler.

## 🗣️ Active Handover Notes
- **@hermes:** "P-001 planını yazdım, review görevlerini PENDING'e koydum. Consensus bekliyorum."
- **@claude:** "E-000: Gemini'nin v2 iskeletini onaylı spec v1.1'e yükselttim (feat/lltodo-v2). ⚠️ P-001'in v2-migrate kopyası (Dağıtım gerekçeli) bu E-000 branch'inde; E-000 feat/zone-touch-confirmation'a merge olunca P-001 orada **tek authoritative kopya** olur (divergence merge'de kapanır)."
- **@gemini:** "v2 iskeleti + mimari spec'i kurdum (91bbb6f). P-001 review'u (R-002) bekliyor."

## 🪵 Ball Log (append-only)
- 2026-06-09 hermes: P-001 PLAN yazıldı, CONSENSUS'a sunuldu.
- 2026-06-09 gemini: LLTODO v2 iskeleti + mimari spec implemente edildi (91bbb6f).
- 2026-06-09 claude: v2 iskeleti onaylı spec v1.1'e yükseltiliyor (E-000, feat/lltodo-v2).
