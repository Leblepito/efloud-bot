---
id: T-20261106-04
title: ECC skill backlog — 14 PR'lık geliştirme + denetim iş listesi
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: null
created: 2026-11-06
touches_live: false
---

## Amaç
ECC (`affaan-m/ECC`) skill setinden (`.agents/skills` 47 + `skills` 314) efloud-bot'a
uyanlar seçildi ve tek-PR-bir-iş sırasıyla iş listesine çevrildi. Bu PR = madde 1
(doküman düzeltmesi) + listenin kendisi. Her sonraki madde ayrı task + ayrı PR.

## Girdi
- Skill kaynağı: ECC repo (`git@github.com:affaan-m/ECC.git`), laptop kopyası `Downloads/ECC-main`.
- Kurulum: laptop `.claude/skills/<ad>/` (gitignore'lu, yalnız claude-code oturumu).
  Not: `.claude/skills/ecc/<ad>/` altındaki eski ECC kopyaları iç içe olduğu için
  Claude Code tarafından **keşfedilmiyordu** (ölü kurulum).

## İş listesi (sıra = PR sırası)
Her PR'da ortak süreç: `change-impact` (önce/sonra) · `tdd-workflow` + `python-testing` ·
`verification-loop` · `conventional-commit-review` · risk yollarında `santa-method`.

| # | PR | Skill'ler | touches_live |
|---|---|---|---|
| 1 | Doküman ölü referansları (bu PR) | docs-governance | false |
| 2 | Güvenlik denetimi — repo + git geçmişi + `.claude/` + MCP | ecc-security-review, security-bounty-hunter, agent-security-hardening, mcp-dependency-review, `/security-scan` | false (rapor) |
| 3 | `REGRESSION.md` modül regresyon defteri | module-regression, change-impact | false |
| 4 | `TESTS.md` TEST-ID kaydı (audit C1–C4/H1–H7, bughunt) | test-collaboration, ai-regression-testing | false |
| 5 | ADR backfill + `CONTEXT.md` sözlük | architecture-decision-records, context-and-decisions | false |
| 6 | LLM ajan katmanı denetimi (veto yolu) | llm-trading-agent-security, agent-architecture-audit | false (rapor) |
| 7 | SEO — Google (robots/sitemap/schema/CWV) + Meta (Open Graph / paylaşım kartları) | seo, `seo-specialist` ajanı | false |
| 8 | Sosyal içerik sistemi — marka sesi + platform uyarlama + onay döngüsü | brand-voice, content-engine, crosspost, x-api, operator-approval-loop, article-writing | false |
| 9 | Video — render hattı (ffmpeg/ElevenLabs) + dashboard demo videosu | video-editing, ui-demo | false |
| 10 | Prod hazırlık + deploy sonrası canary | production-audit, deployment-patterns, docker-patterns, canary-watch | false (script) |
| 11 | Backend + DB (FastAPI, migrations, Supabase waitlist) | fastapi-patterns, database-migrations, postgres-patterns, error-handling | false |
| 12 | Backtest hızı (byte-identical kapı) | benchmark-optimization-loop, recursive-decision-ledger | false |
| 13 | LLM maliyet/gecikme + eval seti, WS tazelik | cost-aware-llm-pipeline, prompt-caching-strategy, eval-harness, latency-critical-systems | false |
| 14 | Yaşayan dokümanlar (CLAUDE.md anayasa/durum ayrımı) | living-docs-governance, brownfield-retrospective | operatör kararı |

Kurallar:
- Repo PUBLIC → güvenlik bulgularının istismar edilebilir ayrıntısı PR/issue'ya yazılmaz;
  private store'a (`~/efloud-collab-private/`) gider, PR'da yalnız nötr fix açıklaması.
- Mainnet trade mantığına dokunan her fix: risk-ops review + operatör onayı (CLAUDE.md Karpathy #1).
- Bilinçli atlananlar: ECC `security-review` (built-in `/security-review` ile isim çakışması →
  `ecc-security-review` adıyla kuruldu), `orch-*`/`security-scan` (komut olarak zaten var),
  `social-publisher` (SocialClaw; biz Composio kullanıyoruz), `fal-ai-media` (fal MCP yok; Higgsfield).

## Beklenen çıktı (Definition of Done)
- [x] `CLAUDE.md`'deki 2 ölü referans (`f96b7d8`'de silinen handoff'lar) git-geçmiş yoluna çevrildi
- [x] İş listesi bu dosyada
- [x] Madde 2–14 her biri kendi task'ı + PR'ı ile (durum 2026-11-07, aşağıda)

## İlerleme (2026-11-07)

| # | Durum | PR / task |
|---|---|---|
| 1 | ✅ | #302 |
| 2 | ✅ rapor + 7 düzeltme + TP/SL/orphan uyarıları | #303–#316 |
| 3 | ✅ | #317 (T-20261107-12) |
| 4 | ✅ | #319 (T-20261107-13) · yan bulgu #318 |
| 5 | ✅ | #320 (T-20261107-15) |
| 6 | ✅ rapor · A3/A4 düzeltildi + deploy | #321, #322, #323 · **A1/A2 operatör kararı** |
| 7 | ✅ canlıda doğrulandı | #324 (T-20261107-18) |
| 8 | ✅ | #325 (T-20261107-19) |
| 9 | ✅ seslendirme kesilmesi + ses seviyesi | #327 (T-20261107-21) · **demo videosu: operatör kararı (hangi veri)** |
| 10 | ✅ canary canlıda ALL GREEN | #326 (T-20261107-20) |
| 11 | ✅ kusur yok | #328 (T-20261107-22) |
| 12 | ✅ | PR (T-20261108-01): 2.1× faster, byte-identical (memo of identical HTF/daily analyses + no `iterrows`) |
| 13 | ✅ ölçüm raporu | #328 · **L1 (yapı doğrulama) operatör + risk-ops kararı** |
| 14 | ◐ kısım 1 | #329 (T-20261107-23) · **kısım 2 (CLAUDE.md anayasa ↔ durum ayrımı) operatör kararı** |

## Kısıtlar
- Kod değişikliği yok; yalnız `CLAUDE.md` 2 satır + collab dosyaları.
- `.mcp.json` github sunucusu sürüm sabitlenmemiş (`@modelcontextprotocol/server-github`, HIGH) —
  gözden geçirilmiş sürüm bilinmediği için bu PR'da sabitlenmedi; madde 2'de ele alınacak.

## Log
- 2026-11-06 claude-code: ECC skill taraması + kurulum; docs-governance audit (1704 kırık link, 1693'ü `external_repos/`; proje-içi gerçek 2); CLAUDE.md fix + backlog.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
