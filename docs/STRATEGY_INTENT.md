# STRATEGY_INTENT — operatörün asıl setup'ı (kanonik niyet)

> **Rol:** map. Operatörün istediği setup'ın tek kanonik tanımı + her implementasyonun bu tanımdan sapması.
> Canlı değer yazmaz; canlı davranış `config:satır` / `path:line` ile gösterilir. Anlık durum: `collab/STATUS.md`.
> Kararlar: `docs/superpowers/specs/2026-11-14-ecc-revision-and-target-model-design.md` §2 (K2–K5).
> Kapı: `docs/adr/0011-edge-go-criteria.md`. Ölçüm geçmişi: `docs/research/DECISIONS.md`.
>
> **Sonuç (2026-11-14): ADR-0011 offline kapısı FAIL** — 180 gün × 10 sembol, kanonik maliyet: A NET −0.26 R, B (operatör SL) NET −0.20 R, brüt ≈ 0; 1h/8h'te de brüt negatif. Ayrıntı: `docs/research/2026-11-14-fvg-offline-gate.md`. Canlı FVG emir yolu açılmaz.
>
> **Uyarı — model bir hipotezdir.** Aşağıdaki pipeline'ın hiçbir bileşeni NET-cost ölçümde KANITLI değildir.
> ADR-0011 kapısını (offline asıl kapı + forward sağlama) geçmeden canlıya alınmaz; canlı emir yolu ayrı PR,
> risk-ops review ve operatör onayı ister (ADR-0003).

`config` = `configs/config.phase2_1k.yaml` (canlı mid profil). Kanıt etiketleri: **KANITLI** = NET-cost ölçümü
pozitif · **KANITSIZ** = ölçüm yok, n yetersiz veya başa baş (bir kapının "gevşetilmesi NET negatif" olması, kapının
koruyucu olduğunu kanıtlamaz) · **TARTIŞMALI** = ölçümler farklı yönleri gösteriyor · **ÇÜRÜTÜLMÜŞ** = NET-cost
ölçümü negatif veya kapıyı geçemedi. "Göreli KANITLI" = aynı ölçümde bazdan daha az zararlı olduğu ölçülmüş, mutlak edge değil.

## 1. Tez

4h yapısal yön doğrultusunda, 15m'de bir CHoCH/BOS kırılımının bıraktığı FVG'ye geri çekilmede **limit emirle**
girilir; stop, kırılımı yapan order block mumunun dış fitilinin biraz ötesine konur; TP1 yoldaki ilk karşı
OB/BB, TP2 işlem yönündeki likiditedir; işlem yalnız R:R ≥ `risk.min_rr` ve maliyet/R bütçesi içindeyse alınır.
Operatörün kendi sözüyle (2026-11-13): "FVG boşluğundan işleme girecek, SL likidasyon noktasının biraz uzağına
atılacak, bütün mesele bu." Ölçümün eklediği şart: bugüne dek ölçülen her varyantta brüt sonuç sıfır civarında,
zararı maliyet üretiyor (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:15-17`). Model ancak
maker giriş + maliyete göre yeterli SL mesafesi + mevcut kapılarla (gevşetmeleri NET negatif ölçüldü; koruyucu
etkileri ölçülmedi, `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:8-24,42-54`) NET pozitif olabilir; bu kanıtlanmadı.

## 2. Pipeline

| Adım | Kural | Parametre (hedef) | Kaynak: operatör ifadesi · kod | Etiket |
|---|---|---|---|---|
| 1 Bias | 4h LuxAlgo swing trend; UNDEF → işlem yok | `swing_length` = `config:189` | "15m işleme girecekse 4h bias" (11-13 21:02) · gölge bias `engine/safe_orchestrator.py:2363` (mid MTF = 4h, `data/timeframes.py:26`); UNDEF → plan yok `engine/smc_v2/fvg_entry.py:106-107`; canlı 12h `engine/safe_orchestrator.py:1256-1258` | Bias kapısı (12h): KANITSIZ — gevşetme NET negatif (−0.17…−0.32 R); koruyucu etkisi ölçülmedi (elenen ≈ baz); 4h KANITSIZ |
| 2 Tetik | 15m, bias yönünde CHoCH veya BOS, son 168 bar | `kinds` = `config:200`; recency = `config:293` | "choch-bos kırılımı sonrasında" (11-13 21:02) · `engine/smc_v2/fvg_entry.py:110-112`; canlı recency `engine/safe_orchestrator.py:1236-1237`, `engine/smc_v2/luxalgo.py:527-535` | Recency: KANITSIZ — gevşetme NET negatif (−0.17…−0.32 R); koruyucu etkisi ölçülmedi (elenen −0.17 R, bazdan iyi); BOS KANITSIZ |
| 3 Bölge | Kırılımın OB'sinden sonra, kırılım+2 bar içinde oluşan, mitige olmamış FVG | `FVG_AFTER_BREAK_BARS = 2` | "FVG boşluğu veren bir mum yapısı oluşmuş olsun" (11-08 03:11) · `engine/smc_v2/fvg_entry.py:28-29,59-64` | KANITSIZ |
| 4 Giriş | FVG yakın kenarına LIMIT (LONG üst, SHORT alt); fiyat kaçarsa iptal; timeout 48 bar | timeout `engine/smc_v2/fvg_entry.py:158` | "Fvg boşluğuna geri çekilme[de] işleme girmeli" (11-13 21:02); seçim "Geri çekilmede FVG limit" (11-14) · `engine/smc_v2/fvg_entry.py:121`, `:228-231` | ÇÜRÜTÜLMÜŞ — ADR-0011 offline: NET −0.26 R (A) / −0.20 R (B), n≈590, brüt ≈ 0 (`docs/research/2026-11-14-fvg-offline-gate.md`) |
| 5 Filtre | (a) premium/discount; (b) maliyet bütçesi: tahmini RT maliyet / SL mesafesi ≤ 0.15 R; (c) R:R ≥ `risk.min_rr` | (a) `config:199`; (b) kodda yok (GATED Ö8); (c) `config:273` | Niyette yok, ölçümden (K3) · (a) `engine/smc_v2/luxalgo.py:541-547`; (c) `engine/smc_v2/fvg_entry.py:67-79` | (a) KANITSIZ — gevşetme NET negatif (−0.17…−0.32 R); koruyucu etkisi ölçülmedi (elenen ≈ baz); (b) gerekçe KANITLI, eşik KANITSIZ; (c) KANITSIZ |
| 6 SL | Kırılımı yapan OB mumunun dış fitili ∓ fiyatın %0.2'si; sweep varsa süpürülen uç. ATR kuralı yok | %0.2 (K3) | "kırılımı gerçekleştiren Order block mumunun biraz uzağına SL" (11-13 21:02); "SL ATR'ye göre konulmamalı" (11-07 21:28); "%0,2 uzağına… entry noktasının değil" (11-08 01:50) · gölge varyant B `engine/smc_v2/fvg_entry.py` `sl_mode="ob_pct"` (PR #348) | ÇÜRÜTÜLMÜŞ — gölge varyant B offline NET −0.20 R, n=588 (15m); 1h'te −0.35 R (`docs/research/2026-11-14-fvg-offline-gate.md`) |
| 7 TP1 | Yoldaki ilk karşı OB veya BB, R ≥ `risk.min_rr` | `config:273` | "bir sonraki TP1 OB-BB olabilir" (11-13 21:02) · `engine/smc_v2/fvg_entry.py:67-79` | KANITSIZ |
| 8 TP2 | TP1'in ≥ 0.5 R ötesindeki, işlem yönündeki EQH/EQL / swing likiditesi | `TP2_MIN_GAP_R = 0.5`; içeri pay `config:206` | "pozisyona girilen yöndeki likidite noktası" (11-13 21:02) · `engine/smc_v2/fvg_entry.py:30-31,82-95` | KANITSIZ |
| 9 Yönetim | TP1'de %50 + SL başa baş → TP2; max-hold yok, 24 saatte uyarı | `config:407,410` | 36 saat zorla kapatmayı kaldır (11-07 22:51) · `engine/lifecycle.py:409-413` | Max-hold 0 göreli KANITLI (zayıf); TP1 %50+BE KANITSIZ |
| 10 Risk | Breaker, exposure tavanı, drift %1, SL < likidasyon, orphan koruması — değişmez | mevcut | — · `engine/safety/breaker.py`, `engine/safety/position_guard.py:271-282`, `exchange/__init__.py:1088-1107` | Guard; zayıflatılmaz |
| Yedek | Mitige-OB / breaker retest + engulfing | — | — · `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:52` | KANITSIZ (+0.24 R, n=30, tek pencere) |

İptal (dolmadan): timeout, fiyatın kaçması (`ran_away`), FVG/OB mitigasyonu. Dolduktan sonra: SL.

## 3. Kararlar (2026-11-14, operatör onaylı — spec §2)

| # | Karar | Gerekçe |
|---|---|---|
| K2 | Hedef modelde HTF bias = **4h**. Canlı 12h değiştirilmez. | Son niyet 11-13; biassız 15m varyantları −0.22…−0.33 R (ÇÜRÜTÜLMÜŞ) |
| K3 | **SL = OB dış fitili ∓ %0.2** (sweep varsa süpürülen uç). ATR kuralı yok; yerine **maliyet bütçesi**: tahmini RT maliyet / SL mesafesi > 0.15 R → setup alınmaz. Gölgede ATR-SL (A) ve bu SL (B) yan yana loglanır. | Operatör altı kez "ATR'ye göre değil"; ölçülmüş zarar kaynağı maliyet/R (~0.27 R @ medyan SL %0.72). Bütçe kapısı ATR kuralı değildir |
| K4 | **Sweep zorunlu değil**; `SWEEP` analiz etiketi olarak kaydedilir. | 11-13 tarifinde yok; zorunlu-sweep varyantları NET negatif |
| K5 | **Kanonik implementasyon = `engine/smc_v2/fvg_entry.py`.** u2Algo-Trade `pin_fvg_touch` **dondurulur**: yeni kol yok, testnet A/B önceden yazılmış durma koşuluna kadar koşar, sonra arşivlenir. | pin_fvg_touch holdout'ları −0.50 / −0.85 R; tek ölçüm hattı ("neden bu kadar zorlaştırdın") |

## 4. Sapma tablosu — her implementasyonun hedeften farkı

Canlı LuxAlgo modu: V1 mainnet yeni girişleri 2026-11-14 12:30 UTC'den beri durdurulmuş (ADR-0012); mantık
değişmedi. `pin_fvg_touch` repo dışıdır (`u2Algo-Trade:recipes/pin_fvg_touch.yaml` @ `3bade43`, salt okundu).

| Adım | Hedef (§2) | Canlı LuxAlgo modu | `fvg_entry` gölgesi | `pin_fvg_touch` (donduruldu) |
|---|---|---|---|---|
| Bias | 4h swing trend | **12h** (`engine/safe_orchestrator.py:1256-1258`) — sapma | 4h (`engine/safe_orchestrator.py:2363`) — uyumlu | **Yok**; 1h pin + 15m sweep — sapma |
| Tetik | 15m CHoCH/BOS, son 168 bar | Uyumlu (`config:200,293`) | CHoCH/BOS, yalnız en yeni kapanmış barda bilinen planlar (`engine/smc_v2/fvg_entry.py:116-118`) | 5m CHoCH (`structure.kind: choch`) + zorunlu sweep — sapma |
| Bölge | Kırılım FVG'si | **Kırılımın OB'si** (`engine/smc_v2/luxalgo.py:536-548`) — sapma | Uyumlu (`engine/smc_v2/fvg_entry.py:59-64`) | CHoCH öncesi FVG (`entry.zone: pre_choch_fvg`) — kısmi |
| Giriş | FVG kenarına LIMIT, teyitsiz | **15m engulfing kapanışı → MARKET** (`engine/smc_v2/confirmation.py:1-8`, `exchange/__init__.py:1151-1153`) — sapma; teyit TARTIŞMALI — baz P1 −0.30 vs P2 −0.75 lehine; ancak teyit almayan dokunuşlarda limit P2 −0.04 R, PF 0.95 (n=407); kaynak: 'değer kattığına dair kanıt da yok' (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:22,43,54`) | Limit simülasyonu, emir yok (`engine/smc_v2/fvg_entry.py:121`) — uyumlu (yalnız log) | Temas (`entry.price: touch`) — uyumlu yönde |
| Filtre (P/D) | Açık, ölçülecek | Zorunlu (`config:199`) | **Yok** — sapma (ölçülmedi) | Yok (`filters: {}`) |
| Filtre (maliyet bütçesi) | ≤ 0.15 R | Yok | Yok | Yok |
| SL | OB dış fitili ∓ %0.2 | OB ucu ∓ 0.5 ATR, 2 ATR taban, 5 ATR tavan (`engine/smc_v2/sl_calc.py:56-78`; `config:294,412-413`) — sapma | **Aynı `calc_sl`**, çapa OB ucu (`engine/smc_v2/fvg_entry.py:122-127`) — sapma | Süpürülen uç ∓ %0.20 (`sl.anchor: ext`, `buffer_pct: 0.20`) — çapa farklı, mesafe uyumlu |
| TP1 | İlk karşı OB/BB ≥ `min_rr` | En yakın ≥ `min_rr` herhangi lux adayı (`engine/safe_orchestrator.py:3056-3059`) — sapma | Uyumlu (`engine/smc_v2/fvg_entry.py:67-79`) | En yakın OB/BB, R:R > 1.8 — uyumlu |
| TP2 | Yön likiditesi, TP1 + ≥0.5 R | Sonraki lux adayı — sapma | Uyumlu (`engine/smc_v2/fvg_entry.py:82-95`) | Tanımsız — sapma |
| Yönetim | TP1 %50 + BE, max-hold yok | Uyumlu (`config:407`; `engine/lifecycle.py:409-413`) | Simülasyon (`engine/smc_v2/fvg_entry.py:158-231`) | TP1 %50 + BE; **max-hold 36 h** — sapma |
| Maliyet modeli | Kanonik = backtest config (ADR-0011) | Ölçüm: −0.30 R/işlem, PF 0.65, n=217 | Kanonik (ADR-0011; PR #348) | Repo dışı model |
| NET kanıt | — | **ÇÜRÜTÜLMÜŞ** (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`; `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:21-24`) | ÇÜRÜTÜLMÜŞ (offline 180 g: NET −0.26 / −0.20 R; `docs/research/2026-11-14-fvg-offline-gate.md`) | ÇÜRÜTÜLMÜŞ (holdout) / KANITSIZ (forward) |

Özet: gölge, hedefin bias / bölge / giriş / TP1 / TP2 adımlarını karşılar; **SL'yi ve P/D + maliyet bütçesi
filtrelerini karşılamaz**. Gölge ≥30 kapanışa ulaşsa bile operatörün SL tarifini ölçmüş olmaz → GATED Ö5
(SL varyant B + kanonik maliyetle `net_r`), Ö8 (maliyet bütçesi).

## 5. Operatör ifadeleri (tarihli, kısa alıntı)

Kaynak kimliği = transcript dosya adının ilk 8 karakteri (`~/.claude/projects/…`, repo dışı) veya commit.
Saatler yereldir (UTC+3).

| Tarih / saat | Konu | Kısa alıntı / özet | Kaynak |
|---|---|---|---|
| 2026-05-23 | Giriş, SL, TP | pullback-to-FVG/OTE + LTF teyit; yapısal SL + ATR buffer; likidite-öncelikli TP1 | memory `smc_v2_rework_initiative.md` |
| 2026-09-30 | Bölge | CHoCH sonrası giriş kırılımı yapan OB/BB'den | `242cef3` |
| 2026-11-01 | Motor | "luxalgo mantığını kullanalım" | `38508f7` |
| 2026-11-06 00:46 | Sonuç | "bizim stratejimize göre zarar etmiş… setup değiştirmemiz lazım" | `59d1fece` |
| 2026-11-07 16:27 | TF | "15m trade, 1h CHoCH-BOS, 1d ana trend"; "12h yaygın değil"; R:R ≥ 1:1.5 | `2e1d15e1` |
| 2026-11-07 21:28 | SL | "likidasyon sonra CHoCH… OB'den giriş, SL ATR'ye göre değil, SSL/BSL'den biraz uzak" | `69ca35d6` |
| 2026-11-07 22:19 | Kontrol noktası | "20-30 işlem sonra hâlâ negatifse birlikte değiştiririz" | `e9527d49` |
| 2026-11-07 22:51 | Yönetim | 36 saat zorla kapatmayı kaldır | `e9527d49` → #339 |
| 2026-11-08 01:37 | Bias, SL | "15m içinde yapalım, ana trend'e bakmayalım"; "SL SSL/BSL'nin %0.2 ötesi" | `69ca35d6` |
| 2026-11-08 01:50 | SL | "SSL/BSL noktasının %0,2 uzağına… entry noktasının değil" | `69ca35d6` |
| 2026-11-08 02:05 | Giriş, TP | sweep → 5m CHoCH → FVG'ye geri çekilmede giriş; TP1 OB/BB; R:R > 1.8 | `69ca35d6` |
| 2026-11-08 03:11 | Bölge | "1.5×ATR şartını kaldıralım, FVG boşluğu veren mum yapısı yeterli" | `69ca35d6` |
| 2026-11-13 10:52 | Öz | "FVG boşluğundan işleme girecek, SL likidasyon noktasının biraz uzağına atılacak, bütün mesele bu. Neden bu kadar zorlaştırdın" | `69ca35d6` |
| 2026-11-13 21:02 | Tam tarif | "15m işleme girecekse 4h bias"; CHoCH-BOS sonrası FVG'ye geri çekilmede gir; SL kırılımı yapan OB mumunun biraz uzağı; TP1 bir sonraki OB-BB; TP2 yön likiditesi | `69ca35d6` |
| 2026-11-14 | Giriş, süreç | Seçim: "Geri çekilmede FVG limit", "Önce gölge, sonra canlı" | `69ca35d6`; `docs/superpowers/specs/2026-11-14-fvg-entry-shadow-design.md` |
| 2026-11-14 | K1–K9 | Kararlar ikinci-beyin modunda önerildi, operatör "evet" ile onayladı | `docs/superpowers/specs/2026-11-14-ecc-revision-and-target-model-design.md` §2 |

Niyet sürüklenmesi (kayıt): bias 1d (11-07) → yok (11-08) → 4h (11-13); sweep var (11-07/08) → yok (11-13);
R:R 1.5 ↔ 1.8. K2 ve K4 bu sürüklenmeyi 2026-11-14 itibarıyla karara bağlar; yeni bir ifade bu tabloya yeni
satır olarak eklenir, karar değişirse yeni ADR veya spec yazılır.
