# 🟧 Hermes — Açık Görevler (2026-06-10)

> Hazırlayan: Claude (Architect/Review). Bitince Claude review edecek.
> Kurallar: canlı mainnet → feature-branch + PR, atomic, secrets sadece VPS,
> destructive-op yok, deploy = flat-book + operatör onayı. Hermes uzmanlığı:
> kod, plan, terminal, **deploy**.

Bağlam: efloud-bot canlı mainnet, sorunsuz. Strateji "bir süre açık işleri
bitirip master'a deploy". master tip = `1f38998`. Prod VPS `/opt/efloud-bot`
branch = `feat/pr1-identity-tokens` @ `ca92ce7` (master DEĞİL — frontend fix
oraya cherry-pick'lendi).

---

## GÖREV 1 (TOP SENDE) — LLTODO P-001 implement (FAZ 3)
**Durum:** P-001 (u2algo Master Plan, Wave 1 TradingView) CONSENSUS sağlandı:
- R-001 (claude): CHANGES_REQUESTED conf 7
- R-002 (gemini): CHANGES_REQUESTED conf 9
- Dağıtım teyit-2: APPROVED

**Yapılacak (LLTODO/STATE.md "Active Handover Notes" → @hermes):**
1. İki review'in bulgularını plana entegre et: **kapsam daraltma**, **görsel
   standartlar**, **CAC/gelir gate'leri**.
2. `LLTODO/STATE.md` → P-001 durumunu `CONSENSUS_REACHED` yap.
3. **T-001'i claim et** (`LLTODO/tasks/IN_PROGRESS/`), implementasyona başla
   (FAZ 3: T-001/T-002/T-003).
4. Append-only + claim kurallarına uy (`git add -A` YASAK, spesifik add).

**Acceptance:** plan revize + STATE güncel + T-001 claimed + ilk implement commit.
→ FAZ 4 ULTRAREVIEW (UR-001 @claude, SLA 24h).

**Ref:** `LLTODO/plans/P-001-u2algo-wave1-tradingview.md`, `LLTODO/reviews/R-001*.md`,
`R-002*.md`, `LLTODO/SCOREBOARD.md`.

---

## GÖREV 2 — LLTODO global scaffolding → master
**Durum:** LLTODO v2 sistemi `feat/zone-touch-confirmation`'da yaşıyor, master'da YOK.
Branch modeli (R1): **global `[M]` dosyalar master'da**, epic işi (P-001 plans/reviews/
tasks) kendi epic-branch'inde.

**Yapılacak:**
1. master'a PR aç: SADECE global scaffolding (`LLTODO/README.md`, `STATE.md`,
   `SCOREBOARD.md`, `templates/`, `scripts/lltodo_lint.py`, `tests/test_lltodo_lint.py`,
   ilgili `PROMPT-*.md`). **Epic-spesifik P-001 dosyalarını DAHİL ETME** (onlar branch'te kalır).
2. `scripts/lltodo_lint.py` 8 test yeşil olsun.
3. gstack entegrasyonu (`.hermes/plans/`, CLAUDE.md skill-routing notları) — additive,
   istersen aynı PR'a veya ayrı.

**Acceptance:** LLTODO master'da kanonik, lint yeşil. → Claude review.

---

## GÖREV 3 — Strategy-opt candidate deploy kararı
**Durum:** `configs/candidate_opt_best.yaml` (gitignored) = phase2_1k +
min_confluence 50→75, recency_bars 40→20. OOS doğrulandı: Sharpe 0.17→0.43,
PF 1.53→2.76, WR 51→59%, DD 2.2→0.7%. PENDING (deploy edilmedi).

**Yapılacak:** prod config'e (phase2_1k conf50→75 + rec40→20) uygulanacaksa
feature-branch + backtest re-verify + operatör onayı + rebuild. Karar + deploy senin.
**Ref:** `docs/handoff/strategy_parameter_optimization_report.md`.

---

## GÖREV 4 — Prod/branch reconciliation (deploy hygiene)
**Durum (önemli):** prod `feat/pr1-identity-tokens` @ `ca92ce7` çalışıyor (master değil).
master'ın #172/#173 (content pipeline, flags-OFF) + #174 (frontend fix) + #175
(entry-slippage, default-safe) prod'da YOK. `bebcc8c` (u2algo token-sync) prod'da
var ama master'da yok.

**Yapılacak:**
1. `feat/pr1-identity-tokens` / `bebcc8c`'i master'a entegre et (PR) — VEYA neden
   ayrı tutulduğunu belgele.
2. Prod'u master'a hizalama planı: tümü default-safe/flags-OFF olduğundan davranış
   değişmez, ama **flat-book + operatör onayı + AUTOSTART=0 → manuel start** akışı.
3. ⚠️ breaker OPEN (healthz 503, pre-existing) — reset operatör kararı.

**Acceptance:** prod↔master topoloji netleşmiş + hizalama PR/planı. → operatör onayı → deploy.

---

### Bitince
Her görev: branch + PR (master) + test. Claude'a "review" sinyali ver.
Açık iş kalmayınca SCOREBOARD güncelle.
