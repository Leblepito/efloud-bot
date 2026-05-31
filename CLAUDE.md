# EFloud-Bot → TradingView Pine Script Projesi

## Amaç
Bu repo Python ile yazılmış bir trading botudur (`efloud-bot`). Hedef: bu botun
çekirdek trade mantığını (Multi-Timeframe Smart Money Concepts + Confluence Scoring)
TradingView Pine Script v6'ya çevirmek — hem INDIKATÖR hem de STRATEGY (backtest) versiyonu olarak.

## Çalışma Kuralları
- Pine kodları `pine/` klasörüne yazılır: `pine/efloud_signals.pine`, `pine/efloud_strategy.pine`.
- Python kaynak mantığını DEĞİŞTİRME. Sadece oku ve referans al.
- Çeviri kararlarını ve teknik haritaları `pine/PINE_SPEC.md` içinde belgele.
- Pine Script v6 syntax ZORUNLU: `indicator()`/`strategy()`, `ta.ema()`/`ta.rsi()`/`ta.atr()`, doğru `var`/`series` tiplemesi. Asla legacy (`study()`, `ema()`) kullanma.
- Her değişiklikte indikatör ve strateji versiyonlarını SENKRON tut (aynı input isimleri).

## TradingView MCP Araçları (Desktop debug portu açık olmalı)
- `tv_health_check` → bağlantı + aktif sembol kontrolü
- `pine_set_source` → kodu Pine Editor'a enjekte et
- `pine_smart_compile` → derle
- `pine_get_errors` → hataları oku, düzelt, yeniden derle (sıfır hata olana kadar)
- `pine_save` → TradingView cloud'a kaydet

## Efloud Çekirdek Mantığı & Parametreleri (Referans Değerler)
- **Timeframe Chain**: HTF (4h) Trend/Bias, MTF (1h) swing breaks, Entry (15m) trigger + SL/TP, Daily (1d) makro filter.
- **Swing Lookback**: 4 (Sol ve sağda 4 daha düşük high / daha yüksek low).
- **Order Blocks (OB)**: 5 ardışık mum (`ob_sequential: 5`). Breakout mumunun gövdesi (body) > 1.5 * ATR(14) olmalı.
- **Confluence Threshold**: Minimum 55.
- **Stop Loss (SL)**: Breakout öncesi son 20 mumun en düşük/en yüksek seviyesi + ATR(14) * 0.5 (veya yüksek volatilitede ATR * 0.75) buffer. Minimum 0.1% mesafe clamp'i.
- **Take Profit (TP)**: 
  - TP1: Yakın HTF likidite swing'leri / Equal Highs-Lows. Range deviation varsa Range EQ. Price discovery durumunda (yapı yoksa) 1.272 Fibo. Min R:R: 1.5.
  - TP2: Karşı Range Extreme (deviation'da) veya 1.618 / 2.618 Fibo uzantısı.

## Pine Script Kısıtları (Python'da olup Pine'a tam çevrilemeyecekler)
- Harici API çağrıları (Gemini AI Structure Validation, sentiment, REST/websocket) → Pine'da atlanmalı, kural tabanlı statik karşılıklar veya input parametreleri eklenmeli.
- CCXT, DB erişimi, dosya I/O → Pine'da sadece grafikte çizim ve strateji emri olur.
- pandas tabanlı look-ahead hesaplar → Pine'da repaint riskine dikkat (sadece kapanmış bar `[1]` veya barstate.isconfirmed kullanılmalı).

## 🚀 Son Durum & Güncel Gelişmeler (2026-05-31)

1. **u2algo-site & Railway Servisi**:
   - Next.js 15 ve Node.js 20 tabanlı pazarlama sayfası Railway üzerinde `considerate-intuition` projesi (`u2algo-site` servisi) altında yayındadır.
   - Canlı URL: `https://u2algo-site-production.up.railway.app`

2. **Supabase & Postgres Fallback Entegrasyonu**:
   - `server.js` backend katmanı 3'lü veritabanı korumasıyla güncellendi:
     1. `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` varsa Supabase REST API ile kayıt.
     2. `DATABASE_URL` veya `SUPABASE_DATABASE_URL` varsa doğrudan PostgreSQL (`pg` driver) ile kayıt ve otomatik tablo migrasyonu (`ensureWaitlistTable`).
     3. Her iki DB bağlantısı koptuğunda veya erişilemez olduğunda `local-jsonl` (`data/waitlist_leads.jsonl`) fallback korumasıyla kesintisiz `200 OK` yanıtı.
   - Supabase direct host bağlantısı IPv6-only olduğu için local ve Railway ortamlarında `ENETUNREACH` vermektedir. Çözüm olarak Supabase Dashboard'dan alınacak **IPv4 pooler DSN** ile `DATABASE_URL` güncellenmelidir.

3. **Hermes MCP Postgres Sunucusu**:
   - Local makinede `supabase_postgres` MCP server kuruldu (7 tool: `health`, `list_tables`, `table_columns`, `ensure_waitlist_leads`, `waitlist_count`, `waitlist_list`, `waitlist_insert`).

