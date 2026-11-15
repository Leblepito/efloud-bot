# FVG hedef modeli — ADR-0011 offline kapısı sonucu (2026-11-14)

**Karar: FAIL.** Operatörün hedef setup'ı (`docs/STRATEGY_INTENT.md`) iki SL varyantında ve iki zaman diliminde
ADR-0011 offline kapısından geçmedi. Brüt ortalama R sıfır civarında ya da negatif; maliyet sonucu daha da aşağı
çekiyor. Bu nedenle canlı FVG emir yolu (GATED Ö9) açılmaz; V1 pause (K1, ADR-0012) sürer.

- Araç: `tools/fvg_offline_replay.py` (PR #349). Gölgenin kendi kodu (`engine/smc_v2/fvg_entry.py::shadow_step`)
  bar bar oynatılır; pencere canlıyla aynı (`kline_limit − 1` kapanmış bar).
- Maliyet: kanonik (ADR-0011; PR #348) — komisyon %0.04/bacak (giriş de taker), funding %0.01/8h (tam
  periyot), SL/BE slippage %0.10, TP slippage %0.05.
- Pencere: 2026-05-18 → 2026-11-14 UTC (180 gün), IS payı 0.67, 10 canlı sembol, denenen varyant sayısı 2.
- Ham çıktılar repoda değil (çalışma makinesinde `C:/tmp/fvg180/`, `C:/tmp/fvgR1/`); tekrar üretmek için
  aşağıdaki komutlar yeterli.

## 1. Canlı profil (15m giriş / 4h bias) — `configs/config.phase2_1k.yaml`, kod `08b0469`

| Varyant | n | WR | ort. brüt R | ort. maliyet R | ort. NET R | NET PF | IS NET R | OOS NET R | OOS PF | + sembol |
|---|---|---|---|---|---|---|---|---|---|---|
| A (`calc_sl`, ATR bandı) | 595 | %31 | −0.032 | 0.229 | **−0.261** | 0.69 | −0.265 | −0.253 | 0.71 | %10 |
| B (OB fitili ∓ %0.2) | 588 | %33 | −0.005 | 0.197 | **−0.202** | 0.75 | −0.199 | −0.210 | 0.74 | %20 |

Yalnız ETH NET pozitif (A +0.27 R, n=53).

## 2. Araştırma R1 (1h giriş / 8h bias) — aynı kurallar, yalnız `timeframes.profile: long`

Hipotez: daha geniş SL ile maliyet/R düşer, varsa brüt avantaj görünür. Ön kapı: brüt ort. R ≥ +0.25.

| Varyant | n | WR | ort. brüt R | ort. maliyet R | ort. NET R | NET PF | IS NET R | OOS NET R | OOS PF | + sembol |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 142 | %27 | −0.149 | 0.146 | **−0.295** | 0.64 | −0.131 | −0.607 | 0.35 | %30 |
| B | 153 | %25 | −0.204 | 0.145 | **−0.349** | 0.59 | −0.265 | −0.503 | 0.43 | %40 |

Maliyet/R beklendiği gibi düştü (0.23 → 0.15 R) ama brüt sonuç da düştü → ön kapı geçilmedi; NET aşamasına
geçilmez.

## 3. Yorum

1. Model maliyetten önce de kazanmıyor (brüt ≈ 0 / negatif). Maker giriş varsayımı ≈ +0.03 R kazandırırdı —
   tabloyu değiştirmez.
2. Operatör SL'i (B) 15m'de A'dan biraz iyi (−0.20 vs −0.26 R) ama negatif; 1h'te daha kötü.
3. Desen önceki bütün varyantlarla aynı (`docs/research/DECISIONS.md`): bu 15m/1h kural ailesi bu sembollerde
   maliyetini karşılayacak brüt avantaj üretmiyor.
4. Sıradaki araştırma (operatör kararı 2026-11-14 "önce brüt edge ara"): mitige-OB / breaker retest'in
   (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:52`, +0.24 R, n=30) 180 günlük yeniden
   ölçümü — aynı ön kapı (brüt ≥ +0.25 R).

## 4. Tekrar üretim

```bash
python -m scripts.prefetch_data --config configs/config.phase2_1k.yaml --days 400
for s in BTC ETH XRP DOGE SOL BNB TRX LINK BCH ADA; do
  python tools/fvg_offline_replay.py run --symbols $s/USDT --days 180 --end 2026-11-13 --out out/$s &
done; wait
python tools/fvg_offline_replay.py merge --inputs out/*.json --out out/ALL
# R1: aynı komutlar, --config <prod config kopyası, timeframes.profile: long>; prefetch --days 460 (1h/8h)
```

## 5. Araştırma R2 — mitige-OB retest (canlı motor yolu, `backtest.cli`)

Hipotez: T-09'un tek pozitif kategorisi ("OB motor penceresinde mitige", +0.24 R, n=30, 60 gün;
`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:52`) daha uzun pencerede gerçek mi?
Araç: `smc_v2.luxalgo.ob_mitigation_filter` araştırma parametresi (yalnız branch `feat/lux-ob-mitigation-filter`
@ `83cbe97`, **merge edilmedi** — kullanılmayan knob engine'e girmez, Karpathy-2); `only_mitigated` = yalnız
mitige OB'li kırılımlar, gerisi canlı akışla aynı (engulfing teyidi, `calc_sl`, lux TP, kanonik maliyet).
180 gün × 10 sembol, `backtest.cli single`, 2026-11-14/15.

| Kol | n | WR | ort. brüt R | ort. NET R | NET PF | IS NET R | OOS NET R | OOS PF | + sembol |
|---|---|---|---|---|---|---|---|---|---|
| Baz (canlı LuxAlgo akışı) | 520 | %31 | −0.237 | **−0.378** | 0.58 | −0.440 | −0.271 | 0.68 | 2/10 |
| only_mitigated | 974 | %32 | −0.196 | **−0.336** | 0.61 | −0.351 | −0.306 | 0.64 | 0/10 |

Sonuç: brüt ön kapı (≥ +0.25 R) geçilmedi; T-09'un +0.24 R'si küçük örneklem gürültüsü. Not: T-09 kategorisi
(grafik dokunuşu + motor penceresinde mitige) buradaki tanımla birebir aynı değil; aynı fikri canlı motor yoluyla
30× örneklemde ölçer. Brüt R = (net pnl + komisyon + funding) / ilk risk; slippage dolum fiyatında.

## 6. Genel sonuç

| Model | ort. brüt R | ort. NET R |
|---|---|---|
| Canlı LuxAlgo (15m/12h) | −0.24 | −0.38 |
| FVG hedef modeli A / B (15m/4h) | −0.03 / −0.005 | −0.26 / −0.20 |
| FVG hedef modeli A / B (1h/8h) | −0.15 / −0.20 | −0.30 / −0.35 |
| Mitige-OB retest (15m/12h) | −0.20 | −0.34 |

Bu SMC kural ailesi bu sembollerde ve 15m/1h'te maliyetten önce de avantaj üretmiyor. Yeni bir setup ancak bu
araçlarla (`tools/fvg_offline_replay.py`, `backtest.cli`) önce **brüt** ön kapıyı (≥ +0.25 R, n ≥ 100) geçerse
NET aşamasına alınır.
