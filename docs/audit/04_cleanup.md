# 04 — Artifact Cleanup (efloud-bot)

> Phase 4 deliverable. Repo kökü bilgi mimarisini eskimişten arındırma ÖNERİLERİ.
> ⚠️ Hiçbir şey bu audit'te SİLİNMEDİ — bu bir öneri listesidir (aksiyon + gerekçe + risk).
> Kaynak: Phase 1 ops/config Explore agent envanteri + Phase 2/3 bulguları. Tarih: 2026-06-02.

---

## 0. Özet
| Aksiyon | Adet | Not |
|---|---|---|
| SİL (dead) | 1 | superagentv3.py |
| ARŞİVLE (`docs/archive/` veya `configs/archive/`) | 7 | *.original.md, PR_BODY, MAINNET rehberi, aggressive_v1 |
| TAŞI (`scripts/diag/`) | ~8 | root test_*.py stale CLI smoke'lar |
| BİRLEŞTİR | 3 grup | CLAUDE*.md, HERMES*.md, daily_report ikilemesi |
| BANNER/işaretle | 2 | aggressive_v1 DO-NOT-DEPLOY, candidate_opt auto-gen |
| KORU (yanlışlıkla silinmesin) | — | docs/results/, configs/archive/ |

---

## A. Kök Python dosyaları

| Dosya | Aksiyon | Gerekçe | Risk |
|---|---|---|---|
| `superagentv3.py` | **SİL** | DeepSeek/Kimi/MiniMax generic harness; bot'ta hiçbir yerde import edilmiyor (Phase 1: "DEAD, stray research file") | Yok — referanssız |
| `test_regime.py` | **TAŞI** `scripts/diag/` | Hardcoded `/home/claude/efloud-bot` sys.path → Windows'ta kırık; CI-dışı diagnostic | Düşük — manuel araç |
| `test_safety.py` | **TAŞI** `scripts/diag/` | Aynı hardcoded Linux path; pytest-collected değil | Düşük |
| `test_doge_diagnose.py` | **TAŞI/SİL** | One-off DOGE incident trace; incident kapandı; canlı ccxt | Düşük |
| `test_smoke.py` | **TAŞI** `scripts/diag/` | Manuel canlı-data smoke; CI-dışı; `test_real_data.py` ile örtüşür | Düşük |
| `test_offline.py` | **TAŞI** `scripts/diag/` | Offline orchestrator smoke; iyi dev aracı ama formal suite değil | Düşük |
| `test_real_data.py`, `test_real_backtest.py`, `test_smoke.py` | **TAŞI** `scripts/diag/` | Network gerektiren manuel smoke'lar; pytest CI'da değil | Düşük |
| `test_backtest.py`, `test_backtest_multi.py` | **TAŞI** `scripts/diag/` | Root integration smoke (sentetik); resmi suite `backend/tests/` | Düşük — backend/tests/ gerçek coverage |
| `test_v2_2_0.py` | **TAŞI** `scripts/diag/` | Standalone print-based, pytest-collected değil | Düşük |

> **NOT (kök test_*.py karışıklığı):** Bunlar pytest tarafından TOPLANIYOR olabilir (isim `test_*`). `pyproject.toml`/`pytest.ini`'de `testpaths = backend/tests` yoksa, CI bunları collect edip network/path hatası verir. Phase 2 §7.2 H1/H2 dışındaki collect davranışını kontrol et. **Aksiyon:** ya `scripts/diag/`'a taşı (collect edilmez) ya da `pytest.ini`'ye `testpaths`/`norecursedirs` ekle. Risk: yanlış taşıma test coverage düşürmez (bunlar zaten CI-dışı), ama `pytest.ini` yoksa lokal `pytest` koşusunu temizler.

## B. Kök *.md dokümanları (birleştir/arşivle)

| Dosya | Aksiyon | Gerekçe | Risk |
|---|---|---|---|
| `CLAUDE.original.md` | **ARŞİVLE** | CLAUDE.python.md (condensed) + CLAUDE.md tarafından supersede; eski Ualgo/U2algo mimarisi | Yok |
| `HERMES.original.md` | **ARŞİVLE** | HERMES.md (2026-05-28) tarafından supersede; eski (2026-05-24, SHA 3fa88b8) | Yok |
| `PR_BODY.md` | **ARŞİVLE/SİL** | 2026-05-11 SL/TP fix PR body; o fix merge oldu; canlı PR değil | Yok |
| `MAINNET_GECIS_REHBERI.md` | **ARŞİVLE** `docs/runbooks/` | Phase 1→2 transition tamamlandı; tarihsel runbook | Yok — referans değeri var, sil değil arşivle |
| `CLAUDE.md` + `CLAUDE.python.md` | **BİRLEŞTİR → tek `CLAUDE.md`** | İki Claude memory; CLAUDE.md Pine + bot durumu karışık, CLAUDE.python.md condensed | Orta — ikisi farklı amaçlı olabilir; birleştirmeden önce diff |
| `HERMES.md` | KORU | Güncel operatör rehberi (2026-05-28); ama VPS state snapshot bölümü stale, "live değil" notu ekle | Düşük |
| `AGENTS.md`, `GEMINI.md`, `RISK_MAP.md`, `README.md` | KORU | Güncel; AGENTS.md Runtime Agent Team aktif, README ecosystem, RISK_MAP evergreen | — |

> **Hedef:** tek tutarlı doküman seti — `CLAUDE.md` (Claude context), `AGENTS.md` (agent mimarisi), `HERMES.md` (operatör), `README.md` (ecosystem), `RISK_MAP.md` (failure modes). `*.original.md` + `PR_BODY.md` + `MAINNET_GECIS_REHBERI.md` → `docs/archive/`.

## C. Config'ler

| Dosya | Aksiyon | Gerekçe | Risk |
|---|---|---|---|
| `configs/config.aggressive_v1.yaml` | **BANNER + `configs/archive/`'a taşı** | CROSSED+hedge=true, PR A (ISOLATED+one-way) doktrinine aykırı; `EFLOUD_CONFIG_PATH` buna işaret ederse güvenlik duruşunu sessizce geri alır (02_findings F3.2). FIL auto-flip incident config'i | **YÜKSEK eğer aktif kullanılırsa** — ama +49% validated; SİLME, arşivle + DO-NOT-DEPLOY banner |
| `config.yaml` (kök) | **testnet/dry_run template'e indir + banner** | smc_version=v1, swing_lookback=4 (diğerleri 5), starting_balance=10000 — divergent; `python main.py` argsız bunu alır (02_findings F3.1) | Orta — CLI default; swing_lookback→5 hizala |
| `configs/candidate_opt.yaml` | **işaretle (auto-gen)** veya `configs/archive/` | Grid search çıktısı, doğrudan deploy edilmemeli (güvenlik blokları eksik) | Düşük |
| `configs/config.testnet.yaml` | **GÜNCELLE** (prod aynası yap) | Severely stripped (margin_mode/smc_version/agent_team/safety blokları yok) — gerçek testnet aynası değil | Orta — testnet doğrulaması güvenilmez |
| `configs/archive/*` | **KORU** | Config evrim tarihi; preflight/bot_runner default'u burayı işaret ediyor (F3.6 — default'u düzelt ama klasörü tutma) | — |
| `configs/config.phase2_micro.yaml` (archive) | **KORU + default'ları düzelt** | preflight.py:105 + bot_runner.py:33 buna işaret ediyor ama kökte YOK (F3.6) | Yüksek — default landmine, kod tarafını düzelt |

## D. scripts/

| Dosya | Aksiyon | Gerekçe |
|---|---|---|
| `scripts/generate_daily_report.py` | **DEĞERLENDİR/SİL** | `ops/daily_report/` email pipeline tarafından muhtemelen supersede |
| `scripts/print_remote_positions.py` | **KORU + path düzelt** | Ops diagnostic faydalı ama hardcoded `/app/state_1k/positions.json` |
| `scripts/autoresearch/results.tsv` | KORU (generated state) | Optimization geçmişi; source değil ama veri |
| Diğer scripts (run_phase_a/c, prefetch, evaluate_gates, supabase, bigquery) | KORU | Aktif backtest/ops araçları |

## E. .claude/ ve MCP

| Öğe | Aksiyon | Gerekçe |
|---|---|---|
| `.mcp.json` | **GÖZDEN GEÇİR** | Sadece `github` tanımlı (npx server-github). TradingView MCP user/global seviyede (Pine işi için). MCP github PAT bu oturumda **bad credentials** verdi → token rotasyonu + restart gerekli. Çakışan/disconnected server yok ama github token health kontrol et |
| `.claude/settings.json` graphify hook | **DEĞERLENDİR** | PreToolUse Bash hook'u grep/find'da graphify reminder enjekte ediyor + pre-commit auto-update çalışıyor (her commit'te AST rebuild, ~570 dosya). graphify-out/ artık gitignored (PR #116). Hook gerekli mi? Commit latency'si var. **Öneri:** koru ama pre-commit auto-update'i opsiyonel yap |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | KORU | Agent team feature aktif kullanılıyor |
| `.claude/settings.local.json` (372 satır) | **KORU (dev state)** | Birikmiş allow-list; mimari değil; dokunma |
| `.claude/skills/efloud-*` | KORU | Aktif (bugfix-workflow, deploy-safety, trading-risk-checklist, forex-adapter-research, uiux-audit) |
| `.claude/skills/writing-plans, claude-automation-recommender` | KORU | Parent workspace'ten; geçerli |
| `.claude/agents/` (9 lokal + #117'nin 4'ü) | **bkz. Phase 6** | efloud-explorer vs Explore, efloud-risk-ops-reviewer vs risk-safety-auditor olası örtüşme — 06_agent_team.md'de ele alındı |

## F. graphify-out/
- `graphify-out/` artık gitignored (PR #116, 53MB AST artifact untrack edildi).
- Pre-commit hook her commit'te `graphify update .` çalıştırıyor (bu audit commit'lerinde de çalıştı, AST rebuild 569→570 dosya).
- **Aksiyon:** Hook aktif ve çalışıyor; gerekli değilse (graphify query aktif kullanılmıyorsa) commit latency'sini azaltmak için pre-commit auto-update'i kaldır. Risk: yok (artifact derived).

---

## G. Risk-sıralı cleanup önceliği
1. **YÜKSEK (landmine):** `preflight.py`/`bot_runner.py` default config path düzeltme (F3.6) — kod fix, cleanup'tan önce roadmap.
2. **YÜKSEK (güvenlik):** `aggressive_v1.yaml` DO-NOT-DEPLOY banner (F3.2).
3. **ORTA:** kök `config.yaml` template/banner + swing_lookback hizalama.
4. **DÜŞÜK:** *.original.md / PR_BODY / superagentv3.py arşivle/sil.
5. **DÜŞÜK:** kök test_*.py → scripts/diag/ + pytest.ini testpaths.

> **Genel risk notu:** Tüm cleanup canlı botu etkilemez (dosya organizasyonu); config banner'ları ve preflight default fix'i tek istisna — onlar davranışsal, roadmap'te kod-değişikliği olarak ele alınmalı. `docs/results/` ve `configs/archive/` ASLA silinmez (kanıt arşivi).
