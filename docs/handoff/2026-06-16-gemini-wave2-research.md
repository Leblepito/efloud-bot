# 🟦 Gemini — Görev: Wave-2 Yeni-Edge Research & Design Proposal (Track 2 / Faz 0) — 2026-06-16

> Hazırlayan: Claude. Bitince Claude review eder → Track-2 brainstorm'una girdi olur.
> Kurallar: canlı mainnet bot → docs-only bu fazda (KOD/strateji DEĞİŞTİRME), feature-branch + PR, secrets repo'ya ASLA.

## 0. Bağlam
Wave-1 SMC stratejisi **NO-GO** (çoklu backtest gate FAIL, negatif/zayıf edge; canlı bot 9 günde −%5.3, %24 WR). Ticari MVP'nin **C-stratejisi** (track record üret → premium fiyat) ancak **gerçek bir edge** olursa işler. **Track 2 = Wave-2 CHoCH/BOS engine redesign** bu yeni-edge hipotezi. Bu görev Track 2'nin **Faz 0'ı: research + tasarım önerisi** (implementasyon DEĞİL — o brainstorm sonrası).

## GÖREV — Wave-2 design proposal dokümanı üret
`docs/handoff/2026-06-16-gemini-wave2-proposal.md` (veya benzer) oluştur, şunları içersin:
1. **Wave-2 yaklaşımı:** CHoCH/BOS tabanlı engine ne demek; market-structure (HH/HL/LH/LL) + break-of-structure + change-of-character mantığı; entry/SL/TP nasıl türetilir.
2. **Wave-1'den farkı:** Wave-1 (OB-retrace + confluence) NEDEN edge taşımadı (çoklu gate FAIL analizi — `LLTODO/reports/REPORT-T-003-gate-run-{2,3}.md` referans); Wave-2 bunu nasıl ele alır (hipotez + neden farklı sonuç beklenir).
3. **Backtest gate kriterleri (öneri):** PF eşiği, WR, OOS-split, rejim-bazlı min sample (≥100/rejim), max-DD, inverted-SL/TP=0, RR-compliance — Wave-1 gate'inden dersler (rejim-etiketleme bug'ı, fill↔edge takası).
4. **İmplementasyon kapsamı (öneri):** hangi engine modülleri (CHoCH/BOS detektör, structure state, entry/SL/TP), tahmini efor, mevcut SMC v2 koduyla ilişki (pine/efloud_signals.pine'a DOKUNMADAN; ayrı modül).
5. **Riskler:** memory notu "engine edge'i bile PF~1.15 mütevazı" — Wave-2'nin de marjinal kalma riski; nasıl erken doğrularız.

## Acceptance
Net, kanıt-temelli bir proposal dokümanı (Wave-1 FAIL analizine dayalı). **Strateji/kod yazma YOK** bu fazda. → Claude review → operatör+Claude Track-2 brainstorm → sonra implement.

## Bitince
branch + doküman + Claude'a "review" sinyali. format-patch + sha256 (VPS) veya doğrudan push.
