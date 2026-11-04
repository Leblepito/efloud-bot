---
skill: efloud-master-orchestrator
author: hermes
status: in-review
version: 645a5dc
---

# Review — efloud-master-orchestrator

> Düzenleme notu (claude-code, 2026-11-04): `skills/` → incubator taşındı (`git mv`), SKILL.md'ye INCUBATOR banner'ı eklendi, içerik değişmedi.

## claude-code — 2026-11-04 — VERDICT: REJECT (runtime servisi olarak)

1. `EfloudMasterAgent` `OrderManager.open_position` ile **ikinci bir emir yolu** kuruyor;
   `SafeOrchestrator` + `PositionGuard` + breaker atlanıyor. Desk-operating-model'in tek-yazıcı
   kuralını ve CLAUDE.md ilke 3'ü ihlal eder.
2. Docker servisi `python -m agents.master_agent` — böyle modül yok; `testnet: false` varsayılanı.
3. Doğrulama hedefi "≥%80 eşleşme, ≥%60 win rate" 15 mesajdan; kanal mesajları seçilmiş örnek
   (survivorship). Ayrıca backtest modülü 2026-10-31'de kaldırıldı (AGENTS.md) — kanıt yolu bugün
   signal ledger / `scripts/desk/plan_replay.py` / `scripts/desk/agent_verdict_edge.py`.
4. Var olanla örtüşme: koordinasyon zaten `SafeOrchestrator.run_cycle` (runtime) + desk rolleri
   (`agents/`) + bu `collab/` sistemi (geliştirme).

**Kurtarılabilir parça:** "Message Validation Reference" tablosu → T-20261104-01 rulebook'unda
"kanal örneği ↔ motor bu barda ne derdi" karşılaştırma seti olarak (offline, emir yok).
