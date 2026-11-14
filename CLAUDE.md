# EFloud-Bot — TradingView Pine Script Projesi

> **🚀 Sonraki Claude için Başlangıç Noktası:** Bu dosya projenin **kalıcı kurallarıdır** (anayasa). Güncel canlı durum: `collab/STATUS.md`; tarihli durum notları: `docs/history/claude-md-status-archive.md`. **Dashboard:** `https://2-28-139-82.nip.io` / panel: VPS'teki birleşik panel (`panel/main.py`; `bot.u2algo.com` Railway kopyası ve DNS kaydı 2026-11-07'de silindi). **Ana iş:** Bot mantığını TradingView Pine Script'e çevirmek (ürün: indicator, kaynak `pine/lab/*` → `pine/efloud_lab.pine`; Pine strategy ürünü ADR-0005 ile rafa kalktı). **Kritik kurallar:** (1) Pine-çeviri görevinde Python kaynak mantığını DEĞİŞTİRME — sadece oku ve referans al (canlı trade mantığı değişikliği ayrı iştir: ADR-0003 kapısı + Karpathy 1/3), (2) Pine v6 syntax ZORUNLU, (3) Her değişiklik TDD + risk-ops review + backtest-gate.

## Cowork/Sandbox Git Uyarısı (2026-07-03)

Cowork sandbox'ından bu repo'da çalışırken mount senkron katmanı git metadata'sını
bozabiliyor (`.git/index` null-byte korupsiyonu, `.git/config` boşalması, Windows
edit'lerinin Linux'ta kesik görünmesi). Kural: (1) commit'leri `GIT_INDEX_FILE=/tmp/...`
sandbox-local index ile yap, (2) her git hatasında önce ilgili `.git/` dosyasında
null-byte kontrolü yap, (3) dosya yazımlarını tek seferde deterministik yap.
Detay: `git show f96b7d8^:docs/handoff/2026-07-03-merge-bugfix-and-repo-hardening.md` (doküman `f96b7d8`'de repodan kaldırıldı, git geçmişinde duruyor).

## Amaç
Bu repo Python ile yazılmış bir trading botudur (`efloud-bot`). Hedef: bu botun
çekirdek trade mantığını (Multi-Timeframe Smart Money Concepts + Confluence Scoring)
TradingView Pine Script v6'ya çevirmek — ürün INDIKATÖR'dür; STRATEGY versiyonu yalnız
Python↔Pine parity artefaktıdır, ürün değildir (ADR-0005).

## Çalışma Kuralları
- Pine kaynağı `pine/lab/*` parçalarıdır (`head_*` + `core.pine` + `tail_*`); `pine/efloud_lab.pine`
  (indikatör) ve `pine/efloud_lab_strategy.pine` (parity artefaktı) `python scripts/build_pine_lab.py`
  ile üretilir, elle düzenlenmez (`--check` = drift kontrolü). Eski çiftler
  (`pine/efloud_signals*.pine`, `pine/efloud_strategy*.pine`) ARŞİV'dir.
- Pine-çeviri görevinde Python kaynak mantığını DEĞİŞTİRME. Sadece oku ve referans al.
  Canlı trade mantığı değişiklikleri bu kuralın değil ADR-0003 kapısının (+ aşağıdaki
  Karpathy 1/3) konusudur. *(LLM danışma katmanı `engine/agents/` **additive**'dir —
  trade mantığına dokunmaz, yalnız danışma (advisory) çağrısı ekler; mevcut breaker /
  guard / orphan koruması değişmez. Detay: `docs/adr/0002-llm-layer-is-advisory-only.md`.)*
- Çeviri kararlarını ve teknik haritaları `pine/PINE_SPEC.md` içinde belgele.
- Pine Script v6 syntax ZORUNLU: `indicator()`/`strategy()`, `ta.ema()`/`ta.rsi()`/`ta.atr()`, doğru `var`/`series` tiplemesi. Asla legacy (`study()`, `ema()`) kullanma.
- Ortak mantık `pine/lab/core.pine`'da tek kaynaktır; indikatör ve parity strateji aynı input isimlerini kullanır.

## Geliştirme Sözleşmesi — Karpathy Prensipleri (efloud-bot'a uyarlanmış)

> Ham prensip metni 2026-07-11'de bu bölüme absorbe edildi (ayrı dosya artık yok — plugin kurulu olmayan ortamlarda da geçerli).

Bu repo'daki HER kod değişikliği (Claude/Gemini/Hermes) aşağıdaki 4 prensibe uyar. Prensipler efloud-bot'un mevcut sert kurallarını **güçlendirir**, değiştirmez. (Kaynak: Andrej Karpathy LLM-coding pitfalls; `andrej-karpathy-skills` plugin.)

1. **Think Before Coding ↔ risk-ops + operatör sign-off** — Mainnet trade mantığına (`engine/safety/`, `engine/risk/`, `engine/lifecycle.py`, `exchange/`, `config` `safety:`/`risk:` blokları) dokunan değişiklik ÖNCE varsayımları + risk trade-off'larını açıkça yazar; birden fazla yorum varsa sessizce seçme — operatöre sun; mainnet'e gitmeden risk-ops review + operatör onayı zorunlu.
2. **Simplicity First ↔ confluence/scoring sadeliği** — Minimum kod, spekülatif soyutlama/flag/configurability yok. Doğrudan audit bulgularına bağlanır: confluence over-counting (M2), post-cap bonus split-brain (H1), dual-ATR (M3) → karmaşıklık ekleme, sadeleştir. "Bir senior mühendis buna over-complicated der mi?" → evet ise sadeleştir.
3. **Surgical Changes ↔ atomic-PR + guard koruması + SMC v2 port** — Sadece gerekeni değiştir; her değişen satır isteğe izlenebilir olmalı. Mevcut safety guard'ı ASLA zayıflatma; SMC v2 port'unu (`pine/lab/core.pine`, `engine/smc_v2/` — özellikle `engine/smc_v2/luxalgo.py`; arşiv `pine/efloud_signals.pine` de) ezme; ilgisiz/önceden var olan dead-code'u SİLME — işaretle (örn. audit H7 ölü rr1-gate). Sadece KENDİ değişikliğinin orphan'larını temizle.
4. **Goal-Driven Execution ↔ backtest-gate + TDD** — Her görevi test-önce doğrulanabilir hedefe çevir: edge/scoring değişikliği → NET-cost backtest gate (offline: `python -m backtest.cli`; forward: gölge logları. Edge Measurement Core / `signal_ledger` canlı v2 akışında veri üretmez — flag kapalı `configs/config.phase2_1k.yaml:467-468`, hook v1 dalında `engine/safe_orchestrator.py:1497→1567`); bug fix → önce reprodüksiyon testi. Yeni davranış toggle'ı default OFF / fail-closed. Bu audit'in C1–C4 / H1–H7 / M1–M5 bulguları önceden yazılmış hedeflerdir: her fix bir failing test + cerrahi diff + geçilen gate (risk-ops/backtest/operatör) gösterir.

> Bu sözleşme `git show f96b7d8^:docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md` audit'inin fix'lerini yürütmek için standing dev-contract'tır.

## Kanonik kaynaklar (2026-11-07)
- Alan dili (V1/V2 bot ↔ SMC v1/v2, breaker OPEN = normal, orphan ↔ bare): `CONTEXT.md`
- Kararlar ve gerekçeleri: `docs/adr/README.md` (ADR-0003 = risk/edge değişiklik kapısı)
- Korunan kurallar → test kanıtı: `TESTS.md` · modül regresyonu: `REGRESSION.md` (`python scripts/regression_ledger.py run --base origin/master`)
- Deploy sonrası: `python scripts/canary.py` · anlık durum: `collab/STATUS.md`
- NET-cost backtest kapısı: `python -m backtest.cli single|portfolio --config configs/config.phase2_1k.yaml` (canlı trade mantığı; çıkışlar borsa ile aynı: TP1 %50 → BE → TP2). Veri: `python -m scripts.prefetch_data --config …`.

## TradingView MCP Araçları (Desktop debug portu açık olmalı)
- `tv_health_check` → bağlantı + aktif sembol kontrolü
- `pine_set_source` → kodu Pine Editor'a enjekte et
- `pine_smart_compile` → derle
- `pine_get_errors` → hataları oku, düzelt, yeniden derle (sıfır hata olana kadar)
- `pine_save` → TradingView cloud'a kaydet

## Canlı motor
- SMC v2 **LuxAlgo modu** (`configs/config.phase2_1k.yaml:180-188`; v2 whitelist + `smc_v2_shadow` `:90-95`). v1 confluence hesaplanır ama v2 sembollerinde girişi susturulur (`engine/safe_orchestrator.py:1486-1495`).
- Akış: HTF lux swing bias → entry-TF CHoCH/BOS → kırılımın OB'sine retest → entry-TF engulfing kapanışı → **MARKET** emir (`exchange/__init__.py:1151-1153`). SL = OB ucu + `calc_sl` ATR bandı; TP1 = ≥ `risk.min_rr` lux adayı.
- Ayrıntı + canlıda etkili/inert anahtarlar: `CONTEXT.md` · anlık durum: `collab/STATUS.md` · ölçülmüş NET edge: `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §0.

## Pine Script Kısıtları (Python'da olup Pine'a tam çevrilemeyecekler)
- Harici API çağrıları (Gemini AI Structure Validation, sentiment, REST/websocket) → Pine'da atlanmalı, kural tabanlı statik karşılıklar veya input parametreleri eklenmeli. **Not:** `engine/agents/` Python tarafında bu çağrıları ortak bir LLM istemcisi üzerinden toplar (sağlayıcı fabrikası `engine/agents/llm.py`; `GeminiClient` adı tarihsel); Pine'a çevirirken bu katman **atlanır** (Pine LLM çağrısı yapamaz), kural tabanlı karşılıklar yazılır.
- CCXT, DB erişimi, dosya I/O → Pine'da sadece grafikte çizim ve strateji emri olur.
- pandas tabanlı look-ahead hesaplar → Pine'da repaint riskine dikkat (sadece kapanmış bar `[1]` veya barstate.isconfirmed kullanılmalı).

## Kalıcı yapı notları
- **u2algo-site** (Railway root dir `/u2algo-site`) bu repoda **kalmalı**; statik HTML + `server.js`, canlı `https://u2algo.com`.
- **Sosyal yayın hattı** (chart → video → caption → onaylı yayın): `skills/social-publishing/SKILL.md`, marka sesi `docs/social/BRAND_VOICE.md`.
