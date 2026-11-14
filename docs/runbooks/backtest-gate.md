# Runbook — NET-cost backtest kapısı (ADR-0011 offline adımı)

> **Ne zaman:** setup / edge / scoring / kapı değeri değişikliği canlıya önerilmeden önce. Sonuç
> `docs/adr/0011-edge-go-criteria.md` kriterine göre raporlanır; kapı geçilmeden canlı emir yolu açılmaz.
> **Araç:** `python -m backtest.cli` (`backtest/cli.py`). Canlı trade mantığını (`SafeOrchestrator.run_cycle`) bar bar
> koşar; çıkışlar borsadaki gibidir (TP1 %50 → BE → TP2).

## 1. Ön koşullar

1. **Temiz git ağacı.** Her koşu `provenance.json` yazar (`git_sha`, `git_dirty`; `backtest/reproducibility.py:29-56`).
   `grid` kirli ağaçta reddeder (`backtest/cli.py:193`); `single` / `portfolio` koşar ama `git_dirty: true` işaretler —
   kirli ağaçtan çıkan sonuç kapı kanıtı sayılmaz.
2. **Config.** Canlı mid profil: `configs/config.phase2_1k.yaml`. Varyant için config'in bir kopyası veya `grid`
   spec'i kullanılır; canlı config dosyası değiştirilmez.
3. **Maliyet bloğu.** Config'te `backtest:` bloğu olmalı (`configs/config.phase2_1k.yaml:480-482`; long `:258-260`,
   scalp `:263-265` dosyalarında da var). **Blok yoksa komisyon ve funding 0.0'a düşer ve koşu BRÜT olur**
   (`backtest/engine.py:418-445`); yalnız slipaj düşülür (`backtest/engine.py:204`, `backtest/slippage.py:6-10`).
   `configs/config.testnet.yaml` ve `configs/config.aggressive_v1.yaml` bu bloğu içermez → kapı için kullanılmaz.
4. **Veri.** `python -m scripts.prefetch_data --config <config> --symbols <S1,S2,…> --days <N>`
   (`scripts/prefetch_data.py:43-65`). CLI her TF için periyot başlangıcından önce `timeframes.kline_limit` bar geçmişi
   yükler (`backtest/cli.py:22-30`, `:81-83`; mid'de `configs/config.phase2_1k.yaml:252`); bu geçmiş cache'te yoksa
   HTF LuxAlgo trendi oluşmaz ve v2 işlem açmaz. Bu yüzden `--days` ≥ periyot + `kline_limit` × HTF bar süresi
   (mid: 750 × 12h = 375 gün). Prefetch zaten cache'te olan sembol/TF çiftini **atlar** (`scripts/prefetch_data.py:83-88`).

## 2. Sabit pencere ucu

CLI'da pencere-sonu argümanı **yok**: pencere `[şimdi − period-days, şimdi]` olarak duvar saatinden hesaplanır
(`backtest/cli.py:34-35`). Cache periyot sonundan 2×TF'den fazla gerideyse `STALE CACHE` uyarısı basılır ama koşu
durmaz (`backtest/cli.py:45-61`). `--end` eklenene kadar (GATED Ö4) kural:

- Bir karşılaştırmanın **bütün kolları aynı gün, aynı cache ile** koşulur; arada prefetch yapılmaz.
- Rapor; koşu tarihini (UTC), her sembol/TF için cache `max_ts`'ini ve `provenance.json` `git_sha`'sını yazar.
- `STALE CACHE` uyarısı görüldüyse gerçek pencere sonu `max_ts`'dir; rapor bunu belirtir.
- Farklı günlerde koşulmuş iki sonuç doğrudan karşılaştırılmaz.

## 3. Koşu

```bash
# Sembol başına ayrı koşu (önerilen kapı koşusu); her biri ayrı süreç
python -m backtest.cli single --symbol BTC/USDT --period-days 180 \
  --config configs/config.phase2_1k.yaml --balance <bakiye>
# Portföy etkileşimi (exposure tavanı, eşzamanlı pozisyon) gerekiyorsa
python -m backtest.cli portfolio --symbols BTC/USDT,ETH/USDT,… --period-days 180 \
  --config configs/config.phase2_1k.yaml --balance <bakiye>
# Parametre taraması (seri; varsayılan --workers 1)
python -m backtest.cli grid --grid <grid.yaml> --symbols BTC/USDT,… --period-days 180
```

- **Sembol başına ayrı koşu:** `single` her sembol için ayrı bir süreçte (ayrı terminal / arka plan işi) başlatılır.
  `portfolio` seri koşar ve uzun pencerede çok yavaştır. `grid` çok-süreçli yolu Windows/py3.14'te askıda kalır;
  varsayılan bu yüzden seri (`backtest/cli.py:304-305`) — `--workers N` Windows'ta açılmaz.
- **Laptop uyku modu:** Windows Modern Standby uzun arka plan işlerini dondurur. Uzun koşu öncesi, operatör onayıyla
  `powercfg /change standby-timeout-ac 0` + kapak açık; koşu bitince eski değere dönülür.
- **`--balance`:** varsayılan 2000 (`backtest/cli.py:289`). Exposure tavanı bakiyeyle ölçeklenir
  (`engine/safety/position_guard.py:271-282`); canlı tavanı yansıtmak için `safety.starting_balance`
  (`configs/config.phase2_1k.yaml:375`) veya o günkü bakiye verilir ve raporda yazılır.
- **`compare` alt komutu** v1 ↔ v2 karşılaştırmasıdır, kendi kapı seti var (`backtest/comparison.py:26-32`); ADR-0011
  kapısı için kullanılmaz.
- **Çıkış kodu:** döngülerin > %1'i hata verdiyse koşu `exit 3` ile düşer (`backtest/cli.py:69-78`); sonuç geçersizdir.

Çıktı: `reports/backtests/<tarih>_<sembol>_<N>d_<id>/result.json` + `provenance.json` (`reports/` gitignore'da;
rapor özeti PR'a `collab/outputs/<model>/` altında girer).

## 4. Metrikler

- `result.json`: `profit_factor`, `total_trades`, `commission_pct`, `total_commission`, `funding_pct_per_8h`,
  `total_funding` (`backtest/engine.py:450-468`; `backtest/metrics.py:109-140`). `commission_pct > 0` iken işlem `pnl`'i ve PF NET'tir
  (`backtest/metrics.py:43-73`).
- **NET R / işlem:** `pnl / (|entry − sl| × size)`; `sl` ilk stop'tur (`backtest/metrics.py:13-40`).
- **IS / OOS:** CLI bölmez. Bölme noktası (ör. kapanış zamanına göre ilk 2/3 IS, son 1/3 OOS) sonuçlara bakmadan
  önce rapora yazılır.

## 5. Rapor (zorunlu satırlar)

```text
Pencere: <başlangıç> → <bitiş> (UTC; koşu tarihi <gün>; cache max_ts <…>)   git SHA: <provenance.git_sha>
Config: <yol> (+ varyant farkı)   Bakiye: <--balance>   Semboller: <liste>
Maliyet: komisyon %<commission_pct>/bacak, funding %<funding_pct_per_8h>/8h, slipaj giriş 5 bp / SL 10 bp / TP 5 bp
         (backtest/slippage.py:8-10); limit giriş varsayımı: <yok | yalnız giriş bacağı maker>
Kollar: baz <n, NET ort R, PF> · aday <n, NET ort R, PF>   IS/OOS bölme: <kural>
Denenen varyant sayısı (bu pencerede): <k>
ADR-0011: n≥100 [ ] · IS NET>0 [ ] · OOS NET>0 [ ] · OOS PF≥1.30 [ ] · sembol ≥%60 + [ ] · bazdan iyi [ ]
Sonuç: GO (forward gölgeye geç) | NO-GO   Kayıt: docs/research/DECISIONS.md'ye yeni satır
```

Maliyet satırı olmayan veya BRÜT koşulmuş sonuç kapı kanıtı sayılmaz.
