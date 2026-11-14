# 02 — Risk, Güvenlik ve Execution İnceleme Raporu (2026-11-14)

- **Kök:** `C:/tmp/wt-ecc-audit` @ `81c2cf7` (origin/master). Salt okuma; hiçbir kod/config değişmedi.
- **Bakış:** risk-safety-auditor + fund-manager-overseer. Ölçüt: operatör NİYETİ çerçeve, ölçülmüş NET edge filtre.
- **Etiketler:** KANITLI / KANITSIZ / ÇÜRÜTÜLMÜŞ (edge) · DOĞRULANMADI (canlıda gözlenmedi, yalnız kod/config okundu) · PLAUSIBLE (kodla tutarlı, reprodüksiyon testi yok).
- **Secret:** `deploy/.env.production*` (VPS'te; repoda yalnız `*.example`, değerleri okunmadı). Rapor hiçbir anahtar/IP+kimlik bilgisi içermez.

---

## 1. Envanter (ne var, ne işe yarıyor, canlı mı/ölü mü/shadow mu)

### 1.1 Güvenlik katmanı (`engine/safety/`)

| Bileşen | Dosya | İş | Canlı (V1 mid) durumu |
|---|---|---|---|
| CircuitBreaker | `engine/safety/breaker.py:69-372` | Günlük kayıp (TRIP → gece yarısı), haftalık DD (HALT), ardışık kayıp (TRIP 120 dk), acil bakiye (HALT) | **CANLI**; acil bakiye kolu **fiilen KAPALI** (eşik 0 → `balance < 0` hiç doğru olmaz, `breaker.py:284-288`) |
| Breaker restore | `breaker.py:393-453`, `backend/bot_runner.py:364-379` | HALT/TRIP durumu restart'ta dosyadan + DB mirror'dan geri yüklenir | CANLI |
| PositionGuard | `engine/safety/position_guard.py:209-359` | max_open, size/margin cap, reserve, toplam exposure, duplicate/opposite yön, min/max SL-ATR, SL<likidasyon (×0.9), %5 risk hard cap | CANLI (v2 yolunda da çağrılıyor, `safe_orchestrator.py:3132-3146`) |
| Reverse-on-profit | `position_guard.py:361-404` + `safe_orchestrator.py:1699-1760, 839-937` | Karşı yön sinyalinde, karda ≥%0.2 ise kapat+ters aç; partial sonrası asla | **v1-only → canlıda ÖLÜ** (v1 tüm canlı sembollerde susturulu; v2 bunu bilinçli kopyalamadı, `safe_orchestrator.py:2867-2868`). Canlı davranış: karşı yön = **RED** (`OPPOSITE_DIRECTION_EXISTS`, `position_guard.py:299-306`) |
| Pause gate | `position_guard.py:62-207` | `EFLOUD_PAUSE_NEW_ENTRIES` > config; yalnız yeni girişi durdurur | CANLI, değer `false` |
| Max-hold force close | `position_guard.py:470-500`, `safe_orchestrator.py:1444-1460` | Süre aşımında borsa+lojik kapanış | **KAPALI** (`max_holding_hours: 0`, `59c32f3`); yerine bilgi amaçlı `HOLD_AGE` (`safe_orchestrator.py:2805-2828`, `hold_alert_hours: 24`) |
| OrphanProtector | `engine/safety/orphan_protection.py:81-252` | Borsada olup lokal takipte olmayan + SL'siz pozisyona `closePosition` STOP_MARKET (entry'den %2) | **CANLI** `place_missing_sl`, `require_tp_present:false`, döngü başı 1 (`config.phase2_1k.yaml:459-465`); reconcile'da `orders_fetch_ok and algo_fetch_ok` kapısı arkasında (`exchange/__init__.py:1411-1435`) |
| MainnetGuard | `engine/safety/guard.py:201-237` + `main.py:validate_config` | `EFLOUD_ALLOW_MAINNET=1` zorunlu | CANLI (çift kilit) |
| Retry/RateLimiter/stale-data | `guard.py:32-194` | Backoff, token bucket, kline tazelik | CANLI |
| StateStore | `engine/safety/state.py:29-70` | Atomik JSON (pid+tid tmp) | CANLI |
| RuntimeState | `engine/safety/runtime_state.py` | healthz + crash-loop (3 crash/30 dk) | CANLI (`bot_runner.py:132-175`) |
| `cleanup_orphan_hedges` | `position_guard.py:503-521` | Hedge orphan tespiti | Fiilen ölü (hedge senaryosu açılmıyor; yalnız uyarı) |
| Volatil "tighten stops" | `safe_orchestrator.py:1328-1338` | VOLATILE/REVERSAL'da TP1 sonrası lokal SL'yi BE±%0.5'e çeker | **ÖLÜ KOD**: koşul `not sl_moved_to_be and tp1_hit`; lifecycle TP1'de ikisini birlikte set ediyor (`engine/lifecycle.py:409-413`) → hiç tetiklenmez. İşaretle, silme. |

### 1.2 Risk / sizing

| Bileşen | Dosya | Durum |
|---|---|---|
| `calc_fixed_position_size` | `risk/__init__.py:51-73` | **CANLI** (`position_size_calculation: fixed`, $50 × 10x = $500 notional) |
| `calc_position_size` (risk-%) | `risk/__init__.py:8-48` | Canlıda kullanılmıyor (legacy) |
| `CustomRiskCalculator` (reverse_from_risk) | `engine/risk/custom_calculator.py` | Ölü (config'te seçili değil; yalnız v1 dalı `safe_orchestrator.py:1598-1610`) |
| Korelasyon sizing | `engine/risk/correlation.py` | **ÖLÜ** — yalnız testler (`backend/tests/test_correlation_sizing.py`); canlı yola bağlı değil |
| EV slot allocation | `engine/allocation.py` | **ÖLÜ** — docstring "wiring ayrı adım" (`allocation.py:8-10`); hiçbir import yok |
| `_sizing_balance` (available) | `safe_orchestrator.py:114-166` | Yalnız v1/legacy dalında; **fixed modda inert** |
| Leblep limitleri | `safe_orchestrator.py:1021-1077` | İnert (`bot_v2.enabled`/`leblep_enabled` yok/false); yalnız v1 dalı |

### 1.3 Execution (`exchange/__init__.py`)

| Bileşen | Satır | Durum |
|---|---|---|
| Market giriş | `1150-1156` | CANLI — giriş **MARKET** emir (limit değil) |
| Entry-drift guard (fail-closed) | `1086-1106`, `536-566` | CANLI, `max_entry_drift_pct: 1.0` |
| SL STOP_MARKET reduceOnly + retry, başarısızsa rollback | `1183-1219`, `963-1034` | CANLI |
| TP1/TP2 TAKE_PROFIT_MARKET (algo), `-2021` sentinel | `1221-1275`, `629-743` | CANLI |
| Post-placement verify & repair | `1852-2012` | CANLI (`enable_post_placement_verify: true`, 2.5 s × 3) |
| Reconcile + orphan tespit + TP/SL repair | `1313-1595`, `745-943` | CANLI |
| BE taşıma (algo cancel + yeni SL) | `1642-1740` | CANLI |
| PnL audit sweep | `2014-2100` | CANLI (her 20 döngü); breaker back-correct **KAPALI** (`breaker_backcorrect_consecutive: false`) |
| `set_leverage` | `189-205` | Hata **yutuluyor** (yalnız warning) |
| `set_margin_mode` GET-first | `207-257` | bot_runner'da fatal, main.py'de non-fatal |
| `set_position_mode` GET-first | `259-292` | Fatal (her iki giriş yolunda) |
| MT5 / OANDA adapter | `exchange/mt5.py`, `exchange/oanda.py` | Canlıda kullanılmıyor (forex hedefi, HERMES.md:20) |

### 1.4 Diğer kapsam

- `engine/journal.py` + `_journal_record_entry` (`safe_orchestrator.py:604`): canlı; **timeframe/htf_bias/confluence/intent alanları boş** yazılıyor (kod içi itiraf `safe_orchestrator.py:~2985-2992`) → journal'dan yol/setup atfı yapılamıyor.
- `engine/postmortem.py`: rapor amaçlı; canlı karar yolunda değil.
- `preflight.py`: salt-okuma ön kontrol (canWithdraw, hedge, flat-book, bakiye bandı `starting_balance×0.8 … ×2.5`).
- Deploy: `docker-compose.prod.yml` **3 bot konteyneri** (V1 mid `efloud-bot`, V2 long `efloud-bot-long`, V3 scalp `efloud-bot-scalp`), her biri kendi env dosyası + `EFLOUD_ALLOW_MAINNET=1`, `AUTOSTART=0` (`deploy/.env.production*.example`). 2026-11-07 itibarıyla üçü de "Up" (`collab/STATUS.md:13`); **V2/V3'ün Start'a basılıp trade ettiği DOĞRULANMADI.**

---

## 2. Canlı gerçek (şu an prod'da fiilen çalışan davranış, kanıtlı)

**Kaynak config:** `configs/config.phase2_1k.yaml` (`deploy/.env.production.example: EFLOUD_CONFIG_PATH`, `backend/bot_runner.py:47,189`). Root `config.yaml` daemon tarafından okunmaz (`config.phase2_1k.yaml:85-88`).

### 2.1 Giriş yolu
1. `smc_version: v2`, 10 sembol whitelist, `smc_v2_shadow: false` (`:90-95`) → v2 setup state machine canlı emir veriyor (`main.py:64-90` store'u kuruyor, `bot_runner.py:331-346`).
2. v1 sinyal yolu bu 10 sembolde **susturulu** (`safe_orchestrator.py:1484-1494`, `_v2_entry_active` `:2449-2473`). `symbols.fixed_core` = whitelist → **v1 giriş yolu canlıda tamamen ölü**; v1'e bağlı her anahtar (`reject_wide_sl`, `allow_volatile_entries`, `smc_tp_targeting`, `min_rr_tp1`, `blended_rr_target`, `min_confluence: 50`, reverse-on-profit, leblep, `sizing_balance_source`) canlı davranışı **etkilemiyor**.
3. v2 emir kapıları sırası (`safe_orchestrator.py:2830-3290`): whitelist → breaker.check → `calc_sl` (SLTooFar red) → TP (`luxalgo.tp_targets`, `min_rr`=risk.min_rr **1.8**) → fixed size → `pos_guard.can_open_position` → pause gate → shadow kapısı → `OrderManager.open_position` (drift guard → MARKET → SL → TP1/TP2 → verify) → lifecycle mirror (F2).
4. **Rejim kapısı v2'ye uygulanmıyor** (bilinçli: `:1179`, `:2849`). Upstream v2 blokları yalnız `stale_data`, `watch_only`, `balance_unavailable` (`:1180-1184`).
5. LuxAlgo modu açık (`smc_v2.luxalgo.enabled: true`, `:187-208`), po3_gate açık (`:131`), `fvg_entry`/`touch_entry` **shadow** (log-only, `:211-216`).

### 2.2 Efektif risk sayıları (V1, kod + config'ten türetilmiş)
Varsayım: guard'a giden `balance` = `get_balance()` = `totalMarginBalance` (`safe_orchestrator.py:3094`, `exchange/__init__.py:141-158`). Güncel bakiye **DOĞRULANMADI**; config tabanı $403.55 (`:375`, `c2da2cb` 2026-09-28).

| Limit | Formül (kanıt) | B ≈ $403 için sonuç |
|---|---|---|
| Notional/pozisyon | 50 × 10 = $500 (`risk/__init__.py:68`) | $500 (cüzdanın ~1.24x'i) |
| Margin cap | 50 ≤ B × 0.35 (`position_guard.py:253-264`) | Geçer (≈%12.4) |
| Toplam exposure | Σnotional ≤ 6 × B (`:271-282`) | **≤ 4 eşzamanlı pozisyon** ($2000 ≤ $2421; 5. → $2500 red). `max_open_positions: 10` fiilen ulaşılamaz |
| Risk hard cap | \|entry−SL\| × size ≤ %5 × B (`:350-357`) | SL mesafesi ≤ ~%4.0 |
| Likidasyon kapısı | SL% < 0.9 / 10 (`:339-348`) | SL < %9 |
| SL ATR bandı | 2.0–5.0 × gerçek Wilder ATR(14) (`v2_use_real_atr: true` `:108`; `sl_calc.py` min/max) | 15m ATR ~%0.3 → SL ≈ %0.6–1.5 |
| Günlük kayıp | %10 × **sabit** `starting_balance` 403.55 (`breaker.py:301`) | ≈ $40 → TRIP, gece yarısı UTC resume |
| Haftalık DD | %25, 7 günlük high-watermark (`breaker.py:308-318`) | HALT (manuel reset) |
| Ardışık kayıp | 3 → 120 dk TRIP (`breaker.py:320-327`) | TRIP (HALT değil) |
| Acil bakiye | eşik 0 (`:424`, `b2154c5`) | **Devre dışı** |
| Max hold | 0 (`:407`, `59c32f3`) | **Devre dışı**; 24 saatte bir bilgi |

### 2.3 Execution güvenceleri (canlı)
- ISOLATED + one-way: `exchange.margin_mode: ISOLATED`, `hedge_mode: false` (`:72-73`); bot_runner Start'ta zorlar, margin hatası **fatal** (`bot_runner.py:50-83, 262-273`).
- Leverage 10x her Start'ta tekrar gönderilir (açık pozisyonun likidasyon fiyatını yeniden hesaplatır — `config.phase2_1k.yaml:36-41` uyarısı doğru).
- SL yerleşmezse anında rollback (`exchange/__init__.py:1201-1217`); verify SL'yi teyit edemezse sibling cancel + market close (`:1975-1997`); hiç okuma yapılamazsa tolere (`:1964-1972`).
- Orphan + SL'siz → %2 SL (`orphan_protection.py:183-220`); alerter SL/orphan/TP uyarıları **yalnız V1 log'unu** okur (`docker-compose.prod.yml:143-166`, volume `efloud_logs`).

---

## 3. Çelişkiler

| # | Çelişki | Kanıt A | Kanıt B | Etki | Önerilen çözüm |
|---|---|---|---|---|---|
| C1 | **Verify, algo-order okuma hatasını "okuma başarılı" sayıyor** (PLAUSIBLE) | `exchange/__init__.py:1842-1850` algo fetch except → yalnız `log.debug`, `return ids, True` | Aynı dosyada reconcile `algo_fetch_ok` ile kapılı (`:1411-1412, 1461, 1484, 1528, 1542`); verify docstring "never force-closes a healthy position on a read failure" (`:1830-1832`) | SL/TP'ler algo emir; algo okuma geçici düşerse SL "eksik" görünür → SL bir kez yeniden konur (çift SL) ve yeniden koyma da başarısızsa **korumalı pozisyon market-close edilir** | Önce reprodüksiyon testi (algo fetch raise + regular ok → rollback olmamalı); sonra `_fetch_protection_order_ids` algo hatasında `ok=False` dönsün. Guard'ı zayıflatmaz, false-close'u önler. risk-ops + operatör onayı. |
| C2 | "Limit emir" iddiası ↔ market giriş | `AGENTS.md:15-16` "limit emir (SL likidite çizgisinde)" | `exchange/__init__.py:1150-1156` `"market"` | Slipaj/maliyet modeli yanlış anlaşılır; NET-cost ölçümü market varsayımıyla yapılmalı | AGENTS.md düzelt: "MARKET giriş (drift guard %1)" |
| C3 | Bölge aşım toleransı | `AGENTS.md:22` `max_zone_overshoot_atr=2.0` | `config.phase2_1k.yaml:168` **6.0** (`ad41004`, 2026-10-03) | Doküman canlı filtreyi 3x dar gösteriyor | Doküman güncelle (değer config'ten okunmalı, kopyalanmamalı) |
| C4 | Acil halt dokümante, kodda yok | `config.phase2_1k.yaml:50,56` "$360 altında acil halt", `:401-402` "$1216 eşiği" | `:424` `emergency_balance_threshold: 0` | Operatör/okuyucu olmayan bir tabanı varsayar | Başlık bloğunu güncelle: "acil bakiye HALT'ı YOK (2026-10-01)" |
| C5 | "10 eşzamanlı pozisyon" | `config.phase2_1k.yaml:47`, `README.md:135-136` | `position_guard.py:271-282` × `max_total_exposure: 6.0` × B≈$403 → ≤4 | Kapasite ve korelasyon riski yanlış raporlanıyor (ki bu fiilen koruyucu) | Dokümanda efektif tavanı formülle yaz; sayıyı yükseltme önerisi YAPMA |
| C6 | `min_rr` "kullanılmaz" diyor, canlı TP onu kullanıyor | `config.phase2_1k.yaml:273` "legacy gate — smc_tp_targeting açıkken kullanılmaz" | `safe_orchestrator.py:3058` lux `tp_targets(..., min_rr=1.8)` | Yorum yanlış; `min_rr` değişikliği canlı TP'yi doğrudan oynatır | Yorumu "LuxAlgo TP min R:R (CANLI)" olarak düzelt |
| C7 | `smc_tp_targeting/min_rr_tp1/blended_rr_target` "aktif" sunuluyor | `config.phase2_1k.yaml:274-281` | Yalnız v1 `generate_signals` (`safe_orchestrator.py:1372-1377`, `signals.py:476-480`); v1 susturulu | Canlıda inert; değiştirmek hiçbir şeyi değiştirmez | Config'te "v1-only, canlıda inert" etiketi |
| C8 | `allow_volatile_entries` "volatil girişler açık" | `AGENTS.md:21`, `HERMES.md:37,134`, `config.phase2_1k.yaml:380-385` | Rejim kapısı v2'ye uygulanmıyor (`safe_orchestrator.py:1179, 2849`); v1 susturulu | Anahtar canlıda **inert**; geri almak da koruma getirmez | Dokümanda "v2'de rejim kapısı hiç yok (operatör kararı)" yaz; kapı eklemek ayrı karar |
| C9 | Ardışık kayıp = HALT iddiası | `HERMES.md:237` "Haftalık DD veya ardışık kayıp → HALTED" | `breaker.py:320-327` ardışık kayıp **TRIPPED 120 dk**, otomatik resume | Incident runbook'u yanlış teşhis/yanlış reset'e yönlendirir | HERMES.md düzelt |
| C10 | Max-hold kaldırma, kendi BT kanıtıyla çelişiyor | `config.phase2_1k.yaml:405` "BT-sweep5: 24h→36h, **48h daha kötü**" | `:407` `max_holding_hours: 0` (`59c32f3`); sınırsız tutuş hiç ölçülmedi; lux counterfactual 36 s cap ile koştu (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:31`) | Elde olan tek ölçüm "daha uzun = daha kötü" yönünde; guard kaldırıldı | NET-cost backtest: 36 s vs 0 (LuxAlgo akışında). Sonuca göre operatör kararı. |
| C11 | `max_entry_dist_atr` yorumu ↔ değer | `config.phase2_1k.yaml:133-140` "4.0'da uçurum, 6.0 seçildi" | `:141` **12.0** (`eb01f40`) "çok SL olursa geri düşür" — ölçüm yok | BT-23 kanıtı (4 ATR ötesi 0 CONFIRMED) 12'yi desteklemiyor | 12.0'ın NET etkisi ölçülene kadar KANITSIZ etiketi; geri alma operatör kararı |
| C12 | "Backtest modülü kaldırıldı" | `config.phase2_1k.yaml:185-186` (`562a6a3`) | `CLAUDE.md:48` `python -m backtest.cli`; PR #335 parity raporu (`collab/outputs/claude-code/2026-11-07-backtest-live-parity.md`) | LuxAlgo'nun "ölçülmedi" notu bayat — **ölçüldü ve NET negatif** | Config yorumunu ölçüm referansıyla değiştir |
| C13 | V2 long breaker kalibrasyonu tutarsız | `config.phase2_long_1k.yaml:188` starting 582; `:214` emergency 472 "$525 cüzdana göre" | 472/582 → %18.9 ≠ daily %10; test yalnız prod'u kapsıyor (`tests/config/test_phase_configs.py:60-98`) | Daily % yanlış tabana göre; emergency eşiği belgelenen orana uymuyor | Operatör gerçek bakiye ile yeniden kalibre etsin; C2 testini canlı 3 config'e genişlet (zayıflatma değil) |
| C14 | V3 scalp kalibrasyonu | `config.phase2_scalp_1k.yaml:200,222` 525/472 → %10.1 | daily %8 (`safety.daily_loss_limit_pct`) | Test kapsamı dışı, ±1 tolerans aşılıyor | C13 ile aynı |
| C15 | Margin setup fatal/non-fatal ayrımı | `backend/bot_runner.py:66-69` fatal | `main.py:684-689` `log.warning` (CLI yolu) | CLI ile başlatılırsa yarım-CROSSED çalışabilir | CLI yolunu bot_runner'a eşitle (`_enforce_margin_setup` paylaş) |
| C16 | `set_leverage` hatası sessiz | `exchange/__init__.py:198-205` | `position_guard.py:339-348` likidasyon kapısı **config** kaldıraçla hesaplar | Borsadaki gerçek kaldıraç farklıysa likidasyon kapısı yanlış ölçekte | Start'ta kaldıraç GET-teyidi (fail-closed) — öneri, onaylı |
| C17 | v2 docstring "ATR proxy, follow-up" | `safe_orchestrator.py:2862-2864` | `v2_use_real_atr: true` (`config.phase2_1k.yaml:108`), `:3009-3023` | Okuyucu yanlış ATR semantiği varsayar | Docstring güncelle |
| C18 | Leblep yeri | `config.yaml:174` "bot_runner.py order-intercept" | `safe_orchestrator.py:1021-1077` (v1-only, inert) | Yanlış konum | Yorum düzelt |
| C19 | Parity backtest portföy kısıtlarını modellemiyor | parity raporu "10 single-symbol run fair stand-in", "10 × $2000" (`2026-11-07-backtest-live-parity.md:33-36, 20-22`) | Canlıda B≈$403, exposure tavanı ≤4 pozisyon | Ölçülen −NET'in canlıdaki dağılımı farklı (daha az eşzamanlı işlem) | Portföy modunda canlı bakiye + exposure ile tekrar ölç |
| C20 | Alerter kapsamı | `collab/STATUS.md:16` "Yalnız mid bot logu" | V2/V3 konteynerleri Up (`STATUS.md:13`), `place_missing_sl` açık | V2/V3'te stop'suz/orphan pozisyon **Telegram'a düşmez** | Alerter'ı V2/V3 log volume'larına genişlet veya V2/V3 kapalı olduğunu belgele |

---

## 4. Bayat / yanlış dokümantasyon

| Dosya:satır | İfade | Gerçek | Kanıt |
|---|---|---|---|
| `AGENTS.md:11` | "Güncel Algoritma Durumu (2026-10-02)" | LuxAlgo modu 2026-11-01'den beri canlı; AGENTS.md'de LuxAlgo hiç yok | `config.phase2_1k.yaml:180-208` |
| `AGENTS.md:13-16` | CHoCH/BOS → OB/BB → engulfing → **limit emir** | LuxAlgo setup + MARKET giriş | C2 |
| `AGENTS.md:22` | overshoot 2.0 | 6.0 | C3 |
| `HERMES.md:24-25` | GitHub master / VPS HEAD `c8dc5c8` | master `81c2cf7`; VPS HEAD DOĞRULANMADI | `git log` |
| `HERMES.md:237` | ardışık kayıp → HALTED | TRIPPED | C9 |
| `HERMES.md:379`, `skills/efloud-incident/SKILL.md:13` | "`emergency_balance_threshold=0` değişmez / değiştirme" | Operatör kararı; ama bu ifade **korumayı geri getirmeyi de yasaklıyor** | Bkz. §6 |
| `README.md:135-136` | "en çok 10 açık pozisyon" | Efektif ≤4 (B≈$403) | C5 |
| `CLAUDE.md:62-65` | SL: son 20 mum + 0.5 ATR, min %0.1; TP1 min R:R 1.5 | Bu **v1/Pine referansı**; canlı v2: `calc_sl` (bölge/anchor + 0.5 ATR, 2–5 gerçek ATR, aşarsa RED) + LuxAlgo TP min R:R 1.8 | `sl_calc.py:56-67`, `safe_orchestrator.py:3049-3058` |
| `CLAUDE.md:61` | "Confluence 55 / CANLI 50" | Canlı v2-LuxAlgo `luxalgo.min_confluence: 1` (OB + ≥1 kavram); 50 yalnız v1 | `config.phase2_1k.yaml:205` |
| `config.phase2_1k.yaml:44-56` | Risk profili başlığı ($360 halt, ≥$403.55 ön koşul) | emergency 0 | C4 |
| `config.phase2_1k.yaml:269-271, 371` | "$100 notional cap ~$10 risk", "$200 günlük ($2000×10%)" | $500 notional; günlük ≈$40 | `:298-299`, `:375` |
| `config.phase2_1k.yaml:396-403` | "$50 / ~$1363 ≈ %3.7", "$1216 eşiği" | B≈$403 → %12.4; eşik 0 | `:375`, `:424` |
| `config.phase2_1k.yaml:143-151` | "8 → 24 bar" | 12 (sonraki paragraf açıklıyor; başlık yanıltıcı) | `:151-158` |
| `engine/safety/position_guard.py:5-8` | "%20 notional, 5x equity, 48h" | Default'lar; canlı 35% / 6x / 0 | config |
| `engine/safety/breaker.py:5-9` | "%8 haftalık … Emergency → HALT" | Canlı %25; emergency kapalı | config |
| `config.phase2_long_1k.yaml:30,49` | "$472 … $525 cüzdan" | starting 582 | C13 |
| `agents/risk-manager.md:24` | Sizing'i `calc_position_size` ile yeniden hesapla | Canlı `calc_fixed_position_size` | `config.phase2_1k.yaml:298` |

---

## 5. Trade mantığı / setup modelleri (risk/execution görünümü)

| Setup / varyant | Tanım (kanıt) | Durum | Edge kanıtı |
|---|---|---|---|
| **v2 LuxAlgo OB retest** | BOS/CHoCH (internal+swing) → kırılımın OB'si → retest + engulfing onayı (48 bar) → MARKET; SL bölge/Strong Low-High + 0.5 ATR; TP karşı OB/EQ/EQH-EQL (min R:R 1.8, wick 0.15R) (`config.phase2_1k.yaml:187-208`, `safe_orchestrator.py:3049-3068`) | **CANLI** (V1; V2/V3 config'lerinde de `enabled: true`) | **ÇÜRÜTÜLMÜŞ**: 60 g, 217 işlem, NET −0.30 R/işlem, PF 0.65, IS/OOS ikisi de negatif (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:15-17,42`); parity 41 g: 137 işlem, brüt PF 0.69, NET −$181.9, 8/10 sembol PF<1 (`2026-11-07-backtest-live-parity.md:20-24`). Brüt ≈ başa baş, maliyet ~0.27 R yiyor (dar SL, medyan %0.72) |
| LuxAlgo kapıları (12h trend, premium/discount, confluence, recency) | Elenen dokunuşlar | CANLI | **KANITLI (koruyucu)**: gevşetilse NET −0.17…−0.32 R (`lux-gate-counterfactual.md:11-13`) → gevşetme önerilmez |
| Mitige-OB retest (breaker benzeri) | Pencerede zaten mitige olmuş OB'ye dönüş | Yalnız ölçüm | **KANITSIZ** (n=30, +0.24 R, IS/OOS +; eşik sınırında — takip) |
| Teyitsiz limit (P2) | Bölge kenarından limit | Ölçüm | KANITSIZ (−0.04 R, PF 0.95, n=407) |
| v2 efloud OB/BB + FVG/OTE yolu | `ob_bb_entry`, `ote_zone_entry`, origin swing | LuxAlgo açıkken **devre dışı** (`config.phase2_1k.yaml:182-184`) | BT-22 tablosu bu döneme ait (aşağı) |
| v1 sinyal (CHoCH MARKET) | `engine/signals.py` | **ÖLÜ** (canlı sembollerde susturulu, `b2154c5`) | — |
| FVG pullback entry | 4h bias, FVG limit, OB SL | **SHADOW** (`c05260c`, #343) | KANITSIZ (go-live ≥30 forward close NET>0 şartı — memory/`fvg_entry_shadow`) |
| Touch entry | Fitil temas | **SHADOW** (`:211`) | KANITSIZ |
| BT-22 gerçek ATR + `max_sl_atr: 5` | SL'yi gerçek ATR ile sınırla | CANLI | **KANITLI (yalnız IS, eski kod)**: 336 canlı işlem, cap5 +403.7→+595.7 USDT, win %66.7→%85.2 (`safe_orchestrator.py:2943-2985`); 2026-05/06 verisi, LuxAlgo öncesi, OOS yok |
| `min_sl_atr: 2.0` | Dar SL reddi | CANLI | KANITSIZ (pozitif edge yok): R/trade −0.363→−0.257, hâlâ negatif (`config.phase2_1k.yaml:412`) |
| `max_entry_dist_atr: 12`, `max_zone_overshoot_atr: 6` | Setup mesafe kapıları | CANLI | KANITSIZ (C11; 4 ATR ötesi 0 CONFIRMED ölçümü 12'yi desteklemiyor) |
| `po3_gate: true` | Manipülasyon fazında giriş yok | CANLI | KANITSIZ (ölçüm bulunamadı — DOĞRULANMADI) |
| Fixed $50 × 10x | Sabit marjin | CANLI | KANITSIZ (operatör talebi `1c20e22`) — risk kararı, edge değil |
| Max-hold 0 | Süre sınırı yok | CANLI | KANITSIZ; tek ölçüm aksi yönde (C10) |
| Reverse-on-profit | Karda flip | v1-only → ÖLÜ | — (canlı davranış: karşı yön RED, daha muhafazakâr) |
| Agent team | LLM inceleme, `gating: false` | Gözlem | KANITSIZ (verdict edge ölçümü bekleniyor) |
| Korelasyon sizing / EV allocation | Primitifler | ÖLÜ | KANITSIZ |

**Fund-manager notu:** Operatör niyeti "OB/BB'den pullback girişi, likidite çizgisinde SL" (`safe_orchestrator.py:2452-2457`). Ölçülmüş NET edge bu niyetin **canlı uygulamasını (LuxAlgo akışı) çürütüyor**; kâr/zarar farkını strateji değil maliyet/SL genişliği belirliyor. Güvenlik katmanı bu durumda **sermayenin tek savunması**; acil halt ve max-hold'un kaldırılması negatif-beklentili bir akışta koruma payını daraltıyor.

---

## 6. ECC revizyon adayları (yalnız doküman/kural/skill/agent/hook; trade mantığı DEĞİL)

1. **AGENTS.md "Güncel Algoritma Durumu"nu yeniden yaz** (C2, C3, C8): LuxAlgo modu, MARKET giriş, v2'de rejim kapısı yok, overshoot 6.0 / entry-dist 12.0, `fvg_entry`/`touch_entry` shadow, ölçülmüş NET −0.30 R. Sayıları kopyalama; `config.phase2_1k.yaml:<satır>` referansı ver.
2. **HERMES.md** (C9 + bayat SHA): breaker state tablosu ekle — `daily → TRIPPED (UTC gece yarısı)`, `consecutive → TRIPPED 120 dk`, `weekly → HALTED`, `emergency → kapalı (V1) / açık (V2/V3, 472)`. "Şu an ne durumda" tablosundaki SHA'yı `collab/STATUS.md`'ye yönlendir.
3. **`HERMES.md:379` ve `skills/efloud-incident/SKILL.md:13` ifadesini daralt:** "`emergency_balance_threshold` operatör onayı olmadan değiştirilmez" — mevcut metin ("değişmez/değiştirme") korumanın **yeniden açılmasını** da yasaklıyor; bu, "guard'ı zayıflatma" ilkesinin tersine işler.
4. **README.md:135-136**: "≤10 açık pozisyon" yerine "max_open 10; efektif tavan = ⌊6 × bakiye / 500⌋ (≈4 @ $403)".
5. **CLAUDE.md "Efloud Çekirdek Mantığı"** başına tek satır: "Bu bölüm v1/Pine referansıdır; canlı bot v2-LuxAlgo (SL `engine/smc_v2/sl_calc.py`, TP `engine/smc_v2/luxalgo.py:tp_targets`)". Mantığı değiştirmez, yanlış referans almayı önler.
6. **`agents/risk-manager.md:24`**: sizing yeniden-hesap girdisini `calc_fixed_position_size` + `max_total_exposure` + `max_position_notional_pct` (margin cap) + %5 risk cap + likidasyon kapısı olarak güncelle; "efektif eşzamanlı pozisyon" hesabını zorunlu çıktı satırı yap.
7. **TESTS.md'ye yeni kural satırları (test önerisi, kod değil):**
   - `TEST-AUDIT-C2` kapsamını 3 canlı config'e genişlet (C13/C14) — mevcut testi sıkılaştırır.
   - "v2 canlıyken v1-only anahtarlar inert" sözleşme testi (C7/C8 için regresyon kalkanı; aksi halde operatörler inert anahtarı çevirip koruma sanır).
   - Verify algo-fetch hatası → rollback yok (C1 reprodüksiyonu).
   - "Docs↔config drift" testi: AGENTS/HERMES/README'deki sayısal güvenlik değerleri config ile eşleşsin (veya sayı yerine referans zorunlu).
8. **`collab/STATUS.md`'ye satır**: alerter kapsamı yalnız V1 (C20) + V2/V3 trade durumu (Start basılı mı) — açık soru olarak.
9. **Config yorum hijyeni** (`config.phase2_1k.yaml:44-56, 133-141, 185-186, 269-271, 273, 371, 396-403`): bayat dolar değerleri; trade mantığına dokunmayan yorum-only PR (bu turun doküman PR'ına uygun aday). Not: config dosyası `safety:/risk:` bloğu içerir → yorum-only olsa da risk-ops gözü önerilir.
10. **Hook (`hooks/live_write_gate.py`)**: config `safety:`/`risk:` bloğuna yazan `Edit` araç çağrılarını da "ask"e düşürme önerisi (şu an yalnız Bash eşleşiyor) — DOĞRULANMADI hook'un Edit'i kapsamadığı dışında bir mekanizma var mı.
11. **Ölü kod işaretleme (silme değil)**: `safe_orchestrator.py:1328-1338` tighten-stops (ulaşılamaz), `engine/allocation.py`, `engine/risk/correlation.py`, `cleanup_orphan_hedges` — `REGRESSION.md`/`TESTS.md`'de "dead, kept" etiketi.
12. **`main.py:73-89` `print("[DEBUG] …")`** satırları: üretim yolu (bot_runner bunu import ediyor, `bot_runner.py:331`) — log'a taşınması kod değişikliği; öneri listesine.

---

## 7. Riskler ve açık sorular

**Zayıflamış guard'lar (işaretleme; geri alma önerisi değil, operatör kararı):**
- **R1 — Mutlak taban yok (V1).** `emergency_balance_threshold: 0` + haftalık DD peak'i 7 günde rebase (`breaker.py:308-314`) → hafta başına <%25 kalan yavaş erime çok haftalı (ör. 3 × %20 ≈ %49) HALT'sız sürebilir. Günlük limit **sabit** `starting_balance` üzerinden → bakiye düştükçe günlük limit cüzdanın daha büyük yüzdesi olur ($250'de $40 = %16).
- **R2 — Max-hold kaldırıldı** (`59c32f3`); tek ölçüm "daha uzun = daha kötü" (C10). Funding drag açık uçlu.
- **R3 — Kaldıraç 10x** (`1c20e22`): ISOLATED %10 ters harekette likidasyon; SL ≤ ~%1.5 olduğundan normalde SL önce çalışır, ama gap/likidasyon kademesi riski 5x'e göre iki katı.
- **R4 — Mesafe kapıları gevşetildi** (overshoot 0.5→2→6, entry-dist 6→8→12); ölçümsüz.
- **R5 — Negatif-beklentili akış canlıda** (§5): breaker'ın yükü artıyor; ölçülmüş NET −0.30 R/işlem × ~3.3 işlem/gün (137/41) ≈ günde ~1 R kayıp beklentisi (fixed $500, SL ~%1 → R ≈ $5 → ~$5/gün; DOĞRULANMADI canlı R dağılımı).

**Execution riskleri:**
- **R6 (PLAUSIBLE)** C1: algo-okuma geçici hatasında korumalı pozisyonun yanlışlıkla kapatılması / çift SL.
- **R7 (PLAUSIBLE)** Rollback market emri başarısız olursa (`exchange/__init__.py:1982-1997`) siblings önce iptal edildiği için pozisyon **çıplak ve takipsiz** kalır; sonraki reconcile orphan olarak görür → %2 SL (orphan protection). Pozisyon entry'den >%2 zarardaysa SL fiyatı mark'ın yanlış tarafında kalır, `create_order` -2021 ile düşer → `skipped_critical_warning` (`orphan_protection.py:198-220`); mesafe kontrolü mutlak değer kullandığı için bunu önceden yakalamaz. Kurtarma = alerter orphan uyarısı + manuel.
- **R8 (PLAUSIBLE)** Lifecycle `WEAKNESS` kısmi kapanışları yalnız lojik (`engine/lifecycle.py:536-559`, borsa emri yok) → exposure guard'ı borsa notional'ını eksik sayabilir, breaker PnL tahmini kayar (M4 back-correct kapalı).
- **R9** `set_leverage` sessiz hata (C16); CLI yolunda margin hatası non-fatal (C15).
- **R10** V2/V3 için Telegram SL/orphan uyarısı yok (C20) ve V2/V3 breaker kalibrasyonu tutarsız (C13/C14).

**Açık sorular (operatöre):**
1. V2 (long) ve V3 (scalp) şu an **trade ediyor mu** (Start basılı mı)? Ediyorsa C13/C14/C20 önceliklidir.
2. Güncel V1 `totalMarginBalance` nedir? `starting_balance: 403.55` hâlâ doğru mu (günlük limit tabanı)?
3. Acil halt'ın kaldırılma gerekçesi "HALTED auto-resume yok" idi; aynı problem haftalık DD için de geçerli. Mutlak taban yerine "TRIP + uyarı" tipi bir taban istenir mi (yeni davranış = default-OFF + TDD + risk-ops)?
4. Ölçülmüş NET negatif akış canlıda kalmaya devam edecek mi, yoksa `pause_new_entries` / shadow'a alma kararı mı (yalnız operatör)?
5. `max_holding_hours: 0` için 36 s vs ∞ NET-cost ölçümü yapılsın mı?
6. v2'ye rejim kapısı uygulanmaması "pending operator decision" olarak duruyor (`safe_orchestrator.py:2849`) — karar kayda geçirilsin mi (ADR)?

---

## 8. Fable'a özet

1. **Canlı edge ÇÜRÜTÜLMÜŞ:** V1'de çalışan v2-LuxAlgo akışı ölçümde NET −0.30 R/işlem, PF 0.65 (217 işlem, IS+OOS negatif); parity'de 137 işlem, NET −$181.9. Brüt başa baş, maliyet ~0.27 R. Güvenlik katmanı şu an sermayenin tek savunması.
2. **v1 yolu canlıda tamamen ölü** (10/10 sembol v2'de) → `reject_wide_sl`, `allow_volatile_entries`, `smc_tp_targeting`, `min_confluence: 50`, reverse-on-profit, leblep canlı davranışı **etkilemiyor**; dokümanlar bunları aktif gösteriyor.
3. **Zayıflamış guard'lar:** acil bakiye HALT'ı 0 (mutlak taban yok, haftalık DD 7 günde rebase), max-hold 0 (kendi BT kanıtı tersini söylüyor), kaldıraç 10x, mesafe kapıları 12/6 ATR (ölçümsüz).
4. **Efektif kapasite ≤4 pozisyon** ($500 notional, `max_total_exposure 6 × ~$403`); "10 pozisyon" ifadesi (README, config) yanlış — bu tavan fiilen koruyucu, yükseltilmemeli.
5. **Execution açığı (PLAUSIBLE):** post-placement verify, algo-order okuma hatasını "okundu" sayıyor (`exchange/__init__.py:1842-1850`); reconcile aynı durumu doğru kapılıyor. Sonuç: çift SL veya korumalı pozisyonun yanlış kapatılması. Önce reprodüksiyon testi.
6. **Canlı TP `risk.min_rr: 1.8`'i kullanıyor**, config yorumu "kullanılmaz" diyor; bu anahtar canlı TP'yi doğrudan oynatır.
7. **V2/V3 kör noktası:** konteynerler Up; alerter yalnız V1 log'unu okuyor; V2 long breaker kalibrasyonu tutarsız (582/472 = %18.9 vs günlük %10), C2 testi yalnız V1'i kapsıyor.
8. **Doküman düzeltmeleri (bu turun PR'ına uygun):** AGENTS.md (limit→market, 2.0→6.0, LuxAlgo eksik), HERMES.md (ardışık kayıp TRIP, bayat SHA), README (efektif tavan), config yorumları (bayat $360/$1216/$1363/$200), CLAUDE.md SL/TP bölümüne "v1/Pine referansı" notu.
9. **"`emergency_balance_threshold=0` değişmez" kuralı** (HERMES.md:379, efloud-incident skill) korumanın geri açılmasını da yasaklıyor → "operatör onayı olmadan değişmez" olarak daraltılmalı.
10. **Ölü kod işaretle, silme:** tighten-stops dalı ulaşılamaz (`safe_orchestrator.py:1333` koşulu), korelasyon sizing ve EV allocation bağlı değil.
