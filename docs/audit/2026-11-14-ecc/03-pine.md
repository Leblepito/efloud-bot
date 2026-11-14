# 03 — Pine Script İnceleme Raporu (2026-11-14)

Kök: `C:/tmp/wt-ecc-audit` (origin/master `81c2cf7`). Kapsam: `pine/**`, `docs/pine-lab/**`, `docs/indicator/**`. Python yalnız karşılaştırma için okundu.
Not: Görevde anılan `pine/AUDIT_v1/v2` dosyaları bu kökte YOK (`find -iname "AUDIT*"` yalnız `backend/audit`, `docs/audit` döndürdü).
Not: `python -I scripts/build_pine_lab.py --check` çalıştırıldı (yazmaz): çıktı boş, üretilen `efloud_lab*.pine` dosyaları `pine/lab/*` ile senkron.

---

## 1. Envanter (ne var, ne işe yarıyor, canlı mı/ölü mü/shadow mu)

Önemli çerçeve: Canlı bot `smc_version: v2` + `luxalgo.enabled: true` (`configs/config.phase2_1k.yaml:90,187-188`). Config yorumu: LuxAlgo açıkken "efloud triggers yolu (OB/BB, OTE, FVG, origin swing) devre dışı kalır" (`:182-185`). Yani canlı setup motoru = `engine/smc_v2/luxalgo.py`. Pine tarafında bunu yansıtan TEK aile `pine/lab/*` → `efloud_lab*.pine`'dır. Diğer tüm Pine dosyaları canlı mantığın ESKİ/başka bir yolunun portudur.

| Dosya | Satır | Son commit | Rol | Durum |
|---|---|---|---|---|
| `pine/lab/{head_indicator,head_strategy,core,tail_indicator,tail_strategy}.pine` | core ~1000 | bfcae56 (2026-11-06) | TEK KAYNAK (düzenlenen) | **ÜRÜN KAYNAĞI** |
| `pine/efloud_lab.pine` (indicator "u2algo Price Action") | 1397 | bfcae56 | ÜRETİLEN (`scripts/build_pine_lab.py`; "edit pine/lab/*, never this file", `:2`) | **Ürün** — canlı v2-LuxAlgo baseline'ı yansıtır; açık-kaynak CC BY-NC-SA yayın hedefi (`docs/indicator/tradingview-publish.md:3`) |
| `pine/efloud_lab_strategy.pine` ("u2algo Price Action Strategy") | 984 | 4fda261 | ÜRETİLEN strategy | **Lab/backtest**; "kayıtlı ama yayımlanmaz" (PINE_SPEC §20) |
| `pine/efloud_signals.pine` (EFloud Signals v2.1, indicator) | 803 | 37bbcd8 (2026-07-06) | Eski "efloud triggers" v2 + V1-absorbe portu | **ESKİ / canlı değil** (canlıda luxalgo bu yolu kapatıyor) |
| `pine/efloud_strategy.pine` (EFloud Strategy v2) | 619 | 3fea139 (2026-07-11) | Yukarıdakinin strategy eşi | ESKİ; son dokunuş F10 state-reset fix |
| `pine/efloud_signals_v1.pine` / `efloud_strategy_v1.pine` | 660 / 519 | c2bd801 / 3fea139 | SMC **v1** (confluence makinesi) portu | ÖLÜ-yol: canlı `smc_version` v2; v1 yalnız geri dönüş |
| `pine/publish/efloud_signals_v2_en.pine` + `PUBLISH_efloud_signals.md` | 23 input | c2bd801 (2026-07-03) | İngilizce "ürün" varyantı (auto profile) — *Protected, Public* yayın paketi | ESKİ ürün adayı; yerini `u2algo Price Action` (lab) aldı. Yayınlanıp yayınlanmadığı DOĞRULANMADI |
| `pine/u2algo/wave1_signals.pine` + `WAVE1_SPEC.md` | — | 2026-06 | P-001 Wave-1 lead-magnet indikatörü | ÖLÜ ürün: memory "Wave-2 DROPPED"; Wave-1 de NO-GO; spec "live conf_thresh=80" (bayat, bkz. §4) |
| `pine/PINE_SPEC.md` | 670 | fa13ef1 | V2 + EK A (V1) + §15-21 değişiklik kayıtları | Karışık: §0-14 eski v2.1; §20-21 güncel lab |
| `docs/pine-lab/README.md` + 2 rapor | — | 2026-11-06 | Operatör akışı, parity ve görsel doğrulama kayıtları | Güncel ama 11-06'da donmuş |
| `docs/indicator/{tradingview-publish,u2algo-price-action}.md` | — | 4fda261 | Yayın kiti + kullanıcı rehberi | Güncel; `<!-- TV_URL -->` yer tutucuları dolu değil |
| Test/araçlar | | | `tests/test_pine_lab_{build,parity,variant,visuals}.py`; `scripts/pine_lab_{parity,variant,fetch_klines}.py`, `build_pine_lab.py` | Canlı CI kapısı: `--check` |

Lab toggle'ları (hepsi default KAPALI, `pine/lab/core.pine:53-62`): T1 `biasTf/biasMode/macroTf`, T2 `obInvalidate` (breaker), T3 `oteEntry` (limit), T4 `sweepSl`, T5 `freshConfirm`, T6 `obDisplacement`, T7 `tpSweptFilter`, T8 `emitOnce`.

Pine'da HİÇ karşılığı olmayan canlı/shadow bileşenler: `touch_entry: shadow`, `fvg_entry: shadow` (11-14, `c05260c`), `data_feed.ws`, near-zone Telegram log alert'i (`near_alert_atr`), `structure_validation`, Kronos/LLM danışma — `grep touch_entry|fvg_entry|ob_bb_entry pine -r` boş.

---

## 2. Canlı gerçek (prod'da fiilen çalışan davranış ↔ Pine'ın neyi yansıttığı)

Canlı davranış kaynağı: `configs/config.phase2_1k.yaml` (`.env.production EFLOUD_CONFIG_PATH`, `:70-77` yorumu). `deploy/` altında `docker-compose.prod.yml` bu kökte YOK (yalnız `deploy/deploy.sh`, `Caddyfile*`) — kökteki `docker-compose.prod.yml` env'i okunmadı; Pine için kritik değil.

Canlı setup üretimi (kanıt `config.phase2_1k.yaml`):
- `smc_version: v2`, 10 sembol whitelist, `smc_v2_shadow: false` (`:90-95`) → v2 CANLI emir.
- `smc_v2.luxalgo.enabled: true` (`:188`): `swing_length 50`, `internal_length 5`, `eq_length 3`, `eq_threshold 0.1`, `ob_filter ATR`, `ob_mitigation HIGHLOW`, `require_premium_discount true`, `kinds: [CHoCH, BOS]`, `min_confluence: 1`, `tp_mode: luxalgo`, `tp_wick_buffer_r: 0.15`, `pullback_timeout_bars: 48` (`:187-205`).
- Kapılar: `po3_gate: true`, `max_entry_dist_atr: 12.0`, `max_zone_overshoot_atr: 6.0`, `max_pending_per_symbol: 6` (`:121-175`); `risk.recency_bars: 168` (`:293`); `min_sl_atr: 2.0`, `max_sl_atr: 5.0` (`:412-413`); `v2_use_real_atr: true` (`:105`).
- Profil `mid` = 15m / 4h / 12h (`:238`; `data/timeframes.py:24-27` PROFILES).
- TP: `smc_tp_targeting: true`, `min_rr_tp1: 0.5`, `blended_rr_target: 1.5` (`:279-281`); `min_rr: 1.8` "legacy gate — smc_tp_targeting açıkken kullanılmaz" (`:273`).
- 36 saat max-hold KALDIRILDI (`59c32f3`, 2026-11-08): `safety.max_holding_hours = 0` → yalnız SL/TP/BE ile kapanış.
- Shadow (emirsiz): `touch_entry: shadow`, `fvg_entry: shadow`, WS parite sayaçları (`:209-221`).

Pine lab baseline'ı bu değerleri BİREBİR input default'u olarak taşır (`pine/lab/core.pine:13-43`: swingLen 50, internalLen 5, eqLen 3, eqThr 0.1, requirePD true, minConfluence 1, recencyBars 168, maxZoneDistAtr 12, maxOvershootAtr 6, timeoutBars 48, maxPending 6, minSlAtr 2.0, maxSlAtr 5.0, minRr 1.8, tpWickBufferR 0.15, po3Gate true). Config↔lab input defaultları şu an ÇELİŞMİYOR. Fakat lab:
- Yalnız mid profil (15m/12h bias) için kurulu; scalp/long seçeneği yok (`f_tf` yalnız 4h/12h/D, `core.pine:~55`).
- `tail_strategy.pine:5,112` hâlâ `maxHoldHours = 36` ile `MAX_HOLD` kapanışı uyguluyor → canlıda 11-08'de kaldırılan davranışı simüle ediyor (bkz. Çelişki #3).
- Canlıdaki 11-14 FVG shadow, touch shadow, near-alert Pine'da yok (shadow oldukları için parity bozmaz).

`pine/efloud_signals.pine` (v2.1) defaultları canlıdan FARKLI: `minSlAtr 0.5` (canlı 2.0, `signals.pine:66`), `pullbackTimeoutBars 8` (canlı 12/48), `maxPending 3` (canlı 6), `minRr 1.8` (canlı smc_tp_targeting yolu), `useConfluenceGate true/min 50` (Lux yolunda confluence skoru yok; canlı `min_confluence: 1` etiket sayısı). `smcTpTargeting/minRrTp1/blendedRrTarget` Pine'da YOK (grep boş) — PINE_SPEC §19'daki "PORT BEKLİYOR" maddesi hâlâ açık ve artık anlamsız (canlı TP yolu luxalgo `tp_mode`).

**Son ölçülmüş parity (lab strategy ↔ Python replay, 128 gün, 3 sembol) — `docs/pine-lab/2026-11-06-ilk-tur.md` §4d:** BTC eşleşme %91.3 (FAIL <95), ETH %100 ama level mismatch %12.1 (FAIL >5), SOL %100 ama level mismatch %8.2 (FAIL). **Formal `GATE: PASS` HİÇ alınmadı**; README kuralı "GATE PASS olmadan toggle turuna geçilmez" gereği toggle turu (T1-T8 skorları) KOŞULMADI. 11-06'dan sonra Pine'a dokunan commit yok (`git log --since=2026-11-07 -- pine docs/pine-lab` boş) ama Python'da 11-08/11-14'te değişiklikler oldu (max-hold kaldırma, FVG shadow, breaker sim-time).

---

## 3. Çelişkiler

| # | Çelişki | Kanıt A | Kanıt B | Etki | Önerilen çözüm |
|---|---|---|---|---|---|
| 1 | CLAUDE.md "Pine kodları `efloud_signals.pine`/`efloud_strategy.pine`'a yazılır" ↔ fiili ürün `pine/lab/*` → `efloud_lab*.pine` | `CLAUDE.md:20,39` | `README.md:64,214-222`; `pine/efloud_lab.pine:2` ("edit pine/lab/*, never this file") | Yeni oturum yanlış (eski, canlı olmayan) dosyayı düzenler; "senkron tut" kuralı yanlış dosya çiftine uygulanır | CLAUDE.md çalışma kuralını "kaynak: `pine/lab/*`; üretilen dosyaya dokunma; `python scripts/build_pine_lab.py --check`" olarak değiştir; eski çifti "ARŞİV/dondurulmuş" etiketle |
| 2 | CLAUDE.md "SMC v2 port'unu (`pine/efloud_signals.pine`, `engine/smc_v2/`) ezme" ↔ canlı v2 artık LuxAlgo yolu; `efloud_signals.pine` o yolu portlamıyor | `CLAUDE.md:39`; `PINE_SPEC.md:3` (spec `engine/smc_v2` shadow der) | `config.phase2_1k.yaml:182-188`; `pine/lab/core.pine:6-8` ("Baseline = live SMC v2 entry logic (luxalgo.py)") | Koruma kuralı yanlış hedefi koruyor; asıl port (lab) korumasız | Koruma kuralına `pine/lab/*` ve `scripts/build_pine_lab.py` ekle |
| 3 | Lab strategy `MAX_HOLD` 36 saat ↔ canlıda max-hold kaldırıldı | `pine/lab/tail_strategy.pine:5,112-113` | `59c32f3` (safety.max_holding_hours 36→0, 2026-11-08) | Backtest/parity, canlıda olmayan bir çıkış yolu içerir; PF/WR yanlış okunur (11-06 turunda MAX_HOLD 1-2 işlem) | `maxHoldHours` default'u kapalı (0/very large) yapılabilir kılmak; Pine'a "0=off" ekle — trade-logic değil, backtest modeli; yine de operatör/backtest-gate |
| 4 | PINE_SPEC "Bu dosya onaylanmadan Pine koduna geçilmeyecek" + §0 "V2: confluence YOK" ↔ aynı dosyada EK A (V1 confluence 100-puan) ve `efloud_signals.pine` v2.1 confluence gate (default 50) taşıyor | `PINE_SPEC.md:3-5,23` | `PINE_SPEC.md:508-526` (§16 v2.1 V1-absorbe); `efloud_signals.pine:53-54` | Spec iç tutarsız; hangi bölüm hangi dosyayı anlatır belirsiz | Spec başına durum tablosu: bölüm → dosya → canlı/arşiv |
| 5 | PINE_SPEC §19 "Pine'a PORT BEKLİYOR (smc_tp_targeting)" ↔ canlı TP artık `tp_mode: luxalgo`; eski port gereksiz | `PINE_SPEC.md:604-617` | `config.phase2_1k.yaml:204`; `grep smcTpTargeting pine` boş | Açık kalmış hayalet TODO | §19'u "SUPERSEDED by lab (luxalgo TP)" işaretle |
| 6 | `PUBLISH_efloud_signals.md` "Source stays **Protected**… Public" ↔ `tradingview-publish.md` "Protected/invite-only YAYIMLANMAZ, yalnız Open-source" | `pine/publish/PUBLISH_efloud_signals.md:3-4` | `docs/indicator/tradingview-publish.md:3`; PINE_SPEC §20 "2026-11-06'ya kadar private/invite-only idi" | İki yayın paketi birbirine ters; eski paket tekrar kullanılırsa lisans ihlali değil (efloud_signals LuxAlgo türevi değil) ama marka/ürün karışır | Eski paketi arşivle ya da "SUPERSEDED" başlığı koy; hangi script'in TV'de yayında olduğunu doğrula (DOĞRULANMADI) |
| 7 | Publish varyantı profil zinciri ↔ tek kaynak PROFILES | `publish/efloud_signals_v2_en.pine:20,27-29` (scalp HTF 12h, long HTF **1w**, 2-TF) ; `PUBLISH_efloud_signals.md:40-41` ("scalp 12h, mid 4h, long 1w") | `data/timeframes.py:25-27` (scalp 5m/1h/4h; mid 15m/4h/12h; long 1h/8h/1d); `efloud_signals.pine:28-32` doğru | Yayın varyantı kullanıcıya yanlış HTF söyler; chain redesign 3c96029 sadece repo portuna yansımış | Yayın varyantı kullanılacaksa zincir senkronla; kullanılmayacaksa arşivle |
| 8 | Mid için HTF: spec §1 "4h" ↔ profil mid = 15m/4h/12h (HTF=12h, MTF=4h) | `PINE_SPEC.md:36-39` (tarihsel not var `:42-46`) | `PINE_SPEC.md:527+` §17, `efloud_signals.pine:30-32` | Düşük: tablo üstündeki profil notu zaten uyarıyor | Tabloyu §17 ile değiştir |
| 9 | Lab dokümanı "kayıtlı EFloud Lab indicator hâlâ v6 (eski)" ↔ verify doc "repo build (pineVersion 44) TV'de" | `ilk-tur.md:§4d` | `indicator-visuals-verify.md` Final state | Tarih sırası farkı (4d daha eski); çelişki değil ama yalnız son durum güvenilir | Rapor başına "SON DURUM" satırı |
| 10 | Wave-1 spec "live prod conf_thresh = **80**" ↔ canlı `min_confluence: 50` (v1) / 1 (lux) | `WAVE1_SPEC.md:~38` | `config.phase2_1k.yaml:282` (50), `:205` (1) | Bayat; ürün ölü | Wave-1 klasörünü arşivle |
| 11 | `docs/pine-lab/README.md` "`GATE: PASS` olmadan toggle turuna geçilmez" ↔ PINE_SPEC §20 ve kamuya yayın "Experimental toggles are off by default" → ürün baseline'ı hiç GATE PASS almadan yayın kiti hazırlandı | `docs/pine-lab/README.md` §2 son paragraf; `ilk-tur.md` §4d ("GATE FAIL ×3") | `docs/indicator/tradingview-publish.md` (b) "Baseline: structure lengths…"; `README.md:35` ("draws the same zones and signals") | Yayın metni "botun mantığını yansıtır" derken parity kapısı kapanmamış (ETH %12 level mismatch) | Yayın metnine "approximates" dili veya parity kapısı kapat |
| 12 | Strategy tarafı `initial_capital` ↔ canlı cüzdan | `head_strategy.pine:6` (1363, lab) vs `efloud_strategy.pine:15-ish` (10000) | config yorumu "cüzdan ~$1363" (`config:2`) | Eski strategy çifti farklı sermaye/sizing (riskPerTradePct) kullanır → eski backtest PF'leri lab ile kıyaslanamaz | Eski çifti arşivle |

Indikatör↔strateji input senkronu (otomatik regex karşılaştırma, `input.*` isimleri + default'lar):
- `efloud_signals` (38) ↔ `efloud_strategy` (33): ortak inputlar isim ve default olarak AYNI. Farklar yalnız görsel (`show*`, `keep*`) ve strategy'ye özgü (`moveSlToBe`, `riskPerTradePct`, `tp1ClosePct`) → senkron SAĞLAM.
- `_v1` çifti (27 ↔ 24): aynı; SAĞLAM.
- `efloud_lab` (58) ↔ `efloud_lab_strategy` (44): core inputları tek kaynaktan geldiği için yapısal olarak aynı (default farkı yok; tek fark strategy-özgü `maxHoldHours/leverage/marginUsd/...`). Lab çifti senkron GARANTİLİ (üretim + `--check`).
- Yayın varyantı ↔ `efloud_signals`: 23 vs 38 input; yayın varyantı `useMtf/minConfluence/useConfluenceGate/obSeq/rangeLb/volAtrBuffer/aiSentiment/customMtf` içermez → "core logic identical" iddiası (`publish:12-13`) 2026-07-06 v2.1 genişlemesinden SONRA geçersiz (yayın varyantı son 2026-07-03).

---

## 4. Bayat / yanlış dokümantasyon

CLAUDE.md (worktree sürümü):
- `:17-18` "Hedef: çekirdek trade mantığını (MTF SMC + **Confluence Scoring**) Pine'a çevirmek" — canlı yol LuxAlgo + `min_confluence: 1` etiketi; 100-puanlık confluence yalnız v1 yolunda. Güncel hedef: "canlı v2-LuxAlgo baseline + lab toggle'ları, parity gate'li".
- `:20` Pine dosya adları bayat (bkz. Çelişki #1).
- `:39` v2 port koruması yanlış dosya (Çelişki #2).
- `:53-56` TV MCP aracı listesi: `pine_get_errors` vb.; skill `skills/tradingview-mcp/SKILL.md` ve memory'deki "TV MCP pine-lab quirks (pine_open/pine_new save hedefini rebind etmez; `indicator set` çalışmayı bozar)" CLAUDE.md'de YOK; `docs/pine-lab/README.md` §5 kurallarında var.
- `:62-66` Confluence 55, SL "son 20 mum" vb. referans değerleri V1 `signals.py` içindir; canlı Lux yolu SL `min_sl_atr 2.0` widen / `max_sl_atr 5.0` reject + 0.5 ATR buffer. Başlık "Referans Değerler" canlı olduğu izlenimi veriyor.
- `:69-72` Pine kısıtları "Gemini/ sentiment atla" doğru ama RE10045 / UDF-collection tuzağı ve `f_xxx` fonksiyon-içi `[off]` geçmiş tuzağı (aşağı) eksik.

PINE_SPEC.md:
- `:1-12` "SMC v2 (shadow mode)" / "Pine'a geçilmeyecek" başlık bayat; v2 artık CANLI (7 Temmuz 2026) ve LuxAlgo.
- `:36-39` tek-chain tablo tarihsel (not var).
- `:347-358` §14 "Onay sonrası Faz B/C" — tamamlandı; hayalet TODO.
- `:604-617` §19 (Çelişki #5).
- §20 ilk madde "Baseline = canlı v2 LuxAlgo modu" doğru; ama "kapı ≥ %95 eşleşme" sonucu (FAIL×3) spec'te yazılı değil.
- §20 son bölümü "Pine derleme kapısı (TV MCP) … operatörde bekliyor" bayat (3. turda TV'de derlendi, 0 hata/0 uyarı).
- §21 RE10045 notu doğru ve değerli ama yalnız §21 sonunda gömülü.

docs/pine-lab:
- `README.md:§4` ve `§2` mid/15m varsayar; 11-08 max-hold kaldırılması ve 11-14 FVG shadow yansımamış (Çelişki #3).
- `2026-11-06-ilk-tur.md:§4d` "kayıtlı EFloud Lab indicator hâlâ v6 (eski)" — sonraki doküman ile üzerine yazılmış; tek başına yanıltıcı.

docs/indicator + README:
- `README.md:163`, `u2algo-price-action.md:3-4`: TV linki "yayından sonra eklenecek" → yayın GERÇEKTEN yapıldı mı DOĞRULANMADI. PINE_SPEC §20 "yayımlanır", `tradingview-publish.md` talimat modunda.
- `docs/indicator/tradingview-publish.md` (b): "A higher-timeframe (12h) bias filter" doğru (mid), "LONG/SHORT signals … Entry, Stop, Target" doğru.
- `skills/social-publishing/SKILL.md:134` hâlâ `pine/publish/PUBLISH_efloud_signals.md`'ye referans veriyor (tek dış referans, `grep`).

pine/publish & pine/u2algo: bkz. Çelişki #6,7,10 — arşivlenmesi gereken bayat paketler.

---

## 5. Trade mantığı / setup modelleri (Pine'da görünen tüm varyantlar)

Edge ölçütü: operatör niyeti çerçeve, ölçülmüş NET edge filtre. KANITLI / KANITSIZ / ÇÜRÜTÜLMÜŞ.

| # | Model | Tanım (Pine kanıtı) | Durum | Edge kanıtı |
|---|---|---|---|---|
| A | **Lab baseline = canlı v2-LuxAlgo** | BOS+CHoCH (swing 50 + internal 5), OB zone (ATR filtreli, HIGHLOW mitigasyon), premium/discount şartı, min 1 confluence etiketi (SWING_OB/OTE/EQ/FVG/SWEEP), pullback → engulfing teyidi, Po3 kapısı, 12h HTF bias, TP likidite/FVG/OB havuzu + 0.15R wick buffer (`core.pine:13-43`) | Canlı mantığın Pine karşılığı; parity GATE FAIL×3 (BTC %91.3, ETH/SOL seviye farkı %12.1/%8.2) | **ÇÜRÜTÜLMÜŞ/negatif:** Pine strategy BTC PF 0.73 (128 gün, 91 trade; `ilk-tur.md:§4c`); ETH PF 0.815, ilk tur BTC 0.846 (§2). Memory: "LuxAlgo baseline NET −0.30R (costs)". **Net-cost pozitif kanıt YOK.** |
| B | T1 bias TF/mode/macro (hard/soft, 4h/12h/1d) | `core.pine:53-56` | Default KAPALI; skor koşulmadı | KANITSIZ (GATE FAIL → toggle turu çalışmadı) |
| C | T2 OB invalidation + Breaker/Mitigation flip | `obInvalidate`; breaker kutuları `showBreakers` | Kapalı. RE10045 11-06'da düzeltildi (`dcdaf4a`) | KANITSIZ (skor yok); görsel doğrulama PASS (BTC/ETH), SOL pencere artığı |
| D | T3 OTE 0.705 limit girişi | `oteEntry`, limit dolum modeli; Python'da limit yolu YOK (parity dışı) | Kapalı | KANITSIZ; `OTE_NAKED` davranışı hiç koşulmadı (`ilk-tur.md` "Yapılmayan") |
| E | T4 sweep-aware SL / T5 fresh confirm / T6 OB displacement / T7 swept-TP filtre / T8 emit-once | `core.pine:57-62` | Kapalı | KANITSIZ (hepsi). T5/T8 canlıdaki C2 `confirm_last_bar_only:false` ve dedup fix ile ilişkili |
| F | Eski efloud-triggers v2.1 (CHoCH-only → FVG>OB>OTE zone → engulfing; `efloud_signals.pine`) | CHoCH tetik, zone zinciri FVG>OB>OTE, SL yapısal + 0.5 ATR, TP hibrit + Fibo (1.272/1.618/2.618), confluence gate 50 | **Canlı değil** (luxalgo bunu kapatıyor) | KANITSIZ: 07-26 `min_sl_atr 0.5→2.0` ölçümü (R/trade −0.363→−0.257) v2 yolu için hâlâ NEGATİF |
| G | SMC v1 portu (confluence 0-100, CHoCH/BOS anlık snap, SL clamp) | `efloud_*_v1.pine` | ÖLÜ-yol (canlıda `smc_version=v2`) | KANITSIZ |
| H | Wave-1 indicator (`wave1_signals.pine`) | OB/FVG/EQ/Breaker görsel + zone-pullback; RE10045 by-pass: UDF'siz inline | Ürün olarak bırakıldı | **ÇÜRÜTÜLMÜŞ** (memory: Wave-2 OOS PF 1.165 < 1.30 → DROPPED; Wave-1 NO-GO) |
| I | Publish varyantı (`efloud_signals_v2_en`, auto profile) | Eski v2 CHoCH→zone→engulfing, 2-TF | Eski paket | KANITSIZ |
| J | Canlıda olup Pine'da olmayan: `touch_entry` (fitil/temas), `fvg_entry` (4h bias FVG limit, SL OB ötesi, TP1 karşı OB/BB, TP2 likidite) | Shadow — yalnız log (`config:209-216`) | Shadow; go-live için ≥30 ileri kapanış NET>0 gerekir (memory) | KANITSIZ |

Parity bulguları (Python↔Pine, kanıtlı):
1. 11-06 kök neden: `f_storeOb` içinde `[off]` geçmiş referansı fonksiyon-çağrı geçmişinden okunuyordu (koşullu çağrılan UDF) → OB mumu hep pivot barı → ZONE_DIFF 47/80 pozisyon. Çözüm: halka tamponlar (`bufHi/bufLo/bufOpen/bufClose/bufTime`, `bufCap=992`), `e5589bd`/`792af5a`. Sonuç: OB 16/16 eşleşme.
2. Kalan sapmalar (PINE_SPEC §20): ATR200 tohumlama (Python her 750-bar pencerede sıfırdan ~%6), FVG eşiği kayan/kümülatif, HTF `[1]+lookahead_on` 1 HTF bar geç (K-2 vs K-1), TP havuzu pencere budaması (5 vaka), Po3 N vs N+1 kapanış sınırı, harness HTF'yi 15m'den resample ediyor (ETH Temmuz bias farkı: Python 41 SHORT / Pine 0).
3. Veri limiti: TV Plus ~128 gün; HTF ısınması (12h/50 ≈ 25-50 gün) → etkin örnek ~80 gün, 91 trade; istatistiksel güç düşük.

Repaint/Pine v6 denetimi:
- Tüm dosyalar `//@version=6`. HTF `request.security` `[1]` + `lookahead_on` (SON KAPANMIŞ HTF barı; `core.pine:357-358,388-389`; `efloud_signals.pine` 5×, v1 6×, lab core 3×, publish 4×) — PINE_SPEC §15 reçetesi. `lookahead_on` sayısı `[1]` kaydırması ile birlikte güvenli; `[1]` eksik tek bir çağrı büyük repaint olur → her `lookahead_on` satırında `[1]`/`f_swingTrend` kaydırmasını CI'da doğrula (öneri, §6).
- `wave1_signals.pine` HİÇ `request.security` kullanmıyor (0 `lookahead_on`) — 1h bias nasıl alınıyor DOĞRULANMADI.
- Lab strategy: kapanış-bazlı 3-geçiş ve `process_orders_on_close` benzeri varsayım var (PINE_SPEC §19.2 F10: entry barında SL/TP state reset hatası → eski (07-11 öncesi) efloud_strategy backtest'leri GEÇERSİZ).
- RE10045 tuzakları (3 ayrı örnek): (a) Wave-1 `f_engine_tp`+`f_nearest_zone`+`f_calc_sl` birlikte UDF+collection → inline by-pass (`WAVE1_SPEC.md:215-225`); (b) lab T2: fonksiyon-lokal iki paralel `array<int>` lock-step + `indexof/get` → tek `map<int,int>` (`dcdaf4a`, verify doc "Follow-up"); (c) UDF-içi `[off]` geçmiş referansı (yalnız koşullu çağrıda) → global ring buffer. Ortak desen: UDF + koleksiyon + koşullu çağrı → TV'de hata/yanlış değer, derleme geçse bile.

---

## 6. ECC revizyon adayları

CLAUDE.md:
1. Çalışma Kuralları: "Pine kodları" satırını `pine/lab/*` tek-kaynak + `build_pine_lab.py --check` kapısı olarak yeniden yaz; `efloud_signals/strategy` + `_v1` + `publish/` + `u2algo/` → "ARŞİV (canlı değil, dokunma)".
2. Karpathy #3 "SMC v2 port'unu ezme" hedefini `pine/lab/core.pine` + `engine/smc_v2/luxalgo.py` olarak güncelle.
3. "Pine Script Kısıtları"na Pine-tuzakları ekle: (i) UDF içinde `[off]` geçmiş referansı, koşullu çağrıda güvenilmez → global ring buffer; (ii) UDF + paralel lokal array + `indexof/get` → RE10045 → `map<>` veya tek koleksiyon; (iii) derleme PASS ≠ runtime PASS: TV'de `data indicator`/tablo sağlık kontrolü zorunlu; (iv) `pine_open`/`pine_new` kayıt hedefini değiştirmez, `indicator set` çalışmayı bozar.
4. "Referans Değerler" bölümüne "canlı değerler için tek kaynak `configs/config.phase2_1k.yaml`; V1 değerleri tarihsel" notu.

PINE_SPEC.md:
5. Üste durum tablosu (bölüm → dosya → canlı/arşiv); §14, §19 "SUPERSEDED"; §20'ye GATE FAIL×3 sonucu ve güncel parity tablosu; "max-hold kaldırıldı" parity-notu; §21'deki RE10045 notunu §12 "Çevrilemeyen/Tuzaklar"a taşı.

docs / yayın:
6. `pine/publish/` ve `pine/u2algo/` → `docs/archive/` ya da başlığa "SUPERSEDED 2026-11-06" + referansları (`skills/social-publishing/SKILL.md:134`) güncelle.
7. TV yayın durumu (URL/ID) tek yerde: `docs/indicator/tradingview-publish.md`; `<!-- TV_URL -->` doldurulana kadar README "yayında" iddiası yapmasın.
8. `docs/pine-lab/` altında "SON DURUM" tek dosya (en güncel parity tablosu, açık harness sorunları, hangi TV build'i kayıtlı).

Skills/agents/hooks:
9. `skills/tradingview-mcp/SKILL.md`: RE10045 ve `[off]` UDF tuzaklarını ekle (şu an `grep RE10045` skill'de yok; yalnız memory ve docs'ta).
10. `pine-engineer` ajanı (AGENTS.md:49 anıyor; `.claude/agents` bu kökte listelenmedi) → talimatına lab-first akışı ve `--check` kapısı.
11. CI/hook: `tests/test_pine_lab_build.py` zaten `--check`; ek: (a) `request.security` + `lookahead_on` satırlarında `[1]`/shift denetimi (statik regex test), (b) lab strategy default'larının `configs/config.phase2_1k.yaml` ile eşitlik testi (yalnız lab inputları: minSlAtr, maxSlAtr, timeout, maxPending, recency, po3, `maxHoldHours`) — config drift'i (Çelişki #3 benzeri) otomatik yakalar.
12. `docs/pine-lab/README.md`: "toggle turu" başlamadan önce backtest-gate: NET-cost (komisyon %0.04 + slippage) PF ≥ 1.30 eşiği (memory: SL/TP redesign NO-GO ölçütü) yazılı kriter olsun.

---

## 7. Riskler ve açık sorular

1. **Parity kapısı kapanmadı; ürün yayın kiti hazır.** Yayın metni "reflects bot signals" der; ETH level mismatch %12.1 (kapı %5). Risk: kamuya yanıltıcı doğruluk iddiası. Öneri: dil yumuşat ya da kalan TP-havuzu/penceresi farkını kapat (trade mantığı değil, Pine tarafı).
2. **Pine lab baseline NET negatif** (BTC PF 0.73; Python tarafı memory'de −0.30R). Ürün bir "indicator-only" (memory: indicator-only is the product) ama TV'de strategy-backtest sonucu görünürse itibar riski; strategy yayımlanmıyor (doğru).
3. **Lab `MAX_HOLD` 36 h** canlıdan sapıyor (Çelişki #3). Python tarafı değişti, Pine takip etmedi; parity harness'in hangi sürümle koşulduğu belirsiz.
4. **TV yayın durumu DOĞRULANMADI:** README `TV_URL` boş; PINE_SPEC "yayımlanır". Eski `efloud_signals_v2_en` Protected olarak yayında olabilir (TV'ye erişilmedi).
5. **Lisans:** core LuxAlgo (CnB3fSph) CC BY-NC-SA 4.0 türevi; `THIRD_PARTY_NOTICES.md` var, başlık atıf içeriyor (`efloud_lab.pine:3-5`). Ticari ürün (u2algo abonelik/premium planı, memory P-003) ile "non-commercial, share-alike" çatışabilir → operatör/hukuki karar; premium Pine sürümü bu lisansla YAYIMLANAMAZ (doc de bunu söylüyor).
6. **Harness HTF resample** (15m→12h) TV native 12h'den farklı: ETH Temmuz bias zıt. "Kaynak veri sapması" gerçek canlı sapma değil ama parity metriklerini kirletiyor.
7. **Örneklem küçük:** ~80 etkin gün/91 trade; toggle T1-T8 skorları anlamlı olmaz (TV Plus limit). Öneri: Python backtest (`backtest/`, #335) ile toggle'ları ölçmek daha güvenilir; Pine yalnız görsel/parity.
8. **Aynı-bar çoklu `fired`:** strategy yalnız ilkini açar; indicator `alert()` bar kapanışında birleşebilir (PINE_SPEC §20) → alert sayısı ≠ strateji girişi.
9. **11-14 FVG shadow** gelecekte live olursa Pine'da yok → parity yeniden kurulmalı (şimdilik shadow, risk yok).
10. Açık: `wave1_signals.pine` 1h bias kaynağı; `deploy/docker-compose.prod.yml` env'i okunmadı (yok); `pine/AUDIT_v1/v2` dosyaları repoda yok (silindi mi? `git log --all -- 'pine/AUDIT*'` boş döndü).
11. Secret taraması: `pine/**`, `docs/pine-lab/**`, `docs/indicator/**` içinde anahtar/token görülmedi; `tgChatId` input'u boş default (`tail_indicator.pine:10`). `.env*` açılmadı.

---

## 8. Fable'a özet

1. **Pine'ın ürün kaynağı `pine/lab/*`** (üretilen `efloud_lab*.pine`, "u2algo Price Action"); `efloud_signals/strategy`, `_v1`, `publish/`, `u2algo/` canlı mantığı yansıtmıyor (luxalgo efloud-triggers'ı kapatıyor) → CLAUDE.md `:20,:39` yanlış dosyayı gösteriyor; ilk ECC revizyonu bu.
2. **Baseline parity GATE hiç PASS olmadı** (3. tur: BTC %91.3 eşleşme; ETH/SOL level mismatch %12.1/%8.2); toggle T1-T8 skorları hiç koşulmadı → "KANITSIZ". Pine son dokunuş 11-06, Python 11-08/11-14'te değişti.
3. **Lab baseline NET negatif:** BTC PF 0.73 (128 gün, 91 trade), ETH ~0.82, ilk tur BTC 0.85; edge "KANITSIZ→negatif". Yayın metni bunu iddia etmiyor (iyi) ama "botun sinyallerini yansıtır" parity kapanmadan zayıf.
4. **Config↔Pine drift:** `tail_strategy.pine:5,112` MAX_HOLD 36 h; canlıda `59c32f3` ile kaldırıldı. Lab input defaultları aksi halde config ile birebir; otomatik config-eşitlik testi öner.
5. **Indicator↔strategy input senkronu SAĞLAM** (3 çift; regex karşılaştırmada ortak isim/default farkı yok); lab çifti `--check` ile garantili. Yayın varyantı (`efloud_signals_v2_en`) ise 23 vs 38 input ile sapmış ve **yanlış profil zinciri** (scalp 12h, long 1w) taşıyor.
6. **RE10045 üç ayrı kez ısırdı** (Wave-1 UDF+collection, lab T2 paralel array, UDF-içi `[off]`); kalıcı kural: UDF+koleksiyon+koşullu çağrıdan kaçın, tek `map`/ring buffer, derleme PASS ≠ runtime PASS → CLAUDE.md + skills/tradingview-mcp'ye yaz.
7. **Yayın durumu DOĞRULANMADI:** `TV_URL` boş; eski paket "Protected/Public", yeni paket "Open-source only" → çelişen iki yayın kiti; eski paketi arşivle. Lisans (LuxAlgo CC BY-NC-SA) premium/ticari Pine planıyla çatışır — operatör kararı.
8. **Pine'da olmayan canlı/shadow parçalar:** touch_entry, fvg_entry (11-14), near-alert, WS; şu an shadow → risk yok, ama go-live olursa parity yeniden kurulmalı.
9. PINE_SPEC bayat başlıkları (§0-14 eski v2.1, §19 hayalet TODO, §20 "derleme kapısı bekliyor") → başına durum tablosu + SUPERSEDED etiketleri; bu tur yalnız DOKÜMAN PR'ı, trade mantığı değişikliği önerilmez.
10. Güvenilir toggle ölçümü için TV Plus ~128 gün limiti yetersiz; toggle skorlarını Python `backtest/` (#335) ile üret, Pine'ı görsel + parity için tut.
