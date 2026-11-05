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
python scripts/pine_lab_parity.py compare --python data/lab/BTC_python.csv --tv data/lab/BTC_B.csv
```

`GATE: PASS` (≥ %95 eşleşme, seviye sapması yok) olmadan toggle turuna geçilmez. FAIL → `pine/lab/*` düzelt ya da sapmayı `pine/PINE_SPEC.md §20`'ye yaz.

## 3. Toggle turu

Her varyant için Strategy Tester export (`data/lab/BTC_T3.csv` …), sonra:

```bash
python scripts/pine_lab_parity.py score --baseline data/lab/BTC_B.csv --variant data/lab/BTC_T1.csv --variant data/lab/BTC_T3.csv
```

`WIN` = spec §6.3 dört kriter birden. Karar + CSV'ler `docs/pine-lab/<tarih>-<variant>.md` altına.

## 4. Sınırlar

TV planı bar/export limiti; T3 (limit emir) Python'da yok → parity dışı, yalnız skor; breaker'lar/funding/drift modellenmez.
T6 FVG saklama penceresiyle sınırlıdır; T3 dolumları resting limit fiyatına göre modellenir.
