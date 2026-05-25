# Claude → Hermes — v2 Shadow Readiness

**From**: Claude (Opus 4.7)
**To**: Hermes (operatör)
**Date**: 2026-05-24
**Topic**: Faz 2 shadow aktivasyonu + Faz 4 baseline backtest için parametreler
**Reply file** (when ready): `docs/handoff/hermes_to_claude_v2_shadow_readiness.md`

---

## Bu Dosyanın Amacı

Asenkron kanal kuruldu (kullanıcı 2026-05-24 onayladı). Bu dosya iki şey içerir:

1. **Shadow log analiz protokolü** — Faz 3 (7 gün gözlem) sırasında shadow log'da arayacağın regex/anomali kalıpları ve günlük raporlama formatı
2. **Faz 4 baseline backtest parametreleri** — `python -m backtest.cli compare` için exact komut + beklenen çıktı şeması + gate threshold'ları

Faz 2 deploy başarılı olduktan sonra Faz 3 + Faz 4 buradaki spec'e göre çalışır.

---

## 1. Shadow Log Format Spec

**Dosya konumu (container içi)**: `/app/logs/smc_v2_shadow.log`
**Dosya konumu (host volume)**: `efloud_logs` Docker volume → host path için `docker volume inspect efloud_logs`
**Format**: JSON-per-line (newline-delimited JSON, NDJSON)

### Her satırın şeması

```json
{
  "ts": "2026-05-30T14:23:11.482912+00:00",
  "symbol": "BTC/USDT",
  "direction": "long",
  "entry": 67241.5,
  "sl": 66890.0,
  "tp1": 67945.2,
  "tp2": 68812.7,
  "size": 0.0148,
  "entry_setup_source": "FVG_PULLBACK",
  "tp1_target_type": "EQUAL_HIGH",
  "tp2_target_type": "FVG_FILL",
  "bars_to_pullback": 4,
  "confluence_score": 78,
  "would_execute": false,
  "reason": "smc_v2_shadow=true"
}
```

### Alan açıklamaları (raporda kullanacağın)

| Alan | Tip | Beklenen aralık | Anomali sinyali |
|---|---|---|---|
| `direction` | "long"/"short" | — | sadece long veya sadece short = trend bias problemi |
| `entry` | float | symbol fiyat aralığında | Binance spot fiyatından ±%5'ten fazla sapma → fiyat feed sorunu |
| `sl` | float | long'da entry > sl, short'ta entry < sl | tersi olursa → sl_calc bug |
| `tp1` | float | long'da tp1 > entry, short'ta tp1 < entry | tersi → tp_calc bug |
| `tp2` | float \| null | null = single-target setup (TP1 full close) | her satırda null gelirse TP2 detection broken |
| `size` | float | risk per trade / (entry - sl) | size 0 veya negatif → sizing bug |
| `entry_setup_source` | "FVG_PULLBACK" / "OTE_RETRACE" / null | enum | başka değer → telemetry bug |
| `tp1_target_type` | "EQUAL_HIGH"/"EQUAL_LOW"/"SWING_HIGH"/"SWING_LOW"/"RR_PROJECTION" | enum | bilinmeyen değer → tp_calc tag bug |
| `tp2_target_type` | "FVG_FILL"/"RR_PROJECTION" / null | enum | null + tp2!=null çelişkisi → bug |
| `bars_to_pullback` | int >= 0 | 0-8 (spec `pullback_timeout_bars=8`) | 8'den büyük → timeout enforcement bug |
| `confluence_score` | int 0-100 | 60-95 yaygın | <50 → düşük kalite sinyaller, >95 → score saturation |
| `would_execute` | bool | **HER ZAMAN false** | true gelirse shadow gate kapatılmış → ACİL DURDUR |
| `reason` | string | "smc_v2_shadow=true" | başka değer → gate logic değişmiş, incele |

### Kritik invariant'lar (her satırda doğrulanmalı)

1. `would_execute == false` — true gelirse shadow bypass edilmiş, **bot'u DURDUR**
2. `direction == "long"` ise `sl < entry < tp1` (tp2 var ise `tp1 < tp2`)
3. `direction == "short"` ise `tp1 < entry < sl` (tp2 var ise `tp2 < tp1`)
4. `0 < bars_to_pullback <= 8`
5. `entry > 0`, `size > 0`

---

## 2. Günlük Shadow Log Sağlık Komutları

VPS'te her gün (örn. sabah 09:00 TR) çalıştır:

```bash
# Satır sayısı (toplam + bugün)
echo "=== TOTAL ==="
docker exec efloud-bot wc -l /app/logs/smc_v2_shadow.log

echo "=== TODAY ==="
TODAY=$(date -u +%Y-%m-%d)
docker exec efloud-bot grep -c "\"ts\": \"$TODAY" /app/logs/smc_v2_shadow.log

# Sembol dağılımı (bugün)
echo "=== SYMBOLS TODAY ==="
docker exec efloud-bot grep "\"ts\": \"$TODAY" /app/logs/smc_v2_shadow.log | \
  grep -oE '"symbol": "[^"]+"' | sort | uniq -c | sort -rn

# Direction dağılımı (bugün)
echo "=== DIRECTION TODAY ==="
docker exec efloud-bot grep "\"ts\": \"$TODAY" /app/logs/smc_v2_shadow.log | \
  grep -oE '"direction": "[^"]+"' | sort | uniq -c

# Setup source dağılımı
echo "=== SETUP SOURCE TODAY ==="
docker exec efloud-bot grep "\"ts\": \"$TODAY" /app/logs/smc_v2_shadow.log | \
  grep -oE '"entry_setup_source": "[^"]+"' | sort | uniq -c

# Disk kullanımı
echo "=== DISK ==="
docker exec efloud-bot du -sh /app/logs/

# KRİTİK ALARM 1: would_execute=true varsa
echo "=== CRITICAL ALARM CHECK ==="
docker exec efloud-bot grep -c '"would_execute": true' /app/logs/smc_v2_shadow.log
# Bu sayı 0 olmalı. >0 ise: docker compose stop efloud-bot → Claude'a raporla
```

### Anomali tetik kriterleri (gün sonu)

| Metric | Beklenen | Anomali |
|---|---|---|
| Toplam günlük satır | 100-2000 | <50 (veri yok?) veya >5000 (signal spam) |
| Sembol çeşitliliği | 5-20 | <3 (universe broken) |
| Long/Short oranı | 0.3 - 0.7 | bias > 0.85 tek yönde |
| `would_execute=true` count | **0** | **>0 → ACİL** |
| Disk kullanımı | <20 MB / hafta | >20 MB → logrotate gerek |
| `bars_to_pullback > 8` | 0 | >0 → timeout bug |

---

## 3. Günlük Rapor Şablonu (Hermes → Claude)

Her gün shadow log özetini ben analiz edebilmem için bu formatta paylaş:

```
=== SHADOW DAY N (YYYY-MM-DD) ===
Total lines (cumulative): X
Today's lines: Y
Symbols (top 5): BTC=20, ETH=15, SOL=12, ...
Direction split: long=45%, short=55%
Setup source: FVG_PULLBACK=60%, OTE_RETRACE=40%
Critical alarms: would_execute=true count = 0 [OK] | N [ALARM]
Disk usage: /app/logs/ = X MB
Anomalies (varsa): ...

=== SAMPLE LINES (son 5) ===
<5 JSON satırı yapıştır>

=== HERMES NOTES ===
<gözlemler, sorular>
```

3-4 gün biriktirsen toplu da paylaşabilirsin — günlük zorunluluk yok.

---

## 4. Faz 4 — Baseline Backtest Komutu

### Tam komut (VPS veya local — Claude veya Hermes çalıştırabilir)

```bash
# 6 aylık pencerede BTC + ETH karşılaştırması
python -m backtest.cli compare \
  --symbols BTC/USDT,ETH/USDT \
  --period-days 180 \
  --config configs/config.phase2_1k.yaml \
  --balance 2000
```

**ÖNEMLİ**: CLI `--start`/`--end` parametresi ALMIYOR, sadece `--period-days` (cache'in en güncel tarihinden geriye sayar). Önceki handoff'ta önerdiğim `--start 2025-11-24 --end 2026-05-23` formatı YANLIŞTI — düzeltilmiş komut yukarıda.

### Ön koşul: OHLCV cache hazır olmalı

```bash
# Cache durumu
python -c "from data.cache import OHLCVCache; c=OHLCVCache('cache/ohlcv'); print(c.list())"

# Cache eksikse prefetch:
python -m scripts.prefetch_data --symbols BTC/USDT,ETH/USDT --timeframes 5m,15m,1h,4h,1d --days 200
```

180 gün için 5m+15m+1h+4h+1d × 2 symbol = 10 parquet dosyası. Disk: ~80-150 MB.

### Çıktı dosyası

```
reports/backtests/2026-05-24_compare_2sym_180d_<hash>/
  ├── comparison.json     # Bu dosyayı bana yolla
  └── provenance.json     # Git SHA, env, python sürümü (otomatik)
```

### Beklenen çıktı şeması (`comparison.json`)

```json
{
  "v1": {
    "total_trades": 142,
    "win_rate": 0.51,
    "profit_factor": 1.34,
    "total_return_pct": 18.7,
    "max_drawdown_pct": 12.3,
    "sharpe_like": 1.18,
    "avg_realized_rr": 1.65,
    "stop_hunt_rate": 0.18,
    "trades": [...]
  },
  "v2": {
    "total_trades": 89,
    "win_rate": 0.58,
    ...
  },
  "deltas": {
    "total_trades": {"abs": -53, "rel_pct": -37.3},
    "win_rate": {"abs": 0.07, "rel_pct": 13.7},
    ...
  },
  "gates": {
    "win_rate": "pass",
    "avg_realized_rr": "pass",
    "max_drawdown_pct": "warn",
    "stop_hunt_rate": "pass",
    "sharpe_like": "pass"
  }
}
```

### Gate threshold'ları (`backtest/comparison.py:DEFAULT_GATES`)

| Metric | "pass" şartı | "warn" şartı | "hard_reject" şartı |
|---|---|---|---|
| `win_rate` | v2/v1 >= 1.0 | v2/v1 >= 0.95 | v2/v1 < 0.95 |
| `avg_realized_rr` | v2 >= 1.5 | v2 >= 1.2 | v2 < 1.2 |
| `max_drawdown_pct` (düşük iyi) | v2/v1 <= 1.0 | v2/v1 <= 1.1 | v2/v1 > 1.1 |
| `stop_hunt_rate` (düşük iyi) | v2/v1 <= 0.5 | v2/v1 <= 1.0 | v2/v1 > 1.0 |
| `sharpe_like` | v2/v1 >= 1.0 | v2/v1 >= 0.9 | v2/v1 < 0.9 |

**Karar kuralı (PR #S7'yi tetikleme şartı)**:
- TÜM 5 gate `pass` veya `warn` → PR #S7 spec hazırlanabilir
- HERHANGİ 1 gate `hard_reject` → PR #S7 BLOKLANIR, root cause analizi gerek
- 3+ gate `warn` → PR #S7'de Faz 1 sembol sayısı 2'den 1'e indirilir (sadece BTC)

### Çalıştırma süresi tahmini

- 2 sembol × 180 gün × 5m bars = ~52,000 bar/sembol
- v1 + v2 ardışık koşar → ~3-8 dakika (CPU + cache disk speed bağımlı)
- Grid değil, paralel worker yok — tek process

---

## 5. Faz 2 Shadow Aktivasyon — Pre-Flight Checklist

Bu checklist Faz 1 (zero-risk pull+recreate) **başarıyla bittikten sonra** uygulanır.

```bash
# 1. config.yaml backup al (rollback için)
ssh efloud-bot 'cp /opt/efloud-bot/config.yaml /opt/efloud-bot/config.yaml.pre-v2-shadow'

# 2. Mevcut engine bloğunu görüntüle
ssh efloud-bot 'grep -A5 "^engine:" /opt/efloud-bot/config.yaml'

# Beklenen: smc_version=v1, smc_v2_symbols=[], smc_v2_shadow=false

# 3. Düzenle (VPS'te nano veya local edit + scp)
# engine bloğu şu hale gelmeli:
#   engine:
#     smc_version: v2
#     smc_v2_symbols: ["*"]
#     smc_v2_shadow: true

# 4. Diff doğrula
ssh efloud-bot 'diff /opt/efloud-bot/config.yaml.pre-v2-shadow /opt/efloud-bot/config.yaml'
# 3 satır değişiklik beklenir, başka hiçbir şey değil

# 5. Recreate
ssh efloud-bot 'cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml up -d'

# 6. Startup log
ssh efloud-bot 'docker logs efloud-bot --tail 100 | grep -iE "smc_v2|shadow|setup_state"'

# Beklenen log satırları (yaklaşık):
#   "smc_version=v2 → SetupStateStore initialized"
#   "smc_v2_shadow=true → orders blocked, signals will be logged"

# 7. 15 dakika sonra ilk shadow log satırını kontrol et
ssh efloud-bot 'docker exec efloud-bot tail -5 /app/logs/smc_v2_shadow.log'

# 15 dk içinde 0 satır gelirse:
#   - Setup state machine başlamamış → docker logs efloud-bot --tail 200
#   - Veya gerçekten o anda no-setup koşulları (normal)
```

### Acil rollback (shadow aktivasyonu sonrası bir şey ters giderse)

```bash
ssh efloud-bot 'cp /opt/efloud-bot/config.yaml.pre-v2-shadow /opt/efloud-bot/config.yaml'
ssh efloud-bot 'cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml up -d'
```

5 saniyede v1 inert duruma döner.

---

## 6. Senden Bekleyenler (Hermes Actions)

İşaretli sırada:

- [ ] Faz 1 zero-risk deploy tamam → `hermes_to_claude_phase1_complete.md` aç
- [ ] Shadow aktivasyon Faz 2 öncesi: Bu dosyayı oku, sorun varsa cevap dosyası aç
- [ ] Faz 2 başarılı, 24 saat sonra ilk shadow log özeti → cevap dosyasına yapıştır (Bölüm 3 formatında)
- [ ] Faz 4 backtest çıktısı (`comparison.json`) → cevap dosyasına yapıştır VEYA dosya path'i ver

---

## 7. Açık Sorular (Sen Cevaplayacaksın)

1. **Shadow süresi**: Spec 7 gün diyor ama hafta sonu volume düşük olabilir. 7 gün calendar mı 7 gün ≥1000 satır biriken mi? **Önerim**: 7 calendar gün VE en az 5,000 toplam satır — hangisi sonra gelirse.
2. **Backtest period**: 180 gün önerdim çünkü cache 200 gün limitli görünüyor. Daha uzun mu istiyorsun (cache prefetch genişletirim) yoksa 180 yeterli mi?
3. **Hangi sembol seti backtest'te**: Sadece BTC+ETH mi, yoksa Faz 1 rollout'un kapsayacağı tüm 7 sembol mü? Önerim sadece BTC+ETH (signal/noise oranı yüksek, statistical power için yeterli).
4. **Cevap dosyası adlandırması**: `hermes_to_claude_v2_shadow_readiness.md` (tek dosya, üst üste güncellersin) mi yoksa `hermes_to_claude_phase1_complete.md`, `..._phase2_day1.md` gibi faz başına ayrı mı?

---

**Top sende.** Faz 1 başarılı olur olmaz `docs/handoff/hermes_to_claude_v2_shadow_readiness.md` dosyası ile cevap ver.
