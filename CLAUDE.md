# EFloud-Bot — TradingView Pine Script Projesi

> **🚀 Sonraki Claude için Başlangıç Noktası:** Bu README projenin giriş noktasıdır. **Son çalışma (2025-01-20):** SL/TP Precision + Candle-Close Sync implementation tamamlandı (6 commit push edildi: price precision rounding, candle-close sync tests, config interval reduction). Branch: `feat/v2-nipio-dashboard`. Unstaged changes var (`backend/bot_runner.py`, `main.py`). **Dashboard:** `https://bot.ualgotrade.com` / `https://178-104-122-91.nip.io`. **Ana iş:** Bot mantığını TradingView Pine Script'e çevirmek (hem indicator hem strategy). **Kritik kurallar:** (1) Python kaynak mantığı DEĞİŞTİRME — sadece oku ve referans al, (2) Pine v6 syntax ZORUNLU, (3) Her değişiklik TDD + risk-ops review + backtest-gate.

## Cowork/Sandbox Git Uyarısı (2026-07-03)

Cowork sandbox'ından bu repo'da çalışırken mount senkron katmanı git metadata'sını
bozabiliyor (`.git/index` null-byte korupsiyonu, `.git/config` boşalması, Windows
edit'lerinin Linux'ta kesik görünmesi). Kural: (1) commit'leri `GIT_INDEX_FILE=/tmp/...`
sandbox-local index ile yap, (2) her git hatasında önce ilgili `.git/` dosyasında
null-byte kontrolü yap, (3) dosya yazımlarını tek seferde deterministik yap.
Detay: `docs/handoff/2026-07-03-merge-bugfix-and-repo-hardening.md`.

## Amaç
Bu repo Python ile yazılmış bir trading botudur (`efloud-bot`). Hedef: bu botun
çekirdek trade mantığını (Multi-Timeframe Smart Money Concepts + Confluence Scoring)
TradingView Pine Script v6'ya çevirmek — hem INDIKATÖR hem de STRATEGY (backtest) versiyonu olarak.

## Çalışma Kuralları
- Pine kodları `pine/` klasörüne yazılır: `pine/efloud_signals.pine`, `pine/efloud_strategy.pine`.
- Python kaynak mantığını DEĞİŞTİRME. Sadece oku ve referans al. *(İstisna: bu
  repo şu sıralar paralel olarak `engine/agents/` altına çalışan bir LLM danışma
  katmanı ekliyor. Bu katman **additive**'dir — `safe_orchestrator.py` trade
  mantığına dokunmaz, sadece sinyal sonrası bir danışma (advisory) çağrısı ekler.
  Mevcut breaker / guard / orphan koruması değişmez. Detay için `AGENTS.md` →
  "Runtime Agent Team" bölümüne bak.)*
- Çeviri kararlarını ve teknik haritaları `pine/PINE_SPEC.md` içinde belgele.
- Pine Script v6 syntax ZORUNLU: `indicator()`/`strategy()`, `ta.ema()`/`ta.rsi()`/`ta.atr()`, doğru `var`/`series` tiplemesi. Asla legacy (`study()`, `ema()`) kullanma.
- Her değişiklikte indikatör ve strateji versiyonlarını SENKRON tut (aynı input isimleri).

## Geliştirme Sözleşmesi — Karpathy Prensipleri (efloud-bot'a uyarlanmış)

Bu repo'daki HER kod değişikliği (Claude/Gemini/Hermes) aşağıdaki 4 prensibe uyar. Prensipler efloud-bot'un mevcut sert kurallarını **güçlendirir**, değiştirmez. (Kaynak: Andrej Karpathy LLM-coding pitfalls; `andrej-karpathy-skills` plugin.)

1. **Think Before Coding ↔ risk-ops + operatör sign-off** — Mainnet trade mantığına (`engine/safety/`, `engine/risk/`, `engine/lifecycle.py`, `exchange/`, `config` `safety:`/`risk:` blokları) dokunan değişiklik ÖNCE varsayımları + risk trade-off'larını açıkça yazar; birden fazla yorum varsa sessizce seçme — operatöre sun; mainnet'e gitmeden risk-ops review + operatör onayı zorunlu.
2. **Simplicity First ↔ confluence/scoring sadeliği** — Minimum kod, spekülatif soyutlama/flag/configurability yok. Doğrudan audit bulgularına bağlanır: confluence over-counting (M2), post-cap bonus split-brain (H1), dual-ATR (M3) → karmaşıklık ekleme, sadeleştir. "Bir senior mühendis buna over-complicated der mi?" → evet ise sadeleştir.
3. **Surgical Changes ↔ atomic-PR + guard koruması + SMC v2 port** — Sadece gerekeni değiştir; her değişen satır isteğe izlenebilir olmalı. Mevcut safety guard'ı ASLA zayıflatma; SMC v2 port'unu (`pine/efloud_signals.pine`, `engine/smc_v2/`) ezme; ilgisiz/önceden var olan dead-code'u SİLME — işaretle (örn. audit H7 ölü rr1-gate). Sadece KENDİ değişikliğinin orphan'larını temizle.
4. **Goal-Driven Execution ↔ backtest-gate + TDD** — Her görevi test-önce doğrulanabilir hedefe çevir: edge/scoring değişikliği → NET-cost backtest gate (Edge Measurement Core, PR #227); bug fix → önce reprodüksiyon testi. Yeni davranış toggle'ı default OFF / fail-closed. Bu audit'in C1–C4 / H1–H7 / M1–M5 bulguları önceden yazılmış hedeflerdir: her fix bir failing test + cerrahi diff + geçilen gate (risk-ops/backtest/operatör) gösterir.

> Bu sözleşme `docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md` audit'inin fix'lerini yürütmek için standing dev-contract'tır.

## TradingView MCP Araçları (Desktop debug portu açık olmalı)
- `tv_health_check` → bağlantı + aktif sembol kontrolü
- `pine_set_source` → kodu Pine Editor'a enjekte et
- `pine_smart_compile` → derle
- `pine_get_errors` → hataları oku, düzelt, yeniden derle (sıfır hata olana kadar)
- `pine_save` → TradingView cloud'a kaydet

## Efloud Çekirdek Mantığı & Parametreleri (Referans Değerler)
- **Timeframe Chain**: HTF (4h) Trend/Bias, MTF (1h) swing breaks, Entry (15m) trigger + SL/TP, Daily (1d) makro filter.
- **HTF Bias Fallback (HTF UNDEF)**: 4h `analyze().trend` UNDEF ise sırayla: (1) son 40 4h-bar slope; |Δ| > %2 → BULL/BEAR (signals.py:308-317). (2) slope nötr (|Δ| ≤ %2) ise **Entry-TF (15m) range** discount/premium'undan türetilir: discount→BULL, premium→BEAR (signals.py:318-322 `range_info(df_entry)`). Bu, 15m bir "range play" senaryosudur ve dokümante edilen HTF(4h)→Entry(15m) yetki zincirini bu özel durumda kasıtlı olarak tersine çevirir. (3) Ne slope ne aktif range varsa → sinyal yok (skip, signals.py:323-325). df_htf < 40 bar → skip (signals.py:326-328).
- **Swing Lookback**: 5 (Sol ve sağda 5 daha düşük high / daha yüksek low).
- **Order Blocks (OB)**: 5 ardışık mum (`ob_sequential: 5`). Breakout mumunun gövdesi (body) > 1.5 * SMA(high-low, 14) olmalı (true-range ATR DEĞİL; bkz. PINE_SPEC §A.3 / smc.py:195).
- **Confluence Threshold**: Minimum 55.
- **Stop Loss (SL)**: Breakout öncesi son 20 mumun en düşük/en yüksek seviyesi + ATR(14, true-range) * 0.5 (veya yüksek volatilitede * 0.75) buffer (true-range; bkz. PINE_SPEC §A.4 / signals.py:518-522). Minimum 0.1% mesafe clamp'i.
- **Take Profit (TP)**: 
  - TP1: Yakın HTF likidite swing'leri / Equal Highs-Lows. Range deviation varsa Range EQ. Price discovery durumunda (yapı yoksa) 1.272 Fibo. Min R:R: 1.5.
  - TP2: Karşı Range Extreme (deviation'da) veya 1.618 / 2.618 Fibo uzantısı.

## Pine Script Kısıtları (Python'da olup Pine'a tam çevrilemeyecekler)
- Harici API çağrıları (Gemini AI Structure Validation, sentiment, REST/websocket) → Pine'da atlanmalı, kural tabanlı statik karşılıklar veya input parametreleri eklenmeli. **Not:** `engine/agents/` Python tarafında bu çağrıları ortak bir `GeminiClient` üzerinden toplar; Pine'a çevirirken bu katman **atlanır** (Pine LLM çağrısı yapamaz), kural tabanlı karşılıklar yazılır.
- CCXT, DB erişimi, dosya I/O → Pine'da sadece grafikte çizim ve strateji emri olur.
- pandas tabanlı look-ahead hesaplar → Pine'da repaint riskine dikkat (sadece kapanmış bar `[1]` veya barstate.isconfirmed kullanılmalı).


## 🚀 Son Durum & Güncel Gelişmeler (2026-05-31)

1. **u2algo-site & Railway Servisi**:
   - Next.js 15 ve Node.js 20 tabanlı pazarlama sayfası Railway üzerinde `considerate-intuition` projesi (`u2algo-site` servisi) altında yayındadır.
   - Canlı URL: `https://u2algo-site-production.up.railway.app`

2. **Supabase REST & Fallback Entegrasyonu**:
   - `server.js` backend katmanı 3'lü veritabanı korumasıyla güncellendi:
     1. `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` varsa Supabase REST API ile kayıt. (Canlıda şu an bu aktif!).
     2. `DATABASE_URL` veya `SUPABASE_DATABASE_URL` varsa doğrudan PostgreSQL (`pg` driver) ile kayıt ve otomatik tablo migrasyonu (`ensureWaitlistTable`).
     3. Her iki DB bağlantısı koptuğunda veya erişilemez olduğunda `local-jsonl` (`data/waitlist_leads.jsonl`) fallback korumasıyla kesintisiz `200 OK` yanıtı.
   - **Mevcut Canlı Durum**: Kırık direct Postgres bağlantısı (`DATABASE_URL`) kaldırıldı. `SUPABASE_URL` ve Key'ler Railway'e başarıyla bağlandı. REST API yetkilendirmesi çalışıyor (health check `PGRST205` dönüyor; yani tablo henüz hazır değil). Tablo oluşturulana kadar waitlist kayıtları yerel JSONL fallback'ine güvenle yazılıyor.

3. **Hermes MCP Postgres Sunucusu**:
   - Local makinede `supabase_postgres` MCP server kuruldu (7 tool: `health`, `list_tables`, `table_columns`, `ensure_waitlist_leads`, `waitlist_count`, `waitlist_list`, `waitlist_insert`).


