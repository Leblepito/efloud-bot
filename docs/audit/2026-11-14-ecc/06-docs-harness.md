# 06 — Doküman ve Agent Harness İnceleme Raporu (2026-11-14)

> Kök: `C:/tmp/wt-ecc-audit` (origin/master `81c2cf7`). Salt okuma; secret değeri okunmadı/alıntılanmadı.
> Ölçüt: living-docs-governance (constitution / map / status / history rolleri) + docs-governance + harness-audit.
> Not: görev metninin başındaki CLAUDE.md örneği (eski, 81 commit geride ana checkout kopyası) bu worktree'deki CLAUDE.md'den FARKLIDIR. Worktree CLAUDE.md 76 satır, "constitution-only" haline gelmiş (`docs/history/claude-md-status-archive.md`, T-20261107-27). Aşağıdaki bulgular worktree'ye göre; ana checkout bu bakımdan bayat (operatörün laptopta okuduğu/yüklediği CLAUDE.md ile master'daki CLAUDE.md farklı — bkz. §7 R1).

## 1. Envanter (ne var, ne işe yarıyor, canlı mı/ölü mü/shadow mu)

### 1.1 Kök ve docs — living-docs rolü ataması

| Dosya | Satır | Önerilen rol | Gerçek durum | Not |
|---|---|---|---|---|
| `CLAUDE.md` | 76 | **constitution** | Kısmen constitution, kısmen bayat Pine-çeviri dönemi talimatı | §3'te ayrıntı |
| `CONTEXT.md` | ~60 | **map (sözlük)** | Güncel, iyi (V1/V2 bot ↔ SMC v1/v2, breaker OPEN=normal) | Referans model; dokunma |
| `docs/adr/README.md` + 0001–0010 | — | **constitution (karar kaydı)** | Güncel; ADR-0003 risk/edge kapısı, ADR-0005 Pine indicator-only | Backfill 2026-11-07 |
| `AGENTS.md` | 89 | **map** (AI giriş noktası) | Karışık: map + 2026-10-02 durum bloğu + "Backtest kaldırıldı" yanlışı | `AGENTS.md:15-27`, `:82` |
| `HERMES.md` | 381 | **map/runbook (operatör)** — şu an status+runbook+rol karışımı | Büyük kısmı 2026-10-02 snapshot'ı; `Master HEAD c8dc5c8` (`HERMES.md:6`) | En bayat kök doküman |
| `README.md` | 245 | **map (public vitrin)** | En güncel kök doküman; İngilizce, public | Eksik: FVG shadow, luxalgo modu |
| `collab/STATUS.md` | ~30 | **status** | CLAUDE.md'nin "güncel durum" işaretçisi — ama 2026-11-07 11:30'da donmuş | `collab/STATUS.md:8-12` |
| `collab/log/claude-code.md` | 331 | **history (append-only)** | Gerçek durum kaynağı fiilen burası (`EF-20261114-01 DEPLOYED bf464d0`) | STATUS'tan 7 gün ileride |
| `CHANGELOG.md` | 75 | **history (müşteri)** | Keep-a-Changelog; "Unreleased" altında "Kaldırıldı: Backtest modülü" — yanlış | `CHANGELOG.md:21` |
| `docs/OPERATOR_GUIDE.md` | 251 | **map/runbook** | 2026-10-02 snapshot tablosu (`:6`, `:89`) | HERMES.md ile %60 örtüşür |
| `docs/repo-cleanup-2026-11-06.md` | 65 | **history** | Tek seferlik denetim notu; `docs/history/`'ye taşınmalı | Backtest/agents kararlarını içerir |
| `docs/history/claude-md-status-archive.md` | — | **history** | Doğru yerde; kendisi "bazı gerçekler bayat" diyor | |
| `docs/handoff/2026-11-03-multi-agent-desk-design.md` | 1 dosya | **history** | AGENTS.md'den linkli "tasarım + runtime yol haritası" | |
| `docs/superpowers/{plans,specs}` | 8 dosya | **history/spec** | Tarihli tasarım dokümanları | |
| `TESTS.md` / `REGRESSION.md` | — | **map** (REGRESSION.md üretilmiş, CI-kontrollü) | Güncel; `tests/ci/test_tests_registry.py` ile doğrulanıyor | Doküman-drift'ine karşı en iyi örnek |
| `THIRD_PARTY_NOTICES.md` | 102 | **constitution (lisans)** | Plugin kaynaklı MIT/CC BY-NC-SA bildirimleri | Bu turda içerik denetlenmedi |

### 1.2 Agent harness

| Yüzey | Konum | Durum | Kanıt |
|---|---|---|---|
| Desk plugin (`efloud-desk` 0.1.0) | `.claude-plugin/plugin.json`, `marketplace.json` | **Canlı (opt-in)**: `/plugin install efloud-desk@efloud`; hooks → `./hooks/live-write-gate.json` | `plugin.json` |
| 7 desk agent'ı | `agents/*.md` (execution-ops, market-analyst, pine-engineer, research-analyst, risk-manager, strategist, trade-reviewer) | Canlı (plugin içinde). `skills:` frontmatter ile skill yüklüyor. `pine-engineer` hâlâ `efloud_strategy.pine`'ı senkron tutmakla görevli (`agents/pine-engineer.md` description) — ADR-0005 ile çelişir | |
| Live-write gate | `hooks/live_write_gate.py`, `hooks/live-write-gate.json` (PreToolUse/Bash, "ask") | Canlı; testli (`tests/hooks/test_live_write_gate.py`). Yalnız komut metnini + doğrudan scripti okur, import izlemez (`live_write_gate.py` docstring) | |
| 13 skill | `skills/*/SKILL.md` | Canlı. 4'ü ≤19 satır "stub" (efloud-deploy 19, -incident 16, -monitor 15, -sync 14, -railway-supabase 15, -journal-analysis 17) | satır sayıları |
| Skill incubator | `collab/skills-incubator/` (5 taslak + REVIEW.md) | Ara durak; `efloud-*` isimleri `skills/efloud-*` ile çakışma riski (master-orchestrator, risk-management, smc-concepts, smc-setup-rules, tradingview-integration) — T-20261104-03/06 hâlâ açık | `collab/tasks/open/` |
| 3 model collab hub'ı | `collab/` (README, SHARED, MODELS, STATUS, models/*, log/*, tasks/open 41 / done 7, prompts/*, outputs/*, mcp/) | Protokol canlı; **fiilen tek aktör claude-code** (log: 331 satır; hermes 3 satır; abacus 86) | `wc -l collab/log/*` |
| CI ajanları | `.github/workflows/{claude-review,hermes-review,scheduled-review}.yml`, `scripts/ci/agents/{risk-safety-auditor,smc-strategy-reviewer}.md` | Canlı; **repoda bu ajanlar `agents/` (desk) ile ayrı bir üçüncü set** | `claude-review.yml:3` |
| Runtime LLM agent ekibi | `engine/agents/` (Overseer/Regime/SignalValidator/RiskReviewer/PostMortem) | **Observation**: `agent_team.enabled: true, gating: false` (`configs/config.phase2_1k.yaml:342-343`); provider openrouter/deepseek; `structure_validation.enabled: false` (`:99-100`) | config |
| `.mcp.json` | kök | Yalnız github MCP, sürüm sabit `@2025.4.8` (T-20261107-09) | `.mcp.json` |
| `.claude/` (rules/ecc, settings, agents, commands, hooks) | **repoda YOK** | `.gitignore:122` → `.claude/` ignore; `git ls-files .claude*` yalnız `.claude-plugin/` verir. ECC kuralları yalnız operatörün laptopunda (`.claude/rules/ecc/common/*`, ana checkout) | `.gitignore:120-126` |
| `.agents/`, `.abacusai/`, `skills-lock.json` | yok | Ignore'lu (`.gitignore:123-125`), repoda yok | |

## 2. Canlı gerçek (şu an prod'da fiilen çalışan davranış)

Kaynak: `configs/config.phase2_1k.yaml` (EFLOUD_CONFIG_PATH; README `Configuration` tablosu + `CONTEXT.md` Live/mainnet satırı), `docker-compose.prod.yml`.

- **Mainnet**, `dry_run: false` (`:312`), `testnet: false` (`:70`), profile `mid` = 15m/4h/12h (`:248`).
- **SMC v2 canlı emir**: `smc_version: v2` (`:90`), `smc_v2_shadow: false` (`:95`), sembol listesi dolu (`:93`).
- **LuxAlgo modu AÇIK** (`:187-188`, `enabled: true`, `kinds: [CHoCH, BOS]`, `tp_mode: luxalgo`, `pullback_timeout_bars: 48`). Config yorumu: "efloud triggers yolu (OB/BB, OTE, FVG, origin swing) devre dışı kalır" (`:180-186`). Yani **AGENTS.md / HERMES.md / OPERATOR_GUIDE'ın anlattığı "OB/BB bölgesi + OTE" giriş akışı canlıdaki yol DEĞİL**; canlıdaki = LuxAlgo BOS/CHoCH + OB + premium/discount + engulfing onay mumu + limit emir. (Kod: `engine/safe_orchestrator.py:1246-1254`, `:3050-3054`.)
- `min_confluence: 50` (risk, `:282`); LuxAlgo içinde ayrı `min_confluence: 1` (`:205`).
- `max_zone_overshoot_atr: 6.0` (`:168`) — dokümanlar 2.0 diyor.
- `max_holding_hours: 0` (süre sınırı KALDIRILDI, `:406-408`, 2026-11-08, EF-20261108-02) + `hold_alert_hours: 24`. Hiçbir kök dokümanda yok.
- `emergency_balance_threshold: 0` (`:424`) — doğru belgelenmiş. `allow_volatile_entries: true` (`:385`) — doğru.
- `min_sl_atr: 2.0`, `v2_use_real_atr: true` (`:110`, BT-22) — kök dokümanlarda yok.
- **Shadow (emir yok)**: `touch_entry: shadow` (`:211`), `fvg_entry: shadow` (`:216`, T-20261114-01, `bf464d0` DEPLOYED — `collab/log/claude-code.md` son giriş). `live` değeri kodda yok (`engine/safe_orchestrator.py:2323-2334`).
- **Observation (shadow ile karıştırılmamalı, `CONTEXT.md`)**: `agent_team.gating: false` (`:343`), Kronos advisory default-off (`:347+`).
- **Compose (prod)**: efloud-bot (V1/mid), efloud-bot-long, efloud-bot-scalp, caddy, autoheal, alerter (`LUX_ALERTS=1`, `TP_ALERTS=1`, `SL_ALERTS=1` — `docker-compose.prod.yml:157-163`), daily-report, overseer (`DRY_RUN=1`, `:218`), overseer-phase0/daily-report, routines (watch+scheduled), kronos-runner. `AUTOSTART=0` (manuel start).
- **Backtest modülü VAR**: `backtest/` (cli.py, engine.py, …) master'da; CLAUDE.md/ TESTS.md `python -m backtest.cli` kullanıyor (#335 restore, #336 hız).
- **Canlı gerçeğin tek doğru tarihli kaynağı**: `collab/log/claude-code.md` (son `VPS: DEPLOYED bf464d0`, 2026-11-14). `collab/STATUS.md` değil.

## 3. Çelişkiler

| # | Çelişki | Kanıt A | Kanıt B | Etki | Önerilen çözüm |
|---|---|---|---|---|---|
| C1 | **STATUS.md "güncel canlı durum" olarak gösteriliyor ama 7 gün bayat** (master `3acea5c` / VPS `3acea5c`; gerçek `bf464d0`/`81c2cf7`) | `CLAUDE.md:3` "Güncel canlı durum: `collab/STATUS.md`" | `collab/STATUS.md:8-9` (11-07 11:30) vs `collab/log/claude-code.md` son giriş (11-14, DEPLOYED bf464d0) | Yeni oturum bayat SHA ile çalışır; `efloud-sync` yanlış fark üretir | STATUS.md'yi "Sistem" tablosunu otomatik üreten bir script'e (örn. `scripts/canary.py`/`regression_ledger` benzeri) bağla VEYA her deploy-log PR'ının kontrol listesine "STATUS Sistem satırı" ekle; model-durum satırlarını sil (log yeterli) |
| C2 | **Hermes'in 3 farklı tanımı** | `HERMES.md:49-58` Hermes = **insan operatör** (VPS SSH, config edit, PR sign-off) | `collab/models/hermes.md` Rol = VPS'te 7/24 **read-only ops-watch + reviewer, canlıya YAZAMAZ**; `HERMES.md:§14` = "Hermes Agent: terminal ve operasyon; Kilo Code orchestrator" | Hermes'e hangi yetki verildiği belirsiz; `collab/README.md §0.1` "Hermes'te canlı-yazma hook'u yok → yazmaz" vs `HERMES.md:49` "config/deploy yapar" | Tek tanım: collab/models/hermes.md (yetki). `HERMES.md` yeniden adlandır → `docs/OPERATOR_RUNBOOK.md` ("operatör = insan"); "Hermes" rol adını yalnız collab'da bırak |
| C3 | **`agents/tasks/`, `agents/TASKBOARD.md`, "Kilo Code" protokolü yok** | `HERMES.md:§14` ("görevleri `agents/tasks/` altına yazar… `agents/TASKBOARD.md`") | `ls agents/` → yalnız 7 desk rol dosyası; collab modelinde Kilo Code yok | Ölü yönerge; ajan olmayan dosyayı arar | HERMES.md §14 sil (collab/ zaten üstlenmiş) |
| C4 | **Yanlış "Backtest modülü kaldırıldı"** | `AGENTS.md:82` "Backtest modülü 2026-10-31'de kaldırıldı"; `CHANGELOG.md:21` "Kaldırıldı: Backtest modülü"; `configs/config.phase2_1k.yaml:184-185` "backtest modülü 562a6a3'te kaldırıldı… NET-cost backtest YAPILMADI" | `CLAUDE.md:` "Kanonik kaynaklar" `python -m backtest.cli …`; `backtest/cli.py` mevcut; `TESTS.md` §1 | Yeni model "backtest yok" sanıp NET-cost kapısını (ADR-0003) atlar; LuxAlgo "ölçülmedi" notu yeniden ölçülebilirken etiketli kalmış | AGENTS.md:82 satırını sil; CHANGELOG "Kaldırıldı" satırını "restore edildi (#335)" ile düzelt; config yorumunu operatör onayıyla güncelle (**yorum değişikliği bile `engine:` bloğu — config PR'ı**, risk-ops gerekmez ama atomic PR) |
| C5 | **Giriş akışı dokümanı ↔ canlı LuxAlgo yolu** | `AGENTS.md:15-21`, `HERMES.md:§5b`, `docs/OPERATOR_GUIDE.md:104-117`: "kırılımı yapan OB/BB (veya FVG/OTE fallback)" | `configs/config.phase2_1k.yaml:180-188` luxalgo.enabled + "triggers yolu devre dışı" | Operatör/AI yanlış mental model; BB/OTE/FVG parametre ayarı canlıyı etkilemez (ölü) | Üç dokümanda tek "Giriş akışı" bölümü → `CONTEXT.md` veya `pine/PINE_SPEC.md`'e; diğerleri link verir. Canlı yolu açıkça "LuxAlgo modu (2026-11-01), efloud triggers yolu = yedek" yaz |
| C6 | **`max_zone_overshoot_atr` 2.0 vs 6.0** | `AGENTS.md:27`, `HERMES.md:§5c`, `docs/OPERATOR_GUIDE.md:101` (2.0) | `configs/config.phase2_1k.yaml:168` (6.0) | Doküman canlı parametreyi yanlış söylüyor | Değer tablosunu dokümandan kaldır (config tek kaynak); "değer için config'e bak" |
| C7 | **Pine "strateji" zorunluluğu ↔ ADR-0005** | `CLAUDE.md` Amaç: "hem INDIKATÖR hem STRATEGY"; Çalışma Kuralları "indikatör ve strateji SENKRON"; `pine/PINE_SPEC.md:7` `efloud_strategy.pine`; `agents/pine-engineer.md` | `docs/adr/0005-pine-indicator-only-product.md` ("no Pine strategy is shipped"); `CLAUDE.md:3` "strategy ürünü ADR-0005 ile rafa kalktı" | CLAUDE.md kendi içinde çelişiyor (başlık satırı vs Amaç) | Amaç + Çalışma Kuralları'nı "indicator ürün; `pine/efloud_strategy*.pine` = araştırma/parity artefaktı, senkron = parity testi (`tests/test_pine_lab_*`)" şeklinde yeniden yaz |
| C8 | **"Python kaynak mantığını DEĞİŞTİRME" ↔ canlı bot sürekli değişiyor** | `CLAUDE.md:3` kritik kural (1) ve §Çalışma Kuralları | Son 10 PR (#317–#344) `engine/`, `configs/`, `ops/` değiştirdi; Karpathy ilke 3 + ADR-0003 ayrıntılı kapı tanımlıyor | Kural pratikte ihlal ediliyor → kural güvenilirliği düşer ("anayasa" görünür ama uygulanmaz) | Kuralı Pine-çeviri görevine daralt ("Pine çevirisi yaparken Python'u referans al"); trade-mantığı değişiklikleri için ADR-0003 + Karpathy-1/3'ü TEK kapı olarak bırak |
| C9 | **CLAUDE.md dangling işaretçi**: "Detay için `AGENTS.md` → 'Runtime Agent Team' bölümüne bak" | `CLAUDE.md:25-26` | `grep "Runtime Agent Team" AGENTS.md` → yok | Kırık bağlantı; additive-istisna gerekçesi izlenemiyor | Gerçek yer: `docs/adr/0002-llm-layer-is-advisory-only.md`; işaretçiyi ADR-0002'ye çevir |
| C10 | **CLAUDE.md "GeminiClient" ↔ gerçek sağlayıcı** | `CLAUDE.md` Pine Kısıtları: "`engine/agents/` … ortak `GeminiClient`" | `engine/agents/gemini_client.py` sınıf adı korunmuş ama `configs/config.phase2_1k.yaml:333-344` provider=openrouter / `deepseek/deepseek-v4.1-flash` | Yanıltıcı isim (Gemini → MiniMax → OpenRouter göçleri) | Doküman: "ortak LLM istemcisi (`engine/agents/gemini_client.py`, ad tarihsel)"; Gemini rol referanslarını kaldır |
| C11 | **Tek doküman içinde eski commit hash'leri/tarihler** | `HERMES.md:6` "Master HEAD `c8dc5c8`", `:5` "2026-10-02", `:33` URL | master `81c2cf7` | Bayat | HERMES/OPERATOR_GUIDE "Şu an ne durumda" tablolarını sil (status rolü yalnız STATUS.md'de) |
| C12 | **README ↔ CLAUDE.md dil/rol**: README (EN, public vitrin) bot'un "Telegram community channel" + "social pipeline" der; CLAUDE.md `Kalıcı yapı notları` Railway `u2algo-site`, `AGENTS.md` sosyal pipeline'ı kök dokümanlarda tekrarlıyor | `README.md:What it does`, `AGENTS.md:Sosyal Medya`, `HERMES.md:§13` | `skills/social-publishing/SKILL.md` (kanonik) | Üç yerde aynı pipeline anlatımı; HERMES §13 "Bot canlı, kararlı, kod %100 hazır. Acele yok, risk yok." — kanıtsız pazarlama cümlesi runbook içinde | HERMES §13 sil; AGENTS'ta tek satır + link |
| C13 | **Repo "ECC rules checked-in" ↔ `.claude/` gitignore'lu** | Harness'in proje talimat bağlamı `.claude/rules/ecc/common/*.md`'yi "checked into the codebase" gösteriyor | `.gitignore:122` `.claude/`; `git ls-files` `.claude/` döndürmüyor | ECC kuralları yalnız operatör laptopunda; collab modelleri (Hermes/Abacus), CI ve temiz worktree'ler (bu denetim dahil) görmez → tutarsız davranış | Karar: (a) kuralları `docs/engineering-rules.md`'ye damıt VE CLAUDE.md'ye link ver, ya da (b) `.gitignore`'a `!.claude/rules/` istisnası. Öneri (a) |
| C14 | **Commit formatı** | ECC `git-workflow.md`: `<type>: <description>` + Co-Authored-By | `collab/README.md §2`: `<type>(<alan>): <özet> [<model>]`; Abacus `-c user.name="Abacus.AI"` (`collab/MODELS.md`) | İki format; collab daha spesifik | ECC'yi override et: CLAUDE.md'de tek satır "commit biçimi = collab/README §2" |
| C15 | **collab/MODELS.md "Hermes MCP: yok (config'de mcp_servers yok)"** ↔ CLAUDE.md eski başlığındaki "Hermes MCP Postgres sunucusu (7 tool)" | `collab/MODELS.md` MCP satırı | `docs/history/claude-md-status-archive.md` (3. madde, supabase_postgres MCP) | Archive'da kalan, bayat | Zaten history; archive başlığındaki "bazı gerçekler bayat" notu yeterli — kullanma |

## 4. Bayat / yanlış dokümantasyon

CLAUDE.md (worktree sürümü, 76 satır):
- `:3` Dashboard URL `https://2-28-139-82.nip.io` — canary (`scripts/canary.py:25`) ile tutarlı, DOĞRU; ancak aynı IP'yi `HERMES.md` 4 yerde, `skills/llm-advisory-backend/SKILL.md:68` tekrarlıyor (tek kaynak yok). `docs/OPERATOR_GUIDE.md` ise `<VPS_IP>` yer tutucu kullanıyor → tutarsız.
- `:3` ve başlık "Sonraki Claude için Başlangıç Noktası" → tek paragraflık 5 ayrı bilgiyi (URL, ana iş, 3 kritik kural, işaretçiler) içeriyor; bölümlere ayrılmalı.
- "Cowork/Sandbox Git Uyarısı (2026-07-03)": ortam-özel, tarihli operasyonel not; constitution değil. Cowork artık kullanılıyor mu DOĞRULANMADI. → `docs/runbooks/` altına taşı (`cowork-git-pitfalls.md`), CLAUDE.md'de 1 satır.
- `Amaç`: "hem INDIKATÖR hem STRATEGY" — bkz. C7.
- `Kanonik kaynaklar (2026-11-07)`: İYİ bölüm, ama `docs/adr/README.md` ile `CONTEXT.md` işaretçileri var; `collab/STATUS.md` (bayat, C1).
- `Efloud Çekirdek Mantığı & Parametreleri`: SL `ATR(14)*0.5`, `min 0.1%`, TP1 `min R:R 1.5`, `Confluence Threshold 55` — v1 (`engine/signals.py`) değerleri; canlı v2/LuxAlgo yolu `min_sl_atr: 2.0` + `v2_use_real_atr` + luxalgo tp_mode kullanıyor (`config:110`, `:204`). Bölüm başlığı "Referans Değerler" ama canlıyı tanımlamıyor. → "v1 referansı (canlı: SMC v2/LuxAlgo — bkz. config + ADR-0004)" etiketi ekle veya `pine/PINE_SPEC.md`'ye taşı.
- `HTF Bias Fallback` ile satır numaraları `signals.py:308-328`: kod 1112 satır, drift olasılığı yüksek; satır numaralı referanslar CI'da doğrulanmıyor (TESTS.md yalnız `path::node` doğruluyor).
- `Efloud … Swing Lookback 5` canlıda luxalgo `swing_length: 50`, `internal_length: 5` (`config:189-190`) — çelişkili/belirsiz.
- "TradingView MCP Araçları" bölümü `skills/tradingview-mcp/SKILL.md` ile tekrar (89 satır) — CLAUDE.md'de tek satır yeter.

AGENTS.md: `:15` başlık "Güncel Algoritma Durumu (2026-10-02)" — LuxAlgo (2026-11-01), max_holding_hours=0 (11-08), fvg/touch shadow eksik; `:82` backtest yanlışı; `Kritik Dosyalar` tablosu `HERMES.md` = "Operatör kılavuzu", `CLAUDE.md` = "Proje bellek, mimari, Pine Script kuralları" (CLAUDE.md artık mimari tutmuyor); `Kurulum/Test` bölümü README ile tekrar.

HERMES.md: başlıkta tarih 2026-10-02 + `c8dc5c8`; `§2 Şu An Ne Durumda?` tüm tablo; `§3` "CLAUDE.md §3" (böyle bir bölüm yok); `§5b` "Bugün canlıda (2026-10-02)"; `§5c` revizyon tablosu (history rolü); `§7` "Shadow log … şu an v2 canlı, log boş olabilir" (oysa touch/fvg shadow logları artık aktif: `[touch shadow]`, `[fvg shadow]` bot logunda); `§8` tehlike sinyalleri (iyi, runbook'a taşınmalı); `§9` IP + SSH kullanıcı + key yolu (secret değil ama operasyonel hassas bilgi public repoda — repo PUBLIC, `collab/README.md §0.2`); `§12` "CLAUDE.md: Proje bellek, kural, mimari" bayat; `§13` social pipeline (SKILL.md'nin kopyası), `§14` bkz. C3.

docs/OPERATOR_GUIDE.md: `:6` "2026-10-02"; `:89-101` değer tablosu (C6); `:104-117` akış (C5).

CHANGELOG.md: `:21` "Backtest modülü … kaldırıldı" (C4); dosya iki "Eklendi" bloğu içeriyor (`Eklendi` + `Eklendi (önceki)`) ve "Unreleased"ta TV "EFloud Strategy v2" müşteri-görünür madde olarak yazılı (`:36-40`) — ADR-0005 strateji ürününü reddetti.

README.md: `Repository layout` içinde `agents/, skills/, hooks/` doğru; ancak `What it does` LuxAlgo modunu ve shadow girişleri (touch/fvg) anmıyor; `Licence` bölümü iyi. Tek eksik: README ↔ AGENTS ↔ HERMES `Test`/`Kurulum` tekrarları.

collab/: `STATUS.md` (C1); `MODELS.md` "Hermes: `~/work/efloud-bot` (T-20261104-05 ile kurulur)" — task hâlâ `tasks/open` (T-20261104-05); `collab/log/hermes.md` 3 satır = Hermes fiilen devreye girmemiş görünüyor (DOĞRULANMADI — VPS'e bakılmadı). `tasks/open` 41 dosya, 28'i 2026-11-07'ye ait ve çoğu merge edilmiş işlerin task'ı (örn. `T-20261107-05` SL alert #314, `-11` orphan alert #315, `-12/13/15` REGRESSION/TESTS/ADR #317–#320, `-23/-27` CLAUDE.md düzeltmeleri) — **kapatılmamış (done'a taşınmamış)**: task ledger drift'i (DOĞRULANMADI: tek tek PR eşlemesi yapılmadı; log'dan örneklenmiştir).

skills/: 6 skill ≤19 satır (efloud-deploy/-incident/-monitor/-sync/-railway-supabase/-journal-analysis) — içerik denetlenmedi; `efloud-railway-supabase` Railway/Supabase panel kopyası (bot.u2algo.com Railway kopyası 2026-11-07'de silindi — `CLAUDE.md:3`) yüzünden bayat olabilir (DOĞRULANMADI).

PINE_SPEC.md (map): `:7` "onaylanmadan Pine koduna geçilmeyecek" (geçmiş dönem kapısı, hepsi çoktan geçildi); `§0` tablosu "V2: Sadece CHoCH", "Confluence YOK", "shadow mode" — `engine/smc_v2/triggers.py:1-14` BOS'u da üretiyor (2026-10-02), confluence artık v2'de de var (v2 `min_confluence` + luxalgo `min_confluence:1`), shadow değil canlı. Dosya ~550 satır ve 2026-05 başlangıç anlatısı içeriyor.

## 5. Trade mantığı / setup modelleri (bu kategoride görünen varyantlar)

Dokümanlarda görünen setup/algoritma varyantlarının **durum matrisi** (edge kanıtı: yalnız repoda bulunan; bu rapor backtest KOŞMADI).

| # | Varyant | Tanım (kaynak) | Durum | Edge kanıtı |
|---|---|---|---|---|
| S1 | **SMC v1** | Tek-geçiş `engine/signals.py`; CHoCH/BOS anlık, confluence 100 puan, Gemini gate (`PINE_SPEC §0`) | **Susturuldu** (v2'nin sahiplendiği sembollerde `_v2_entry_active()`; `AGENTS.md:21`) | Eski; ölçüm yok (ADR-0005: strateji versiyonu negatif edge, T-003 GATE_RUN 2/3/4) → **ÇÜRÜTÜLMÜŞ** (strateji portu) |
| S2 | **SMC v2 "efloud triggers"** | CHoCH/BOS → OB/BB zone (+OTE/FVG fallback) → pullback → engulfing → limit; SL impulse swing/likidite (`engine/smc_v2/triggers.py:1-14`) | **Config'te devre dışı** (`config:180-186`), kod hâlâ mevcut (yedek) | BT-22/BT-25 sweep'leri config yorumlarında (`config:105-110`, `:160-167`): v2 R/trade −0.363→−0.257; 223/336 işlem, PnL +403→+596 USDT. Tek-sistem, in-sample → **KANITSIZ (kısmi)** |
| S3 | **SMC v2 "LuxAlgo modu"** | BOS+CHoCH + OB + premium/discount, TP luxalgo, pullback_timeout 48 bar (`config:187-208`) | **CANLI** (2026-11-01, operatör kararı "luxalgo mantığını kullanalım") | Config yorumu: "NET-cost backtest YAPILMADI" (`:184-185`, yanlış gerekçeli — backtest restore edildi). `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md`: kapı başına karşı-olgu NET R, "hangi giriş pozitif edge taşıyor bilinmiyor". → **KANITSIZ** |
| S4 | **BOS girişleri** | Devam kırılımı da setup (`658a905`, 2026-10-02; `triggers.py:12`) | Canlı (S2/S3 yolu içinde) | Ayrı ölçüm yok → **KANITSIZ** |
| S5 | **touch_entry (fitil/temas)** | Gölge `[touch shadow] would-enter` (`config:211`; T-20261104-12 / #280) | **SHADOW** (live değeri kodda yok) | Gölge sayaçları var; NET-cost yok → **KANITSIZ** |
| S6 | **fvg_entry (operatör FVG setup'ı)** | 4h bias, kırılımın bıraktığı FVG'ye limit, SL OB ötesi, TP1 karşı OB/BB, TP2 yön likiditesi (`config:212-216`; spec `docs/superpowers/specs/2026-11-14-fvg-entry-shadow-design.md`) | **SHADOW**, `bf464d0` deploy edildi | Go-live kapısı: ≥30 forward kapanış, NET>0, canlı v2'den iyi (`collab/log/claude-code.md` son giriş) → **KANITSIZ (henüz)** |
| S7 | **Wave-1 / Wave-2 Pine ürünleri** | `pine/u2algo/wave1_signals.pine`; Wave-2 premium redesign | Wave-1 = yayınlanan indikatör; Wave-2 **DROP** (OOS PF 1.165 < 1.30, ADR-0005) | **ÇÜRÜTÜLMÜŞ** (Wave-2); Wave-1 trade edge iddiası yok (display-only) |
| S8 | **Pine strateji (efloud_strategy*.pine)** | Pine `strategy()` portu | Repoda artefakt, ürün değil (ADR-0005) | **ÇÜRÜTÜLMÜŞ** (negatif edge, ADR-0005) |
| S9 | **Agent ekibi (Overseer/Regime/SignalValidator/RiskReviewer/PostMortem)** | LLM danışma; `gating:false` (`config:342-343`) | **Observation** | Ölçüm planı: `scripts/desk/agent_verdict_edge.py`; sonuç raporu yok → **KANITSIZ** |
| S10 | **Senkron LLM yapı doğrulaması** | `structure_validation.enabled:false` (`config:99-100`) | **KAPALI**; "19 günde 23.085/23.085 çağrı fallback'e düştü" (`:96-98`) | Ölçülmüş: işlevsiz → **ÇÜRÜTÜLMÜŞ** (mevcut sağlayıcıyla) |
| S11 | **Kronos advisory** | Zaman serisi tahmini + LLM sentez (`config:347+`) | Default-OFF master kill switch; yalnız Telegram/DB | **KANITSIZ** (trade'e bağlı değil) |
| S12 | **Max-holding 36h → 0** | `max_holding_hours: 0` (`config:406-408`) | **CANLI** (2026-11-08) | A/B 41g, 4 sembol: −46.05 → −12.02 NET (log EF-20261108-02) → **KISMEN KANITLI** (kısa pencere, 4 sembol) |
| S13 | **min_sl_atr 2.0 / v2_use_real_atr** | BT-sweep5 / BT-22 (`config:105-110`) | **CANLI** | 336 canlı işlem üzerinde post-hoc → **KISMEN KANITLI (in-sample)** |
| S14 | **Emergency balance HALT=0** | Acil halt kaldırıldı (`config:424`) | **CANLI** (operatör niyeti) | Edge konusu değil; risk-ops konusu — günlük %10/haftalık %25 breaker korunuyor |

Doküman açısından kritik nokta: **hiçbir kök dokümanda bu matris yok** — S3/S5/S6/S12'nin canlı/shadow/kanıt durumu yalnız config yorumlarında ve collab/log'da. Önerilen yer: `CONTEXT.md` altında "Setup modelleri ve durumları" tablosu (map rolü) + `collab/STATUS.md` kanıt sütunu.

Operatör niyeti (çerçeve) → ölçülmüş NET edge (filtre) ilişkisi bu kategoride: operatör niyeti net (LuxAlgo mantığı, FVG setup'ı, süre sınırı kaldırma); ölçüm tarafı yalnız S12/S13 için kısmi; S3 (canlı ana yol) için NET-cost kanıtı yok.

## 6. ECC revizyon adayları

### 6.1 Dokümanlar — silinecek / taşınacak / kısaltılacak

| İşlem | Hedef | Gerekçe |
|---|---|---|
| **SİL** | `HERMES.md §2, §5b, §5c, §6'nın "Şu an" cümleleri, §13, §14` | Status/history rolü STATUS.md+log'a ait; §14 var olmayan `agents/tasks/`'a bakıyor (C3) |
| **TAŞI** | `HERMES.md` kalanı (§4, §6 deploy/rollback, §7, §8 tehlike sinyalleri, §11 acil akış) → `docs/runbooks/operator-runbook.md`; `HERMES.md` silinir veya 10 satırlık "Hermes rolü → collab/models/hermes.md" yönlendirmesine iner | C2: tek rol tanımı |
| **BİRLEŞTİR** | `docs/OPERATOR_GUIDE.md` ↔ `HERMES.md` operasyon bölümleri | %60 tekrar (deploy, breaker reset, healthz, config) |
| **KISALT** | `AGENTS.md` → "map" (≤50 satır): giriş + kanonik link listesi + test komutu. "Güncel Algoritma Durumu" bloğu silinir (yerine `CONTEXT.md` setup tablosu + `collab/STATUS.md`) | C4–C6 |
| **TAŞI** | `docs/repo-cleanup-2026-11-06.md` → `docs/history/` | history rolü |
| **TAŞI** | CLAUDE.md "Cowork/Sandbox Git Uyarısı" → `docs/runbooks/` | ortam-özel |
| **TAŞI** | CLAUDE.md "Efloud Çekirdek Mantığı & Parametreleri" → `pine/PINE_SPEC.md` (veya `docs/`); CLAUDE.md'de 1 işaretçi | v1 parametreleri anayasa değil; drift |
| **KISALT** | `pine/PINE_SPEC.md §0` "V1 vs V2" tablosunu güncelle (BOS, confluence, canlı) | §4 |
| **DÜZELT** | `CHANGELOG.md:21` + `AGENTS.md:82` + config yorumu (backtest restore) | C4 |
| **YENİ** | `docs/engineering-rules.md` (≤60 satır): ECC common kurallarının efloud'a damıtılmış hali (aşağıda 6.3) | C13 |

### 6.2 Yeni CLAUDE.md iskeleti (≤70 satır, constitution-only)

1. `# EFloud-Bot` + 3 satır tanım (ne bu repo; PUBLIC; canlı MAINNET bot)
2. `## Okuma sırası` — CONTEXT.md → AGENTS.md → collab/STATUS.md (canlı) → docs/adr/README.md
3. `## Değişmez kurallar` — (a) emri yalnız motor verir (desk-operating-model), (b) secret yok (repo public), (c) master'a doğrudan push yok (collab/README §2), (d) mainnet trade-mantığı değişikliği = ADR-0003 kapısı (risk-ops + NET-cost backtest + operatör onayı)
4. `## Geliştirme Sözleşmesi (Karpathy 4 ilke)` — mevcut metin korunur, "audit C1–C4/H1–H7" bağları `docs/history/`'deki audit linkine bağlanır
5. `## Kanonik kaynaklar` — mevcut bölüm (STATUS.md satırı "otomatik/deploy-log'dan" notuyla)
6. `## Test ve kapılar` — `pytest`, `regression_ledger run`, `canary.py`, NET-cost backtest komutu (mevcut `Kanonik kaynaklar`'dan)
7. `## Pine kuralları` — v6 zorunlu; indicator = ürün (ADR-0005); `pine/lab/*` tek kaynak, `build_pine_lab.py --check`; PINE_SPEC + TradingView MCP skill işaretçisi
8. `## Commit/PR biçimi` — collab/README §2 biçimi (ECC override'ı)
9. `## Kalıcı yapı notları` — u2algo-site Railway root, sosyal hat SKILL.md
10. `## Harness haritası` — 5 satır: `agents/` (desk), `scripts/ci/agents/` (CI), `engine/agents/` (runtime), `skills/` (aktif), `collab/skills-incubator/` (taslak)

Her doküman için rol cetveli (`docs/README.md` veya CLAUDE.md `Okuma sırası` altında): constitution = CLAUDE.md + ADR + THIRD_PARTY; map = CONTEXT + AGENTS + README + TESTS/REGRESSION + PINE_SPEC; status = collab/STATUS.md (+ otomatik üretim); history = CHANGELOG + collab/log + docs/history + docs/handoff + docs/superpowers + docs/repo-cleanup.

### 6.3 ECC rules (.claude/rules/ecc/common) ↔ proje kuralları — çelişki ve öneri

| ECC kuralı | Proje gerçeği | Çelişki/boşluk | Öneri |
|---|---|---|---|
| `testing.md`: "Minimum 80% coverage, ALL 3 test türü zorunlu (unit+integration+E2E)" | CI'da coverage kapısı YOK (`pyproject.toml`/`ci.yml` içinde `cov`/`fail_under` bulunamadı); gerçek kapı = `REGRESSION.md` downstream ledger + `TESTS.md` TEST-ID + canary | ECC sayı-bazlı, proje etki-bazlı; ECC kuralı uygulanmıyor ama "MANDATORY" yazıyor | `engineering-rules.md`: "Kapı = regression_ledger exit kodu + TESTS.md; 80% hedef değil kapı" — ya da gerçek ölçüm ekle (öneri: yalnız `engine/safety/`, `engine/risk/`, `exchange/` için coverage raporu; karar operatör) |
| `testing.md`: TDD RED→GREEN→refactor | Karpathy-4: "bug fix → önce repro testi; yeni davranış default OFF" | Uyumlu; Karpathy daha spesifik | Karpathy bölümü kazanır; ECC'den "tdd-guide agent" referansını kaldır (repo'da yok) |
| `agents.md`: "planner agent ZORUNLU karmaşık özelliklerde; code-reviewer her kod sonrası; tdd-guide her feature" | Repo'da bu agent'lar YOK (`agents/` = 7 desk rolü; `.claude/agents` ignore'lu); `/review` skill `efloud-code-reviewer` / `efloud-risk-ops-reviewer` çağırıyor (kullanıcı-düzeyi, repoda tanımsız) | Kural hayalet agent'lara bağlı; collab'da review = başka model (SHARED §4) | ECC `agents.md`'yi projede "desk agent'ları + CI agent'ları" ile eşle (tablo); `efloud-*-reviewer` tanımlarını `agents/` veya `scripts/ci/agents/`'a al (DOĞRULANMADI: kullanıcı-düzeyi tanım yeri) |
| `development-workflow.md` step 0: "GitHub code search / registry araması ZORUNLU, yeni implementasyon öncesi" | Karpathy-3 Surgical + canlı mainnet küçük PR'lar; bu araştırma yükü her config/bugfix'te anlamsız | Çelişki: ECC her yeni implementasyonda araştırma ister | "Yeni modül/bağımlılık için; bug fix/config için değil" kapsam notu |
| `development-workflow.md` step 1: "PRD, architecture, system_design, tech_doc, task_list üret" | `docs/superpowers/{specs,plans}` + ADR + `collab/tasks` zaten bu iş | Yinelenen artefakt riski | Tek format: spec (docs/superpowers/specs) + task (collab/tasks); ADR yalnız geri-dönmesi-zor kararlarda |
| `coding-style.md`: "Immutability CRITICAL, fonksiyon <50 satır, dosya ≤800 satır" | `engine/safe_orchestrator.py` **3361 satır**, `exchange/__init__.py` 2490, `backend/bot_runner.py` 1381, `engine/signals.py` 1112, `backend/api.py` 1047; Karpathy-3: "ilgisiz kodu yeniden yapılandırma/silme" | Doğrudan çelişki: ECC "ayır" der, Karpathy-3 "dokunma, işaretle" der; canlı mainnet dosyasının bölünmesi risk-ops konusu | Karpathy kazanır: dosya-boyutu kuralı YENİ kod içindir; mevcut dev dosyalar için "refactor = ayrı ADR + risk-ops + regression ledger" |
| `coding-style.md`: "camelCase, UPPER_SNAKE" (JS örnekleri) | Python repo (snake_case) + TS frontend | Dile özgü kural eksik: `rules/python/` kurulmamış (ECC README yapısı var; yalnız `common/` kurulu) | `rules/ecc/python` kurulması veya `engineering-rules.md`'de "Python: PEP8/ruff (`pyproject.toml`)" |
| `git-workflow.md`: `<type>: <description>` | collab: `<type>(<alan>): <özet> [<model>]` | C14 | Collab biçimi kazanır |
| `git-workflow.md`: includeCoAuthoredBy notu | harness: commit sonuna `Co-Authored-By: Claude …` satırı zorunlu; collab/MODELS: "commit'te `Co-Authored-By: Claude`" | Uyumlu | — |
| `security.md`: "Rate limiting on all endpoints; CSRF" | T-20261107-06-panel-csrf hâlâ `open`; login rate-limit panel'de var (memory: audit-fixes) | Açık görev | task'ı durumuyla doğrula (DOĞRULANMADI) |
| `security.md`: "secret rotate" | `.gitleaksignore` + CI gitleaks + `.env*` ignore; repo public | Uyumlu, daha sıkı | — |
| `hooks.md`: "dangerously-skip-permissions kullanma; allowedTools" | `hooks/live-write-gate.json` PreToolUse "ask" backstop | Uyumlu; ama yalnız plugin kuruluysa çalışır — plugin repoda tanımlı, operatör laptopunda kurulu mu DOĞRULANMADI | `claude-code.md` modeline "plugin kurulu mu" ön-kontrolü (`/plugin list`) |
| `performance.md`: model seçim (Haiku/Sonnet/Opus) | repo-genel öneri yok; runtime LLM `deepseek-v4.1-flash` (OpenRouter) | Farklı konular (geliştirici modeli vs runtime) | Karıştırma; ECC performance.md'yi proje belgesinde atla |
| `common/patterns.md` "Repository Pattern / API envelope" | Kod tabanında uygulanmıyor (FastAPI doğrudan) | Sadece tavsiye | Atla |

Genel prensip önerisi: `engineering-rules.md` başlığı **"ECC common kurallarından efloud'da DEĞİŞENLER"** — yalnız farkları listeler (override tablosu); ECC'nin tamamını kopyalamaz (Simplicity-First).

### 6.4 Agent / skill / hook revizyon adayları

1. **Üç ayrı agent seti**: `agents/` (desk, 7), `scripts/ci/agents/` (CI: risk-safety-auditor, smc-strategy-reviewer), `engine/agents/` (runtime LLM). `risk-manager` (desk) ↔ `risk-safety-auditor` (CI) rol örtüşmesi; `strategist`/`market-analyst` ↔ `smc-strategy-reviewer`. → Tek "agent haritası" tablosu (CLAUDE.md §10) + örtüşenler için "tek tanım, iki çağrı noktası" kararı (ADR). DOĞRULANMADI: içerik farkı (agent gövdeleri tam okunmadı).
2. **`pine-engineer`** description'ını ADR-0005'e göre güncelle (strategy = parity artefaktı).
3. **Kullanılmayan/yinelenen**: `collab/skills-incubator/*` 5 taslak, isimleri `skills/efloud-*` ile çakışıyor ve T-03/T-06 1+ haftadır açık → karar: promote veya sil (operatör).
4. **Stub skill'ler** (6 adet ≤19 satır): `efloud-deploy`, `-incident`, `-monitor`, `-sync`, `-railway-supabase`, `-journal-analysis` — runbook'larla (`docs/runbooks/*`, 19 dosya) çakışır; skill = tetikleyici + runbook linki olarak sabitle (frontmatter `description` trigger-doğru mu `skill-health` ile ölç).
5. **`.claude/` ignore'lu**: ECC rules/hook/settings paylaşılamaz. Öneri: `.claude/settings.json` (izin listesi, hook referansı) ve `.claude/rules/` repoya (`.gitignore`'da `!.claude/settings.json`, `!.claude/rules/**`; `settings.local.json` ignore kalır, zaten `:67`). Karar operatör (secret/yerel yol riski — settings'te yerel yol/secret olmamalı).
6. **`.claude-plugin/plugin.json` versiyonu** 0.1.0 sabit; agent/skill değiştikçe bump politikası yok. Öneri: CI'da `plugin.json` ↔ `agents/*` frontmatter tutarlılık testi (tests/ altında hooks testi var, agent testi yok — DOĞRULANMADI).
7. **Live-write gate sınırı**: import izlemiyor (docstring); Hermes/Abacus'ta hook yok (`collab/README §0.1`) — protokolle korunuyor, teknik zorlama yok. T-20261107-01 (gate hardening) hâlâ open. Önceliklendirme önerisi: P1 (canlı mainnet).
8. **`.mcp.json`**: yalnız github; sürüm sabit (iyi). `collab/mcp/README.md` modeller arası MCP kaydı; TradingView MCP'nin repoda config'i yok (yalnız laptop) — doğru.
9. **Dokümantasyon drift CI'ı**: `tests/ci/test_tests_registry.py` ve `regression_ledger --check` modeli var; aynı kalıpta `tests/ci/test_docs_roles.py` önerisi: (a) CLAUDE.md ≤ N satır, (b) `collab/STATUS.md` "VPS HEAD" == son `DEPLOYED <sha>` (log), (c) docs'ta geçen `path` referanslarının varlığı, (d) AGENTS/HERMES'te 202x-xx-xx "Şu an" başlıkları yasağı. En yüksek getiri C1/C3/C9 sınıfını (kırık/bayat işaretçi) yakalar.
10. **Task ledger**: `tasks/open/` 41 dosya; merge edilmiş işlerin task'ları `done`'a taşınmamış olabilir (§4). `scripts/` içinde `collab` test mevcut (`tests/collab`); "task status vs PR merge" tutarlılık testi önerisi.

## 7. Riskler ve açık sorular

- **R1 (en yüksek)**: Operatörün laptop ana checkout'u 81 commit geride; orada CLAUDE.md eski 'Son Durum' blokları + eski URL'ler taşıyor ve oturum bağlamına yükleniyor. Yeni oturumlar **yanlış anayasa** ile başlıyor (bu görevin kendi başlığındaki CLAUDE.md örneği de eski sürümdü). Çözüm: ana checkout'u fast-forward et (başka oturumların WIP'i var → worktree/`feedback_never_stash_shared_checkout`); veya oturum başlangıcında `git fetch && git diff HEAD origin/master -- CLAUDE.md` guard'ı.
- **R2**: Dokümanlar canlı kararlarla çelişiyor (C5/C6) → operatör "BB/OTE parametresini ayarla" derse ölü yola yazılır. LuxAlgo yolu NET-cost kanıtsız canlı ana yol (S3) — bu doküman PR'ının kapsamı dışı (öneri listesi: backtest-gate + operatör onayı).
- **R3**: `HERMES.md` ve `OPERATOR_GUIDE.md`'de public repo'da VPS IP + SSH kullanıcı/key yolu; `collab/README §0.2` "repo PUBLIC" der. Secret değil ama saldırı yüzeyi bilgisi → `<VPS_IP>` yer tutucu (OPERATOR_GUIDE zaten yapıyor; HERMES.md yapmıyor). Hassasiyet kararı operatör.
- **R4**: Dosya taşıma/silme önerileri `tests/ci`, `tests/collab` testlerini kırabilir (ör. `HERMES.md`/AGENTS.md içeriğine bakan testler) — uygulamadan önce `git grep -n "HERMES.md\|AGENTS.md" tests scripts .github` (bu denetimde yapılmadı → DOĞRULANMADI).
- **R5**: STATUS.md'yi otomatikleştirmek yeni kod demektir (Simplicity-First); alternatif: STATUS "Sistem" satırlarını sil ve log'u tek kaynak ilan et.
- **Açık soru 1**: Hermes fiilen aktif mi? (`collab/log/hermes.md` 3 satır; T-20261104-05 open) — VPS'e bakılmadı.
- **Açık soru 2**: Abacus hâlâ kullanılıyor mu (log 86 satır, son ~11-05)?
- **Açık soru 3**: Kilo Code hâlâ orkestratör mü (HERMES.md §14)? Repoda iz yok.
- **Açık soru 4**: `efloud-code-reviewer` / `efloud-risk-ops-reviewer` (`/review` skill'i) nerede tanımlı — kullanıcı düzeyinde mi?
- **Açık soru 5**: Cowork sandbox uyarısı güncel mi?
- **Açık soru 6**: README "TradingView: link added after publication" (`TV_URL` yer tutucu) — yayın durumu? CHANGELOG'daki "EFloud Strategy v2" ve README'deki "u2algo Price Action" isim/ürün tutarsızlığı.

## 8. Fable'a özet (en önemli 5–10 madde)

1. **Canlı ana yol LuxAlgo modu** (`config.phase2_1k.yaml:187`, enabled) ve **NET-cost kanıtı yok** (`:184-185`; ayrıca gerekçe "backtest modülü kaldırıldı" artık YANLIŞ — `backtest/` restore edildi #335). Dokümanların anlattığı "OB/BB+OTE" yolu config'te devre dışı (C4, C5). Operatör niyeti net, ölçüm eksik → backtest-gate + operatör kararı gerek (bu turda yalnız öneri).
2. **Doküman PR'ı kapsamı (öncelik sırası)**: (a) AGENTS.md "Güncel Algoritma Durumu" bloğunu sil/yenile + `:82` backtest yanlışı; (b) HERMES.md → runbook'a dönüştür, §2/§5b/§5c/§13/§14 sil; (c) OPERATOR_GUIDE değer tablosunu sil (config tek kaynak; `max_zone_overshoot_atr` 2.0→gerçek 6.0, C6); (d) CHANGELOG backtest satırı; (e) CLAUDE.md dangling "Runtime Agent Team" (C9) + Amaç/Strateji çelişkisi (C7).
3. **STATUS.md 7 gün bayat** ama CLAUDE.md onu "güncel canlı durum" gösteriyor (C1). Gerçek durum: `collab/log/claude-code.md` (DEPLOYED `bf464d0`, FVG shadow). Ya otomatikleştir ya "Sistem" tablosunu sil.
4. **Hermes 3 çelişkili tanım** (insan operatör / VPS read-only ajan / Kilo-Code'lu terminal ajanı) (C2, C3) → tek tanım collab/models/hermes.md; HERMES.md yeniden adlandır.
5. **Ana checkout 81 commit geride** → yeni oturumlara eski CLAUDE.md yükleniyor (R1). Bu denetimin görev başlığındaki CLAUDE.md bile eskiydi.
6. **ECC rules repoda yok** (`.gitignore:122`) (C13) → collab modelleri/CI görmez. Öneri: `docs/engineering-rules.md` override tablosu (Karpathy > ECC: dosya boyutu 800 satır ↔ `safe_orchestrator.py` 3361 satır; 80% coverage ↔ CI'da kapı yok; planner/tdd-guide agent'ları repoda yok; commit biçimi collab).
7. **Yeni CLAUDE.md iskeleti** (§6.2): constitution-only; v1 "Çekirdek Parametreler" PINE_SPEC'e, Cowork uyarısı runbook'a, TV MCP bölümü skill'e; "Python'u değiştirme" kuralı Pine-çeviri görevine daraltılsın (C8).
8. **Setup matrisi dokümanda yok** (§5): S3 LuxAlgo canlı/KANITSIZ, S5 touch shadow, S6 FVG shadow (go-live ≥30 forward kapanış NET>0), S12 max-hold=0 kısmen kanıtlı, S1/S7/S8/S10 çürütülmüş. `CONTEXT.md` altına tablo olarak eklenmeli.
9. **Agent harness**: 3 ayrı agent seti (desk/CI/runtime), örtüşen roller; 5 incubator skill 1+ hafta açık; 6 stub skill; plugin canlı-yazma gate'i yalnız plugin kuruluysa çalışıyor — Hermes/Abacus'ta teknik zorlama yok (T-20261107-01 open).
10. **Drift'i CI'a bağla**: `tests/ci/test_docs_roles.py` (kırık path, STATUS↔log SHA, "Şu an" başlığı yasağı) — mevcut TESTS.md/REGRESSION.md kalıbıyla aynı sınıf, en ucuz kalıcı çözüm.
