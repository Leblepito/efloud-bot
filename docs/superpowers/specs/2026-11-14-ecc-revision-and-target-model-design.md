# ECC Doküman Revizyonu + Hedef Setup Modeli + Operatör Kararları — Tasarım (2026-11-14)

> Girdi: `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` (Fable 5.2 sentezi) + `01`–`07` kategori raporları.
> Onay: operatör 2026-11-14 — (1) canlıya bu turda yalnız doküman PR'ı; trade mantığı öneri listesi; (2) sentez ölçütü "niyet çerçeve, NET edge filtre"; (3) önce PR-A sonra PR-B; (4) açık operatör kararları ikinci-beyin modunda asistan tarafından karara bağlandı ve operatör "evet" ile onayladı (K1 mainnet adımı dahil). K1 operatörün kendi komutuyla uygulandı (2026-11-14 12:30 UTC). K6/K7'deki ileri tarihli runtime maddeleri (go-live sizing, %75 taban) ADR-0011/0012 yazılırken ve uygulanmadan önce **ayrıca** operatör onayı alır.
> Not: denetim, geçmişteki ~30 AskUserQuestion'ın tamamında "(Önerilen)" seçeneğinin seçildiğini buldu (07 §5.2). Bu yüzden her kararın gerekçesi aşağıda açık yazılır; ileride geri dönülebilir olması için kararlar ADR olarak kaydedilir.

## 1. Amaç ve başarı ölçütü

1. Mainnet'te ölçülmüş NET-negatif akışın zarar üretmesini durdurmak (K1), veri toplamayı kesmeden.
2. Kök dokümanlardaki olgu hatalarını düzeltmek (PR-A) — her canlı-davranış iddiası `config:satır` / `path:line` ile.
3. Dokümanlara living-docs rolleri vermek ve operatörün asıl setup'ını tek kanonik dokümanda, kanıt etiketiyle tanımlamak (PR-B).
4. Hedef modeli canlıya taşıyacak kod işlerini önceliklendirilmiş, default-OFF, TDD + gate'li bir kuyruğa koymak (GATED).

Başarı: K1 uygulanmış ve logla doğrulanmış; PR-A ve PR-B açılmış, testleri yeşil, iki bağımsız review'dan geçmiş; GATED kuyruğu `TESTS.md` + ADR'lerde kayıtlı.

## 2. Karar kaydı (K1–K9)

| # | Karar | Gerekçe (kanıt) |
|---|---|---|
| K1 | **V1 mainnet'te yeni girişler durdurulur** (`EFLOUD_PAUSE_NEW_ENTRIES=true`, VPS `.env.production`, yalnız `efloud-bot` servisi `--no-deps` ile yeniden oluşturulur, image rebuild yok). Açık pozisyonlar ve borsadaki SL/TP'ler yönetilmeye devam eder; FVG gölgesi ve diğer shadow loglar sürer. | Akış NET −0.30 R/işlem, PF 0.65, n=217 (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`); parity PF 0.69, n=137. Operatörün 11-07 kuralı ("20-30 işlem sonra hâlâ negatifse değiştiririz") aşıldı. Mevcut guard kullanılır (`engine/safety/position_guard.py:46-65`), guard zayıflatılmaz, tek env ile geri alınır. Gölge yolu ayrı (`engine/safe_orchestrator.py:2347`). |
| K2 | Hedef modelde **HTF bias = 4h**. Canlı 12h değiştirilmez (zaten durdurulmuş). | Son niyet 11-13 "15m girecekse 4h bias"; biassız 15m varyantları −0.22…−0.33 R (ÇÜRÜTÜLMÜŞ, 07 §5.5 S8). |
| K3 | **SL = kırılımı yapan OB mumunun dış fitili ∓ fiyatın %0.2'si** (sweep varsa bu nokta süpürülen uçtur). ATR kuralı yok. Yerine **maliyet bütçesi kapısı**: tahmini RT maliyet / SL mesafesi > 0.15 R ise setup alınmaz. Gölgede ATR-SL (A) ve bu SL (B) yan yana loglanır. | Operatör 6 kez "ATR'ye göre değil" (07 §5.3-3); ölçülmüş katil = maliyet/R (~0.27 R @ medyan SL %0.72). Bütçe kapısı ATR değildir; niyetle çelişmez. |
| K4 | **Sweep zorunlu değil**; `SWEEP` analiz etiketi olarak kaydedilir. | 11-13 tarifinde yok; zorunlu-sweep varyantları S6–S10 NET negatif. |
| K5 | **Kanonik implementasyon = efloud `engine/smc_v2/fvg_entry.py`.** u2Algo-Trade `pin_fvg_touch` dondurulur: yeni kol yok, testnet A/B önceden yazılmış durma koşuluna kadar koşar, sonra arşiv. | pin_fvg_touch holdout'ları −0.50 / −0.85 R; tek ölçüm hattı (operatörün "neden bu kadar zorlaştırdın" şikâyeti). |
| K6 | **GO kriteri (ADR-0011):** Offline (asıl kapı): ≥180 gün × 10 sembol, n ≥ 100, kanonik maliyet (backtest config), IS ve OOS NET ort. R > 0, OOS NET PF ≥ 1.30, sembollerin ≥ %60'ı pozitif, denenen varyant sayısı raporda. Forward (sağlama): n ≥ 30 kapanış, NET > 0, ort. R ≥ offline ort. R'nin yarısı. Go-live kademeli: ilk 30 işlem $25 notional, sonra $50. | 30 işlemde PF çok gürültülü → offline ana kapı; baz negatif olduğu için "canlıdan iyi" tek başına yetmez (Fable N4). |
| K7 | Durdurma süresince exposure/sizing değişmez. Yeni modelin go-live'ında: `max_open_positions` = ⌊`max_total_exposure` × bakiye / notional⌋ (tavan yükseltilmez); `starting_balance` o günkü bakiyeyle güncellenir; mutlak taban Ö12 ("TRIP + Telegram", default-OFF) go-live günü bakiyenin %75'inde açılır. | Efektif tavan ≤4 (`position_guard.py:271-282`); dokümandaki "10 pozisyon" yanlış; kalıcı HALT istenmiyor (`b2154c5`). |
| K8 | V2/V3 (long/scalp) mevcut config'lerle işlem yapmamalı. K1 uygulanırken durumları okunur; işlem yapıyorlarsa aynı env ile durdurulur. | Proxy ATR, kapı yok, alarm kapsamı yok, breaker kalibrasyonu tutarsız (Fable X29, N11). |
| K9 | Hijyen: (a) transcript'teki **testnet** anahtarını operatör Binance testnet'te rotate eder (transcript düzenlenmez); (b) ana checkout temiz → `git pull --ff-only` (stash yok); (c) memory'de eski dev şifresi ve ölü URL'ler temizlenir. | 05/07 raporları; gerçek fon riski yok. |

## 3. Hedef setup & algoritma modeli (PR-B'de `docs/STRATEGY_INTENT.md`)

Pipeline (etiket = ölçülmüş NET kanıt):

| Adım | Kural | Etiket |
|---|---|---|
| 1 Bias | 4h LuxAlgo swing trend; UNDEF → işlem yok | Bias kapısı KANITLI (göreli, 12h'te); 4h KANITSIZ |
| 2 Tetik | 15m, bias yönünde CHoCH veya BOS, son 168 bar | Recency KANITLI (göreli); BOS KANITSIZ |
| 3 Bölge | Kırılımın OB'sinden sonra, kırılım+2 bar içinde oluşan, mitige olmamış FVG | KANITSIZ |
| 4 Giriş | FVG yakın kenarına LIMIT; fiyat kaçarsa iptal; timeout 48 bar | KANITSIZ (gölge ≈ 0.00 R, n=85) |
| 5 Filtre | Premium/discount; maliyet bütçesi ≤ 0.15 R; R:R ≥ `risk.min_rr` (1.8) | P/D KANITLI (göreli, lux akışında); bütçe eşiği KANITSIZ |
| 6 SL | OB dış fitili ∓ %0.2 (K3) | KANITSIZ |
| 7 TP1 | Yoldaki ilk karşı OB/BB | KANITSIZ |
| 8 TP2 | TP1'in ≥0.5 R ötesindeki yön likiditesi (EQH/EQL/swing) | KANITSIZ |
| 9 Yönetim | TP1'de %50 + SL başa baş; max-hold yok, 24 saatte uyarı | Max-hold 0 göreli KANITLI (zayıf) |
| 10 Risk | Breaker, exposure tavanı, drift %1, SL < likidasyon, orphan koruması — değişmez | Guard |
| Yedek | Mitige-OB / breaker retest + engulfing | KANITSIZ (+0.24 R, n=30) |

Model bir hipotezdir; K6 kapısını geçmeden canlıya alınmaz.

## 4. PR-A — olgu düzeltmeleri (yalnız `.md`)

Branch `docs/ecc-audit-2026-11-14` (worktree `C:/tmp/wt-ecc-audit`). Kapsam = Fable §6.1 A1–A18, iki değişiklikle:
- **A4:** v1 "Çekirdek Mantık" bölümü CLAUDE.md'de **yerinde kalır**, başlığı "v1 referansı (canlıda susturulmuş)" olur ve üstüne 5 satırlık "Canlı motor" pointer'ı eklenir — çünkü `tests/test_docs_param_parity.py` CLAUDE.md'de `Swing Lookback**: 5` arar. Taşıma + test güncellemesi PR-B'de.
- **A10:** `collab/STATUS.md` VPS durumunu kaynağıyla yazar ("son DEPLOYED kaydı `bf464d0`, collab/log") + K1 uygulama kaydı.

Commit'ler: (1) `docs(audit)` raporlar + bu spec; (2) kök dokümanlar; (3) alan dokümanları (PINE_SPEC, ADR notları, agents, skills, runbook'lar, CI reviewer metni, arşiv başlıkları).
Yazım kuralı: constitution dosyalarına tarih/SHA/"şu an" yok; canlı iddia = `config:satır` / `path:line`; kod/config/compose/Caddy/Pine kaynağına dokunulmaz.

## 5. PR-B — doküman mimarisi

- Yeni: `docs/STRATEGY_INTENT.md` (§3 + operatör tarihli ifadeleri + sapma tablosu: canlı lux, `fvg_entry`, `pin_fvg_touch`), `docs/adr/0011-edge-go-criteria.md` (K6), `docs/adr/0012-live-flow-pause-and-ramp.md` (K1, K7, K8), `docs/research/DECISIONS.md` (soyağacı), `docs/engineering-rules.md` (ECC ↔ Karpathy override tablosu, ≤60 satır), `docs/runbooks/backtest-gate.md`.
- Değişen: CLAUDE.md ≤70 satır iskelet (Fable §7); v1 bölümü PINE_SPEC'e taşınır ve `tests/test_docs_param_parity.py` PINE_SPEC'i okuyacak şekilde güncellenir (tek test değişikliği; trade mantığı değil); HERMES.md → `docs/runbooks/operator-runbook.md` (+ OPERATOR_GUIDE birleşimi, kökte yönlendirme) — önce `git grep` ile test/script bağımlılığı kontrol edilir (`tests/collab/test_collab_layout.py` STATUS.md vb. arar); `TESTS.md` "missing" satırları (Fable B8); ADR index güncellemesi.
- B9 (lokal branch'lerdeki NO-GO raporlarının kurtarılması) ana checkout'taki branch'ler okunabiliyorsa yapılır, değilse STATUS'a açık iş olarak yazılır.

## 6. GATED kod kuyruğu (bu turun dışında; her biri ayrı PR, failing test → cerrahi diff → risk-ops → gerekiyorsa NET gate → operatör)

1. Ö1 verify algo-fetch `ok=True` reprodüksiyon + fix (`exchange/__init__.py:1842-1850`).
2. Ö2 CONFIRMED re-emit reprodüksiyonu (`engine/smc_v2/setup_state.py:121-126`); doğrulanırsa `smc_v2.block_reemit_after_confirm` default-OFF.
3. Ö5 gölgeye SL varyant B + kanonik maliyetle `net_r` + gölge defteri kalıcılığı (`smc_v2.fvg_entry_sl_shadow_variants`).
4. Ö3/Ö4 journal `engine_path` + tek maliyet kaynağı + gate script'i ADR-0011'e.
5. Ö8 maliyet bütçesi kapısı (`smc_v2.max_cost_r: null`), önce gölge.
6. Ö12 bakiye tabanı TRIP (`safety.balance_floor_trip_usdt: null`).
7. Ö9 FVG limit canlı emir yolu — yalnız K6 offline + forward kapısı geçtikten sonra.
8. Ö6/Ö7/Ö10/Ö11/Ö13/Ö14/Ö15 Fable §6.2 sırasıyla.

## 7. K1 uygulama ve doğrulama

1. Salt okuma: `docker ps` (3 bot konteyneri durumu), V1 açık pozisyonlar/bakiye (bot API, `reference_live_bot_control`), compose çalışma dizini.
2. VPS `.env.production`'a `EFLOUD_PAUSE_NEW_ENTRIES=true` (yedek kopya alınır: `.env.production.bak-20261114`).
3. `docker compose -f docker-compose.prod.yml up -d --no-deps efloud-bot` (build yok).
4. Doğrulama: log dosyasında `pause_new_entries config loaded: effective=True source=env` (event `position_guard.pause_config_loaded`; V1 `EFLOUD_AUTOSTART=0` olduğundan döngü `/api/bot/start` ile pause aktifken başlatılır); `/healthz` ok; açık pozisyon sayısı ve borsadaki SL/TP emirleri önce/sonra aynı; sonraki teyitli sinyalde `gate blocked: pause_new_entries active`; FVG gölge log satırları sürüyor.
5. K8: V2/V3 işlem yapıyorsa aynı adım onlar için; yapmıyorsa yalnız STATUS'a not.
6. Geri alma: env satırını kaldır/false + aynı `up -d --no-deps`.
7. Erişim izin katmanında reddedilirse: operatöre `! ssh efloud-bot …` komutları verilir; asistan çıktıları doğrular.

## 8. Test ve review

- PR-A/PR-B: `pytest tests/test_docs_param_parity.py tests/collab/ tests/ci/` + `python scripts/regression_ledger.py` kontrolü; tek seferlik referans-doğrulama script'i (yeni `path:line` referanslarının varlığı; repoya girmez).
- İki bağımsız review: `efloud-code-reviewer` (atomic, yan etki) + kararlarımdan habersiz fact-checker ajanı (yeni iddiaları kaynakta çürütmeye çalışır).
- Secret yok; `.env*` değerleri hiçbir dokümana girmez.

## 9. Kapsam dışı

Trade mantığı/config/compose/Caddy/Pine kaynak değişiklikleri (GATED/NO); v1 girişlerini açmak; kapı gevşetme; exposure artırma; long/scalp restart.
