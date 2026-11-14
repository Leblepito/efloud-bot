# ECC Revizyonu + K1 Durdurma + PR-A/PR-B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** V1 mainnet yeni girişlerini güvenle durdurmak (K1), kök dokümanlardaki olgu hatalarını düzeltmek (PR-A) ve living-docs mimarisi + hedef model dokümanlarını eklemek (PR-B).

**Architecture:** K1 = mevcut `EFLOUD_PAUSE_NEW_ENTRIES` guard'ının VPS env ile açılması (kod değişikliği yok). PR-A = yalnız `.md` düzeltmeleri, kaynak = `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §6.1 A1–A18. PR-B = yeni ADR/strateji dokümanları + CLAUDE.md iskeleti + tek test güncellemesi.

**Tech Stack:** Markdown, git/gh, pytest, Docker Compose (VPS, `ssh efloud-bot`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-14-ecc-revision-and-target-model-design.md` (K1–K9).
- Kod/config/compose/Caddy/Pine kaynağına dokunulmaz (tek istisna PR-B Task 9: `tests/test_docs_param_parity.py`).
- Canlı-davranış iddiası yalnız `config:satır` / `path:line` ile; constitution dosyalarına (CLAUDE.md, ADR) tarih/SHA/"şu an" yazılmaz.
- `.env*` değerleri hiçbir dokümana, commit'e, log'a girmez.
- Ana checkout'ta stash yok; çalışma `C:/tmp/wt-ecc-audit` worktree'sinde.
- Commit sonu: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; PR gövdesi sonu: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Guard zayıflatılmaz; v1 girişleri açılmaz; exposure artırılmaz.

---

## Faz 1 — Operasyon (K1, K8, K9)

### Task 1: K1 — V1 yeni girişleri durdur

**Files:** VPS `<compose_dir>/.env.production` (repo dışı).

- [ ] **Step 1: Salt-okuma ön durum**
```bash
ssh efloud-bot 'docker ps --format "{{.Names}} {{.Status}}" | grep efloud-bot; docker inspect efloud-bot --format "{{index .Config.Labels \"com.docker.compose.project.working_dir\"}}"'
```
Beklenen: 3 bot konteyneri listesi + compose dizini (`<compose_dir>`).
- [ ] **Step 2: Açık pozisyon + borsa koruma emirleri anlık görüntüsü** (bot API, `reference_live_bot_control`):
```bash
ssh efloud-bot 'docker exec efloud-bot python -c "import json,urllib.request;from backend.auth import issue_token;t=issue_token();r=urllib.request.Request(\"http://127.0.0.1:8080/api/positions\",headers={\"Authorization\":\"Bearer \"+t});print(urllib.request.urlopen(r).read().decode()[:3000])"'
```
Beklenen: pozisyon listesi (sayı + her birinde sl/tp). Kaydet.
- [ ] **Step 3: Env yedeği + bayrak**
```bash
ssh efloud-bot 'cd <compose_dir> && cp -p .env.production .env.production.bak-20261114 && (grep -q "^EFLOUD_PAUSE_NEW_ENTRIES=" .env.production && sed -i "s/^EFLOUD_PAUSE_NEW_ENTRIES=.*/EFLOUD_PAUSE_NEW_ENTRIES=true/" .env.production || printf "
EFLOUD_PAUSE_NEW_ENTRIES=true
" >> .env.production) && grep -c "^EFLOUD_PAUSE_NEW_ENTRIES=true" .env.production'
```
Beklenen: `1`.
- [ ] **Step 4: Yalnız V1'i yeniden oluştur (build yok)** — önce `docker inspect efloud-bot --format '{{.Image}}'` == `docker image inspect efloud-bot:latest --format '{{.Id}}'` olduğunu doğrula (aksi halde recreate yeni kodu yükler).
```bash
ssh efloud-bot 'cd <compose_dir> && docker compose -f docker-compose.prod.yml up -d --no-deps efloud-bot'
```
- [ ] **Step 5: Doğrula**
```bash
ssh efloud-bot 'sleep 60; docker logs --since 3m efloud-bot 2>&1 | grep -E "pause_config_loaded|pause_new_entries" | tail -3; docker ps --format "{{.Names}} {{.Status}}" | grep "^efloud-bot "'
```
Beklenen: konteyner `Up (healthy)`. **Not (2026-11-14 uygulamada bulundu):** V1 `EFLOUD_AUTOSTART=0` ile çalışır; recreate sonrası trading döngüsü kapalı kalır ve pause log satırı orchestrator kurulunca yazılır. Döngüyü pause aktifken başlat: `ssh efloud-bot 'bash -s' < C:/tmp/k1_start.sh` (env `true` değilse başlatmayı iptal eder, `/api/bot/start` çağırır). Ardından log dosyasında (`/app/logs/efloud_bot.log`) `pause_new_entries config loaded: effective=True source=env`. Step 2'yi tekrarla: pozisyon sayısı ve SL/TP aynı.
- [ ] **Step 6: Geri alma (yalnız sorun olursa)**: `.env.production.bak-20261114`'ü geri kopyala + Step 4.
- [ ] **Step 7:** Erişim reddedilirse komutları operatöre `! ssh efloud-bot '…'` biçiminde ver, çıktıyı doğrula.

### Task 2: K8 — V2/V3 durumu

- [ ] **Step 1:** `ssh efloud-bot 'for c in efloud-bot-long efloud-bot-scalp; do echo == $c; docker logs --since 24h $c 2>&1 | grep -ciE "order placed|entry filled|opened position"; done'`
- [ ] **Step 2:** Sayı > 0 ise: o servislerin env_file'ı (`docker-compose.prod.yml:52,82`) için Task 1 Step 3–5'i tekrarla. 0 ise yalnız STATUS'a "işlem yok (24h)" notu.

### Task 3: K9 — hijyen

- [ ] **Step 1:** Ana checkout: `git -C C:/Users/utkuc/Downloads/efloud-bot status --porcelain` boşsa `git -C C:/Users/utkuc/Downloads/efloud-bot pull --ff-only origin master`. Boş değilse DOKUNMA, rapora yaz.
- [ ] **Step 2:** Memory `reference_dashboard_access.md`: şifre ipucu satırını ve ölü URL'leri çıkar; güncel dashboard `https://2-28-139-82.nip.io` (05 raporu). `MEMORY.md` satırını güncelle.
- [ ] **Step 3:** Operatöre testnet anahtar rotasyonu notu (kullanıcıya özet mesajında).

---

## Faz 2 — PR-A (olgu düzeltmeleri, yalnız `.md`)

Kaynak tablo: `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §6.1 (A1–A18) + §2 (X1–X32). Her madde için: önce hedef satırı ve kanıt satırını oku, sonra cerrahi düzelt.

### Task 4: Kök dokümanlar (A1–A7, A9, A10, A13)

**Files:** `CLAUDE.md`, `AGENTS.md`, `README.md`, `HERMES.md`, `CONTEXT.md`, `CHANGELOG.md`, `collab/STATUS.md`.

- [ ] **Step 1:** A1, A2, A3 (CLAUDE.md): Pine ürün kaynağı `pine/lab/*` → `efloud_lab*.pine` (strategy = parity artefaktı; ADR-0005); "Python'u değiştirme" kuralı Pine-çeviri görevine daraltılır, trade mantığı kapısı ADR-0003 + Karpathy-1/3; ilke 4 gate = `python -m backtest.cli` offline + gölge logları forward, EMC "flag kapalı, hook v1 dalında (`engine/safe_orchestrator.py:1497→1567`)".
- [ ] **Step 2:** A4: `## Efloud Çekirdek Mantığı…` başlığı → `## v1 referansı (canlıda susturulmuş — Pine port tarihçesi)`; bölüm metni KORUNUR (özellikle `- **Swing Lookback**: 5` satırı). Üstüne `## Canlı motor` (≤5 satır): SMC v2 LuxAlgo modu, `configs/config.phase2_1k.yaml:180-188`, giriş = 15m engulfing kapanışı → MARKET (`exchange/__init__.py:1151-1153`), ayrıntı `CONTEXT.md`, ölçüm sonucu `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §0.
- [ ] **Step 3:** A5 AGENTS.md: `:11-22` "Güncel Algoritma Durumu" bloğu → CONTEXT.md + collab/STATUS.md linkleri; `:75` "Backtest kaldırıldı" ifadesi → `backtest/` mevcut (#335).
- [ ] **Step 4:** A6 README.md: `:28-30` giriş akışı = lux OB retest → engulfing → MARKET; SL OB ucu (ATR bantlı `calc_sl`); TP lux aday havuzu, `risk.min_rr`. `:135-136` "10 pozisyon" → "efektif eşzamanlı pozisyon = ⌊`max_total_exposure` × bakiye / notional⌋ (`engine/safety/position_guard.py:271-282`)".
- [ ] **Step 5:** A7 HERMES.md: breaker durum tablosu (günlük/ardışık = TRIPPED, haftalık = HALTED, acil = `emergency_balance_threshold: 0` ile kapalı, `engine/safety/breaker.py:284-327`); `:237` "HALTED" düzeltmesi; `:379` → "operatör onayı olmadan değiştirilmez"; bayat SHA/tarih blokları → "güncel durum: collab/STATUS.md".
- [ ] **Step 6:** A9 CONTEXT.md: Confirmation = 15m engulfing kapanışı; v1 skor ↔ lux konsept sayısı ayrımı; iki yol zinciri; tablolar: setup durum matrisi (Fable §3 özeti, 1 satır/setup) ve "canlıda etkili / inert anahtarlar" (Fable X6 listesi, `config:satır` ile).
- [ ] **Step 7:** A13 CHANGELOG.md `:18` → "kaldırıldı (562a6a3), geri yüklendi (#335)".
- [ ] **Step 8:** A10 collab/STATUS.md: master `81c2cf7`; son DEPLOYED kaydı `bf464d0` (collab/log); LuxAlgo akışı "ölçüldü, NET negatif"; K1 uygulama kaydı (Task 1 sonucu, tarih); V2/V3 durumu (Task 2); alerter kapsamı "yalnız V1"; efektif pozisyon tavanı formülü; gölgeler + ADR-0011 go-live barı (PR-B'de).
- [ ] **Step 9:** `pytest tests/test_docs_param_parity.py tests/collab/ -q` → PASS.
- [ ] **Step 10:** Commit `docs: fix stale facts in root docs (ECC audit PR-A, part 1)`.

### Task 5: Alan dokümanları (A8, A11, A12, A14–A18)

**Files:** `skills/efloud-incident/SKILL.md`, `pine/PINE_SPEC.md`, `docs/adr/0005-*.md`, `docs/adr/0009-*.md`, `agents/strategist.md`, `agents/pine-engineer.md`, `agents/risk-manager.md`, `scripts/ci/agents/smc-strategy-reviewer.md`, `skills/luxalgo-smc/SKILL.md`, `skills/efloud-deploy/SKILL.md`, `skills/social-publishing/SKILL.md`, `skills/efloud-railway-supabase/SKILL.md`, `skills/tradingview-mcp/SKILL.md`, `docs/runbooks/crash-loop-recovery.md`, `docs/runbooks/disaster-recovery.md`, `pine/publish/PUBLISH_efloud_signals.md`, `pine/u2algo/WAVE1_SPEC.md`, `docs/pine-lab/README.md`.

- [ ] **Step 1:** A8: `skills/efloud-incident/SKILL.md:13` → "operatör onayı olmadan değiştirilmez".
- [ ] **Step 2:** A11 PINE_SPEC: üste durum tablosu (bölüm → dosya → canlı/arşiv); "§0–§14 TARİHSEL"; §14, §19 SUPERSEDED; §20'ye "baseline parity GATE FAIL ×3" + "lab MAX_HOLD 36h ↔ canlı 0 sapması (`pine/lab/tail_strategy.pine:5,112`, `configs/config.phase2_1k.yaml:407`)"; Tuzaklar'a RE10045.
- [ ] **Step 3:** A12 ADR-0009 sonuna "2026-11 notu: teyit göreli koruyucu (−0.30 vs −0.75 R), mutlak edge negatif" *(PR-B fact-check düzeltmesi: "göreli koruyucu" aşırı iddia → teyit TARTIŞMALI; uygulanan metin ADR-0009 2026-11 notunda)*; ADR-0005'e "Wave-2 PF LuxAlgo öncesi motora ait".
- [ ] **Step 4:** A14 agents/*: ölçüm araçları (`backtest.cli`, `scripts/pine_lab_parity*`, `fvg_shadow_report`) + maliyet satırı zorunluluğu; pine-engineer → ADR-0005; risk-manager fixed $50×10x + efektif tavan formülü. Dosyalarda adı geçen script yollarını `ls` ile doğrula.
- [ ] **Step 5:** A15 CI reviewer: canlı kapı seti (lux `min_confluence`, premium/discount, `risk.min_rr`, BT-23/25, Po3, SL ATR bandı); "rejim kapısı v2'de yok (`engine/safe_orchestrator.py:1179`)"; "dedup/re-emit etkisi?" maddesi.
- [ ] **Step 6:** A16 skills: luxalgo-smc (teyit/MARKET/SL kuralı + profil farkları); efloud-deploy (tek-servis `up -d --no-deps <svc>`, "deploy.sh tüm stack = 3 mainnet bot" uyarısı); social-publishing (doğrulanamayan test sayısını kaldır); efloud-railway-supabase (hedef `u2algo-site`); tradingview-mcp (RE10045 / UDF tuzakları).
- [ ] **Step 7:** A17 runbook'lar: ölü host → `scripts/canary.py:25`'teki host veya container içi `curl 127.0.0.1:8080/healthz`.
- [ ] **Step 8:** A18: üç dosyaya "> SUPERSEDED 2026-11-06 — ARŞİV" başlığı; pine-lab README'ye "SON DURUM" bölümü (ürün = `pine/lab/*`, GATE FAIL ×3).
- [ ] **Step 9:** Testler: `pytest tests/test_docs_param_parity.py tests/collab/ tests/ci/ -q`; `python scripts/regression_ledger.py --help` ile check alt komutunu bul ve koş.
- [ ] **Step 10:** Referans doğrulama (repo dışı script, `C:/tmp/check_refs.py`): PR diff'indeki yeni `path:line` / `path` referanslarının varlığını ve satır sayısını kontrol et → 0 hata.
- [ ] **Step 11:** Commit `docs: align domain docs, skills and runbooks with live engine (ECC audit PR-A, part 2)`.

### Task 6: PR-A review + PR

- [ ] **Step 1:** Paralel iki review: `efloud-code-reviewer` (diff `origin/master...HEAD`, atomic/yan etki) ve bağımsız fact-checker (yeni iddiaları kaynakta çürütmeye çalışır; spec/Fable kararlarını görmez, yalnız diff + repo).
- [ ] **Step 2:** CRITICAL/HIGH bulguları düzelt, commit.
- [ ] **Step 3:** `git push -u origin docs/ecc-audit-2026-11-14` + `gh pr create` (başlık `docs: ECC audit 2026-11-14 — reports, design, stale-fact fixes (PR-A)`; gövde: özet, K1 durumu, test planı, GATED listesi linki).

---

## Faz 3 — PR-B (mimari)

Branch: `docs/ecc-architecture-2026-11-14`, PR-A branch'inin üzerinden (PR-A merge edilince rebase).

### Task 7: Yeni kanonik dokümanlar

**Files (create):** `docs/STRATEGY_INTENT.md`, `docs/adr/0011-edge-go-criteria.md`, `docs/adr/0012-live-flow-pause-and-ramp.md`, `docs/research/DECISIONS.md`, `docs/engineering-rules.md`, `docs/runbooks/backtest-gate.md`; **Modify:** `docs/adr/README.md` (index).

- [ ] **Step 1:** STRATEGY_INTENT: spec §3 pipeline tablosu + 07 §5.4 tarihli operatör ifadeleri + sapma tablosu (canlı lux / `engine/smc_v2/fvg_entry.py` / `pin_fvg_touch` donduruldu, K5).
- [ ] **Step 2:** ADR-0011 = spec K6 (`docs/adr/template.md` biçimi). ADR-0012 = K1+K7+K8 (Context: ölçümler; Decision; Consequences; geri alma).
- [ ] **Step 3:** DECISIONS.md = Fable §3 soyağacı + 04 §5.1 karar kronolojisi; her satırda kanıt yolu.
- [ ] **Step 4:** engineering-rules.md (≤60 satır): ECC ↔ proje override tablosu (Karpathy > ECC; 800 satır kuralı yalnız yeni kod; coverage kapısı yok → regression ledger + TESTS.md; commit biçimi `collab/README §2`; `.claude/` gitignore notu).
- [ ] **Step 5:** backtest-gate runbook: sabit pencere ucu (`--end`), sembol başına ayrı koşu (Windows MP notu), `backtest:` bloğu yoksa BRÜT uyarısı, maliyet satırı zorunlu.
- [ ] **Step 6:** Commit `docs: add strategy intent, ADR-0011/0012, decisions log, engineering rules`.

### Task 8: HERMES → operator runbook

- [ ] **Step 1:** `git grep -n "HERMES.md\|OPERATOR_GUIDE" -- tests scripts .github hooks` → bağımlılık varsa taşıma yerine yalnız kısaltma yap.
- [ ] **Step 2:** Bağımlılık yoksa: `docs/runbooks/operator-runbook.md` = HERMES §runbook bölümleri + OPERATOR_GUIDE birleşimi; tarihsel bölümler (§2/§5b/§5c/§13/§14) `docs/history/hermes-2026.md`; kök `HERMES.md` 10 satırlık yönlendirme.
- [ ] **Step 3:** `pytest tests/collab/ -q` PASS; commit.

### Task 9: CLAUDE.md iskeleti + parity testi taşıma

**Files:** `CLAUDE.md`, `pine/PINE_SPEC.md`, `tests/test_docs_param_parity.py`.

- [ ] **Step 1 (failing test):** Testi PINE_SPEC'i okuyacak şekilde değiştir:
```python
def test_v1_reference_swing_lookback_matches_engine_default():
    spec = (ROOT / "pine" / "PINE_SPEC.md").read_text(encoding="utf-8")
    m = re.search(r"Swing Lookback\*\*:\s*(\d+)", spec)
    assert m, "could not find the Swing Lookback bullet in pine/PINE_SPEC.md (v1 reference)"
    doc_lb = int(m.group(1))
    engine_default = inspect.signature(SMCEngine.__init__).parameters["swing_lb"].default
    cfg = yaml.safe_load((ROOT / "configs" / "config.phase2_1k.yaml").read_text(encoding="utf-8"))
    prod_lb = cfg["structure"]["swing_lookback"]
    assert doc_lb == engine_default == prod_lb == 5, (
        f"swing_lookback drift: PINE_SPEC={doc_lb}, engine default={engine_default}, prod config={prod_lb}"
    )
```
- [ ] **Step 2:** `pytest tests/test_docs_param_parity.py -q` → FAIL ("could not find … PINE_SPEC").
- [ ] **Step 3:** v1 referans bölümünü CLAUDE.md'den `pine/PINE_SPEC.md` sonuna `## Ek V1 — v1 referansı (canlıda susturulmuş)` olarak taşı (metin aynen).
- [ ] **Step 4:** Test PASS.
- [ ] **Step 5:** CLAUDE.md'yi Fable §7 iskeletine indir (≤70 satır): ne/okuma sırası/değişmez kurallar/Karpathy 4 ilke (ilke 4 → `backtest.cli` + ADR-0011)/kapılar ve komutlar/Pine kuralları/commit biçimi/harness haritası/kalıcı yapı notları; Cowork uyarısı → `docs/runbooks/cowork-git-pitfalls.md`, TV MCP → `skills/tradingview-mcp/SKILL.md` işaretçisi. `wc -l CLAUDE.md` ≤ 70.
- [ ] **Step 6:** `TESTS.md` "missing" satırları (Fable B8).
- [ ] **Step 7:** `pytest tests/test_docs_param_parity.py tests/collab/ tests/ci/ -q` PASS; commit.

### Task 10: PR-B review + PR

- [ ] **Step 1:** `efloud-code-reviewer` + fact-checker (Task 6 ile aynı).
- [ ] **Step 2:** Düzelt, push, `gh pr create` (base: master; PR-A'ya bağımlılık notu).

---

## GATED kod kuyruğu (bu planın dışında — yalnız kayıt)

Spec §6 sırası; her biri ayrı plan + PR: Ö1 verify algo-fetch, Ö2 re-emit, Ö5 gölge SL-B + net_r, Ö3/Ö4 journal + tek maliyet + gate script, Ö8 maliyet bütçesi, Ö12 bakiye tabanı, Ö9 FVG limit canlı yol (K6 sonrası), kalan Ö6/Ö7/Ö10/Ö11/Ö13/Ö14/Ö15.
