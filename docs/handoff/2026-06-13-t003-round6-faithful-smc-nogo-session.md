# Session Summary — 2026-06-13

**Konu:** P-001 T-003 (u2algo Wave-1 Pine STRATEGY) — backtest gate turları + faithful-SMC brainstorming/prototip
**Branch:** `feat/p001-t003-strategy` (PR #194, DRAFT/BLOCKED) · izole worktree `C:/tmp/wt-t003`
**Model:** Opus 4.8 (1M context) · uzun oturum

## What We Did

1. **GATE_RUN_2 (round-4, limit-at-OB entry) → FAIL.** 5 perp 15m (BTC/ETH/SOL/BNB/XRP), `allow_ob_less=true`. count=168 PASS, inverted/subRR=0 PASS, AMA WR ~%10-15, agg PF 1.44<1.5, **limit-fill ~%41** (9-60 değişken; ETH %9). G-T4b OOS-Sharpe değerlendirilemez (`bt_oos_pct` ÖLÜ input). Latent bug: `bt_date_end` default=2025 → 2026 verisinde 0 trade. Rapor + PR yorumu + commit `72e9755`.
2. **Round-5 (market-at-close entry) IMPLEMENTE + GATE_RUN_3 → FAIL (decisive).** Hermes patch'i VPS'te kaldı/erişilemedi → Claude spec'ten implemente etti. smc-strategy-reviewer APPROVE_WITH_NITS (B-01 spec senkronu + H-01 unused-var fix). count=270 PASS AMA **agg PF 0.71<1, net −%14.3, 4/5 kaybeden, MaxDD>%5**. Fill ~%100 oldu ama edge yok. Commit `f24f736`.
3. **Brainstorming → spec → plan (superpowers).** Engine keşfi: canlı Python engine zone-pullback yapar (`safe_orchestrator.py:1648-1697`), entry zone = FVG/OTE (`zones.py`, OB değil!), TP = likidite EQH/EQL + FVG (`tp_calc.py`), Breaker = mitigated OB (`became_breaker`). Kararlar: sadık-engine-port, Mode-B zone-touch, kapsam TP+BB. Spec + plan `docs/superpowers/` (commit `3d66916`/`614c779`).
4. **Round-6 prototip (subagent-driven).** FVG + EQH/EQL + Breaker Pine detektörleri (3 implementer subagent) + engine-faithful TP (likidite/FVG precedence, min_rr-gate, single-target — `tp1*1.02` hack'i yok) + near-edge zone-pullback entry. **G-T3 compile PASS (0 marker, ~580 satır array-Pine).**
5. **GATE_RUN_4-prelim → NO-GO.** Round-6 (OB-only): 15 trade/5sem (frekans çökme). Round-6b (FVG/OTE+gevşek sinyal, operatör onaylı): frekans+fill ÇÖZÜLDÜ (BTC 69/ETH 110, %38-58 fill) AMA edge negatif (PF 0.66-0.84). Commit `8077e0a`.

## Decisions Made

- **Hermes round-5 patch'i supersede edildi** — VPS'te erişilemedi, Claude spec'ten implemente etti; origin = source-of-truth (divergence önlendi).
- **Round-5/6 boyunca pragmatik subagent-driven adaptasyonu** — implementer subagent'lar kod yazdı; orchestrator (Claude) TV-compile/backtest + coupled trade-logic rewire + commit'leri yaptı (TV stateful/tek-instance + branch güvenliği).
- **Validation-first kill-switch** — round-6'da 600+ satır finalize/SENKRON/spec yazılmadan, prototip backtest'iyle edge yokluğu yakalandı.
- **Stratejik çatal → İKİSİ DE yapılacak, öncelik sırası:** (1) **indicator-only ship** (bounded, ticari değer, dürüst — `wave1_signals.pine` round-6 detektör/TP görseliyle SENKRON-port → TV publish → site), (2) **Wave-2 tam redesign** (CHoCH/BOS engine port, ayrı epic, ticari MVP'yi bloklamaz).

## Key Learnings

- 🔑 **KAPSAMLI BULGU (4+ tur): Wave-1 SMC sinyali tradeable edge taşımıyor.** Strateji yeterli trade ürettiğinde edge HEP negatif (round-5 PF 0.71, round-6b 0.66-0.84); pozitif edge sadece round-4'ün seçici+derin-limit'inde belirdi (PF 1.44, %41 fill, marjinal). **Sorun ENTRY MEKANİZMASI DEĞİL** — fill↔edge takası, entry uzayı tükendi (limit-deep / market / zone-pullback OB / FVG-OTE).
- Engine'in canlı edge'i bile mütevazı (Gemini backtest PF 1.15) → Wave-2 büyük emek, belirsiz getiri.
- TV MCP: internal-api strateji okuma KIRIK → diagnostik `table.new` + `data_get_pine_tables` tekniği (sayaç + `strategy.*` built-in). Sembol değişince `chart_ready=false`, ~6s bekle. Input ID `in_N` deklarasyon sırası. `pine_set_source` "Could not open Pine Editor" → `ui_open_panel pine-editor` open.
- Pine v6: `for i=0 to size-1` boş array'de 0-iterasyon (güvenli); fonksiyon-içi-fonksiyon + global-array erişimi OK; `array<T>` API derleniyor.

## Open Threads

- **Öncelik 1 (indicator-only ship):** round-6 detektörlerini (FVG/EQH-EQL/Breaker + engine-TP görseli) `wave1_signals.pine`'a SENKRON-port → G-T2 compile → TV publish → site/P-002/P-003 entegrasyonu.
- **Öncelik 2 (Wave-2 redesign):** yeni spec (CHoCH/BOS trigger + tam FVG/OTE + confirmation) → plan → prototip → gate. Ayrı epic.
- **#194 BLOCKED** — merge edilmez (strateji shippable değil). Korunan iş: detektörler + engine-TP + bt_date fix + OOS-split (derleniyor, PR'da).
- Paralel açık (Claude değil): Gemini entry-slippage (HALTED), operatör-gated prod hizalama/breaker reset. ⚠️ VPS `/opt/efloud-bot` HEAD Hermes branch'inde (`d6b3b22`) — rebuild öncesi prod/master'a dön.

## Tools & Systems Touched

TradingView Desktop MCP (compile/backtest/pine_tables), izole git worktree `wt-t003`, superpowers (brainstorming/writing-plans/subagent-driven-development/wrapup), smc-strategy-reviewer subagent, 3× general-purpose implementer subagent, GitHub PR #194, LLTODO (STATE/reports/lint), engine Python kaynakları (smc.py/smc_v2/safe_orchestrator referans-okuma).
