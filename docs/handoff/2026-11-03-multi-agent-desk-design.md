# efloud-bot çok-ajanlı masa — tasarım + hypergrok güvenlik incelemesi (2026-11-03)

Durum: **Aşama D (dev-time masa) bu PR'da.** Aşama R1–R3 (runtime) operatör onayı bekliyor.

## 1. hypergrok-trading-desk güvenlik incelemesi

Kaynak: `galleonlabs/hypergrok-trading-desk` @ `8ec18c3` (v1.7.1, MIT), shallow clone,
**hiçbir kodu çalıştırılmadı**.

| Kontrol | Sonuç |
| --- | --- |
| Ne olduğu | Claude Code / Cursor / Grok / Gemini **plugin paketi**: 7 rol (agents/*.md), 17 skill, 1 hook, doğrulama script'leri. Trade botu değil. |
| Kurulumda kod çalışması | Yok: npm bağımlılığı, `postinstall`, `bin` yok. |
| Hook (`hooks/exchange_write_gate.py`) | Stdlib, ağ/dosya yazımı yok; yalnız `ask` döner, asla `allow` değil. Zararsız. Sınırı: Hyperliquid'e özel, import takibi yok. |
| Ağ erişimi | Sadece script'lerde: Hyperliquid public `/info` (read-only) ve GitHub. Exchange write yok. |
| Gizli bilgi | Repo'da key/secret literal'i yok. |
| Prompt injection / gizli talimat | Gizli Unicode (bidi/zero-width) yok; veri sızdırma, "kullanıcıya söyleme" türü talimat yok. Bulunan eşleşmeler güvenlik kuralı ("key'i chat'e yapıştırma"). |
| CI | `pull_request_target` aynı-repo koşuluyla korunmuş; bizi etkilemez. |
| Lisans | MIT — kopyalanan/uyarlanan kısımlarda telif + izin metni korunmalı (`THIRD_PARTY_NOTICES.md` eklendi). |

**Karar:** Örnek olarak kullanmak güvenli. Plugin'i olduğu gibi kurmak gereksiz (Hyperliquid'e
özel); onun yerine operating model, rol yapısı ve hook efloud'a uyarlandı.

## 2. Temel mimari fark

hypergrok **takdire dayalı** bir masa: her işlem bir ticket, insan ticket id ile onaylar,
LLM rolleri emri hazırlar. efloud-bot **otonom, deterministik** bir motor: 7/24 kendi
kurallarıyla emir verir; breaker/guard/orphan katmanları güvenliği sağlar.

hypergrok'u birebir kopyalamak = LLM'i emir yoluna koymak. Bu hem CLAUDE.md'ye
(ajan katmanı advisory, `gating: false`) hem de hypergrok'un kendi felsefesine
(insan onayı olmadan send yok) aykırı. Doğru uyarlama:

| hypergrok | efloud karşılığı |
| --- | --- |
| Execution Trader (tek yazıcı) | **Motor** strateji emirleri için; `execution-ops` operasyonel değişiklikler için (deploy, start/stop, kill switch, manuel kapatma) — ticket ile |
| Risk Manager PASS / veto | `risk-manager` + deterministik breaker/guard (değişmez) |
| Market / Research Analyst | `market-analyst` (LuxAlgo port'u ile brief) |
| Strategist | `strategist` (NET-cost edge ölçümü, signal ledger) |
| Trade Reviewer | `trade-reviewer` (journal, post-mortem, incident) |
| Desk Lead | Ana Claude oturumu + `desk-operating-model` skill'i |
| — | `pine-engineer` (projenin ana işi: Pine v6 port) |
| Engagement levels research/testnet/mainnet | research / shadow / testnet / mainnet |
| exchange-write-gate hook | `hooks/live_write_gate.py` (Binance/ccxt, bot API, prod deploy, Supabase apply) |

## 3. Aşama D — dev-time masa (bu PR)

Kök dizin bir Claude Code plugin'i oldu (`.claude-plugin/`), kullanıcının yereldeki
gitignore'lu `.claude/` klasörüyle çakışmaz:

- `agents/`: market-analyst, strategist, risk-manager, execution-ops, trade-reviewer, pine-engineer
- `skills/`: mevcut 7 skill + `desk-operating-model` + `luxalgo-smc`
- `hooks/live_write_gate.py` + `tests/hooks/` (51 test)
- Kurulum: `/plugin marketplace add Leblepito/efloud-bot` → `/plugin install efloud-desk@efloud`
  (yerel klonda: `/plugin marketplace add ./`). `claude plugin validate .` geçiyor.

Trade mantığına, config'e, safety'ye dokunulmadı.

## 4. Runtime yol haritası (operatör onayı gerekli — CLAUDE.md ilke 1)

Bugün: `engine/agents/` (Overseer, Regime, SignalValidator, RiskReviewer, PostMortem)
kök `config.yaml`'da açık, ama **canlı prod config'de (`configs/config.phase2_1k.yaml`)
`agent_team` bloğu yok → prod'da kapalı** (`safe_orchestrator.py:711`, tek-dosya config).

- **R1 — Gözlem (shadow).** Prod config'e `agent_team: {enabled: true, gating: false}`.
  Verdict'ler `state/agent_disagreements.jsonl`'e yazılır, işlem akışı değişmez.
  Ölçüm: ajan "reddet" dediği sinyallerin NET sonucu vs kabul ettikleri (signal ledger).
  Maliyet: sinyal başına LLM çağrısı (prod `llm.provider: minimax`). Ticket ile deploy.
- **R2 — Raporlama.** Rutinler (`scripts/routines/`) günlük brief + review'i rol formatında
  Telegram'a yollar. Read-only.
- **R3 — Veto-only gating (opsiyonel).** Ancak R1'de yeterli örneklemde (öneri ≥100
  sinyal) ajan vetosu NET expectancy'yi anlamlı iyileştirirse. Ajan yalnız **engelleyebilir**,
  asla emir/size/SL/TP **üretemez**. Açık karar: LLM hatasında fail-open (motor devam)
  mı fail-closed (işlem yok) mı?

**Asla:** LLM'in emir açması, size/SL/TP belirlemesi, risk limitlerini değiştirmesi.

## 5. Operatör kararları

1. **LuxAlgo lisansı (kritik).** `engine/smc_v2/luxalgo.py` CC BY-NC-SA 4.0 bir script'in
   port'u ve canlı mainnet'te aktif (`smc_v2.luxalgo.enabled: true`); u2algo ticari.
   NC (ticari olmayan) şartı bu kullanımı kapsıyor olabilir. Hukuki görüş alınması ve
   seçeneklerin (LuxAlgo'dan ticari izin / kendi bağımsız implementasyon / kişisel kullanım
   sınırı) değerlendirilmesi önerilir. Bu bir hukuki tavsiye değildir.
2. R1'e geçilsin mi (prod'da advisory takım shadow modda)?
3. R3 için fail-open / fail-closed tercihi.

## 6. Bu incelemede yapılamayanlar

- TradingView sayfası (`tr.tradingview.com/v/CnB3fSph`) bulut oturumunun ağ politikası
  nedeniyle açılamadı; LuxAlgo mantığı repodaki port'tan (`engine/smc_v2/luxalgo.py`)
  okundu.
- TradingView Desktop MCP araçları yalnız operatörün masaüstü oturumunda var.

## 7. Ek inceleme (2026-11-03, ikinci tur): tradingview-mcp, day-trader-skill, TradingAgents

Üçü de shallow clone, **hiçbir kodu çalıştırılmadı**; sabitlenen commit'ler aşağıda.

| Repo @ commit | Lisans | Güvenlik bulgusu | Karar |
| --- | --- | --- | --- |
| tradesdontlie/tradingview-mcp @ `c05b8f5` | MIT | Kurulumda kod yok (2 bağımlılık). CDP `127.0.0.1:9222`, **kimlik doğrulamasız**. **Yüksek risk:** `ui_evaluate` (oturumu açık TradingView'da keyfi JS), `ui_click`/`ui_keyboard` (Trading Panel dahil her buton), `tv_update` (upstream `main`'e fast-forward = incelenmemiş kod). Paketteki `performance-analyst` agent'ı `tools: "*"`. | Repoya kopyalanmadı. `skills/tradingview-mcp`: sabit commit'le kurulum + riskli araçlar için deny listesi + "TradingView'a broker bağlama" uyarısı + LuxAlgo parity prosedürü. Yalnız operatörün masaüstünde çalışır. |
| Jakeschincariol/day-trader-skill @ `3d0f4ef` | MIT | Temiz: tek `subprocess` = `pdftotext`; ağ = Yahoo/SEC/House/Nasdaq (salt okuma); gizli talimat/Unicode yok. `trader-broker` IBKR/Alpaca emir gönderir (onaylı). | 11 skill'in 10'u ABD hissesine bağlı (NYSE seansı, ORB, PDT; `trader-risk` kriptoyu bloklar) → alınmadı. **Time Machine** Binance'e uyarlandı: `scripts/desk/plan_replay.py` + `skills/plan-replay` (20 test). efloud'da offline backtest olmadığı için gerçek boşluk dolduruyor. |
| TauricResearch/TradingAgents @ `c454491` | Apache-2.0 | Emir yürütme yok (analiz + 5'li rating). pickle/eval yok; `subprocess` sadece kendi login'i. ChatGPT OAuth token'ı `~/.tradingagents` 0600 (opsiyonel). CLI `api.tauric.ai` duyurularını çeker (kütüphane çekmez). Haber/Reddit/Stocktwits metni LLM'e girer → prompt injection yüzeyi. **`pandas>=3.0.6` ↔ bizim `pandas==3.0.3` çakışması.** | Bot ortamına/imajına **kurulmadı**. İzole `.venv-research` + `requirements-research.txt` (pinli). Adaptör `scripts/desk/tradingagents_brief.py` (25 test, kütüphane olmadan test edilir) → `desk/briefs/` altına advisory brief + motor bias'ı ile karşılaştırma. Yeni rol `research-analyst`. |

**Agent'ların skill'leri otomatik kullanması:** her agent frontmatter'ında `skills:` listesi var;
Claude Code bu skill'lerin tam içeriğini agent başlarken bağlama enjekte eder
(code.claude.com/docs/en/sub-agents → "Preload skills into subagents"). Plugin skill'lerinin
`skills:` içinde yalın mı `efloud-desk:` önekli mi yazılacağı dokümante değil; yalın ad
kullanıldı ve her agent'a "yoksa Skill aracıyla çağır" yedeği eklendi.
`tests/hooks/test_desk_plugin.py` her listelenen skill'in var olduğunu doğrular.

**LuxAlgo lisansı:** TradingView'ı bağlamak lisans sorusunu değiştirmez; lisans metni
(CC BY-NC-SA 4.0) port'un docstring'inde ve script'in kaynak başlığında zaten var.
tradingview-mcp'nin buradaki değeri **parity kontrolü** (indikatör çıktısı vs `analyze()`).
Hukuki karar §5'te açık kalıyor.
