# EFloud-Bot

Binance USD-M Futures üzerinde çalışan SMC (Smart Money Concepts) trade botu + TradingView Pine v6 indikatörü + izleme paneli / pazarlama sitesi.
Repo **PUBLIC**'tir: secret, kişisel veri ve ham veri dosyası commit'lenmez.
Bot **MAINNET**'te gerçek parayla işlem yapar; her değişiklik bu varsayımla ele alınır.

## Okuma sırası
1. `CONTEXT.md` — alan dili, canlı motor, canlıda etkili / inert anahtarlar
2. `AGENTS.md` — AI giriş haritası, test komutu
3. `collab/STATUS.md` — tek "anlık durum" kaynağı
4. `docs/adr/README.md` — kararlar ve gerekçeleri (ADR-0003 = risk/edge değişiklik kapısı)
5. `docs/STRATEGY_INTENT.md` — operatörün hedef setup'ı ve implementasyon sapmaları

## Değişmez kurallar
- Emri yalnız motor verir: hiçbir model emir açmaz, size/SL/TP/config değerini kendi belirlemez (`collab/README.md` §0).
- Secret yok: key/token repo'ya, commit'e, log'a, dokümana girmez; yalnız sunucudaki env dosyasında yaşar.
- `master`'a doğrudan push yok; her değişiklik branch + PR.
- Mevcut safety guard'ı (breaker, position guard, orphan koruması) ASLA zayıflatma.
- Her kod değişikliği TDD (önce failing test / reprodüksiyon); mainnet trade mantığı + ADR-0003 kapısı + risk-ops review + operatör onayı; edge/scoring + NET-cost backtest-gate (ADR-0011).
- Canlı davranış iddiası yalnız `config:satır` + kod yolu ile yazılır; bu dosyaya tarih, SHA ya da "şu an" cümlesi girmez.
- Pine-çeviri görevinde Python kaynak mantığını DEĞİŞTİRME. Sadece oku ve referans al.
  Canlı trade mantığı değişiklikleri bu kuralın değil ADR-0003 kapısının (+ aşağıdaki
  Karpathy 1/3) konusudur. *(LLM danışma katmanı `engine/agents/` **additive**'dir —
  trade mantığına dokunmaz, yalnız danışma (advisory) çağrısı ekler; mevcut breaker /
  guard / orphan koruması değişmez. Detay: `docs/adr/0002-llm-layer-is-advisory-only.md`.)*

## Geliştirme sözleşmesi (Karpathy 4 ilke)

Bu repo'daki HER kod değişikliği (Claude/Gemini/Hermes) aşağıdaki 4 prensibe uyar. Prensipler efloud-bot'un mevcut sert kurallarını **güçlendirir**, değiştirmez. (Kaynak: Andrej Karpathy LLM-coding pitfalls; `andrej-karpathy-skills` plugin.)

1. **Think Before Coding ↔ risk-ops + operatör sign-off** — Mainnet trade mantığına (`engine/safety/`, `engine/risk/`, `engine/lifecycle.py`, `exchange/`, `config` `safety:`/`risk:` blokları) dokunan değişiklik ÖNCE varsayımları + risk trade-off'larını açıkça yazar; birden fazla yorum varsa sessizce seçme — operatöre sun; mainnet'e gitmeden risk-ops review + operatör onayı zorunlu.
2. **Simplicity First ↔ confluence/scoring sadeliği** — Minimum kod, spekülatif soyutlama/flag/configurability yok. Doğrudan audit bulgularına bağlanır: confluence over-counting (M2), post-cap bonus split-brain (H1), dual-ATR (M3) → karmaşıklık ekleme, sadeleştir. "Bir senior mühendis buna over-complicated der mi?" → evet ise sadeleştir.
3. **Surgical Changes ↔ atomic-PR + guard koruması + SMC v2 port** — Sadece gerekeni değiştir; her değişen satır isteğe izlenebilir olmalı. Mevcut safety guard'ı ASLA zayıflatma; SMC v2 port'unu (`pine/lab/core.pine`, `engine/smc_v2/` — özellikle `engine/smc_v2/luxalgo.py`; arşiv `pine/efloud_signals.pine` de) ezme; ilgisiz/önceden var olan dead-code'u SİLME — işaretle (örn. audit H7 ölü rr1-gate). Sadece KENDİ değişikliğinin orphan'larını temizle.
4. **Goal-Driven Execution ↔ backtest-gate + TDD** — Her görevi test-önce doğrulanabilir hedefe çevir: edge/scoring değişikliği → NET-cost gate (offline: `python -m backtest.cli`; forward: gölge logları; GO kriteri: `docs/adr/0011-edge-go-criteria.md`); bug fix → önce reprodüksiyon testi. Yeni davranış toggle'ı default OFF / fail-closed. Algoritma audit'inin C1–C4 / H1–H7 / M1–M5 bulguları önceden yazılmış hedeflerdir (kanıt tablosu: `TESTS.md` §4.1): her fix bir failing test + cerrahi diff + geçilen gate (risk-ops/backtest/operatör) gösterir.

ECC kurallarıyla çatışmada geçerli olan: `docs/engineering-rules.md` (Karpathy > ECC).

## Kapılar ve komutlar
- Test: `python -m pytest --ignore=external_repos --import-mode=importlib -q` · korunan kural → kanıt: `TESTS.md`
- Modül regresyonu: `python scripts/regression_ledger.py run --base origin/master` (defter: `REGRESSION.md`)
- NET-cost backtest: `python -m backtest.cli single|portfolio --config configs/config.phase2_1k.yaml` (veri: `python -m scripts.prefetch_data --config …`; adımlar: `docs/runbooks/backtest-gate.md`)
- Deploy sonrası: `python scripts/canary.py` (canlı host listesi bu script'tedir)
- Pine üretim drift'i: `python scripts/build_pine_lab.py --check`

## Pine kuralları
- Pine Script v6 ZORUNLU: `indicator()`/`strategy()`, `ta.ema()`/`ta.rsi()`/`ta.atr()`, doğru `var`/`series` tiplemesi. Asla legacy (`study()`, `ema()`) kullanma.
- Ürün indikatördür (ADR-0005); strategy yalnız Python↔Pine parity artefaktıdır. İndikatör ve parity strateji dosyaları aynı input isimlerini kullanır (senkron).
- Kaynak `pine/lab/*` (`head_*` + `core.pine` + `tail_*`); `pine/efloud_lab.pine` ve `pine/efloud_lab_strategy.pine` `python scripts/build_pine_lab.py` ile üretilir — üretilen dosyaya elle dokunma. Eski çiftler (`pine/efloud_signals*.pine`, `pine/efloud_strategy*.pine`) ARŞİV'dir.
- Çeviri kararları `pine/PINE_SPEC.md`'ye yazılır (teknik haritalar ve Pine kısıtları — harici API, I/O, repaint — da orada, Ek K).
- Compile PASS ≠ runtime PASS: RE10045 tuzakları ve TradingView MCP araç döngüsü → `skills/tradingview-mcp/SKILL.md`.

## Commit / PR biçimi
`collab/README.md` §2 (branch + PR, dosyalar adıyla stage edilir, commit mesajı biçimi orada).

## Harness haritası
- `agents/` — desk rolleri (strategist, risk-manager, pine-engineer, …)
- `scripts/ci/agents/` — CI reviewer ajanları
- `engine/agents/` — runtime LLM danışma katmanı; advisory, emir yetkisi yok (ADR-0002)
- `skills/` — aktif proje skill'leri
- `hooks/live_write_gate.py` — canlı sisteme yazma kapısı (backstop)
- `.claude/` — yalnız lokal (gitignore'lu); repoda geçerli mühendislik kuralları `docs/engineering-rules.md`

## Kalıcı yapı notları
- **u2algo-site** (Railway root dir `/u2algo-site`) bu repoda **kalmalı**; statik HTML + `server.js`, canlı `https://u2algo.com`.
- **Sosyal yayın hattı** (chart → video → caption → onaylı yayın): `skills/social-publishing/SKILL.md`, marka sesi `docs/social/BRAND_VOICE.md`.
- Cowork/sandbox'tan git ile çalışırken: `docs/runbooks/cowork-git-pitfalls.md`.
