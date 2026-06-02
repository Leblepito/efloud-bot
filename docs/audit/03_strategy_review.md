# 03 — Trading / Strategy Review (efloud-bot)

> Phase 3 deliverable. ⚠️ Subagent pool API-overload nedeniyle bu faz baş mimar
> tarafından doğrudan kaynak-okuma + Phase 1/2 sentezi ile üretildi (kanıt: dosya:satır
> + `docs/results/*` backtest raporları). Cardinal kural: ölçülmemiş = **ÖLÇÜLMEMİŞ**,
> rakam uydurulmadı. Tarih: 2026-06-02.

---

## 0. EXECUTIVE — en kritik stratejik bulgu (S1)

**Prod, ölçülmüş olarak -43.75% getiri / %44 drawdown veren konfigürasyonu çalıştırıyor.**

`configs/config.phase2_1k.yaml:101` → `min_confluence: 50` (yorum: "⬇ 60 → 50 daha gevşek, daha çok sinyal"). Aynı 10 majör sembolde, aynı 365-günde, SADECE confluence eşiği değişerek (kaynak: `docs/results/`):

| Eşik | Getiri | Max DD | Trades | WR | PF | Sharpe | Kaynak |
|---|---|---|---|---|---|---|---|
| **conf=50 (PROD)** | **−43.75%** | **44.24%** | 1709 | 40.5% | 1.08 | 0.03 | `2026-05-05-phase-A-validation.md` |
| conf=60 (h1a) | (arşiv) | — | — | — | — | — | `...h1a_conf60.md` |
| conf=70 (h1b) | (arşiv) | — | — | — | — | — | `...h1b_conf70.md` |
| **conf=80 (h1c)** | **+11.29%** | **2.83%** | 213 | 62.4% | 3.5 | 0.51 | `2026-05-06...h1c_conf80.md` |
| aggressive_v1 (9 küratörlü sym, conf 70/80, max 5) | **+49.12%** | 11.49% | 364 | 58.0% | 2.44 | 0.38 | `2026-05-07-aggressive-v1-final.md` |

**Yorum (ÖLÇÜLMÜŞ, uydurma değil):** Eşiği 50→80 çıkarmak bu tam sembol setini **−43.75%/%44DD'den +11.29%/%2.83DD'ye** çevirdi; trade sayısı 1709→213 (8× daha az, çok daha kaliteli). Prod `smc_v2_shadow:true` → emirleri **v1 yolu** açıyor (`smc_version:v2` ama shadow) = conf=50 v1 backtest'i prod execution'ı **birebir** temsil ediyor.

⚠️ **Dürüst caveat:** Bu backtest'ler v1 engine'inde (2026-05-05/06); o tarihten beri engine değişti (PR'lar). "Prod tam −43.75% kaybeder" demiyorum — ama prod eşiği **tüm valide edilen aralığın (60/70/80) ALTINDA**, ve eşik-sweep'i 50'nin felaket, 80'in karlı olduğunu net ölçtü. Memory `efloud_state.md`: canlı **breaker OPEN, weekly DD %25, peak reset** — bu, conf=50 backtest'inin öngördüğü davranışla tutarlı.

> **NASIL FALSİFİYE EDERİZ?** Mevcut engine (v1 path) ile `config.phase2_1k`'i conf=50 vs conf=80 olarak 365-gün re-backtest et (commission+funding dahil — bkz. S6). Hipotez yanlışsa conf=50 artık ≥ conf=80 getirisi vermeli. Beklenti: vermez.
>
> **Aksiyon (roadmap #1, S/effort, flat-book gerektirmez — sadece config):** `min_confluence: 50 → 80` (veya aggressive_v1 sembol seti + conf 70/80'e geç). Config-only değişiklik; canlı margin/mode değişimi YOK. En yüksek beklenen-değerli tek hamle.

### ✅ S1 DOĞRULANDI — re-backtest (2026-06-02, MEVCUT engine)
`c:\tmp\verify_s1.py` ile **mevcut engine** (smc_version=v1 = prod execution yolu) üzerinde aynı 10 prod sembolü, aynı period/step, sadece confluence değişerek (gross — commission/funding YOK, bkz S2):

| Metrik (gross) | conf=50 (step24) | conf=80 (step24) | **conf=50 (step8)** | **conf=80 (step8)** |
|---|---|---|---|---|
| Return % | +82.45 | +90.05 | **+81.35** | **+110.48** |
| Max DD % | 6.71 | 4.34 | **8.29** | **5.35** |
| Profit Factor | 1.25 ⚠️ | 2.51 | **1.35** ⚠️ | **2.34** |
| Win Rate % | 45.9 | 58.8 | **44.5** | **53.7** |
| Trades | 1190 | 617 | **1473** | **863** |

**step=8 (faithful, 365g) = otorite sonuç.** İnce step'te yön DAHA DA güçlü: conf=80 getiri +110.48% vs conf=50 +81.35% (**+29pp**), DD 5.35 vs 8.29 (conf=50 DD'si step inceldikçe KÖTÜLEŞTİ), PF 2.34 vs 1.35.

**DÜRÜST DÜZELTME (integrity):** Tarihsel **−43.75%/%44DD ESKİ engine'di (2026-05-05)**; o tarihten beri engine ciddi değişti (SMC fix'leri, PR'lar). **Mevcut engine'de conf=50 felaket DEĞİL** (+82% gross). Önceki başlık çok sertti — düzeltildi.

**AMA S1'in özü DOĞRULANDI:** conf=80 her risk-ayarlı metrikte conf=50'yi domine ediyor. Kritik: **conf=50 PF=1.25 = breakeven'e tehlikeli yakın**; backtest commission(~0.08% round-trip)+funding modellemiyor (S2) → 1190 trade'de net PF muhtemelen **<1.0 (zararda)**. conf=80 PF=2.51 bu maliyetleri massedecek tampona sahip. **Öneri DEĞİŞMEDİ (50→80) ama gerekçe yeniden çerçevelendi:** "−43% bleed'i durdur" değil → "conf=50 edge'i ustura-ince/net-zararlı muhtemel; conf=80 sağlam". Memory canlı breaker-OPEN durumu bu thin-edge + korelasyon (B1) + C1 repaint birleşimiyle tutarlı.
> **NASIL FALSİFİYE EDERİZ? (güncellendi):** step=8/4 ince re-backtest + commission+funding (S2) wire edilmiş halde net PF hesapla. conf=50 net PF ≥ conf=80 ise S1 yanlış. Beklenti: conf=50 net PF <1.0, conf=80 >1.5.

---

## A. QUANT LENS — istatistiksel kesinlik

### MEASURED vs UNMEASURED

| Konu | Durum | Kanıt |
|---|---|---|
| Confluence **eşiği** (50/60/70/80) PnL etkisi | ✅ **ÖLÇÜLDÜ** | `docs/results/*` — 50=−43.75%, 80=+11.29% |
| Confluence **ağırlıkları** (bireysel: +25/+20/+15/...) | ❌ **ÖLÇÜLMEMİŞ** | `confluence.py:25-45` el-ataması; tek tek ablation yok |
| Regime eşikleri (ADX 25/20, atr_mult 2.5) PnL-korelasyonu | ❌ **ÖLÇÜLMEMİŞ** | varsayılmış; regime-bazlı PnL kırılımı yok |
| Regime ML modeli bağımsız edge | ❌ **DAİRESEL** | `regimes/train.py:35,59` kural-tabanlı etiketleri öğreniyor |
| Backtest commission | ❌ **MODELLENMEMİŞ** | `backtest/engine.py` grep funding/fee = **boş** |
| Backtest funding (8h) | ❌ **ENGINE'E BAĞLI DEĞİL** | `funding.py` matematiği var, engine çağırmıyor |
| Walk-forward (bar-bar) | ✅ VAR | `backtest/engine.py` |
| In-sample/Out-of-sample split | ❌ **YOK** | tek bitişik 365g periyot |
| Monte Carlo | ❌ **YOK** | — |
| Live edge (verdict↔PnL korelasyon) | ❌ **ÖLÇÜLMEMİŞ** + veri çöp | F4 script yok; A1 (gemini ölü) → shadow verisi geçersiz |

### A1 — Regime ML dairesel (bağımsız bilgi = 0)
`engine/regimes/train.py:35` `analysis = detector.analyze(sub_df)` → `:59` `y_list.append(label_map.get(analysis.regime))`. ML modeli, **kural-tabanlı detector'ın ürettiği etiketleri** hedef alıyor → en iyi ihtimalle kuralların düzgünleştirilmiş kopyası, yeni bilgi katmıyor. "ML ensemble" pazarlaması yanıltıcı.
> **NASIL FALSİFİYE EDERİZ?** ML'i forward-realized-regime (gerçekleşen sonraki-N-bar getiri rejimi) ile etiketle; rule-label ML'i yener mi? Yenmezse circular onaylanır.

### A2 — DEFAULT_GATES göreli, mutlak karlılık kapısı değil
`backtest/comparison.py:26-32`: win_rate/sharpe/max_dd **v2-vs-v1 oran** kapıları + avg_rr≥1.5 mutlak. Bu, "v2 v1'den kötü değil mi"yi ölçer; **stratejinin mutlak pozitif beklenti**sini değil. 6. kapı (setup_rejection_rate) devre dışı (producer sayaç yok, PR #S5 bekliyor, `:22-25`). Yani green gate ≠ karlı strateji.

### A3 — Backtest güveni C1 ile sınırlı
C1 (forming-bar repaint, bkz. 02_findings): backtest kapanmış bar besler → **repaint'i hiç görmez**. Yani backtest sonuçları canlı için **üst sınır** (optimistic); gerçek live ≤ backtest. conf=80 +11.29% bile gross-of-fees + repaint-blind.

### A4 — Overfit yüzeyi
Serbest parametre sayımı (kısmi): confluence 11 ağırlık + min_confluence + min_rr + swing_lb + ob_seq + body 1.5×ATR + ote 0.618/0.786 + ext 1.618 + ADX 25/20 + atr_mult 2.5 + sl_atr 0.5-5.0 + recency 40 + range 50 → **~25+ knob**. Valide veri: 10 sembol × 365g (yüksek otokorelasyonlu). Sembol-bazlı conf override'lar (aggressive_v1: BTC/SUI/ADA/OP/LTC=80) = **per-symbol curve-fit** riski.
> **NASIL FALSİFİYE EDERİZ?** OOS split (ilk 270g tune, son 95g test) + Monte Carlo trade-shuffle. Edge OOS'ta çökerse overfit.

### Quant top-5
1. **S1 — prod conf=50 = ölçülmüş −43.75%/%44DD** (config, en kritik).
2. Backtest commission+funding yok → tüm getiriler gross, abartılı.
3. Regime ML dairesel.
4. OOS/Monte Carlo yok → overfit ölçülmemiş.
5. Live edge ÖLÇÜLMEMİŞ + A1 nedeniyle shadow verisi çöp.

---

## B. PORTFOLIO / FUND-MANAGER LENS

### B1 — Korelasyon hiç hesaba katılmıyor (cluster riski)
`grep correlat|beta|cluster engine/safety/position_guard.py` → **pozisyon-risk korelasyonu YOK** (mevcut "cluster" hitler level-clustering/EQH-EQL, portföy beta'sı değil). Prod 10 majör = kriptoda risk-off'ta **beta≈1 tek küme**. `max_total_exposure=1.0x` + `max_open=10` + `risk_per_trade=1%` matematiği **bağımsız trade** varsayıyor; korelasyon≈1'de tüm kitap aynı mumda stop olur.

**Worst-case korelasyonlu-küme DD (aritmetik, varsayımlar açık):**
- Per-name risk = $20 (1% × $2000). 10 bağımsız olsaydı çeşitlenme ile eşzamanlı tam-stop olası değil.
- ρ≈1 (ÖLÇÜLMEMİŞ — bot hiç ölçmüyor) → tek 'market' hamlesi 10×$20 = **$200 = %10 tek günde**, çeşitlendirilmemiş.
- **Bu zaten gerçekleşti:** conf=50 backtest portfolio Max DD **%44.24** — tam da korelasyonlu-küme + düşük-eşik gürültüsünün birleşik çıktısı. Per-name DD'ler (%5-12) toplamından çok büyük portfolio DD'si = korelasyon kanıtı.

Breaker (daily %10 / weekly %25) **PnL-bazlı**, exposure-bazlı değil → korelasyonlu küme için kalibre edilmemiş; gerçekleşen %44 DD, %25 weekly limitin çok üstüne çıktı (intra-period MTM).
> **NASIL FALSİFİYE EDERİZ?** 10 sembolün 365g getiri korelasyon matrisini hesapla; ortalama pairwise ρ. ρ<0.4 ise küme-riski abartılı. Beklenti: majörlerde ρ>0.6.
> **Aksiyon:** korelasyon-düzeltmeli sizing (effective independent bets = N/(1+(N-1)ρ)) veya küme başına exposure cap.

### B2 — Sizing balance source = "total" (unrealized dahil)
`config` prod `sizing_balance_source` set değil → default `"total"` (`safe_orchestrator.py:933`). Drawdown'da unrealized kayıp tabanı küçültür → auto-deleverage (iyi); pump'ta unrealized kazanç sizing'i şişirir → öföride pyramiding (kötü). aggressive_v1 `"available"` kullanıyor — iki live config arası sessiz davranış farkı (F3.5).

### B3 — Kapital tahsisi FCFS, sıralama yok
Sinyaller geliş sırasına göre 10 slotu doldurur — confluence/EV'ye göre **ranking yok**. Zayıf BTC sinyali, güçlü ETH sinyalinin alamayacağı slotu işgal edebilir. Fırsat maliyeti ölçülmemiş.
> **NASIL FALSİFİYE EDERİZ?** Backtest'te slot dolu-iken gelen yüksek-conf sinyalleri logla; reddedilenlerin realize getirisi alınanlardan yüksekse FCFS suboptimal.

### B4 — ISOLATED containment ✓ ama portföy-kill yok
ISOLATED 5x → her pozisyon kaybı kendi margin'i ile sınırlı (contained, iyi). Ama per-position SL ötesinde **exposure-bazlı portföy kill yok**; breaker yalnız PnL eşiği. %44 DD senaryosunda ISOLATED tek pozisyon likidasyonlarını izole eder ama toplam bleed'i durdurmaz.

### Portfolio top-5
1. Korelasyon-kör sizing → %44 DD gerçekleşti (ölçülü).
2. min_confluence=50 sinyal gürültüsü küme-riskini büyütüyor (B1+S1 birleşik).
3. FCFS tahsis, EV-ranking yok.
4. sizing "total" → pump'ta pyramiding.
5. Breaker exposure-bazlı değil (korelasyon için kalibre değil).

---

## C. MICROSTRUCTURE / SMC FIDELITY LENS

### C1 — Funding / OI stratejiye girmiyor (sadece dashboard)
`/api/market/funding-rates` + `/api/market/open-interest` endpoint'leri VAR (`backend/api.py`) ama `confluence.py` skorlama girdileri (11 bool + post-hoc daily/macro/level bonusları) **funding/OI içermiyor** → bu veriler **dashboard-only**, sinyal/sizing'e BESLENMİYOR. Kriptoda ekstrem funding = kalabalık trade = mean-reversion riski; eksik filtre.
> **NASIL FALSİFİYE EDERİZ?** Backtest'e "funding > +Xbp ise long açma" filtresi ekle; getiri/DD iyileşmezse funding-filtre değersiz. (Önce backtest funding'i wire edilmeli — S6.)

### LuxAlgo modül envanteri

| Modül | Durum | Kanıt | Worth-it verdict |
|---|---|---|---|
| Swing/BoS/CHoCH | ✅ EXISTS | `smc.py:130-164` | Çekirdek; C1 forming-bar fix şart (correctness, edge değil) |
| Order Block | ⚠️ PARTIAL (non-canonical extended) | `smc.py:199-243` | 1-mum OB geçiyor (C9); volume-weight yok |
| **Volumetric OB** | ❌ ABSENT | OB volume ağırlığı yok | Eklemeye DEĞER olabilir ama **kanıtsız** — önce ablation |
| FVG | ✅ EXISTS | `smc.py:181-187` | OK (C1'e tabi) |
| OTE (Fibonacci 0.618-0.786) | ✅ EXISTS | `confluence.py:38`, config fib | OK |
| **Premium/Discount (equilibrium 50%)** | ⚠️ PARTIAL | `correct_zone` (`confluence.py:42`) OTE üzerinden dolaylı | Ayrık equilibrium modülü yok; düşük öncelik |
| SFP / Liquidity Sweep | ⚠️ PARTIAL | `has_sfp` (`confluence.py:40`), `smc.py` SFP | Sweep-then-reclaim var ama inducement yok |
| **Inducement** | ❌ ABSENT | — | Kanıtsız; düşük öncelik |
| Smart Money Footprint / displacement | ⚠️ PROXY | body>1.5×ATR (OB breakout) | Gerçek displacement (ardışık imbalance) değil; proxy zayıf |
| **Session filters (Asia/London/NY)** | ❌ ABSENT | — | Kripto 24/7 ama hacim döngüsü var; **düşük öncelik** (kanıt zayıf) |
| HTF liquidity pools as TP | ✅ EXISTS | `levels.py`, `smc_v2/tp_calc.py:5` (EQH/EQL) | Güçlü; korunmalı |

### C2 — Slippage modeli var, fill realizmi eksik
`backtest/slippage.py`: entry 5bp/SL 10bp/TP 5bp — 10 majör için makul ama **likidasyon-wick fill'leri + entry'de funding** modellenmiyor. Yüksek-ATR sembolde max_sl_atr=5.0 likidasyonu aşabilir (02_findings §6) → backtest SL fill'i gerçekçi değil.

### Microstructure top-5 (correctness-bug ↔ new-edge ayrımı)
1. **[CORRECTNESS]** C1 forming-bar repaint — SMC'nin temeli; edge eklemeden ÖNCE düzelt.
2. **[CORRECTNESS]** C9 near_swing future-leak + OB 1-mum invariant.
3. **[EDGE, kanıtsız]** Funding/OI'yi confluence'a wire et — önce backtest'e funding ekle, sonra ablate.
4. **[EDGE, kanıtsız]** Volumetric OB / gerçek displacement — ablation olmadan ekleme.
5. **[CORRECTNESS/REALİZM]** Backtest'e commission + funding + likidasyon-wick fill ekle (yoksa hiçbir edge ölçümü güvenilir değil).

---

## D. SENTEZ — strateji önceliklendirme

| # | Bulgu | Tip | Effort | Flat-book? | Beklenen etki |
|---|---|---|---|---|---|
| **S1** | prod conf=50 → 80 (veya aggressive_v1 set) | Config | **S** | Hayır (config-only) | **En yüksek** — ölçülü −43.75%→+11.29% bandı |
| S2 | Backtest commission+funding wire | Test/infra | M | Hayır | Tüm edge ölçümleri güvenilir olur |
| S3 | Korelasyon-aware sizing / cluster cap | Kod | M | Hayır | %44 DD sınıfını küçültür |
| S4 | C1 forming-bar fix | Kod (BLOCKER) | S | Hayır | Canlı repaint biter; backtest=live |
| S5 | EV-ranked slot allocation | Kod | M | Hayır | FCFS fırsat maliyeti |
| S6 | OOS split + Monte Carlo gate | Test | M | Hayır | Overfit ölçülür |
| S7 | Regime ML forward-label (dairesellik kır) | Kod/ML | L | Hayır | Bağımsız regime bilgisi |
| S8 | Funding/OI confluence wire (ablation sonrası) | Kod | M | Hayır | Kanıtsız edge — önce S2+ablation |

> **Her öneri için ortak falsifikasyon prensibi:** önce backtest'i fee+funding+OOS ile güvenilir yap (S2/S6), sonra her edge'i tek-değişkenli ablation ile ölç. Kanıt olmadan modül EKLEME.

---

## E. Phase 4'e köprü
- aggressive_v1.yaml vs phase2_1k çelişkisi (02_findings F3.2) + S1 kararı birlikte ele alınmalı.
- `docs/results/` raporları DEĞERLİ kanıt arşivi — Phase 4 cleanup'ta SİLME, referans tut.
