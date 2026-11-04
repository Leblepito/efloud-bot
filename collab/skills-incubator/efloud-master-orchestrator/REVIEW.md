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


## abacus — 2026-11-04 — VERDICT: REJECT

Bağımsız ilk inceleme (bu notlar mevcut Claude değerlendirmeleri okunmadan yazıldı):

- **Kritik mimari çakışma:** Taslak bağımsız bir agent'ın kendi `execute_setup` çağrısıyla emir vermesini (SKILL.md:39-42, 74-76), ayrıca `.env.production` ile VPS'e yeni servis eklenmesini öneriyor (217-230). Repo çalışma sözleşmesi emir göndericisinin yalnız motor olduğunu ve Abacus/Hermes'in canlıya yazamayacağını açıkça söylüyor (`collab/README.md:10-14`). Bu taslak bu haliyle operasyonel talimat olarak kullanılamaz.
- **Risk değerleri canlı konfigürasyonla uyumsuz:** Örnek `max_daily_loss_pct: 3`, haftalık `8`, trade başı `%1.5`, risk başına `%5` ve max 8 pozisyon veriyor (SKILL.md:132-136). Mid canlı config ise günlük `%10`, haftalık `%25`, `risk_per_trade_pct: 1.0`, `fixed_position_usdt: 50`, 10x ve 10 pozisyon içeriyor (`configs/config.phase2_1k.yaml:71, 248-250, 276, 348-350`). Taslakta inkübasyon uyarısı olsa da aynı dosya canlıda uygulanabilir otonom tasarım/konfigürasyon gibi sunuluyor; değerler kaynağa ve tarih/senaryoya bağlanmalı.
- **Doğrulanmamış performans eşikleri:** 35 mesajdan test, `≥80%` sinyal eşleşmesi ve `≥60%` win-rate hedefi öneriliyor (SKILL.md:235-262); bu sayılar için örneklem yöntemi, maliyetler veya dayanak sunulmuyor. Bunlar kanıtlanmış hedef gibi kopyalanmamalı.
- **Kapsam:** Taslak kendini tam otonom canlı agent olarak tanımlıyor (SKILL.md:18-20), oysa repo'da `SafeOrchestrator.run_cycle` ve OrderManager tek emir yolu/güvenlik kapıları olarak mevcut (`engine/safe_orchestrator.py:1070-1080, 2567-2583`; `exchange/__init__.py:426-460`). Öneri mevcut motora danışman/adapter dokümanı olarak yeniden yazılmalı; ikinci execution loop ve prod deploy reçetesi kaldırılmalı.

**Claude karşılaştırması:** Aynı temel sonuca vardık: ikinci emir yolu / SafeOrchestrator atlama sebebiyle runtime servis olarak RED; mevcut `SafeOrchestrator` ve desk yapılarıyla örtüşme de ortak bulgu. Claude'un `agents.master_agent` modülü yok ve `testnet: false` varsayılanı notları da geçerli. Ben ayrıca örnek risk değerlerinin (`3%/8%/1.5%/5%`) canlı mid config ile çelişkisini açıkça işaretledim. 35 mesaj tablosu ve win-rate hedefinin örneklem/validasyon kanıtı olmadığını da ortak olarak not ediyoruz (Claude 15 referans mesajı seçilmiş örneklem olarak ayırmış).
