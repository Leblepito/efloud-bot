# Pine Lab — operatör akışı

Spec: `../superpowers/specs/2026-11-05-pine-lab-design.md` · Plan: `../superpowers/plans/2026-11-05-pine-lab.md`

## 1. Build ve TradingView'a yükleme

```bash
python scripts/build_pine_lab.py
```

TradingView MCP (masaüstü, `skills/tradingview-mcp/SKILL.md`): `pine_set_source` ← `pine/efloud_lab.pine` → `pine_smart_compile` → `pine_get_errors` (0 hata) → `pine_save`. Aynısı `pine/efloud_lab_strategy.pine` için. Script'ler **private / invite-only** kalır (LuxAlgo CC BY-NC-SA 4.0).

## 2. Baseline parity (sembol başına)

1. Grafik: sembol 15m (ör. BTCUSDT.P), toggle'lar kapalı. "Export chart data" → `data/lab/BTC_15m.csv`.
2. Replay:

```bash
python scripts/pine_lab_parity.py replay --ohlcv data/lab/BTC_15m.csv --symbol BTC/USDT --out data/lab/BTC_python.csv
```

3. Strategy Tester → "List of trades" export → `data/lab/BTC_B.csv`.
4. Karşılaştır:

```bash
python scripts/pine_lab_parity.py compare --python data/lab/BTC_python.csv --tv data/lab/BTC_B.csv --since 2026-07-12
```

Export kuralları:

- Grafik saat dilimi **UTC** olmalı (CLI zaman filtresi ve `tv_intervals` UTC ms karşılaştırır).
- Strategy Tester aralığı replay aralığını kapsamalı.
- En az `window` (750) 15m bar + HTF ısınması (12h/50 için ~50 gün) export edilmeli.
- Kısmi TP1 "List of trades"te iki ayrı Trade # satırı olarak görünebilir; `score` (ve `tv_intervals`) bunları entry zamanı + entry sinyaliyle birleştirir.
- `compare`, açık bir TV pozisyonu sırasında onaylanan Python setup'larını `blocked by pos` olarak ayırır; entry toleransı fill fiyatıyla, engulfing entry `entry=` yorumuyla (`entry_ref`) ölçülür.

`--since` Pine ısınması + 2–3 gün sonrasına konur (ör. `--since 2026-07-12`); öncesi kırpılır. `tp pool shift` satırı: giriş/SL aynı, TP merdiveni bir seviye kaymış çiftler (canlı 750-bar pencere artefaktı — Python TP havuzunda pencere başı pivotu eksik); seviye sapması kapısına dahil değildir, ayrı raporlanır. `GATE: PASS` (eşleşme ≥ %95, pine-only ≤ %5, seviye sapması ≤ %5) olmadan toggle turuna geçilmez. FAIL → `pine/lab/*` düzelt ya da sapmayı `pine/PINE_SPEC.md §20`'ye yaz.

## 3. Toggle turu

Her varyant için Strategy Tester export (`data/lab/BTC_T3.csv` …), sonra:

```bash
python scripts/pine_lab_parity.py score --baseline data/lab/BTC_B.csv --variant data/lab/BTC_T1.csv --variant data/lab/BTC_T3.csv
```

`WIN` = spec §6.3 dört kriter birden. Karar + CSV'ler `docs/pine-lab/<tarih>-<variant>.md` altına.

## 4. Sınırlar

TV planı bar/export limiti; T3 (limit emir) Python'da yok → parity dışı, yalnız skor; breaker'lar/funding/drift modellenmez.
T6 FVG saklama penceresiyle sınırlıdır; T3 dolumları resting limit fiyatına göre modellenir.
HTF ısınması: harness HTF'yi 15m export'tan resample eder; ilk ~25–50 gün 12h/50 bias UNDEF'tir → compare başlangıcını bu ısınmadan sonraya al.
ATR200 tohumlama: Python her 750-bar pencerede ATR200'ü sıfırdan tohumlar (pencere sonunda ~%6 sapma), Pine tam geçmiş `ta.atr(200)` kullanır; FVG eşiği de farklı pencerelenir → küçük parity sapmaları beklenir (PINE_SPEC §20).

## 5. Indicator görselleri (OB / BB-MB / FVG / likidite / OTE)

Yalnız çizim katmanlarıdır (sinyal mantığına dokunmaz); girdiler `showObs`, `showZones`, `showLevels`, `showBreakers`, `showFvg`, `showLiq`, `showOte`, `showHistory`, `maxZonesPerSide`.

**Python referansı:**
```bash
python -I C:/tmp/fetch_klines.py BTCUSDT 1782864000000 data/lab/BTC_15m.csv
python scripts/pine_lab_parity.py visuals --ohlcv data/lab/BTC_15m.csv --out data/lab/BTC_visuals.json   # --window N pencereyi değiştirir
```
Python referansı pencereye duyarlıdır (FVG eşiği ve kümülatif durum); Pine yüklü tüm geçmişi görür. 750 pencerede Pine'da fazladan eski nesneler görünür; `--window 1000` ile de karşılaştır.

**Katman izolasyonu (compile-varyantı):** `make_variant.py` (repo dışında) `pine/efloud_lab.pine` kopyasında yalnız yedi `show*` ile `showHistory` `input.bool` varsayılanlarını ve `maxZonesPerSide` varsayılanını yeniden yazar.
Sonra `pine set --file <varyant>` + `pine compile`; 30 sn sonra sağlık kontrolü: `data indicator <id>` yaklaşık 61 girdi VE `data tables -f "EFloud Lab"` 9 satır.
Ardından `data boxes/lines/labels/tables -f "EFloud Lab"` okunur ve Python JSON'u ile mintick toleransında eşleştirilir.

**Kurallar:**
- Önce "EFloud Lab" scriptini Pine Editor'da aç: compile açık scriptin içine kaydeder (`pine_open` yalnız içeriği yükler).
- `indicator set` KULLANMA: TradingView "Can't parse pine" der ve çalışma ölür. Ayarı yalnız varyant derleyerek değiştir.
- Çalışma sağlıksızsa (girdi yok / tablo yok): `indicator remove <id>`, sonra "Komut dosyalarım"dan "EFloud Lab" ekle (`indicator add`), yeni entity id'yi kullan, varyantı yeniden derle. Son adım: gerçek build'i `pine set --file pine/efloud_lab.pine` ile geri yükle.
- Sonuçlar: `docs/pine-lab/2026-11-06-indicator-visuals-verify.md`.
