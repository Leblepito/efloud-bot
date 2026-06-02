# Audit Journal — efloud-bot Full Critical Audit + Roadmap

> Mission: baş mimar + eleştirel auditor + roadmap mühendisi. Çalışma branch'i
> `audit/codebase-and-strategy-review` (base: `docs/readme-sponsor-agent-team` / PR #117).
> Bu dosya: hangi subagent'ı / methodu neden çağırdığım + ne öğrendiğim. Gelecek
> strateji/setup işlerinde buraya dönülecek; aynı sorular sıfırdan sorulmayacak.

---

## Oturum 1 — 2026-06-02

### Karar: Phase 1 paralel Explore fan-out
- **Skill:** `superpowers:dispatching-parallel-agents` çağrıldı. Üç bağımsız domain
  (engine / exchange+backend / ops+config) shared-state olmadan paralel
  haritalanabilir → tam uyumlu.
- **Subagent'lar (model: sonnet, read-only Explore):**
  1. `engine/` (smc, signals, safe_orchestrator, safety, risk, regimes, agents, lifecycle, journal)
  2. `exchange/` + `backend/` (CCXT client, OrderManager, FastAPI, bot_runner, db, reconcile, healthz, audit)
  3. `ops/` + `scripts/` + `backtest/` + configs + `.claude/` + root *.md
- **Sonuç:** 3/3 başarılı (ilk turda 2'si `529 Overloaded` ile düştü → yeniden dispatch ile geldi).
- **Çıktı:** `01_map.md` (tam mimari harita + Mermaid).

### BLOKER tespiti: GitHub MCP "Bad credentials"
- `mcp__github__get_pull_request` → `Authentication Failed: Bad credentials`.
- **Etki:** audit branch'ini #117 üstünde oluşturma, commit, draft PR açma **şu an imkânsız**.
- **Geçici çözüm:** Tüm `docs/audit/*.md` çıktıları LOKAL üretiliyor. GitHub PAT
  yenilenince (kullanıcı/operatör) push + draft PR yapılacak; alternatif olarak
  MiniMax executor lokal git ile devralır.
- **Aksiyon gereği (kullanıcı):** `.mcp.json` veya env'deki `GITHUB_PERSONAL_ACCESS_TOKEN`
  expired → yenile. Bkz. memory `github_mcp_setup.md`.

### Çapraz-kontrol dersi (bu oturum)
- Handoff'a/CLAUDE.md'ye körü körüne güvenme: kök `CLAUDE.md` aslında BabelFlow
  (translator) projesinin leak'i + Pine çeviri notları; gerçek bot mimarisi
  koddan haritalandı. **Kanıt koddan, handoff'tan değil.**
- `config.testnet.yaml` "testnet mirror" sanılıyordu — gerçekte severely-stripped
  (margin_mode, smc_version, agent_team, safety blokları YOK). Doğrulama olmadan
  "testnet prod'u yansıtır" varsayımı yanlış olurdu.

### Phase 1'de yakalanan ve Phase 2'ye taşınan RED FLAG tohumları
(Detay + severity Phase 2 `02_findings.md`'de doğrulanacak — şu an sadece liste.)
- `gemini-3.5-flash` model adı 4 ayrı dosyada (gemini_client, signals, team, sentiment) —
  **Google API'de böyle bir model YOK** → LLM advisory katmanı pratikte hep `{}` (devre dışı). **MAJOR.**
- `safe_orchestrator.py:838` `size_notional_pct=0.0` hardcoded → RiskReviewer notional-blind (F1 follow-up doğrulandı).
- `backend/db.py` `record_trade_close` symbol+`closed_at IS NULL` ile eşliyor, trace_id YOK → aynı sembolde hızlı open/close yanlış satır kapatabilir. **MAJOR (known gap).**
- `bot_runner.py:373-376` reconciled close çift DB write yolu (`_on_position_change` + `_persist_close`).
- `safe_orchestrator.py:780-783` `p._reported_to_breaker` runtime attribute, persist edilmiyor → restart'ta PnL çift sayım riski.
- Çok sayıda `except Exception: pass` (state.py, levels.py, exchange __init__ 1473/282, bot_runner 424/431).
- Backtest: **commission (maker/taker) modellenmiyor**, funding matematiği var ama engine loop'una bağlı değil, IS/OOS split yok, Monte Carlo yok.
- Config çelişkisi: `aggressive_v1` (CROSSED + hedge=true) vs prod `phase2_1k` (ISOLATED + one-way) — exchange seviyesinde uyumsuz.
- `preflight.py` default config path arşivlenmiş `config.phase2_micro.yaml`'a işaret ediyor.

### Phase 2 SONUÇ — 4 paralel uzman agent (tamamlandı)
- **Subagent'lar:** risk-safety-auditor (opus), smc-strategy-reviewer (opus),
  agent-team-engineer, general-purpose. 3/4 ilk turda döndü; general-purpose 529
  yedi → SendMessage ile background resume'dan kurtarıldı (ders: errored agent
  context'i canlı, SendMessage ile recover edilebilir).
- **Çıktı:** `02_findings.md` — 1 BLOCKER (C1 forming-bar repaint), 11 MAJOR, 8 MINOR,
  + REFUTED/SAFE listesi + risk envelope matematiği + H1/H2 blind-spec'leri.
- **En kritik canlı-etki bulguları (operatör BUGÜN bilmeli):**
  * **C1 BLOCKER** — tüm engine forming (kapanmamış) bar'da çalışıyor → canlıda repaint,
    backtest'te GÖRÜNMEZ. Tek-nokta fix: `exchange/__init__.py:fetch_ohlcv` son satır düş.
  * **C2 MAJOR** — `_reported_to_breaker` persist edilmiyor → restart'ta breaker PnL
    çift-sayım → gerçek weekly-DD HALT'ı maskeleyebilir (= 2026-05-14 bare-pozisyon sınıfı).
  * **A1 CRITICAL/data** — `gemini-3.5-flash` geçersiz model → advisory + sentiment +
    Gemini-signal-validation PR #112'den (2026-06-01) beri sessizce ÖLÜ. Shadow verisi çöp.
- **İYİ HABER:** Deterministik risk matematiği (notional/exposure/daily/emergency)
  $200/$2000 sınırında üçlü-hizalı, tutarlı. Test suite kalitesi yüksek. Gerçek
  fake-handoff/stub-success YOK — kod inert path'leri hakkında dürüst.
- **Çapraz-kontrol dersi (güçlendi):** "deletions:0" gibi additive-kanıt arıyorduk;
  burada da korkulan "yeniden uydurma" sınıfı kodda ÇIKMADI — ama A1 gibi sessiz
  doc-vs-code çelişkisi (model pin) gerçekti. Sessiz başarısızlık ≠ fabrikasyon.

### Sıradaki adım (Phase 3+)
- Phase 3 (strateji): `quant-strategy-analyst` + `fund-manager-overseer` +
  `market-microstructure-expert`. Ölçülmüş/ölçülmemiş ayrımı net; LuxAlgo-kıyas;
  her öneri için "nasıl falsifiye ederiz?".
- Phase 4 cleanup, Phase 5 roadmap, Phase 6 agent team.

### GitHub UNBLOCK (2026-06-02, oturum içi)
- MCP github oturum içinde eski token'la kaldı (sunucu env restart gerektirir) →
  kullanıcı PAT verdi → **lokal `git` + `gh` CLI + `GH_TOKEN` env** ile bypass.
  Token hiçbir tracked dosyaya yazılmadı (gh credential helper, git config'e yazmaz).
- `audit/codebase-and-strategy-review` branch master'dan açıldı, 00/01/02 commit
  (`d9f7c93`), origin'e push. **Draft PR #118** (base: master, DO-NOT-MERGE).
- Pre-commit hook graphify AST update çalıştı ama graphify-out/ gitignore'lu → commit'e girmedi.
- ⚠️ Operatör: bu PAT sohbet geçmişinde → iş bitince ROTATE et.
- Ders: MCP creds bozuksa ve token elde varsa, lokal gh + GH_TOKEN env temiz bypass
  (audit branch push master'ı/Railway'i etkilemez).

### API overload (2026-06-02)
- Phase 3 strateji agent'ları (3x, sonra probe) tekrarlı **529 Overloaded** (0 tool-use) →
  global model yoğunluğu, subagent spawn pool down. Benim kendi tool çağrılarım (git/Read/Grep) ÇALIŞIYOR.
- **Ders + pivot:** subagent unavailable iken Phase 3'ü KENDİM yaptım (mimar/sentez rolü).
  Doğrudan kaynak-okuma > overloaded subagent bekleme. docs/results/ backtest arşivi altın çıktı.

### Phase 3 SONUÇ — strateji eleştirisi (03_strategy_review.md, kendim)
- **🔴 SMOKING GUN (S1):** prod `min_confluence:50` (`config.phase2_1k.yaml:101`) =
  ölçülmüş **−43.75% getiri / %44.24 DD** (2026-05-05 Phase-A, tam 10 prod sembolü).
  Aynı sembol+periyot conf=80 = **+11.29% / %2.83 DD** (h1c). Eşik sweep'i (50/60/70/80)
  50'nin felaket, 80'in karlı olduğunu NET ölçtü. Prod smc_v2_shadow=true → emirler v1
  yolu = conf=50 backtest'i birebir temsil. Memory canlı "breaker OPEN, weekly DD %25"
  ile tutarlı. **Aksiyon: config-only conf 50→80 (flat-book gerekmez), roadmap #1.**
- Backtest **commission+funding YOK** (engine grep boş) → tüm getiriler gross/abartılı.
- Regime ML **DAİRESEL** (train.py kural-etiketi öğreniyor).
- Korelasyon **hesaba katılmıyor** (position_guard'da beta/correlation yok) → %44 DD = küme riski kanıtı.
- OOS split / Monte Carlo YOK. Funding/OI dashboard-only (stratejiye girmiyor).
- LuxAlgo envanteri: SFP/OTE/HTF-liquidity VAR; Volumetric OB / Inducement / Session / gerçek displacement YOK — ama hepsi "önce backtest'i fee+funding+OOS ile güvenilir yap, sonra ablate; kanıtsız ekleme".

### Sıradaki: Phase 4 (cleanup) + 5 (roadmap) + 6 (agent team) — Phase 1 envanterinden kendim.

---

### Subagent → ne zaman çağır (oturum haritası, gelecek referans)
| İhtiyaç | Subagent | Neden |
|---|---|---|
| Geniş read-only kod haritası | `Explore` (sonnet) | Hızlı fan-out, dosya dökmeden sonuç |
| Safety/risk/lifecycle/config audit | `risk-safety-auditor` (opus) | Breaker/guard zayıflaması yakalama |
| SMC/signals/confluence audit | `smc-strategy-reviewer` (opus) | Repaint/look-ahead/kanonik tanım |
| agents/ katman sözleşmesi | `agent-team-engineer` | Advisory-only + gating ihlali |
| Backtest çalıştır/özetle | `backtest-runner` (sonnet) | Confluence/risk/regime sonrası parite |
| Strateji edge eleştirisi | `quant-strategy-analyst` + `fund-manager-overseer` + `market-microstructure-expert` | LuxAlgo-vari uzman bakış |
