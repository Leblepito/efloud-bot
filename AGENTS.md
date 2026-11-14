# AGENTS.md — AI Agent Context (efloud-bot)

> Her AI modeli (Claude, Gemini, Hermes, Codex) bu dosyayı okuyarak projeye
> sıfırdan giriş yapabilir. Kapsamlı referans için `skills/social-publishing/SKILL.md`.

## Proje: efloud-bot

Binance USDT-M futures üzerinde SMC doktriniyle otonom trade botu.
Python (CCXT, FastAPI) + TradingView Pine Script v6.

## Güncel Algoritma Durumu

Bu dosya algoritma durumunu kopyalamaz (elle kopyalanan sayılar bayatlıyordu).
Canlı giriş akışı, terimler ve canlıda etkili/inert config anahtarları: `CONTEXT.md`.
Anlık canlı durum (deploy, bot konteynerleri, açık sorular): `collab/STATUS.md`.
Kısa özet: canlı motor SMC v2 LuxAlgo modudur (`configs/config.phase2_1k.yaml:180-188`),
giriş entry-TF engulfing kapanışında **MARKET** emirdir (`exchange/__init__.py:1151-1153`).

## Kritik Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `docs/runbooks/operator-runbook.md` | Operatör runbook'u (deploy, config, incident); `HERMES.md` artık yönlendirme |
| `CLAUDE.md` | Proje bellek, mimari, Pine Script kuralları |
| `skills/social-publishing/SKILL.md` | Sosyal medya pipeline'ı (HER modele) |
| `AGENTS.md` | Bu dosya — AI giriş noktası |
| `configs/config.phase2_1k.yaml` | Production config (risk/safety/engine) |
| `engine/smc_v2/triggers.py` | v2 trigger (CHoCH+BOS → SetupCandidate) |
| `engine/safe_orchestrator.py` | Ana orchestrator (v1 susturma + v2 entry) |

## Ortak çalışma — `collab/` (YENİ 2026-11-04)

Üç model (claude-code, hermes, abacus) eşzamanlı çalışır. Giriş: `collab/README.md`
(protokol: görevler `collab/tasks/`, model başına append-only log `collab/log/<model>.md`
ve `VPS: DEPLOYED|NOT-DEPLOYED: DEMO|N/A` notu, çıktılar `collab/outputs/<model>/`, skill
taslakları `collab/skills-incubator/` → review → `skills/`). Modeller: `collab/MODELS.md`,
pano: `collab/STATUS.md`, MCP kaydı: `collab/mcp/README.md`. Ham veri git dışında
(`~/efloud-collab-private/`, VPS `/root/efloud-collab-private/`) — repo PUBLIC.

## Desk Plugin — çok-ajanlı masa (YENİ 2026-11-03)

Repo kökü bir Claude Code plugin'idir (`efloud-desk`, `.claude-plugin/`): roller
`agents/` (market-analyst, research-analyst, strategist, risk-manager, execution-ops,
trade-reviewer, pine-engineer), skill'ler `skills/`, canlı-yazma kapısı
`hooks/live_write_gate.py`. Her agent kendi skill'lerini `skills:` frontmatter'ı ile
otomatik yükler. Araştırma araçları: `scripts/desk/plan_replay.py` (Monte Carlo plan
oranları), `scripts/desk/tradingagents_brief.py` (TradingAgents advisory brief — izole
`.venv-research`, `requirements-research.txt`). TradingView Desktop MCP:
`skills/tradingview-mcp/SKILL.md`.
Tüm roller önce `skills/desk-operating-model/SKILL.md`'yi okur: motor tek emir
göndericisidir, canlı sistem değişiklikleri ticket + Risk PASS + operatör onayı ister.
SMC/LuxAlgo referansı: `skills/luxalgo-smc/SKILL.md`.

Kurulum (Claude Code): `/plugin marketplace add Leblepito/efloud-bot` →
`/plugin install efloud-desk@efloud`. Tasarım + runtime yol haritası:
`docs/handoff/2026-11-03-multi-agent-desk-design.md`.

## Sosyal Medya Pipeline'ı (YENİ 2026-07-26)

Tek komut: `python -m scripts.daily_social_run --date $(date -u +%F)`

Bot sinyali → chart PNG (ENTRY/SL/TP) → MP4 klip → X/IG/YT paketleri.
Üç güvenlik kapısı (hepsi default KAPALI): onay, live, platform flag'leri.

Detay: `skills/social-publishing/SKILL.md`

## Kurulum

Yeni kullanıcı: `cp .env.example .env && docker compose up -d --build` (README.md). VPS: `deploy/deploy.sh` + `docker-compose.prod.yml`.
Backtest modülü `backtest/` mevcut (2026-10-31'de `562a6a3` ile kaldırılmış, #335 ile geri
yüklendi): `python -m backtest.cli single|portfolio --config configs/config.phase2_1k.yaml`.

## Test

```bash
python -m pytest --ignore=external_repos --import-mode=importlib -q
```

Modül regresyonu: `REGRESSION.md` (üretilmiş defter). Değişiklikten sonra
`python scripts/regression_ledger.py run --base origin/master` → değişen modül + bütün
downstream tüketicileri koşar; karar çıkış kodudur. Modül tablosu değişince
`python scripts/regression_ledger.py render`.
Test varlıkları ve korunması gereken kurallar (TEST-ID → kanıt): `TESTS.md`.
Alan dili (V1/V2 bot vs SMC v1/v2, breaker OPEN=normal, orphan vs bare): `CONTEXT.md`.
Geri dönmesi zor kararlar ve gerekçeleri: `docs/adr/README.md`.

ECC kural paketi (yalnız lokal: `.claude/` `.gitignore:122` ile repo dışı — bu import'lar
VPS'te ve başka klonlarda çözülmez). Çatışmada proje sözleşmesi (CLAUDE.md Karpathy
ilkeleri) önceliklidir:

@.claude/rules/ecc/README.md
@.claude/rules/ecc/common/agents.md
@.claude/rules/ecc/common/code-review.md
@.claude/rules/ecc/common/coding-style.md
@.claude/rules/ecc/common/development-workflow.md
@.claude/rules/ecc/common/git-workflow.md
@.claude/rules/ecc/common/hooks.md
@.claude/rules/ecc/common/patterns.md
@.claude/rules/ecc/common/performance.md
@.claude/rules/ecc/common/security.md
@.claude/rules/ecc/common/testing.md
