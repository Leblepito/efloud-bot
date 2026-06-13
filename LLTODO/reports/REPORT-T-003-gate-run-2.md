# REPORT — T-003 Gate Run 2 (G-T3 + G-T4..G-T6 + Fill/F-01)

**Tarih:** 2026-06-13 · **Koşan:** @claude (TV Desktop MCP, lokal, izole worktree `C:/tmp/wt-t003`)
**Kod:** `feat/p001-t003-strategy` @ `533e225` (round-4 APPROVE_WITH_NITS, PR #194)
**Ortam:** TradingView Strategy Tester · BINANCE: BTCUSDT.P / ETHUSDT.P / SOLUSDT.P / BNBUSDT.P / XRPUSDT.P @ 15m
**Önceki:** GATE_RUN_1 → trade_count=0 (pencere tuzağı + OB-zorunlu sinyal darlığı). R1+R3 sonrası re-run.

---

## NET SONUÇ: ❌ **FAIL → round-5 (gerçek market-entry R3)**

R1+R3 gevşetmesi trade üretimini **0 → 168 closed-leg** yaptı (sayı gate'i artık geçiyor),
ama kalite gate'leri geçmiyor: düşük win-rate, marjinal/negatif PF (2 sembol kaybeden),
**zayıf ve değişken limit-fill (~%41)**, ve OOS Sharpe gate'i mevcut tasarımda
**değerlendirilemiyor** (ölü `bt_oos_pct` input). Gate prompt'unun açık kuralı:
*"FAIL (özellikle fill oranı düşükse) → round-5: gerçek market-entry R3."* Fill oranı düşük.

---

## Valide Edilen Config (≠ yayınlanan default — ürün-bütünlüğü notu)

| Input | Gate-run config | Committed default | Not |
|---|---|---|---|
| `allow_ob_less` | **true** | `false` | R1.b; false → strict-OB → GATE_RUN_1=0 trade |
| `bt_date_end` | **2026-12-31** | `2025-12-31` | ⚠️ **LATENT BUG** — bkz. Bulgu #1 |
| `bt_date_start` | 2025-01-01 | 2025-01-01 | yüklü 2026 verisinin tamamını kapsar |
| `conf_thresh` | 55 (default) | 55 | plan §3d |
| `limit_expiry_bars` | 40 (default) | 40 | R3 |
| `extended_expiry_in_trend` | false (default) | false | R3 |
| diğerleri | default | — | — |

---

## Metodoloji (kanıt)

- **G-T3 (compile):** EXACT committed `wave1_strategy.pine` (656 satır) `pine_set_source` +
  `pine_smart_compile` + `pine_get_errors` → **0 hata, 0 marker. ✅ PASS** (gerçek committed kod).
- **Metrik okuma:** TV internal-api strateji tool'ları (`data_get_strategy_results/trades`)
  bu kurulumda strateji handle'ını GÖRMÜYOR ("No strategy found"). Strategy Tester UI'ı da
  ikon-tab + DPI ölçeği nedeniyle güvenilir otomatize edilemedi. Bu yüzden **ölçüm-amaçlı
  diagnostik build** kullanıldı: committed trade mantığı DEĞİŞMEDEN (görsel stripped, sayaçlar +
  `strategy.*` built-in'lerini gösteren `table.new` eklendi), metrikler `data_get_pine_tables`
  ile okundu (gate prompt'unun onayladığı yöntem). Diagnostik build de 0-hata derlendi.
- **Veri:** TV 15m lazy-load; sembol başına derinlik DEĞİŞİYOR (BTC ~1 Şub, ETH ~1 Mar başlangıç;
  `chart_scroll_to_date` MCP'de kırık — "evaluate is not defined"). Counts bu derinlikten etkilenir.

---

## Per-Sembol Sonuçlar (~4.3 ay 15m, 5×10k bağımsız hesap)

| Sembol | closedlegs | orders | win% | PF | net% | maxDD% | gprofit | gloss | subRR | invert |
|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT.P | 28 | 36 | 17.9 | 1.57 | +1.1 | 1.6 | 302 | 193 | 0 | 0 |
| ETHUSDT.P | 6 | 32 | 66.7 | 3.97 | +1.6 | 0.8 | 211 | 53 | 0 | 0 |
| SOLUSDT.P | 24 | 20 | 8.3 | 1.29 | +0.2 | 0.4 | 80 | 62 | 0 | 0 |
| BNBUSDT.P | 54 | 49 | 14.8 | 2.59 | +2.6 | 0.8 | 418 | 161 | 0 | 0 |
| XRPUSDT.P | 56 | 66 | 5.4 | **0.38** | **−2.0** | 2.6 | 120 | 315 | 0 | 0 |
| **TOPLAM** | **168** | **203** | — | **1.44** | **+3.5** | ≤2.6 | 1131 | 784 | **0** | **0** |

> **closedlegs = TV "Total Closed Trades"** = `strategy.closedtrades`. TP1 %50-kısmi + kalan runner
> = pozisyon başına ~2 leg, dolayısıyla **fiili pozisyon ≈ closedlegs/2 ≈ 84**. "trade_count ≥ 100"
> gate'i konvansiyonel TV-trade metriğiyle (legs) okunur → 168.
> net% toplamı 5 bağımsız 10k hesabın aritmetik toplamı; birleşik 50k üzerinde **≈ +%0.70 / 4 ay**.

---

## Gate Değerlendirmesi

| Gate | Kriter | Sonuç | Kanıt |
|---|---|---|---|
| **G-T3** | compile 0 hata/marker | ✅ **PASS** | committed kaynak, `pine_get_errors`=0 |
| **G-T4a** | trade_count ≥ 100 | ✅ **PASS** | 168 closed-legs (≈84 pozisyon) |
| **G-T4b** | OOS Sharpe ≥ IS×0.7 | ⬜ **DEĞERLENDİRİLEMEZ** | `bt_oos_pct` ölü input (Bulgu #2); Pine Sharpe yok |
| **G-T5** | inverted SL/TP = 0 | ✅ **PASS** | `invert=0` (5/5); `valid` gate yapısal garanti |
| **G-T6** | sub-min-RR = 0 | ✅ **PASS** | `subRR=0` (5/5); `f_calc_tp` min_rr clamp |
| — | MaxDD ≤ %5 | ✅ PASS | tüm semboller ≤ %2.6 |
| — | Win-rate ≥ %50 | ❌ **FAIL** | toplam ~%10-15; sadece ETH (%66.7) geçiyor |
| — | PF ≥ 1.5 | ❌ **MARJİNAL FAIL** | toplam 1.44; per-sembol 3/5 (BTC/ETH/BNB) ✓, SOL 1.29 / XRP 0.38 ✗ |
| **Fill** | (F-01 sürücüsü) | ❌ **ZAYIF/DEĞİŞKEN** | ~%41 agregat, **9-60 aralığı** (ETH %9, SOL %60) |

---

## Bulgular

**#1 — `bt_date_end` default = 2025 → yayınlanan strateji her kullanıcıda 0 trade (LATENT BUG, HIGH).**
`wave1_strategy.pine:502/528` entry'leri `in_window = time >= bt_date_start and time <= bt_date_end`
ile filtreliyor; default `bt_date_end = timestamp("2025-12-31")`. TV 15m derinliği 2026 olduğundan,
default'la `allow_ob_less` ne olursa olsun **0 trade**. GATE_RUN_1'in 0-trade kök nedeninin bir
bileşeni de buydu (sinyal darlığıyla confounded). **Merge öncesi düzeltilmeli** — ya rolling-window
default ya da makul 2026+ tarih. Operatör input'tan değiştirebiliyor ama "çalışan default" şart.

**#2 — `bt_oos_pct` ÖLÜ input → OOS gate'i yapısal olarak değerlendirilemez (MEDIUM).**
`bt_oos_pct` yalnız yorum satırlarında (`:75`, `:500-501`) geçiyor; hiçbir yürütme mantığında
IS/OOS bölme YOK. "OOS Sharpe ≥ IS×0.7" gate'i mevcut kodla ölçülemez (manuel 2-pencere koşumu +
TV summary Sharpe okuma gerekir; TV summary UI bu kurulumda otomatize edilemiyor). Gate'i gerçek
kılmak için OOS-split kodda implement edilmeli.

**#3 — Limit-fill oranı zayıf ve sembole bağlı (F-01 kararı için kritik).**
203 limit emri yerleştirildi, ~84 pozisyon doldu (**~%41 fill, ~%59 expire**). Aralık çok geniş:
ETH **%9** (32 emir → ~3 pozisyon), SOL %60. R3'ün expiry uzatması (20→40 bar) **yetmiyor**:
OB-kenarı retrace-bekleyen limit modeli sinyallerin yarıdan fazlasını ıskalıyor. Bu, F-01'in
(R3 yeniden-tanım kabulü) tam endişesi → **round-5 gerçek market-entry** lehine güçlü kanıt.

**#4 — Düşük win-rate + marjinal/negatif edge.**
WR %5-18 (ETH hariç). PF>1 olan sembollerde edge nadir büyük TP2-runner'larına bağlı (kırılgan).
XRP açıkça kaybeden (PF 0.38, net −%2.0). Agregat PF 1.44 < 1.5 hedefi. Birleşik getiri ~+%0.7/4ay.

**#5 — `closedlegs` ≠ pozisyon (metrik tuzağı).**
TP1 %50-kısmi + kalan = pozisyon başına ~2 closed-leg. `strategy.closedtrades` bunu 2× sayar.
Diagnostik `filledpos` (0→nonzero geçiş) sayacı **intrabar fill'lerde güvenilmez** (pozisyon
bar-içi açılıp kapanınca bar-kapanışta size=0 → geçiş yakalanmaz); pozisyon ≈ closedlegs/2 estimate.

**#6 — F4 intrabar caveat (round-3'ten korunur).**
`calc_on_every_tick=false` → limit fill bar-içi belirsizliği; raporlanan PF/net iyimser olabilir.
OOS güven bandı: gerçek Sharpe burada ölçülemese de, intrabar iyimserlik + ~%59 expire +
marjinal edge birlikte muhafazakâr okumayı zorunlu kılıyor.

---

## Öneri

1. **#194 master'a MERGE EDİLMESİN / STATE = IMPL_READY YAPILMASIN.** Sayı gate'i geçti ama
   kalite (WR/PF/fill) + OOS değerlendirilemezliği nedeniyle gate **FAIL**.
2. **Round-5 (R3 gerçek market-entry):** Sinyal barı kapanışında market entry (OB-kenarı limit
   yerine). Bot'un market+drift-guard davranışına da yakın; ~%59 expire sorununu çözer.
   F-01 → **BLOCKING**'e yükseltilir (Hermes'e patch talebi).
3. **Yan-defektler (merge'den bağımsız, round-5 ile birlikte):**
   - Bulgu #1: `bt_date_end` default'unu çalışır hale getir.
   - Bulgu #2: OOS-split'i kodda implement et (yoksa G-T4b gate'i sahte).
4. Round-5 sonrası gate re-run: aynı 5-sembol + (mümkünse) gerçek OOS Sharpe.

---

## Notlar

- Tüm iş izole worktree `C:/tmp/wt-t003`'te; ana repo (`experiment/entry-slippage-backtest`,
  Gemini workspace) ve `pine/efloud_signals.pine` (SMC v2 port) DOKUNULMADI.
- Diagnostik build TV editöründe ephemeral; committed dosya repo'da değişmedi.
- Kanıt screenshot'ları: `~/tradingview-mcp/screenshots/gate2_*.png` (lokal).
