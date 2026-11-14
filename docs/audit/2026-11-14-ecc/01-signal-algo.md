# 01 — Sinyal Algoritması İnceleme Raporu (2026-11-14)

> Kök: `C:/tmp/wt-ecc-audit` @ `81c2cf7` (origin/master). Salt okuma; kod/config değiştirilmedi.
> Bakış: smc-strategy-reviewer + quant-strategy-analyst. Kanıt biçimi: `path:line` (repo-relative), commit SHA, PR no.
> Ölçüt: operatör NİYETİ çerçeve; ölçülmüş NET edge filtre → her bileşen **KANITLI / KANITSIZ / ÇÜRÜTÜLMÜŞ**.
> Secret var: `.env.production`, `.env.production.long`, `.env.production.scalp` (`docker-compose.prod.yml:11-12,52-53,82-83`). Değerleri okunmadı.

---

## 1. Envanter (ne var, ne işe yarıyor, canlı mı/ölü mü/shadow mu)

Durum etiketleri mid bot (`configs/config.phase2_1k.yaml`) içindir; long/scalp farkları §2.4'te.

| Bileşen | Dosya | Rol | Prod durumu | Kanıt |
|---|---|---|---|---|
| SMC v2 durum makinesi | `engine/smc_v2/setup_state.py`, `engine/safe_orchestrator.py:2061-2313` | Aday → bölge → teyit → emir | **CANLI** | `config.phase2_1k.yaml:90-95` (`smc_version: v2`, 10 sembol, `smc_v2_shadow: false`) |
| LuxAlgo port | `engine/smc_v2/luxalgo.py` | BOS/CHoCH, OB, FVG, EQH/EQL, premium/discount, HTF bias, TP havuzu | **CANLI** (3 profilde) | `config.phase2_1k.yaml:188`, `config.phase2_long_1k.yaml:272`, `config.phase2_scalp_1k.yaml:277`; `38508f7` |
| Engulfing teyidi | `engine/smc_v2/confirmation.py` | Bölge içi engulfing close | **CANLI** (`require_confirmation` config'te yok → kod default `True`) | `safe_orchestrator.py:2114`; ADR-0009 |
| Yapısal SL | `engine/smc_v2/sl_calc.py` | anchor ∓ 0.5 ATR, min/max ATR | **CANLI** | `safe_orchestrator.py:3025-3048` |
| Wilder ATR | `engine/smc_v2/atr.py` | Gerçek ATR(14) | **CANLI** (yalnız mid) | `config.phase2_1k.yaml:108`; `safe_orchestrator.py:3009-3023` |
| Po3 kapısı | `engine/smc_v2/po3.py` | MANIPULATION fazında girişi beklet | **CANLI** (mid), long/scalp KAPALI | `config.phase2_1k.yaml:131`; `safe_orchestrator.py:2475-2489`; `a2f7890` |
| efloud v2 tetik yolu | `engine/smc_v2/triggers.py`, `zones.py`, `swing_anchor.py`, `tp_calc.py` | OB/BB → FVG/OTE/EQ_RETEST zone, origin swing anchor | **ÖLÜ** (lux açıkken bypass) | `safe_orchestrator.py:2659-2660` (`precomputed_candidates` → `generate_setup_candidates` atlanır) |
| MPA filtreleri | `engine/smc_v2/liquidity.py`, `v_recovery.py`, `bias_ledger.py` | Sweep/grab, V-recovery, BCEL | **KABLOSUZ** | `engine/` + `backend/` + `main.py`'de import yok (grep) |
| FVG geri çekilme gölgesi | `engine/smc_v2/fvg_entry.py` | Operatör setup'ı (4h bias, FVG limit) | **SHADOW** (log-only, `live` değeri yok) | `config.phase2_1k.yaml:216`; `safe_orchestrator.py:2333-2379`; PR #343 / `c05260c` |
| Fitil/temas gölgesi | `safe_orchestrator.py:2390-2447` | Intrabar dokunuş "would-enter" | **SHADOW** | `config.phase2_1k.yaml:211`; `271c96a` |
| v1 confluence motoru | `engine/signals.py`, `engine/confluence.py`, `engine/smc.py` | 0-100 skor, MARKET giriş | **HESAPLANIYOR, GİRİŞ SUSTURULMUŞ** (10/10 sembol v2 whitelist'te) | `safe_orchestrator.py:1355-1380` (her cycle), `:1486-1495` (mute), `:2449-2473`; `b2154c5` |
| v1 SMCEngine (smc.py) v2 için | `safe_orchestrator.py:1201-1216` | swings/OB/SFP/range/RSI | **ÖLÜ HESAP** (lux modda yalnız ölü efloud yoluna gider) | `:1275-1297` |
| Rejim dedektörü | `engine/regimes/__init__.py` | TRENDING/VOLATILE vb. | **Yalnız v1 kapısı** (susturulmuş) + açık pozisyon stop sıkılaştırma | `safe_orchestrator.py:1179`, `:1331-1339`, `:1468-1474` |
| Rejim ML | `engine/regimes/model.py`, `train.py` | Günlük BTC/ETH retrain | Advisory (`regime_ml_can_override_gate: false`) | `safe_orchestrator.py:1001-1019`; `config.phase2_1k.yaml` safety |
| Levels | `engine/levels.py` | MO/WO/Monday H-L, stacked zone | v1 bonus + senaryo; v2'ye etkisi yok | `signals.py:700-714`; `safe_orchestrator.py:1342-1347` |
| Senaryolar | `engine/scenarios.py` | 3 senaryo + STEP 7 piramit | Piramit **ETKİSİZ** (`max_pyramid_adds: 0`; borsa emir yolu yok) | `safe_orchestrator.py:1383-1397`, `:1890-1950`; `position_guard.py:418` |
| Intent | `engine/intent.py` | TP1 sonrası "zayıflık" %25 kısmi kapanış | **CANLI çıkış davranışı** (her iki yol) | `lifecycle.py:536-557`; `safe_orchestrator.py:1402-1408` |
| Adaptive | `engine/adaptive.py` | Self-tuning parametre | **ÖLÜ** (yalnız `scripts/regression_ledger.py:60` referansı) | grep |
| Universe | `engine/universe.py` | Dinamik sembol evreni | Kullanılıyor ama `mode: fixed`, `dynamic_top_n: 0` | `config.phase2_1k.yaml` symbols |
| TF profilleri | `data/timeframes.py:24-28` | scalp 5m/1h/4h · mid 15m/4h/12h · long 1h/8h/1d | **CANLI** | `config.phase2_1k.yaml:248` (`profile: mid`) |
| Kronos | `engine/ai/kronos.py` | Trade-open advisory | **KAPALI** (3 config) | `config.phase2_1k.yaml:353`; long `:170`; scalp `:182` |
| Makro sentiment | `engine/ai/sentiment.py` | LLM makro duygu | **Telemetri** (skora girmez) | `signals.py:685-688`; `1485f98` |
| AgentTeam | `engine/agents/` | LLM danışma | `enabled: true, gating: false` → v2'de yalnız açılış SONRASI async | `config.phase2_1k.yaml` agent_team; `safe_orchestrator.py:3281-3289` |
| Structure validation | `signals.py:357` | LLM yapı doğrulama | **KAPALI** | `config.phase2_1k.yaml:99-100` |
| Signal ledger | `engine/signal_ledger.py` | Edge ölçüm kaydı | **KAPALI** | `config.phase2_1k.yaml` signal_ledger |
| `pin_fvg_touch` ± Kronos A/B | — | Forward A/B | **Bu repoda YOK** (ayrı repo u2Algo-Trade) — DOĞRULANMADI | grep: 0 eşleşme |

---

## 2. Canlı gerçek (şu an prod'da fiilen çalışan davranış, kanıtlı)

### 2.1 Hangi config çalışıyor
- Config yolu `EFLOUD_CONFIG_PATH` env'inden okunur, yoksa `configs/config.phase2_1k.yaml` (`backend/bot_runner.py:47,189`; `main.py:588`). Env değeri secret dosyasında → **DOĞRULANMADI**; dolaylı kanıt `collab/STATUS.md:14` ve `CONTEXT.md:29`.
- Long ve scalp instance'ları 2026-11-07 itibarıyla durdurulmuş (`CONTEXT.md:48`, AUTOSTART=0 `docker-compose.prod.yml:43-45,73-75`). Bugünkü durumları **DOĞRULANMADI**.
- Kök `config.yaml` inert (`smc_version: v1`, `config.yaml:26`; `CONTEXT.md:29`).

### 2.2 Mid bot (15m / 4h / 12h) giriş akışı, adım adım
1. **Veri:** yalnız kapanmış barlar; oluşan son bar düşülür (`exchange/__init__.py:111-116`). `kline_limit: 750`.
2. **HTF bias:** 12h üzerinde LuxAlgo `swing_trend` (`swing_length: 50`) (`safe_orchestrator.py:1256-1258`). `UNDEF` → aday yok (`luxalgo.py:524-525`). **Slope/range fallback YOK, Daily (1d) filtresi YOK.**
3. **Tetik:** 15m'de swing (50) + internal (5) kırılımları, `kinds: [CHoCH, BOS]`, bias ile aynı yön, son `recency_bars: 168` bar (42 saat) içinde (`config:200,293`; `safe_orchestrator.py:1236-1237`; `luxalgo.py:527-535`).
4. **Aday filtresi:** kırılımın OB'si var ve mitige değil; premium/discount (LONG yalnız `ob.top ≤ equilibrium`) (`luxalgo.py:536-547`); `min_confluence: 1` etiket (`config:205`). **Not:** swing kırılımı otomatik `SWING_OB` etiketi alır (`luxalgo.py:477-478`), yani swing OB'leri bu kapıdan her zaman geçer; kapı fiilen yalnız internal kırılımları filtreler.
5. **Emit kapıları:** BT-23 yakın kenar > 12 ATR → düş (`config:141`); BT-25 fiyat uzak kenarın > 6 ATR ötesinde → düş (`config:168`) (`safe_orchestrator.py:2697-2781`). Dedup (aynı sembol+yön+trigger_ts aktifse) + sembol başına cap 6 (`setup_state.py:121-140`; `config:158`).
6. **Bekleme:** timeout 48 entry-bar = 12 saat (lux override `safe_orchestrator.py:2119-2120`; `config:207`). Bölgeye ilk girişte `IN_ZONE`, çıkışta `AWAITING_REENTRY`.
7. **Teyit:** bölge içinde kapanan engulfing; `confirm_last_bar_only: false` → tetikten beri TÜM barlar taranır, ilk eşleşen barın close'u giriş fiyatı olur (`confirmation.py:72-97`; `config:117`).
8. **Giriş blokları:** Po3 MANIPULATION, stale data, watch_only, balance_unavailable (`safe_orchestrator.py:1180-1192`, `:2263-2283`). **Rejim kapısı v2'ye uygulanmaz** (`:1179`, `:2848-2849`).
9. **Emir:** whitelist + shadow false (`:2876-2900`) → breaker (`:2903-2911`) → ATR = Wilder ATR(14) (`:3009-3012`) → SL = OB ucu − 0.5 ATR, < 2 ATR ise 2 ATR'ye genişlet, > 5 ATR ise RED (`sl_calc.py:58-78`; `config:412-413`) → TP = `luxalgo.tp_targets`, TP1 = `risk.min_rr: 1.8` × risk'i karşılayan en yakın aday, likidite hedefleri 0.15R içeride (`luxalgo.py:575-633`; `safe_orchestrator.py:3050-3059`) → sizing fixed $50 × 10x = $500 notional (`config:299,71`) → pos_guard (exposure 6x, aynı/ters yön) → pause guard → **MARKET emir** (`exchange/__init__.py:1152`) + entry drift guard %1 (`config:433`).
10. **v1:** `generate_signals` her cycle koşar, log üretir, **giriş yapmaz** (`safe_orchestrator.py:1486-1495`).
11. **Gölgeler:** `[fvg shadow]` ve `[touch shadow]` log satırları; emir yok.

### 2.3 Ölçülmüş canlı huni (2026-11-08 → 13)
`docs/superpowers/specs/2026-11-14-fvg-entry-shadow-design.md:13-25`: 215 setup → 77 dokunuş → 22 teyit → 9 emir. 11 teyit pos_guard (exposure > 6x), 2 teyit breaker reddi; Po3 25 kez blokladı.
**Exposure matematiği:** `6.0 × 403.55 = $2421` → $500'lük en fazla 4 eşzamanlı pozisyon. `max_open_positions: 10` (`config:272`) fiilen ulaşılamaz (`config:375,403`; `position_guard.py:270-281`). Huninin en büyük kaybı bu.

### 2.4 Long / scalp profilleri (aynı lux yolu, farklı parametre)
| Parametre | mid | long | scalp | Kanıt |
|---|---|---|---|---|
| ATR | Wilder ATR(14) | `max(%1 fiyat, zone genişliği)` proxy | proxy | `safe_orchestrator.py:2934-2936`; `v2_use_real_atr` yalnız mid |
| min/max SL ATR | 2.0 / 5.0 | 0.5 / 5.0 | 0.3 / 3.0 | long `:209-210`, scalp `:218-219` |
| TP1 min_rr | 1.8 | 2.2 | 1.0 | long `:127`, scalp `:133` |
| Po3 / BT-23 / BT-25 | açık / 12 / 6 | kapalı / kapalı / kapalı | kapalı / kapalı / kapalı | anahtar yok → `safe_orchestrator.py:2483,2698,2727-2730` |
| Cap / recency | 6 / 168 | 3 / 40 | 3 / 40 | `main.py:85` default; long `:129`, scalp `:135` |
Proxy ATR ile long/scalp'ta SL tabanı fiyatın %0.5'i (long) / %0.3'ü (scalp); BT-22'nin düzelttiği "max_sl_atr hiç bağlamıyor" kusuru bu iki profilde sürüyor (`safe_orchestrator.py:3004-3008` bunu bilinçli bırakmış).

---

## 3. Çelişkiler

| # | Çelişki | Kanıt A | Kanıt B | Etki | Önerilen çözüm |
|---|---|---|---|---|---|
| C1 | Bölge aşım toleransı 2.0 deniyor, canlı 6.0 | `AGENTS.md:22`; eski CLAUDE.md başlığı (`docs/history/claude-md-status-archive.md:10`) "0.5→2.0" | `config.phase2_1k.yaml:168` = 6.0; `ad41004` (2.0→6.0) | Yanlış gate varsayımıyla analiz | AGENTS.md'yi 6.0'a düzelt (doc PR) |
| C2 | Config yorumu "0.5 = yarım ATR tolerans" | `config.phase2_1k.yaml:166-167` | aynı dosya `:168` = 6.0 | Okuyanı yanıltır | Yorum temizliği (config PR, davranış değişmez) |
| C3 | BT-23 yorumu "6.0 seçildi" | `config:132-140` | `config:141` = 12.0 (`eb01f40`, ölçümsüz) | 6.0 kanıtı 12.0'ı desteklemez | Yorumda 12.0'ın ölçümsüz olduğunu yaz |
| C4 | Pullback timeout yorumları 8→24→12 | `config:143-157`, `:151` = 12 | `safe_orchestrator.py:2119-2120` lux override → `config:207` = 48 | `smc_v2.pullback_timeout_bars` lux modda inert | Yoruma "lux açıkken 48 geçerli" ekle |
| C5 | `risk.min_rr` "legacy, kullanılmaz" | `config:273` | `safe_orchestrator.py:3058` (lux TP1 kapısı), `:2368` (fvg shadow) | Canlı TP kapısı yanlış etiketli | Yorum: "v2 lux TP1 kapısı" |
| C6 | `allow_volatile_entries` "volatil girişler açık" | `config:380-385`; `AGENTS.md:21` | v2'ye rejim kapısı yok (`safe_orchestrator.py:1179,2848-2849`); v1 susturulmuş | Ayar fiilen etkisiz | Doc'larda "yalnız v1; v2'de inert" |
| C7 | `risk.min_confluence: 50` "frekans artırmak için" | `config:282`; `CLAUDE.md:63`; `scripts/ci/agents/smc-strategy-reviewer.md:25-27,40` | v1 susturulmuş (`safe_orchestrator.py:1486`); canlı kapı `luxalgo.min_confluence: 1` (`config:205`) | Reviewer yanlış kapıyı koruyor | Doc + reviewer prompt güncelle |
| C8 | MPA "HİÇBİRİ kablolanmadı" | `config.yaml:42-48`; `po3.py:19-21` ("false varsayılan → canlı birebir") | Po3 kablolu (`safe_orchestrator.py:2475-2489`, `a2f7890`) ve mid'de açık (`config:131`) | Po3 ölçümsüz canlı kapı | Yorumları düzelt; Po3'ü §5 KANITSIZ listesine al |
| C9 | "limit emir" | `AGENTS.md:14-16`; `README.md:30`; `safe_orchestrator.py:1491` log metni | `exchange/__init__.py:1152` MARKET | Maliyet modeli (taker) yanlış anlaşılır | Doc'u "MARKET (taker)" yap |
| C10 | Lux anchor "Strong Low/High ile birleştirilir" | `luxalgo.py:518-519` docstring | `luxalgo.py:548` yalnız OB ucu (`6a8c0cf`) | Pine/analiz hatası riski | Docstring düzelt (kod PR, davranışsız) |
| C11 | `_place_v2_entry_order` "ATR proxy, boş HTF → RR_PROJECTION" | `safe_orchestrator.py:2861-2866` | mid: gerçek ATR (`:3009`), lux TP (`:3052`) | Bayat docstring | İşaretle |
| C12 | PINE_SPEC "V2 sadece CHoCH, BOS göz ardı" | `pine/PINE_SPEC.md:19,73,156` | `658a905`; `config:200` `[CHoCH, BOS]`; `triggers.py:232-237` | Pine portu yanlış referans | Banner + düzeltme |
| C13 | PINE_SPEC "v2 HTF fallback v1 ile aynı" | `PINE_SPEC.md:98-108` | `triggers.py:228-229` ve `luxalgo.py:524-525` UNDEF → [] | v2'de fallback yok | §3'ü düzelt |
| C14 | PINE_SPEC durum makinesi "IN_ZONE yapışkan, timeout 8, cap 3" | `PINE_SPEC.md:112-150,292` | `setup_state.py:34` (AWAITING_REENTRY), timeout 48, cap 6 | Bayat spec | §4'ü TARİHSEL işaretle |
| C15 | PINE_SPEC başlığı "shadow mode" | `PINE_SPEC.md:3` | `config:95` LIVE | — | Başlık güncelle |
| C16 | TF zinciri yorumları | `docker-compose.prod.yml:43` (long "1h/8h/1w"), `:73` (scalp "5m/1h/12h"); `config.phase2_scalp_1k.yaml:2,4` ("V1 mid 15m/1h/4h") | `data/timeframes.py:24-28` | Yanlış TF varsayımı | Yorumları PROFILES'a hizala |
| C17 | "Daily (1d) makro filter ortaktır" | `CLAUDE.md:59` | v2 yolunda `df_daily` kullanılmaz (`safe_orchestrator.py:1343,1361` yalnız levels/v1) | Canlıda günlük filtre yok | CLAUDE.md düzelt |
| C18 | Exposure 6.0 "10×$500 desteklemek için" | `config:399-403` ($1363 varsayımı) | `config:375` bakiye 403.55 → ~4 pozisyon; 11 exposure reddi (spec `:22`) | Huninin ana kaybı | Operatöre sun (risk kararı) |
| C19 | "backtest modülü repo'dan kaldırıldı" | `config.phase2_1k.yaml:185`, long `:269`, scalp `:274` | `backtest/` mevcut, #335 / `7ac1f16` | Gate'in çalıştırılamaz sanılması | Yorum güncelle |
| C20 | İki farklı NET maliyet modeli | `fvg_entry.py:26` (%0.07 RT, maker giriş) | `config` backtest %0.04/bacak taker + funding; canlı giriş MARKET | FVG gölge NET'i canlı v2 NET'iyle doğrudan kıyaslanamaz | Rapor aracında normalize et |
| C21 | Scalp "Fibonacci-aware TP/SL v3" | `config.phase2_scalp_1k.yaml:2` | `range_tp1_fib`/`min_tp_gap_r` yalnız v1 (`safe_orchestrator.py:1368-1370`), v1 susturulmuş, TP lux | Özellik inert | Başlık yorumunu düzelt |
| C22 | efloud yolu anahtarları "operatör onayı" ile aktif gibi | `config:115,124,176-178` (`anchor_time_axis`, `ob_bb_entry`, `ob_bb_zone_atr_pad`, `origin_swing_lookback`, `ote_zone_entry`) | lux bypass `safe_orchestrator.py:2659-2660` | Ölü anahtarlar canlı sanılıyor | Blok başına "lux açıkken inert" notu |
| C23 | Journal yol/skor ataması yok | `safe_orchestrator.py:689-692` (`htf_bias=""`, `confluence_score=0`) | BT-22 kanıtı "this bot, not this path" (`:2989-2997`) | Setup bazında edge ölçülemez | Journal'a `engine_path`/lux tag (kod PR, gate'li) |

---

## 4. Bayat / yanlış dokümantasyon

| Doküman:satır | Bayat ifade | Gerçek |
|---|---|---|
| `CLAUDE.md:17` | "hem INDIKATÖR hem STRATEGY" | Ürün yalnız indicator (ADR-0005, aynı dosya `:3`) |
| `CLAUDE.md:20,29,39` | Pine = `pine/efloud_signals.pine` / `efloud_strategy.pine`, "SENKRON" | Canlı baseline `pine/efloud_lab.pine` ("u2algo Price Action", `:7`) + `pine/lab/*`; PINE_SPEC §20 |
| `CLAUDE.md:59` | Daily makro filtre ortak; "4h/1h/15m tarihsel" | v2'de daily yok; mid HTF 12h |
| `CLAUDE.md:60` | HTF Bias Fallback (signals.py:308-328) | Yalnız v1 (susturulmuş); satırlar artık `signals.py:515-541`; v2 lux'ta fallback yok |
| `CLAUDE.md:61-62` | Swing 5, OB 5 mum + 1.5×SMA | v1 SMCEngine (`smc.py:109,195-204`); canlı lux: swing 50 / internal 5, OB = pivot→kırılım aralığındaki uç mum (`luxalgo.py:338-351`) |
| `CLAUDE.md:63` | Confluence 55/50 | v1 kapısı; canlı kapı lux `min_confluence: 1` etiket |
| `CLAUDE.md:64-67` | SL = 20 mum dibi + 0.5/0.75 ATR, %0.1 clamp; TP1 min R:R 1.5 | Canlı: OB ucu − 0.5 ATR, min 2 / max 5 ATR (RED); TP1 ≥ 1.8R lux havuzu |
| `AGENTS.md:11-22` | Tarih 2026-10-02; "limit emir"; overshoot 2.0; LuxAlgo yok | MARKET, 6.0, lux modu 2026-11-01'den beri, Po3, FVG/touch gölgeleri |
| `README.md:28-30` | "OB/breaker zone + OTE → limit entry; SL beyond impulse swing" | Zone = lux OB (OTE yalnız etiket); MARKET; SL OB ucu |
| `pine/PINE_SPEC.md:1-14, §0-§5, §11 (292)` | efloud v2 (pre-LuxAlgo), CHoCH-only, shadow, timeout 8 | §20 (lux baseline) asıl canlı; üst bölümler TARİHSEL |
| `config.yaml:42-48` | MPA hiçbiri kablolanmadı | Po3 kablolu ve mid'de açık |
| `engine/smc_v2/po3.py:19-21` | "false varsayılan → canlı birebir korunur" | mid'de `true` |
| `collab/STATUS.md:10-16` | master `3acea5c`, 2026-11-07 | Bugün `81c2cf7`; lux/fvg/touch gölgeleri ve Po3 satırı yok |
| `skills/luxalgo-smc/SKILL.md:58-71` | Doğru ama eksik | Engulfing teyidi, MARKET, Po3, BT-25=6.0, SWING_OB'nin min_confluence'ı otomatik geçmesi, long/scalp proxy ATR eksik |
| `CONTEXT.md:27` | "Shadow" = yalnız `smc_v2_shadow` | `fvg_entry: shadow`, `touch_entry: shadow` yeni anlamlar |

---

## 5. Trade mantığı / setup modelleri

Edge kanıtı kaynakları: `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md` (60g, 10 sembol, NET-cost, #277), `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md` (41g, #335), FVG spec + `collab/log/claude-code.md:329`, ADR-0009, `config.phase2_1k.yaml` BT yorumları.

### S1 — LuxAlgo OB retest + engulfing (CANLI, 3 profil)
- **Tetik:** 15m swing/internal CHoCH veya BOS, 12h lux swing trend yönünde, ≤168 bar.
- **Filtre:** OB mitige değil; premium/discount; ≥1 etiket (SWING_OB/OTE/EQ/FVG/SWEEP); BT-23 ≤12 ATR; BT-25 ≤6 ATR; cap 6; Po3.
- **Giriş:** bölge içi engulfing close → o close fiyatından MARKET (drift ≤%1).
- **SL:** OB ucu ∓ 0.5 ATR; < 2 ATR → genişlet; > 5 ATR → RED.
- **TP1/TP2:** en yakın ≥1.8R lux adayı (karşı OB, karşı FVG, EQH/EQL, swing pivot −0.15R, equilibrium, trailing extreme); TP2 sonraki aday veya range fib 1.272/1.618/2.618. TP1'de %50 + BE (`lifecycle`), TP1 sonrası intent zayıflık çıkışları.
- **Invalidation:** 48 bar timeout; OB mitige (yeni aday üretilmez); SL.
- **Edge:** **ÇÜRÜTÜLMÜŞ** — 60g NET −0.30 R/işlem, PF 0.65, n=217, IS −0.48 / OOS +0.03 (counterfactual `:14-17,42`); 41g backtest NET −$181.9, PF 0.69, 8/10 sembol PF<1 (parity `:21-24`). Brüt ≈ 0 (−0.03R); maliyet ~0.27R (dar SL, medyan %0.72). Canlıya NET-cost ölçümsüz alındı (`config:185`; `38508f7`).

### S1 alt bileşenleri
| Bileşen | Durum | Edge |
|---|---|---|
| 12h trend, premium/discount, recency, confluence kapıları | CANLI | **KANITLI (koruyucu):** elenen kategoriler −0.17…−0.32R (counterfactual `:11-13,43-50`) |
| Engulfing teyidi | CANLI | Lux içinde **göreli KANITLI** (P1 −0.30 vs P2 limit −0.75); mutlak değer negatif. ADR-0009 PF 1.41 (n=685) pre-LuxAlgo motora ait, aktarılamaz |
| `min_sl_atr: 2.0` | CANLI | **KANITLI (göreli):** R/trade −0.363 → −0.257 (`config:412`, BT-sweep5), yine negatif |
| `max_sl_atr: 5.0` + gerçek ATR | CANLI (mid) | **KANITLI:** 336 journal işlemi, PnL +403.74 → +595.66 (`safe_orchestrator.py:2975-2985`); yol-agnostik, pre-LuxAlgo |
| BT-23 = 6.0 | — | KANITLI (replay `config:132-139`); **12.0 KANITSIZ** (`eb01f40`) |
| BT-25 = 6.0 | CANLI | **KANITSIZ** (`ad41004` gerekçesi frekans) |
| Cap 6, timeout 12→48, recency 168 | CANLI | **KANITSIZ** (frekans gerekçeli: `4417e90`, `ad41004`) |
| BOS setup'ları | CANLI | **KANITSIZ** (`658a905`) |
| Po3 kapısı | CANLI (mid) | **KANITSIZ** (Efloud notları, backtest yok); 5 günde 25 blok |
| `allow_volatile_entries` | v2'de inert | — |

### S2 — efloud v2 tetik yolu (OB/BB → FVG/OTE/EQ_RETEST, origin swing anchor)
- Tetik: v1 SMCEngine CHoCH/BOS; zone kırılımı yapan OB/BB (+0.5 ATR pad) yoksa FVG/OTE; RSI/SFP etiketleri (`triggers.py:165-407`).
- **Durum: ÖLÜ** (lux 3 profilde açık → bypass). Geri dönüş tek satır (`luxalgo.enabled: false`).
- **Edge: ÇÜRÜTÜLMÜŞ/zayıf** — BT-sweep5 v2 R/trade −0.257 (`config:412`); ADR-0009 PF 1.41 eski motor, NET değil.

### S3 — v1 confluence MARKET girişi
- Tetik: entry-TF CHoCH/BOS bias yönünde (BOS recency/2); skor = 25 bias (filtre gereği her zaman verilir → M2 over-counting) + 20 MTF CHoCH + 15 HTF FVG + 10/5/3 OB + 10 OTE + 10 SFP + 5 PD + 5 dev, sonra cap SONRASI daily ±5, level +5/+8 (H1) (`confluence.py:26-46`; `signals.py:690-714`).
- SL: son swing ∓ buffer, 20-bar ucuna clamp, %0.1 min; TP: HTF FVG/likidite veya 1.272/min_rr clamp; TP2 fib_ext/2.618 (`signals.py:764-928`).
- HTF fallback: 40-bar slope ±%2 → range discount/premium → skip (`signals.py:515-541`).
- **Durum: SUSTURULMUŞ** (her cycle hesaplanır). **Edge: ÇÜRÜTÜLMÜŞ** — memory'deki Wave-1/Wave-2 NO-GO kayıtları repoda DOĞRULANMADI; mute kararı operatör niyeti (`b2154c5`).

### S4 — v1 range-deviation oyunu
- `has_dev` → TP1 range fib, TP2 karşı uç. `dev_bull/dev_bear` pratikte hiç tetiklenmez (`PINE_SPEC.md:453`). **ÖLÜ + susturulmuş.**

### S5 — FVG geri çekilme gölgesi (operatör setup'ı, SHADOW, mid)
- Bias: 4h lux swing trend (`df_mtf`, `safe_orchestrator.py:2363`). Tetik: bias yönlü CHoCH/BOS'un OB'sinden sonra, kırılım+2 bar içinde oluşan mitige olmamış FVG (`fvg_entry.py:58-64`).
- Giriş: LONG FVG üst kenarı / SHORT alt kenarı limit (`:118`); SL `calc_sl` OB ucu çapalı (`:121-124`); TP1 ≥ min_rr karşı OB veya BB (mitige ters OB) (`:67-79`); TP2 TP1+0.5R ötesindeki EQH/EQL/pivot (`:82-95`). Timeout 48, `ran_away` iptali.
- **Fark (S1'e göre):** premium/discount yok, min_confluence yok, Po3 yok, teyit mumu yok, 4h bias. Yalnız lux açıkken koşar (`safe_orchestrator.py:1253-1273`).
- **Edge: KANITSIZ** — offline 45g/10 sembol: 85 kapanış, win %30.6, NET ≈ +0.00R (`collab/log/claude-code.md:329`). Go-live kapısı: ≥30 forward kapanış, NET>0, canlı v2'den iyi (spec `:104-109`).

### S6 — Fitil/temas gölgesi (SHADOW, mid)
- Bekleyen aday bölgesine WS fitili değince aday başına bir `would-enter` (`safe_orchestrator.py:2390-2447`). **Edge: KANITSIZ**; counterfactual P2 (teyitsiz limit) −0.75R/−0.04R → zayıf.

### S7 — Mitige OB (breaker benzeri) retest
- Yalnız araştırma kategorisi: n=30, +0.24R, IS +0.23 / OOS +0.25, 5/10 sembol (counterfactual `:18-20`). Kodda giriş yolu yok (FVG gölgesi TP1'de BB kullanıyor). **KANITSIZ (sınırda)** — takip ölçümü adayı.

### S8 — `pin_fvg_touch` ± Kronos forward A/B
- Bu repoda yok (grep 0). Memory'ye göre ayrı repo u2Algo-Trade, testnet, 0 forward kapanış → **DOĞRULANMADI / KANITSIZ**. Kronos bu repoda tüm botlarda KAPALI.

### S9 — Pine lab (u2algo Price Action)
- `pine/efloud_lab.pine` + `pine/lab/core.pine`: S1 paritesi (minConfluence 1, recency 168, overshoot 6.0, min/max SL 2/5, minRr 1.8, Po3) (`core.pine:26-41`) + geliştirme toggle'ları (`counterBias`, `macroBias`, `core.pine:511`). Görüntü/backtest; emir yok. Parite kapısı ≥%95 (`PINE_SPEC.md:630`).

---

## 6. ECC revizyon adayları

Doküman PR'ı (bu tur canlıya gidebilecek, davranış değiştirmez):
1. **`CLAUDE.md:57-67` "Efloud Çekirdek Mantığı"**: iki alt başlığa böl — "Canlı motor: SMC v2 LuxAlgo modu" (S1 parametreleri, config referanslı, sayı yerine `config:satır` linki) ve "v1 confluence (susturulmuş; Pine V1 portu için tarihsel)". Satır referanslarını düzelt (`signals.py:515-541`), Daily filtre cümlesini kaldır.
2. **`CLAUDE.md:17,20,29,39`**: Pine hedefini ADR-0005'e hizala — ürün `pine/efloud_lab.pine` + `pine/lab/*`; strategy yalnız araştırma; "SENKRON" kuralı lab head/tail/core için.
3. **`AGENTS.md:11-22`**: "Güncel Algoritma Durumu"nu kaldırıp `collab/STATUS.md`'ye yönlendir veya düzelt: LuxAlgo modu, MARKET, overshoot 6.0, Po3, rejim kapısının v2'de olmadığı, FVG/touch gölgeleri.
4. **`README.md:28-30`**: giriş akışını düzelt (lux OB, engulfing, MARKET, SL OB ucu, TP lux havuzu).
5. **`pine/PINE_SPEC.md`**: üstte banner — "§0-§14 TARİHSEL (pre-LuxAlgo efloud v2). Canlı baseline §20." BOS (§0/§2.2/§5) ve HTF fallback (§3) satırlarına `658a905` / UNDEF→[] düzeltme notu.
6. **`scripts/ci/agents/smc-strategy-reviewer.md:25-40`**: "confluence floor 55/50" yerine canlı kapı seti (lux `min_confluence`, premium/discount, `risk.min_rr` = TP1 kapısı, BT-23/25, Po3, min/max SL ATR); yeni kontrol maddesi: "değişiklik `setup_state.add` dedup/re-emit davranışını etkiliyor mu?" ve "rejim kapısı v2'ye uygulanmıyor".
7. **`skills/luxalgo-smc/SKILL.md`**: "From concepts to engine setups" bölümüne teyit/emir/SL kuralları, Po3, BT-25, SWING_OB otomatik geçiş, profil farkları (§2.4 tablosu).
8. **`CONTEXT.md`**: "Shadow" girdisini genişlet (`fvg_entry`, `touch_entry`); yeni terimler: "LuxAlgo modu", "efloud tetik yolu (ölü)", "v1 mute".
9. **`collab/STATUS.md`**: "Canlı config (mid)" satırına etkin kapı seti + gölgeler; master SHA güncelle.
10. **Yeni kural (rules)**: "Canlı davranış iddiası yalnız `config:satır` + kod yolu ile yazılır; serbest sayı (2.0, 55, limit) yasak" — doc drift'in kök nedeni elle kopyalanan sayılar.

Config yorum PR'ı (ayrı, operatör onayı; davranış değişmez ama config dosyası): C2, C3, C4, C5, C19, C21, C22, `config.yaml:42-48` (C8), long/scalp/compose TF yorumları (C16).

Trade mantığı ÖNERİ listesi (yalnız öneri; NET-cost backtest + risk-ops + operatör onayı gerekir):
- R1: `max_total_exposure` / `fixed_position_usdt` / `max_open_positions` uyumu (C18) — risk kararı, sunulacak üç yorum: (a) exposure'u bakiyeye göre yükselt, (b) notional'ı düşür, (c) bilinçli olarak 4 pozisyonda bırak ve `max_open_positions`'ı 4 yap.
- R2: Maliyet/risk oranı (dar SL + taker) — counterfactual'ın önerdiği maker çıkış ve SL genişliği senaryoları.
- R3: `confirm_last_bar_only: true` (stale teyit; §7 Q1) — kod hazır, gate bekliyor.
- R4: Lux journal etiketleri (C23) — setup bazlı edge ölçümü için ön koşul.
- R5: Ölçümsüz gevşetmeleri (BT-23=12, BT-25=6, cap 6, recency 168, BOS) NET-cost ile tek tek doğrula; kanıt çıkmazsa ölçülmüş değerlere dönüş operatöre sunulsun.
- R6: Long/scalp'ta `v2_use_real_atr` (BT-22 kanıtı mid'e özgü) — profil başına ayrı backtest.

---

## 7. Riskler ve açık sorular

- **Q1 (kod-okuma çıkarımı, canlı log ile DOĞRULANMADI): CONFIRMED sonrası aynı kırılımın yeniden emit edilmesi.** `_advance_setup_state_tick` adayı `CONFIRMED` yapıp `_place_v2_entry_order`'ı çağırır (`safe_orchestrator.py:2276-2283`); emir pos_guard/breaker ile reddedilse de durum CONFIRMED kalır. Aynı cycle'da emit fazı (`:1275`) dedup'ı yalnız aktif durumlara karşı yapar (`setup_state.py:121-126`), recency 168 > timeout 48 olduğundan aynı kırılım yeni aday olarak geri gelir. `confirm_last_bar_only: false` iken teyit tetikten beri tüm barları taradığı için eski engulfing anında yeniden "teyit" verir ve emir, eski close fiyatıyla yeniden denenir. Sonuç: reddedilen setup her ~2 cycle'da tekrar dener; pozisyon TP ile kapanırsa (OB mitige değilse) aynı setup bayat giriş fiyatıyla yeniden açılabilir (yalnız %1 drift guard korur). 11 exposure reddinin kaçının tekrar olduğu bilinmiyor. Önce reprodüksiyon testi (TDD) önerilir.
- **Q2:** Canlı motor NET negatif (S1). Operatör niyeti (çok giriş, chart zone'larında giriş) ile kanıt (kapılar koruyucu, maliyet edge'i yiyor) çatışıyor; son gevşetmelerin (12.0, 6.0, 48, cap 6) hepsi frekans gerekçeli ve ölçümsüz.
- **Q3:** v1 her cycle tam hesaplanıyor, v2 için efloud SMCEngine hesapları da ölü yola gidiyor (`safe_orchestrator.py:1201-1216,1355-1380`) — gecikme/CPU maliyeti ölçülmedi.
- **Q4:** HTF lux bias 12h × `swing_length 50` = 25 günlük pivot onayı; bias geç dönüyor. Counterfactual'da "12h trende ters" kategorisi −0.31R, yani gevşetme kanıtı yok; FVG gölgesi 4h bias'ı ölçecek.
- **Q5:** Po3 kapısı ölçümsüz ama canlı; 5 günde 25 blok. Etkisi (koruyucu mu, fırsat kaybı mı) bilinmiyor.
- **Q6:** `swing_length 50` + 750-bar pencere: ATR(200) tohumlama ve ilk pivotun kaybı Python/Pine sapması yaratıyor (`PINE_SPEC.md:645,654`). Canlı TP havuzunda eksik seviye olabilir.
- **Q7:** Long/scalp instance'ları yeniden başlatılırsa mid'de düzeltilmiş kusurlarla (proxy ATR, BT-23/25 yok) canlıya çıkar.
- **Q8:** EFLOUD_CONFIG_PATH değeri secret dosyada; "mid = phase2_1k" iddiası dolaylı kanıtlı.
- **Q9:** FVG gölgesinin NET tanımı (%0.07 maker) canlı v2'nin taker + funding maliyetinden iyimser; go-live karşılaştırması aynı maliyet modeliyle yapılmalı (C20).

---

## 8. Fable'a özet

1. **Canlıda çalışan tek giriş modeli S1:** SMC v2 + LuxAlgo modu (12h lux bias → 15m CHoCH/BOS → OB retest → engulfing → MARKET). 10/10 sembol v2'de; v1 confluence motoru her cycle hesaplanıyor ama girişi susturulmuş (`safe_orchestrator.py:1486-1495`).
2. **S1'in NET edge'i ÇÜRÜTÜLMÜŞ:** 60g −0.30 R/işlem (PF 0.65, n=217); 41g backtest PF 0.69, NET −$181.9. Brüt ≈ 0; maliyet (dar SL + taker) edge'i yiyor. Lux modu NET-cost ölçümü olmadan canlıya alındı (`config:185`).
3. **Kapılar koruyucu (KANITLI); son gevşetmeler ölçümsüz (KANITSIZ):** BT-23 12.0, BT-25 6.0, timeout 48, cap 6, recency 168, BOS, Po3.
4. **Huninin ana kaybı exposure:** 6.0 × $403 bakiye → ~4 eşzamanlı $500 pozisyon; 22 teyidin 11'i bu yüzden reddedildi. `max_open_positions: 10` fiilen ulaşılamaz (C18, risk kararı).
5. **Etkisiz ama aktif sanılan ayarlar:** `risk.min_confluence 50`, `allow_volatile_entries`, `smc_v2.pullback_timeout_bars 12`, efloud yolu anahtarları (`ob_bb_entry`, `ote_zone_entry`, `ob_bb_zone_atr_pad`...); `risk.min_rr` "legacy" etiketli ama canlı TP1 kapısı.
6. **Doküman drift'i yaygın:** CLAUDE.md "Çekirdek Mantık" (v1 tarif ediyor), AGENTS.md (limit, overshoot 2.0), README (limit), PINE_SPEC §0-§14 (CHoCH-only, shadow, timeout 8), `config.yaml` MPA yorumu (Po3 artık kablolu). Bu tur doküman PR'ının kapsamı §6 madde 1-9.
7. **Gölgeler:** FVG gölgesi (operatör setup'ı, 4h bias, FVG limit) offline ≈ +0.00R (n=85), KANITSIZ; maliyet modeli canlıdan iyimser (C20). Touch gölgesi KANITSIZ.
8. **Olası hata (DOĞRULANMADI, test gerekli):** CONFIRMED sonrası aynı kırılım yeniden emit ediliyor ve bayat engulfing ile tekrar "teyit" alıyor (§7 Q1). Reddedilen setup'lar tekrar deneniyor; TP sonrası bayat fiyatla yeniden giriş mümkün.
9. **Profil ayrışması:** long/scalp gerçek ATR, Po3, BT-23/25 olmadan aynı lux yolunu koşar; yeniden başlatılırlarsa mid'de düzeltilmiş kusurlarla çıkarlar.
10. **`pin_fvg_touch` ± Kronos A/B bu repoda yok**; Kronos efloud-bot'ta tüm botlarda kapalı.
