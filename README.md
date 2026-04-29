# Efloud SMC Trade Bot v2.1

Çok-coinli, güvenli, Efloud Price Action kurallı algoritmik trade botu.
Binance futures üzerinde çalışır; önce testnet + dry_run, sonra mainnet.

## Özellikler

- **10 coin takibi**: Sabit çekirdek (BTC/ETH/SOL/BNB/XRP/RENDER) + dinamik top-volume
- **Efloud SMC analizi**: CHoCH/BOS, Order Block, FVG, SFP, OTE, Range
- **Multi-timeframe**: HTF bias → MTF onay → Entry TF giriş
- **Confluence scoring**: Minimum %80 (sıkı filtre — kalite > miktar)
- **R:R ≥ 2**: Her sinyal minimum 1:2 oranı sağlamalı
- **5 katmanlı güvenlik**:
  - Circuit breaker (daily loss, weekly DD halt, consecutive loss)
  - Regime detector (trending/ranging/volatile)
  - Position guards (size cap, exposure, tight-SL rejection)
  - State persistence (crash recovery)
  - Mainnet guard (yanlışlıkla canlıya çıkmaya karşı)
- **Yaşayan pozisyon yönetimi**: Partial TP, piramit ekleme, hedge pozisyonlar
- **Efloud tarzı rapor**: Her cycle markdown rapor (pozisyon durumu, senaryolar, öneri)

## Hızlı Başlangıç

```bash
# 1. Paket aç
tar -xzf efloud-bot-v2.1.tar.gz
cd efloud-bot

# 2. Bağımlılıklar
pip install -r requirements.txt

# 3. API credentials (env var önerilir)
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"

# 4. Offline testleri çalıştır
python test_safety.py       # güvenlik katmanları
python test_regime.py       # rejim tespiti
python test_offline.py       # orchestrator smoke test

# 5. Backtest (synthetic data)
python test_backtest.py
python test_backtest_multi.py

# 6. Testnet'te canlı — dry run
python main.py

# 7. MAINNET LIVE (dikkatli!):
export EFLOUD_ALLOW_MAINNET=1
# config.yaml'da testnet: false, dry_run: false yap
python main.py
```

## Config (Özet)

```yaml
symbols:
  mode: hybrid                  # 6 fixed + 4 dynamic = 10 coin
  fixed_core: [BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT, RENDER/USDT]
  dynamic_top_n: 4

timeframes:
  htf: 4h | mtf: 1h | entry: 15m

risk:
  min_confluence: 80           # Senin kuralın: %80+
  min_rr: 2.0                   # Senin kuralın: 1:2
  risk_per_trade_pct: 1.0

safety:
  max_position_notional_pct: 5.0  # 10 coin için dağılım
  daily_loss_limit_pct: 3.0
  weekly_drawdown_limit_pct: 8.0
```

## Mimari

```
main.py
  └─ SafeOrchestrator (engine/safe_orchestrator.py)
       ├─ SymbolUniverse (universe.py)         ← 10 coin resolver
       ├─ SMCEngine (smc.py)                    ← swing/CHoCH/OB/FVG
       ├─ LevelEngine (levels.py)               ← MO/WO/DO
       ├─ IntentEngine (intent.py)              ← istekli alım
       ├─ ScenarioPlanner (scenarios.py)        ← 3 senaryo
       ├─ PositionLifecycle (lifecycle.py)      ← hedge/piramit
       ├─ ReportEngine (report.py)              ← Efloud stil markdown
       ├─ RegimeDetector (regimes/)             ← trending/ranging
       └─ Safety Layer (safety/)
            ├─ CircuitBreaker                   ← daily/weekly loss
            ├─ PositionGuard                     ← size/SL/exposure
            ├─ StateStore                        ← crash recovery
            ├─ ExchangeGuard                     ← retry/rate-limit
            └─ MainnetGuard                      ← canlı koruması
```

## Testler

| Test | Amaç | Durum |
|---|---|---|
| test_safety.py | Circuit breaker, state, position guards | ✅ 8/8 |
| test_regime.py | Trending/Ranging/Volatile sınıflama | ✅ 3/3 |
| test_offline.py | Orchestrator synthetic smoke test | ✅ |
| test_backtest.py | Tek senaryo walk-forward backtest | ✅ |
| test_backtest_multi.py | 7 farklı piyasa rejimi | ✅ (az sinyal — synthetic data beklenen) |
| test_smoke.py | Network'lü ETH test (SSL var ortamda) | ⚠️ env bağlı |
| test_real_data.py | Gerçek Binance datasıyla | ⚠️ API key gerek |

## Risk Haritası

Bkz `RISK_MAP.md` — 30+ arıza senaryosunun tam analizi:
- Piyasa rejimleri (choppy, blow-off, reversal, news spike)
- Teknik arızalar (API 503, stale data, clock drift, crash)
- Pozisyon riskleri (runaway loss, over-leverage, orphan hedge)
- Veri kalitesi (timezone, volume NaN, rounding)
- Operasyonel (secret leak, mainnet kazası, log spam)

## Canlıya Geçiş Kontrol Listesi

- [ ] Min 1 hafta testnet + dry_run çalıştır, raporları okuyup onaylar
- [ ] Reports klasöründeki markdown'ları gözden geçir
- [ ] Circuit breaker trip senaryolarını simüle et (backtest'le)
- [ ] `BINANCE_API_KEY` ve `BINANCE_API_SECRET` env var olarak ayarla (config'e asla yazma)
- [ ] `EFLOUD_ALLOW_MAINNET=1` ayarla
- [ ] Config'de `testnet: false`, `dry_run: true` bırak → 2-3 gün izle
- [ ] Sonra `dry_run: false` yap, küçük bakiye ile başla
- [ ] Weekly DD limit'e ulaşırsan HALT olur, manual reset gerek

## Uyarılar

- Efloud kendisi de haftada 1-2 setup alır. `min_confluence: 80` ile bot da seçici — az trade normaldir
- Synthetic data'da trade sayısı düşüktür (random walk'ta OB/FVG yapıları temiz oluşmaz)
- Gerçek BTC/ETH datasında setup sayısı daha yüksek olur
- İlk canlı kullanımdan önce `RISK_MAP.md`'yi mutlaka oku
