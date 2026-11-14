# 00 — Fable 5.2 Sentez ve Karar Raporu (2026-11-14)

> Kök: `C:/tmp/wt-ecc-audit` @ `81c2cf7` (origin/master). SALT OKUMA; bu dosya dışında hiçbir şey yazılmadı, git state değişmedi.
> Girdi: `01-signal-algo.md` … `07-history.md` (7 rapor, tamamı okundu) + 24 yerinde spot-check (§1).
> Ölçüt: operatör NİYETİ çerçeve, ölçülmüş NET edge filtre. Etiketler: **KANITLI** / **KANITSIZ** / **ÇÜRÜTÜLMÜŞ**; kaynakta teyit edilemeyen = **DOĞRULANMADI**.
> Operatör kararı: bu turda canlıya yalnız DOKÜMAN PR'ı gider. Trade mantığı, config ve deploy değişiklikleri yalnız öneridir (§6.2).
> Secret işaretleri (değer okunmadı/alıntılanmadı): `secret var: deploy/.env.production*` (VPS), `secret var: ~/.claude/projects/…/69ca35d6-….jsonl` (testnet key, 07 §7 R5), `secret var: memory/reference_dashboard_access.md` (eski dev şifresi).

---

## 0. Yönetici özeti (10 madde)

1. **Canlıda tek giriş modeli var:** SMC v2 + LuxAlgo modu (12h lux swing bias → 15m CHoCH/BOS → OB retest → 15m engulfing kapanışı → **MARKET**). 10/10 sembol v2 whitelist'inde; v1 confluence motoru her cycle hesaplanır ama girişi susturulmuştur (`engine/safe_orchestrator.py:1486-1495`, `configs/config.phase2_1k.yaml:90-95,188`).
2. **Bu modelin NET edge'i ÇÜRÜTÜLMÜŞ.** 60 gün: n=217, −0.30 R/işlem, PF 0.65 (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`); 41 gün backtest: n=137, PF 0.69, NET −$181.9 (`…/2026-11-07-backtest-live-parity.md:21-24`); Pine Lab BTC PF 0.73. Brüt ≈ 0; dar SL (medyan %0.72) + taker giriş maliyeti ~0.27 R yiyor. Model 2026-11-01'de ölçümsüz canlıya alındı (`38508f7`).
3. **Hiçbir setup varyantı KANITLI değil.** Tek pozitif aday mitige-OB/breaker retest (+0.24 R, n=30, tek pencere) ve operatörün FVG setup'ı (offline ≈ 0.00 R, n=85) KANITSIZ. Diğer 10+ varyant ÇÜRÜTÜLMÜŞ (§3).
4. **Kapılar koruyucu, gevşetmeler ölçümsüz.** 12h trend / premium-discount / recency / confluence kapılarının elediği işlemler −0.17…−0.32 R (KANITLI, göreli). `max_entry_dist_atr 12`, `max_zone_overshoot_atr 6`, cap 6, recency 168, BOS, Po3 ise ölçümsüz (KANITSIZ). "Az işlem" şikâyetinin ana nedeni kapılar değil **exposure tavanı**: 6.0 × $403.55 → en çok 4 eşzamanlı $500 pozisyon; 22 teyidin 11'i buradan reddedildi.
5. **Niyet ↔ uygulama en büyük sapma SL'de.** Operatör altı kez "SL ATR'ye göre değil, likidite/OB'nin biraz (%0.2) ötesi" dedi; hem canlı hem FVG gölgesi `calc_sl` (0.5 ATR tampon, 2 ATR taban, 5 ATR tavan) kullanıyor (`engine/smc_v2/fvg_entry.py:121-124`). Gölge ≥30 kapanışa ulaşsa bile operatörün setup'ını ölçmüş olmayacak.
6. **Güvenlik payı daralmış durumda:** acil bakiye HALT'ı 0 (`config:424`), haftalık DD tepe değeri 7 günde yeniden tabanlanıyor (`engine/safety/breaker.py:308-314`), max-hold 0, kaldıraç 10x — ve akış negatif beklentili. Bu rapor hiçbir guard gevşetmesini GO yapmaz.
7. **İki olası execution/mantık hatası (PLAUSIBLE, reprodüksiyon testi yok):** (a) post-placement verify algo-order okuma hatasında `ok=True` dönüyor (`exchange/__init__.py:1842-1850`) → çift SL veya korumalı pozisyonun yanlış kapatılması; (b) `CONFIRMED` aday dedup'a görünmüyor (`engine/smc_v2/setup_state.py:35,121-126`), recency 168 > timeout 48 → reddedilen setup bayat engulfing fiyatıyla yeniden denenebilir.
8. **Doküman drift'i sistemik:** kök dokümanlar (CLAUDE.md "Çekirdek Mantık", AGENTS.md, README, HERMES.md, PINE_SPEC §0-14, CONTEXT.md:18,36) canlıda ölü olan v1 / efloud-triggers yolunu anlatıyor; `collab/STATUS.md` 7 gün bayat; ana checkout 81 commit geride ve oturumlara bayat CLAUDE.md yüklüyor. Kök neden: elle kopyalanan sayılar ve "durum" bilgisinin anayasa/harita dosyalarına yazılması.
9. **Ölçüm altyapısı tutarsız:** dört farklı maliyet modeli, koda yazılmamış GO eşiği, canlıda ölü Edge Measurement Core (flag kapalı + hook v1 dalında, `safe_orchestrator.py:1497→1567`), setup atfı yapılamayan journal (`:689-692`), yalnız lokal branch'te duran NO-GO raporları.
10. **Karar:** GO = doküman PR'ı (§6.1). GATED = 15 maddelik trade/execution/ölçüm öneri listesi (§6.2), ilk sırada iki hata reprodüksiyonu ve ölçüm ön koşulları. NO = kapı gevşetme, exposure artırma, teyitsiz giriş, FVG'yi kapısız canlıya alma (§6.3). Canlı akışın sürmesi/durdurulması operatör kararıdır (§8 S1).

---

## 1. Kanıt doğrulama günlüğü (spot-check)

| # | İddia (rapor) | Yerinde kontrol | Sonuç |
|---|---|---|---|
| 1 | v1 sinyali v2 sembollerinde susturuluyor (01,02,04) | `engine/safe_orchestrator.py:1486-1495` `elif signals and self._v2_entry_active(symbol)` → yalnız log | DOĞRU |
| 2 | Giriş emri MARKET (01 C9, 02 C2, 04 #3) | `exchange/__init__.py:1151-1153` `create_order(ccxt_sym, "market", …)` | DOĞRU |
| 3 | "Limit emir" dokümanda (AGENTS, README) | `AGENTS.md:14-16`, `README.md:28-30` "limit entry"; kod yorumu `safe_orchestrator.py:1491` "→ limit" | DOĞRU |
| 4 | `risk.min_rr` canlı lux TP1 kapısı, yorum "kullanılmaz" (01 C5, 02 C6) | `safe_orchestrator.py:3056-3058` `risk_cfg.get("min_rr", 1.8)`; `config.phase2_1k.yaml:273` | DOĞRU |
| 5 | Rejim kapısı v2'ye uygulanmıyor (01 C6, 02 C8) | `safe_orchestrator.py:1179` "Regime gate deliberately NOT applied"; `:2849` "pending operator decision" | DOĞRU |
| 6 | Verify algo-fetch hatasında `ok=True` (02 C1) | `exchange/__init__.py:1842-1850` except → `log.debug`, `return ids, True`; reconcile `algo_fetch_ok` kapılı (`:1335,1348,1412`) | DOĞRU (kod); sonuç senaryosu PLAUSIBLE, test yok |
| 7 | Acil halt fiilen kapalı; haftalık tepe 7 günde rebase; ardışık kayıp TRIP (02) | `engine/safety/breaker.py:284-288,308-314,320-327`; `config:424` | DOĞRU |
| 8 | Baz akış −0.30 R, PF 0.65, n=217 (hepsi) | `…lux-gate-counterfactual.md:42` | DOĞRU |
| 9 | "IS+OOS ikisi de negatif" (02 §5, §8) | Aynı satır: IS −0.48, **OOS +0.03**, 3/10 sembol | **ÇÜRÜDÜ** — OOS sıfır civarı pozitif; doğru ifade 01/04'teki |
| 10 | Parity: 137 işlem, PF 0.69, NET −$181.9, 8/10 PF<1; 8/10 canlı giriş eşleşti | `…backtest-live-parity.md:12-24` | DOĞRU (not: 10 × $2000 varsayımı, canlı bakiye ~$403) |
| 11 | Mitige-OB +0.24 R, n=30, IS/OOS + ; P2 "engulfing gelmedi" −0.04 R n=407 | `…counterfactual.md:52,54` | DOĞRU |
| 12 | TF profilleri scalp 5m/1h/4h, mid 15m/4h/12h, long 1h/8h/1d; compose yorumu 1w/12h | `data/timeframes.py:24-28`; `docker-compose.prod.yml:42,72` | DOĞRU |
| 13 | Exposure tavanı ≤4 pozisyon (01 C18, 02 C5) | `engine/safety/position_guard.py:271-282`; `config:299,375,403` → 6×403.55=2421 < 2500 | DOĞRU (güncel bakiye DOĞRULANMADI) |
| 14 | FVG gölgesi SL = `calc_sl` (ATR), maliyet %0.07 RT (07 C1, 04 #9) | `engine/smc_v2/fvg_entry.py:25-27,121-124`; `engine/smc_v2/sl_calc.py:56-78`; spec `:35` bunu "✅" işaretlemiş | DOĞRU |
| 15 | CONFIRMED dedup dışında (01 Q1) | `engine/smc_v2/setup_state.py:35` `PERSISTED_STATES` CONFIRMED içermez; `:121-126`; `safe_orchestrator.py:2276-2283` | Öncül DOĞRU; yeniden-giriş sonucu DOĞRULANMADI |
| 16 | SWING_OB etiketi swing kırılımına otomatik; anchor yalnız OB ucu (01) | `engine/smc_v2/luxalgo.py:477-478,518-519,548` | DOĞRU |
| 17 | Signal ledger hook'u v1 dalında, flag kapalı (04) | `safe_orchestrator.py:1497` (`elif signals:`) → `:1567`; `config:468` | DOĞRU |
| 18 | Tighten-stops dalı ulaşılamaz (02) | `safe_orchestrator.py:1333` koşulu ↔ `engine/lifecycle.py:409-413` ikisini birlikte set eder | DOĞRU |
| 19 | Pine lab MAX_HOLD 36 h; canlı 0 (03) | `pine/lab/tail_strategy.pine:5,112-113`; `config:407`; `59c32f3` | DOĞRU |
| 20 | max-hold 0 "ölçümsüz / tek ölçüm aksi yönde" (02 C10) | `collab/log/claude-code.md:319`: A/B 41g × 4 sembol −46.05 → −12.02 NET | **KISMEN ÇÜRÜDÜ** — ölçüm var ve göreli iyileşme gösteriyor; ama tek pencere, 4 sembol, iki kol da negatif (04 D18 doğru) |
| 21 | Canlı yol "… + limit emir"; LuxAlgo "NET-cost KANITSIZ" (06 §2, §5 S3) | #2 ve #8/#10 | **ÇÜRÜDÜ** — giriş MARKET; edge ölçüldü ve negatif (ÇÜRÜTÜLMÜŞ) |
| 22 | "Backtest kaldırıldı" yanlışı: `AGENTS.md:82` (06) / `:75` (04) | `AGENTS.md:75`; `backtest/` mevcut; `agents/strategist.md:34-35`; `CHANGELOG.md:18` | İçerik DOĞRU; 06'nın satır numaraları kaymış (`:82`→`:75`, `:15-27`→`:11-22`) |
| 23 | `collab/STATUS.md` bayat; gerçek deploy `bf464d0` | `collab/STATUS.md:10-11` (`3acea5c`, 11-07); `collab/log/claude-code.md` son giriş "VPS: DEPLOYED bf464d0" | DOĞRU |
| 24 | CLAUDE.md iç çelişkiler; CONTEXT.md:18,36; `.claude/` gitignore; SL/TP raporu origin'de yok | `CLAUDE.md:17,20,26,29,40,59,63` (76 satır); `CONTEXT.md:18,36`; `.gitignore:122`; `git branch -r --contains 073a485` boş | DOĞRU (07'nin `CLAUDE.md:21,26` atfı `:20,:29` olmalı) |

Ek küçük kaymalar: `v2_use_real_atr` satırı `:108` (03 `:105`, 06 `:110` demiş); `max_entry_dist_atr` `:141` (07 `:129`); `eb01f40` tarihi 2026-11-02. `HERMES.md:379` ve `skills/efloud-incident/SKILL.md:13` "`emergency_balance_threshold=0` değişmez / değiştirme" ifadeleri yerinde teyit edildi. Tarafımca yeniden sınanmayanlar: 05'in canlı probe'ları (panel 502, ölü hostlar), VPS/konteyner durumu, güncel bakiye, "229 test", u2Algo-Trade repo içeriği → **DOĞRULANMADI**.

**Etiket uyuşmazlıklarında hakem kararı:** BT-22 gerçek ATR + 5 ATR tavanı → 01 "KANITLI", 04 "KANITSIZ" demiş; ölçüm gerçekleşmiş sonuca göre süzme (in-sample, LuxAlgo öncesi) olduğu için **KANITSIZ**. `min_sl_atr 2.0` → **KANITLI (göreli)**: R/trade −0.363 → −0.257, mutlak değer hâlâ negatif. v1 confluence → "ÇÜRÜTÜLMÜŞ" yerine **gate'i geçemedi** (Wave-2 OOS PF 1.165 < 1.30; yalnız komisyon, LuxAlgo öncesi motor).

---

## 2. Birleşik çelişki matrisi

Karar türü: **GO-doc** = bu turun doküman PR'ı · **GATED** = backtest-gate / risk-ops / operatör onayı gerekir, bu turda canlıya gitmez · **NO** = yapılmaz.

| # | Çelişki | Taraflar + kanıt | Kök neden | ÇÖZÜM KARARI | Tür |
|---|---|---|---|---|---|
| X1 | Giriş emri "limit" mi MARKET mı | `AGENTS.md:14-16`, `README.md:30`, `safe_orchestrator.py:1491` yorumu ↔ `exchange/__init__.py:1152` | Operatör niyeti (limit) dokümana, uygulama (MARKET) koda yazılmış | Dokümanlar "engulfing kapanışı → MARKET (taker, drift guard %1)" olur. Kod yorumu ayrı | GO-doc (+kod yorumu GATED) |
| X2 | Dokümandaki giriş akışı (OB/BB + OTE/FVG) ↔ canlı LuxAlgo yolu | `AGENTS.md:11-22`, `HERMES.md §5b`, `docs/OPERATOR_GUIDE.md:104-117`, `README.md:28-30` ↔ `config:180-188`, `safe_orchestrator.py:2659-2660` | 2026-11-01 geçişi dokümana işlenmedi | Tek kanonik "Giriş akışı" bölümü (CONTEXT.md); diğerleri link verir | GO-doc |
| X3 | `max_zone_overshoot_atr` 2.0 ↔ 6.0 | `AGENTS.md:22`, HERMES, OPERATOR_GUIDE ↔ `config:168` (`ad41004`) | Elle kopyalanan sayı | Dokümandan sayıları kaldır; `config:satır` referansı kuralı | GO-doc |
| X4 | "Backtest modülü kaldırıldı / LuxAlgo ölçülmedi" ↔ backtest var, ölçüldü, negatif | `AGENTS.md:75`, `CHANGELOG.md:18`, `agents/strategist.md:34-35`, `config:185-186`, `collab/STATUS.md` ↔ `backtest/`, #335, parity raporu | Restore sonrası temizlik yapılmadı | Dokümanları düzelt + ölçüm sonucunu yaz; config yorumu ayrı PR | GO-doc (+config yorumu GATED) |
| X5 | `risk.min_rr` "legacy, kullanılmaz" ↔ canlı TP1 kapısı | `config:273` ↔ `safe_orchestrator.py:3058`, `luxalgo.py:576-586` | Yorum v1 dönemi | Dokümanlarda "canlı lux TP1 kapısı = `risk.min_rr`"; config yorumu ayrı PR | GO-doc / GATED |
| X6 | Aktif sanılan ama canlıda inert anahtarlar | `risk.min_confluence 50`, `allow_volatile_entries`, `smc_tp_targeting`/`min_rr_tp1`/`blended_rr_target`, `smc_v2.pullback_timeout_bars 12`, `ob_bb_entry`, `ote_zone_entry`, `ob_bb_zone_atr_pad`, `origin_swing_lookback`, reverse-on-profit, leblep (`config:115-178,274-282,380-385`) ↔ `safe_orchestrator.py:1179,1486,2119-2120,2659-2660,2849` | v1 susturma + lux bypass | CONTEXT.md'ye "canlıda etkili / inert anahtar" tablosu; sözleşme testi önerisi | GO-doc (+test GATED) |
| X7 | CLAUDE.md "Çekirdek Mantık" v1'i canlı gibi anlatıyor | `CLAUDE.md:57-67` (conf 55/50, SL 20 mum, TP 1.5R, Daily filtre, slope fallback) ↔ canlı lux (swing 50/5, `luxalgo.min_confluence 1`, `calc_sl` 2–5 ATR, 1.8R, daily yok, UNDEF→aday yok `luxalgo.py:524-525`) | Pine-çeviri dönemi kalıntısı | Bölüm "v1 referansı (susturulmuş)" olarak PINE_SPEC'e taşınır; CLAUDE.md'de canlı motor için pointer | GO-doc |
| X8 | Pine strategy zorunluluğu ↔ ADR-0005 indicator-only | `CLAUDE.md:17,20,29,39`, `agents/pine-engineer.md` ↔ `CLAUDE.md:3`, `docs/adr/0005-…` | Kural güncellenmedi | Ürün = `pine/lab/*` → `efloud_lab*.pine`; strategy = parity artefaktı; eski çiftler ARŞİV | GO-doc |
| X9 | "Python mantığını DEĞİŞTİRME" ↔ sürekli değişen canlı kod | `CLAUDE.md:3,20-26` ↔ #317–#344, ADR-0003 | Kural Pine görevine aitti | Kural Pine-çeviri kapsamına daraltılır; trade mantığı için tek kapı ADR-0003 + Karpathy-1/3 | GO-doc |
| X10 | "NET-cost gate = Edge Measurement Core" ↔ EMC canlıda ölü | `CLAUDE.md:40` ↔ `config:468`, `safe_orchestrator.py:1497→1567`; gerçek araç `CLAUDE.md:49` | İki ölçüm aracı tek isimde | İlke 4: offline gate = `backtest.cli`; forward = gölge logları; EMC "v2'de veri üretmez" | GO-doc (hook taşıma GATED) |
| X11 | GO eşiği kodda/dokümanda tek yerde yok | Wave-2 (OOS PF ≥1.30, ≥4/5 sembol), T-09 (n≥30, IS+OOS>0), FVG spec `:104-109` ↔ `backtest/comparison.py:26-32` (bayat v1↔v2), `scripts/evaluate_backtest_gates.py:2` (kırık HERMES §6 atfı) | Her inisiyatif kendi eşiğini yazdı | ADR-0011 "Edge GO kriteri" (§5.4) | GO-doc (gate script'i GATED) |
| X12 | Dört maliyet modeli | `backtest/slippage.py:8-10` + config ↔ `engine/edge_costs.py:4-14` ↔ `fvg_entry.py:25-27` ↔ T-09 `counterfactual.md:34` | Araçlar ayrı yazıldı | ADR-0011'de kanonik maliyet = backtest config; her raporda zorunlu maliyet satırı | GO-doc (tek kaynak kodu GATED) |
| X13 | FVG gölgesi operatör SL tarifini ölçmüyor | Operatör 11-07/11-08/11-13 ifadeleri (07 §5.1) ↔ `fvg_entry.py:121-124`; spec `:35` "✅" | Spec eşlemesi sapmayı işaretlemedi | `docs/STRATEGY_INTENT.md` sapma tablosu; gölgeye ikinci SL varyantı | GO-doc / GATED |
| X14 | Bias TF: canlı 12h ↔ operatör 1d → yok → 4h | `safe_orchestrator.py:1256-1258` ↔ transcript 11-07, 11-08, 11-13 | Niyet sürüklenmesi | Niyet dokümanında "güncel: 4h (11-13)"; canlı 12h dokunulmaz; 4h FVG gölgesinde ölçülür | GO-doc / operatör sorusu |
| X15 | Sweep ön koşulu + iki implementasyon | efloud `fvg_entry` (sweep yok) ↔ u2Algo-Trade `pin_fvg_touch` (sweep'li) | Tek kanonik niyet dokümanı yok | STRATEGY_INTENT.md kanonik; her implementasyon sapma satırı | GO-doc / operatör sorusu |
| X16 | "10 pozisyon" ↔ efektif ≤4 | `config:47,272`, `README.md:135-136` ↔ `position_guard.py:271-282` × 6.0 × ~$403 | Bakiye $1363 → $403 sonrası yorum güncellenmedi | Dokümana formül: ⌊6 × bakiye / 500⌋. Tavan yükseltilmez | GO-doc; artırma NO |
| X17 | Acil halt dokümante ↔ eşik 0; kural "değişmez" | `config:13,50,56,401-402` ↔ `:424`; `HERMES.md:379`, `skills/efloud-incident/SKILL.md:13` | `b2154c5` sonrası başlık kaldı; kural geri açmayı da yasaklıyor | İfade "operatör onayı olmadan değiştirilmez" olur (korumanın geri açılmasına izin verir) | GO-doc |
| X18 | Ardışık kayıp "HALTED" ↔ TRIPPED 120 dk | `HERMES.md:237` ↔ `breaker.py:320-327` | Runbook hatası | HERMES'e breaker durum tablosu | GO-doc |
| X19 | Ölçümsüz gevşetmeler ↔ ölçülmüş kanıt | `config:141` (12.0, yorum "6.0 seçildi"), `:168` (6.0), cap 6, recency 168, BOS `658a905`, Po3 `:131` ↔ counterfactual `:11-13` | Frekans talebi backtest'siz uygulandı | Tek tek NET ölçüm; kanıt çıkmazsa ölçülmüş değere dönüş operatöre sunulur | GATED |
| X20 | Max-hold 0 ↔ "48h daha kötü" notu | `config:405,407` ↔ `collab/log/claude-code.md:319` (−46 → −12) | İki ölçüm farklı motor/pencere | Göreli KANITLI (zayıf); lux akışında ≥90 gün 36h vs 0 tekrarı | GATED |
| X21 | ADR-0009 "edge'i korur" ↔ teyitli akış NET negatif | `docs/adr/0009-…:28` ↔ counterfactual `:42,54` | Haziran motoru ≠ bugünkü motor | ADR'ye 2026-11 notu: "göreli zarar azaltır (baz −0.30 vs −0.75); mutlak edge yok" | GO-doc |
| X22 | PINE_SPEC §0-14 (CHoCH-only, shadow, timeout 8, cap 3, v1 fallback) ↔ canlı | `pine/PINE_SPEC.md:3,19,98-150,292` ↔ `658a905`, `setup_state.py:34`, `config:95,158,207` | Spec üstü eski, §20 güncel | Üste durum tablosu + "§0-§14 TARİHSEL", §19 SUPERSEDED, §20'ye GATE FAIL×3 | GO-doc |
| X23 | Pine lab MAX_HOLD 36 h ↔ canlı 0 | `pine/lab/tail_strategy.pine:5,112` ↔ `config:407` | Pine 11-06'da dondu | "0 = off" girdisi + config-eşitlik testi | GATED (Pine kodu) |
| X24 | TF zinciri yorumları | `docker-compose.prod.yml:42,72`, `config.phase2_scalp_1k.yaml:2,4`, `pine/publish/efloud_signals_v2_en.pine:20-29`, memory ↔ `data/timeframes.py:24-28` | `3c96029` sonrası yorumlar kaldı | Publish paketi ARŞİV etiketi (doc); compose/config yorumları ayrı PR | GO-doc / GATED |
| X25 | `collab/STATUS.md` "güncel durum" ↔ 7 gün bayat | `CLAUDE.md:3,48` ↔ `STATUS.md:10-11`, log son giriş | Elle güncelleme | STATUS güncellenir; deploy-log şablonuna zorunlu madde; drift testi önerisi | GO-doc (+test GATED) |
| X26 | Hermes'in üç tanımı; var olmayan `agents/tasks/`, TASKBOARD | `HERMES.md:49-58`, `§14` ↔ `collab/models/hermes.md` | Eski orkestrasyon kalıntısı | Tek tanım collab; HERMES.md operatör runbook'una dönüşür | GO-doc |
| X27 | ECC kuralları ↔ repo gerçeği | 800 satır / %80 coverage / planner-tdd-guide / commit biçimi ↔ `safe_orchestrator.py` 3361 satır, CI'da coverage kapısı yok, `.gitignore:122`, `collab/README §2` | ECC genel paket; `.claude/` repo dışı | `docs/engineering-rules.md` override tablosu (Karpathy > ECC) | GO-doc |
| X28 | Alerter/canary yalnız V1 ↔ 3 bot konteyneri | `docker-compose.prod.yml:147-166`, `scripts/canary.py:25` ↔ V2/V3 Up | Sidecar'lar tek bot için yazıldı | STATUS'a kapsam notu; genişletme ayrı iş | GO-doc / GATED |
| X29 | V2/V3 breaker kalibrasyonu ve profil kusurları | `config.phase2_long_1k.yaml:188,214` (582/472), scalp `:200,222`; long/scalp'ta proxy ATR, Po3/BT-23/25 yok ↔ test yalnız prod | Düzeltmeler yalnız mid'e uygulandı | "Restart öncesi şart listesi" dokümante; test genişletme + profil backtest'i | GO-doc / GATED |
| X30 | Deploy yüzeyi: ölü hostlar, tam-stack `deploy.sh`, panel compose dışında | `deploy/Caddyfile:13,30,46,91`, `deploy/deploy.sh:21-25`, `docker-compose.panel.yml` ↔ `skills/efloud-deploy/SKILL.md:12`, ADR-0001 | VPS taşınması sonrası temizlik yok | Skill ve runbook metni tek-servis `--no-deps` akışına hizalanır; Caddy/compose/script ayrı PR | GO-doc / GATED |
| X31 | Journal setup atfı yapamıyor | `safe_orchestrator.py:689-692` (`htf_bias=""`, `confluence_score=0`) ↔ BT-22 "yol-agnostik" kanıtı | v2 yolu journal alanlarını doldurmuyor | Journal'a `engine_path` + lux etiketleri | GATED |
| X32 | Ana checkout 81 commit geride; memory bayat | Oturuma yüklenen CLAUDE.md ↔ worktree `CLAUDE.md` (76 satır); memory TF/URL/"v1 aktif" | Paylaşılan checkout'ta WIP | Operatör işi: ff veya oturumları worktree'den açma kuralı; memory "as-of" temizliği | Operatör (repo dışı) |

---

## 3. Algoritma & setup soyağacı (kronolojik)

| Tarih | Düğüm | PR / SHA | Ne değişti · neden | Sonuç / edge | Durum |
|---|---|---|---|---|---|
| ≤2026-05 | **v1 confluence** (`engine/signals.py`): CHoCH/BOS anında MARKET, 0-100 skor, SL son swing + ATR, Fib TP | — | İlk motor | Wave-2 falsifikasyonu OOS PF 1.165 < 1.30 (yalnız komisyon) → gate'i geçemedi | Hesaplanıyor, giriş SUSTURULMUŞ |
| 05-14 | Reverse-on-profit guard | `0622849` | FIL auto-flip olayı | Edge konusu değil | v1-only → canlıda ÖLÜ (canlı: karşı yön RED) |
| 05-23→24 | **SMC v2 efloud triggers**: CHoCH → FVG/OB/OTE bölge → pullback → engulfing; yapısal SL | 15 PR, `3fa88b8` | "CHoCH barında giriş, R:R orantısız" şikâyeti | BT-sweep5 R/trade −0.257 (`config:412`) | Lux açıkken BYPASS (ölü yol) |
| 06-04 | `min_confluence` 80→50 | `38ec7cc` | "Daha çok işlem" | Fee'siz kanıt, kaynağı silinmiş | v1'de; canlıda inert |
| 06-13/17 | Pine strateji / Wave-2 premium | ADR-0005, #220 | Ürün denemesi | NO-GO / DROP | DROPPED; ürün indicator-only |
| 06-15 | Teyitsiz MARKET (`require_confirmation:false`) | ADR-0009, #205 | Slippage inisiyatifi | PF 0.62 (n=26) vs 1.41 | ÇÜRÜTÜLMÜŞ; teyit zorunlu kaldı |
| 06-18 | Edge Measurement Core | #227 | Forward ledger | Altyapı var, veri yok | ÖLÜ (flag off + v1 dalı) |
| 06-19 | SL/TP redesign bayrakları | `073a485` (yalnız lokal branch) | Yapısal SL / ara TP | net PF ≤1.25; `tp_intermediate` yönsel negatif | NO-GO; master'da yok |
| 07-06/07 | TF merdiveni; v2 canlı | `3c96029`, `444cd11` | mid 15m/4h/12h; shadow:false | — | CANLI temel |
| 07-18/25 | C1 `anchor_time_axis`, C2 `confirm_last_bar_only` | `config:110-118` | Zaman ekseni / son bar teyidi | NET −0.015 R | ÇÜRÜTÜLMÜŞ; default OFF |
| 07-24 | Fixed $50 × 10x | `1c20e22` | Operatör talebi | Risk kararı | CANLI |
| 07-26 | BT-22 gerçek ATR + 5 ATR tavan; `min_sl_atr 2.0`; BT-23 = 6.0 | `3d4370f` | SL sınırları bağlasın | 2.0 taban göreli KANITLI; BT-22 in-sample (KANITSIZ) | CANLI (yalnız mid) |
| 09-30 | OB/BB'den giriş + Po3 kapısı | `242cef3`, `a2f7890` | Efloud price-action notları | Po3 ölçümsüz | Po3 CANLI (mid), KANITSIZ |
| 10-01 | v1 mute; acil halt 0; volatil giriş; overshoot 0.5→2.0 | `b2154c5`, `228382d` | "Anında giriş" ve kalıcı HALT şikâyeti | Ölçümsüz | CANLI |
| 10-02/03 | **BOS setup'ları**; cap 6; recency 168; overshoot 6.0 | `658a905`, `4417e90`, `ad41004` | "Bot girmiyor" | Ölçümsüz | CANLI, KANITSIZ |
| 10-31 | Backtest modülü silindi | `562a6a3` | Repo sadeleştirme | Ölçüm kör dönemi | 11-07'de geri geldi |
| 11-01/02 | **LuxAlgo modu canlı**; anchor yalnız OB ucu; `max_entry_dist_atr` 12 | `38508f7`, `6a8c0cf`, `eb01f40` | "luxalgo mantığını kullanalım" | Sonradan: −0.30 R, PF 0.65 / PF 0.69 | **CANLI, ÇÜRÜTÜLMÜŞ** |
| 11-04 | Kapı karşı-olgusu (T-09) | #277 | "Grafikteki bölgelerden girsin" | Gevşetme −0.17…−0.32 R; mitige-OB +0.24 R (n=30) | Gevşetme NO-GO; mitige-OB takip adayı |
| 11-05 | touch_entry gölgesi | #280 | Fitil/temas girişi | Ölçüm yok; P2 analoğu −0.04/−0.75 R | SHADOW, KANITSIZ |
| 11-06 | Pine Lab baseline | `bfcae56` | Parity + indikatör ürünü | GATE FAIL ×3; BTC PF 0.73 | Ürün kaynağı (indikatör) |
| 11-07 | Backtest restore + parity | #335, #336 | Ölçüm aracı | 8/10 canlı giriş eşleşti | Araç KANITLI |
| 11-07/08 | ICT Kılçık, Sweep CHoCH (4h/1h/15m), Pin→sweep→5m CHoCH→FVG | `4b626ff` (lokal branch) | Operatörün yeni setup tarifleri | net −0.09…−0.33 R | ÇÜRÜTÜLMÜŞ; merge edilmedi |
| 11-08 | Max-hold 36h → 0 | `59c32f3`, #339 | Operatör kararı | −46 → −12 $ (41g, 4 sembol) | CANLI; göreli KANITLI (zayıf) |
| 11-09→13 | `pin_fvg_touch` ± Kronos forward A/B (u2Algo-Trade) | ayrı repo | "Basit setup + Kronos" | Holdout'lar negatif; forward 0 kapanış | Testnet forward; KANITSIZ (repo dışı, DOĞRULANMADI) |
| 11-14 | **FVG pullback gölgesi** (4h bias, FVG limit, OB çapalı `calc_sl`, OB/BB TP1, likidite TP2) | #343, `c05260c`/`bf464d0` | Operatörün 11-13 tarifi | Offline ≈ 0.00 R, n=85, WR %30.6 | SHADOW, KANITSIZ |

Okuma: her düğüm bir öncekinin şikâyetine yanıt; hiçbiri NET-cost kapısını geçerek canlıya girmedi (BT-23=6.0 ve `min_sl_atr` hariç). Negatiflik motor değiştikçe sürdü → ortak etken motorun kendisi değil **maliyet/R oranı ve giriş kalitesi**.

---

## 4. Sentez: çelişen trade mantıklarının uzlaştırılması

| Çelişen çift | Niyet (çerçeve) | Ölçüm (filtre) | Korunan / atılan | Etiket |
|---|---|---|---|---|
| **Giriş: OB + engulfing + MARKET** ↔ **FVG'ye limit** ↔ **temas** | "FVG boşluğundan girecek" (11-13); temas daha çok işlem verir | Engulfing+MARKET −0.30 R; teyitsiz baz limit −0.75 R; FVG limit ≈ 0.00 R (farklı maliyet) | Hedef modelde **FVG limit** korunur (niyet + maker giriş maliyeti düşürür). Temas girişi atılır. Engulfing "isteğe bağlı kalite filtresi" olarak ölçülür | FVG limit KANITSIZ; temas ÇÜRÜTÜLMÜŞ |
| **Bias 12h** ↔ **4h** ↔ **1d** ↔ **yok** | Son söz: "15m girecekse 4h bias" | 12h'e ters girişler −0.31 R (kapı koruyucu); 4h hiç NET ölçülmedi; biassız 15m sweep varyantları −0.22…−0.33 R | "Bias var" korunur, "bias yok" atılır. TF = 4h hipotezi gölgede ölçülür; canlı 12h dokunulmaz | Bias kapısı KANITLI (göreli); 4h KANITSIZ; biassız ÇÜRÜTÜLMÜŞ |
| **SL: ATR bantlı** ↔ **likidite/OB'nin %0.2 ötesi** | Altı kez: "ATR değil" | 2 ATR taban R/trade'i iyileştirdi; %0.2 sweep ötesi SL'li 15m varyantları net negatif; maliyet ~0.27 R @ SL %0.72 | Çapa niyetten alınır (OB / süpürülen uç + %0.2). ATR tabanı "ATR kuralı" olarak değil **maliyet bütçesi** olarak tutulur: SL mesafesi maliyet/R ≤ eşik sağlamıyorsa işlem alınmaz. İki varyant yan yana gölgelenir | Saf yapısal dar SL: ÇÜRÜTÜLMÜŞ-yönlü; ATR tabanı KANITLI (göreli); hibrit KANITSIZ |
| **TP: en yakın ≥1.8R lux adayı** ↔ **TP1 sonraki OB/BB, TP2 yön likiditesi** | 11-13 tarifi | İkisi de ayrı ölçülmedi; `tp_intermediate` yönsel negatif | Niyet tarifi hedef modele alınır; `min_rr 1.8` kapısı korunur | KANITSIZ |
| **"Daha çok işlem"** ↔ **kapılar** | Sürekli şikâyet | Elenen her kategori NET negatif; huninin ana kaybı exposure reddi (11/22) | Kapılar korunur. Frekans çözümü kapı gevşetmek değil; exposure/sizing uyumu risk kararı olarak sunulur (artırma önerilmez) | Kapılar KANITLI; gevşetme ÇÜRÜTÜLMÜŞ |
| **BOS + CHoCH** ↔ **yalnız CHoCH** | "CHoCH-BOS kırılımı sonrası" | BOS ayrı ölçülmedi | İkisi de kalır; journal etiketiyle ayrı raporlanır | KANITSIZ |
| **Sweep ön koşulu** var ↔ yok | 11-07/08 var; 11-13 tarifinde yok | Sweep'li varyantlar (S7–S9, pin_fvg_touch) negatif | Hedef modelde zorunlu değil; "SWEEP" bir confluence etiketi olarak kaydedilir | KANITSIZ (zorunlu sweep ÇÜRÜTÜLMÜŞ-yönlü) |
| **Max-hold 36h** ↔ **0** | Kaldır (11-08) | −46 → −12 $ (zayıf); eski not "48h daha kötü" | 0 kalır; daha uzun pencerede yeniden ölçülür; funding uyarısı sürer | Göreli KANITLI (zayıf) |
| **Acil halt 0** ↔ mutlak taban | Kalıcı HALT istemiyor | Negatif beklentili akışta mutlak taban yok | Niyete saygı: HALT geri getirilmez; "TRIP + uyarı" tipi taban default-OFF önerilir | Risk kararı |
| **10 pozisyon** ↔ **≤4** | 10×$500 | Tavan fiilen koruyucu | Tavan yükseltilmez; doküman düzeltilir | — |
| **Teyit şart (ADR-0009)** ↔ "teyit değer katmıyor" (P2 −0.04 R) | — | Popülasyonlar farklı: baz setuplarda teyit açık ara iyi (−0.30 vs −0.75); −0.04 yalnız teyit almayan dokunuşlarda | ADR-0009 kalır, gerekçesi "göreli" diye düzeltilir | KANITLI (göreli) |
| **efloud `fvg_entry`** ↔ **u2Algo `pin_fvg_touch`** | Aynı öz | pin_fvg_touch holdout'ları negatif; fvg_entry ≈ 0 | Kanonik niyet tek dokümanda; efloud gölgesi ana ölçüm hattı önerilir (operatör teyidi §8) | KANITSIZ |
| **v1 skor ≥50** ↔ **lux konsept sayısı ≥1** | — | v1 susturulmuş; swing OB kapıyı otomatik geçiyor (`luxalgo.py:477-478`) | Dokümanlarda iki kavram ayrılır; lux kapısının fiilen yalnız internal kırılımı süzdüğü yazılır | Bilgi |

---

## 5. HEDEF SETUP & ALGORİTMA MODELİ ("asıl yapılmak istenen")

### 5.1 Tek paragraf tez

4h yapısal yön doğrultusunda, 15m'de bir CHoCH/BOS kırılımının bıraktığı **FVG'ye geri çekilmede limit emirle** girilir; stop, kırılımı yapan OB'nin (veya süpürülen likidite ucunun) **biraz ötesine** konur; TP1 yoldaki ilk karşı OB/BB, TP2 işlem yönündeki likiditedir; işlem yalnız R:R ≥ 1.8 ve **maliyet/R bütçesi** içindeyse alınır. Operatörün kendi sözüyle: "FVG boşluğundan işleme girecek, SL likidasyon noktasının biraz uzağına atılacak, bütün mesele bu." Ölçümün bu teze eklediği tek zorunlu şart şudur: bugüne dek ölçülen her varyantta brüt sonuç sıfır civarında, zararı maliyet üretiyor; dolayısıyla model ancak maker giriş + yeterli SL mesafesi + koruyucu kapılarla NET pozitif olabilir ve **bu henüz kanıtlanmadı**. Model bir hipotezdir; bugün canlıya alınacak bir tarif değildir.

### 5.2 Pipeline

| Adım | Kural | Parametre (öneri) | Kaynak: niyet · kod | Etiket |
|---|---|---|---|---|
| 1. HTF bias | 4h LuxAlgo swing trend; UNDEF → işlem yok | `swing_length 50` (4h) | "15m girecekse 4h bias" (11-13) · `safe_orchestrator.py:2363` (gölge), canlı 12h `:1256-1258` | Bias kapısı KANITLI (göreli, 12h'te); 4h KANITSIZ |
| 2. Tetik (15m yapı) | Bias yönünde swing/internal CHoCH veya BOS, son 168 bar | `kinds [CHoCH,BOS]`, recency 168 | "choch-bos kırılımı sonrası" · `luxalgo.py:527-535`, `config:200,293` | Recency kapısı KANITLI (göreli); BOS KANITSIZ |
| 3. Bölge | Kırılımın OB'sinden sonra, kırılım+2 bar içinde oluşmuş, mitige olmamış FVG | `FVG_AFTER_BREAK_BARS 2` | "FVG boşluğu veren mum yapısı yeterli" (11-08) · `fvg_entry.py:28,58-64` | KANITSIZ |
| 4. Giriş | FVG yakın kenarına **limit** (LONG üst, SHORT alt); fiyat kaçarsa iptal; timeout 48 bar | timeout 48, `ran_away` | "Geri çekilmede FVG limit" (11-14) · `fvg_entry.py:118` | KANITSIZ (≈0.00 R, n=85); teyitsiz OB-kenarı limit ÇÜRÜTÜLMÜŞ (−0.75 R) |
| 5. Filtreler | (a) premium/discount; (b) maliyet bütçesi: tahmini RT maliyet / SL mesafesi ≤ eşik; (c) Po3 MANIPULATION; (d) mesafe kapıları; (e) dedup + cap | (a) açık; (b) eşik ölçümle; (c)-(d) ölçülene dek gölgede etiket | Niyette yok, ölçümden · `luxalgo.py:536-547`, `safe_orchestrator.py:2475-2489,2697-2781` | (a) KANITLI (göreli, lux akışında; FVG'de ölçülmedi); (b) gerekçesi KANITLI, eşik KANITSIZ; (c)(d) KANITSIZ |
| 6. SL | Varyant A (bugünkü gölge): OB ucu ∓ 0.5 ATR, 2 ATR taban, 5 ATR tavan (RED). Varyant B (niyet): OB ucu / süpürülen uç ∓ %0.2, tavan RED, taban yerine 5(b) bütçesi | A: `config:294,412-413`; B: `%0.2` | "ATR'ye göre değil … %0.2 ötesi" (6 kez) · `sl_calc.py:56-78`, `fvg_entry.py:121-124` | A: taban KANITLI (göreli), tavan KANITSIZ; B: KANITSIZ (benzeri S8 ÇÜRÜTÜLMÜŞ) |
| 7. TP1 | Yoldaki ilk karşı OB veya BB; R ≥ `min_rr` değilse setup alınmaz | `min_rr 1.8` | "TP1 bir sonraki OB-BB", "R:R > 1.8" · `fvg_entry.py:67-79`, `safe_orchestrator.py:3058` | KANITSIZ |
| 8. TP2 | TP1'in ≥0.5R ötesindeki, işlem yönündeki EQH/EQL / swing likiditesi (0.15R içeride) | `tp_wick_buffer_r 0.15` | "TP2 yön likiditesi" · `fvg_entry.py:82-95`, `luxalgo.py:575-633` | KANITSIZ |
| 9. Yönetim | TP1'de %50 kapat → SL başa baş → TP2; süre sınırı yok, 24 saatte uyarı | `max_holding_hours 0`, `hold_alert_hours 24` | 11-08 kararı · `engine/lifecycle.py:405-413`, `config:407,410` | Max-hold 0 göreli KANITLI (zayıf); TP1 %50+BE ayrı ölçülmedi (KANITSIZ) |
| 10. Invalidation | Dolmadan: timeout, fiyat kaçması, FVG/OB mitige. Dolduktan sonra: SL | — | — · `fvg_entry.py` (`ran_away`), spec `:90` | KANITSIZ |
| 11. Risk çerçevesi (değişmez) | Breaker (günlük %10, haftalık %25, 3 ardışık), exposure 6x, drift %1, SL < likidasyon, %5 risk tavanı, orphan koruması | mevcut | — · `breaker.py`, `position_guard.py`, `exchange/__init__.py:1086-1106` | Guard; zayıflatılmaz |
| 12. Yedek aday | Mitige-OB / breaker retest + engulfing | — | — · counterfactual `:52` | KANITSIZ (umut verici; +0.24 R, n=30) |

### 5.3 Bugünkü canlı davranıştan farklar

| Boyut | Canlı (S1) | Hedef model | Fark türü |
|---|---|---|---|
| Bias TF | 12h | 4h | Parametre |
| Giriş bölgesi | Kırılımın OB'si | Kırılımın FVG'si | Mantık |
| Giriş tetiği | Bölge içi engulfing kapanışı | Bölge kenarına limit (teyit mumu yok) | Mantık |
| Emir türü | MARKET (taker) | LIMIT (maker) | Execution — yeni emir yolu gerekir |
| Premium/discount, `min_confluence` | Zorunlu | Gölgede yok; (a) filtresi olarak ölçülmeli | Filtre |
| SL | OB ucu ∓ 0.5 ATR, 2–5 ATR | Aynı çapa; ATR tabanı yerine %0.2 + maliyet bütçesi (B) | Mantık |
| TP1 / TP2 | En yakın ≥1.8R herhangi lux adayı / sonraki aday veya Fib | Karşı OB-BB / yön likiditesi | Mantık |
| Maliyet profili | ~0.27 R/işlem (ölçülmüş) | Daha düşük (maker giriş) — ölçülmedi | Beklenti |
| Kod durumu | Canlı emir | Yalnız log (`live` değeri kodda yok) | — |

### 5.4 Doğrulama planı (her KANITSIZ bileşen için kapı)

**Ortak GO kriteri (ADR-0011 önerisi):** (1) maliyet = backtest config modeli (taraf başına %0.04 + funding + 5/10/5 bp slippage); limit girişte yalnız giriş bacağı maker sayılır; (2) sabit pencere ucu + git SHA; (3) n ≥ 100 işlem/kol offline (≥180 gün × 10 sembol), n ≥ 30 kapanış/kol forward; (4) IS ve OOS NET ort. R > 0; (5) OOS NET PF ≥ 1.30; (6) sembollerin ≥ %60'ı pozitif; (7) aynı pencerede baz koldan iyi **ve** mutlak eşikler sağlanmış ("canlı v2'den iyi" tek başına yetmez, çünkü baz negatif); (8) çoklu deneme notu: denenen varyant sayısı raporda yazılır.

| Bileşen | Kapı | Eşik |
|---|---|---|
| FVG limit girişi (adım 3-4) | Offline 180g+ (kanonik maliyet) → forward gölge | Ortak kriter; forward ≥30 kapanış NET>0 + PF ≥1.30 |
| 4h bias (adım 1) | Aynı FVG akışında 4h ↔ 12h A/B | ΔNET > 0, IS+OOS |
| SL varyant A ↔ B (adım 6) | Gölgede iki SL aynı setup'a yan yana loglanır + offline A/B | B, A'dan iyi ve mutlak kriter |
| Maliyet bütçesi eşiği (5b) | Offline tarama (ör. 0.10 / 0.15 / 0.20 R) | En az iki komşu eşikte tutarlı iyileşme |
| Premium/discount FVG akışında (5a) | Offline açık/kapalı A/B | ΔNET > 0 |
| TP1 OB/BB, TP2 likidite (7-8) | Offline ↔ lux TP havuzu | ΔNET > 0, PF ≥1.30 |
| Po3; `max_entry_dist_atr` 12 ↔ 6; overshoot 6 ↔ 2; cap 6 ↔ 3; recency; BOS | Canlı akışta tek tek A/B | Kanıt yoksa ölçülmüş/önceki değere dönüş operatöre sunulur |
| Max-hold 0 | ≥90g × 10 sembol, 36h ↔ 0 | ΔNET > 0 ve funding payı raporlanır |
| Mitige-OB retest (12) | ≥180g yeniden ölçüm → gölge | n ≥ 100, ortak kriter |
| Long/scalp profilleri | Profil başına backtest (gerçek ATR + kapılar) | Restart ön koşulu |

---

## 6. CANLI KARARLARI

### 6.1 GO — doküman PR'ına girecekler

Kural: yalnız `.md` dosyaları; kod, config, compose, Caddy, Pine kaynakları **dokunulmaz**. Sayı yerine `config:satır` / `path:line` referansı. Öneri: iki PR — **PR-A (olgu düzeltmeleri)**, **PR-B (mimari)**. PR-B öncesi `git grep -n "HERMES.md\|AGENTS.md" tests scripts .github` ile test bağımlılığı kontrol edilir (bu denetimde yapılmadı).

**PR-A — olgu düzeltmeleri**

| # | Dosya | Değişiklik | Gerekçe |
|---|---|---|---|
| A1 | `CLAUDE.md:17,20,29,39` | Pine hedefi: ürün `pine/lab/*` → `efloud_lab*.pine` (`scripts/build_pine_lab.py --check`); strategy = parity artefaktı; eski çiftler ARŞİV; koruma hedefi `pine/lab/core.pine` + `engine/smc_v2/luxalgo.py` | X8 |
| A2 | `CLAUDE.md:3,20-26` | "Python'u değiştirme" kuralı Pine-çeviri görevine daraltılır; kırık "Runtime Agent Team" işaretçisi ADR-0002'ye çevrilir; "GeminiClient" → "ortak LLM istemcisi (ad tarihsel)" | X9, 06 C9/C10 |
| A3 | `CLAUDE.md:40` | İlke 4: offline gate = `backtest.cli`; forward = gölge logları; EMC "flag kapalı, hook v1 dalında" | X10 |
| A4 | `CLAUDE.md:57-67` | Bölüm "v1 referansı (canlıda susturulmuş)" olarak işaretlenir ve PINE_SPEC'e taşınır; yerine 5 satırlık "Canlı motor" pointer'ı; Daily filtre ve slope fallback cümleleri v1'e bağlanır | X7 |
| A5 | `AGENTS.md:11-22,75` | "Güncel Algoritma Durumu (2026-10-02)" bloğu kaldırılır → CONTEXT.md + STATUS.md linki; "Backtest kaldırıldı" silinir | X1–X4 |
| A6 | `README.md:28-30,135-136` | Giriş akışı: lux OB retest → engulfing → MARKET; SL OB ucu; TP lux havuzu. "en çok 10 pozisyon" → formül | X1, X2, X16 |
| A7 | `HERMES.md` | Breaker durum tablosu (günlük/ardışık = TRIPPED, haftalık = HALTED, acil = kapalı); bayat SHA/tarih blokları STATUS'a yönlenir; `:379` ifadesi "operatör onayı olmadan değiştirilmez" | X17, X18 |
| A8 | `skills/efloud-incident/SKILL.md:13` | Aynı ifade düzeltmesi | X17 |
| A9 | `CONTEXT.md:18,27,36` | Confirmation = 15m engulfing kapanışı; v1 skor ↔ lux konsept sayısı; iki yollu zincir; "Shadow" genişletilir; yeni tablolar: setup durum matrisi (§3 özeti) ve "canlıda etkili / inert anahtarlar" (X6) | X6, 07 C7/C8 |
| A10 | `collab/STATUS.md` | master `81c2cf7`, VPS `bf464d0`; LuxAlgo "ölçüldü, NET negatif"; gölgeler + go-live barları; alerter kapsamı "yalnız V1"; V2/V3 durumu açık soru; efektif pozisyon tavanı | X25, X28 |
| A11 | `pine/PINE_SPEC.md` | Üste durum tablosu (bölüm → dosya → canlı/arşiv); "§0-§14 TARİHSEL"; §14, §19 SUPERSEDED; §20'ye GATE FAIL×3 ve max-hold sapması notu; RE10045 notu "Tuzaklar"a | X22 |
| A12 | `docs/adr/0009-…`, `0005-…` | 2026-11 notları: teyit göreli koruyucu, mutlak edge negatif; Wave-2 PF'si LuxAlgo öncesi motora ait | X21 |
| A13 | `CHANGELOG.md:18` | "Backtest kaldırıldı" → "kaldırıldı (562a6a3), geri yüklendi (#335)" | X4 |
| A14 | `agents/strategist.md:34-35`, `agents/pine-engineer.md`, `agents/risk-manager.md:24` | Ölçüm araçları listesi (backtest.cli, pine_lab_parity, fvg_shadow_report) + maliyet satırı; pine-engineer ADR-0005'e; risk-manager fixed sizing + efektif tavan | 04 #2, 02 §6 |
| A15 | `scripts/ci/agents/smc-strategy-reviewer.md:25-40` | Canlı kapı seti (lux `min_confluence`, premium/discount, `risk.min_rr`, BT-23/25, Po3, SL ATR bandı); "rejim kapısı v2'de yok"; "dedup/re-emit etkisi?" maddesi. Not: CI reviewer davranışını etkiler; trade mantığını değil | 01 C7 |
| A16 | `skills/luxalgo-smc/SKILL.md`, `skills/efloud-deploy/SKILL.md`, `skills/social-publishing/SKILL.md`, `skills/efloud-railway-supabase/SKILL.md`, `skills/tradingview-mcp/SKILL.md` | Sırasıyla: teyit/emir/SL kuralları + profil farkları; tek-servis `--no-deps` akışı ve "tam-stack = 3 mainnet bot" uyarısı; container-gerçekçi zamanlama + doğrulanamayan test sayısının kaldırılması; hedefin `u2algo-site`'a daraltılması; RE10045 / UDF `[off]` tuzakları | 01, 03, 05 |
| A17 | `docs/runbooks/crash-loop-recovery.md:30,92`, `disaster-recovery.md:48` | Ölü host yerine `scripts/canary.py:25`'teki güncel host veya container içi healthz | 05 #4 |
| A18 | `pine/publish/PUBLISH_efloud_signals.md`, `pine/u2algo/WAVE1_SPEC.md`, `docs/pine-lab/README.md` | "SUPERSEDED 2026-11-06 / ARŞİV" başlığı; pine-lab'a "SON DURUM" bölümü | 03 #6, #7, #10 |

**PR-B — mimari (§7)**

| # | Dosya | Değişiklik |
|---|---|---|
| B1 | `docs/adr/0011-edge-go-criteria.md` (yeni) | §5.4 ortak GO kriteri + kanonik maliyet modeli |
| B2 | `docs/research/DECISIONS.md` (yeni) | 04 §5.1 karar kronolojisi + §3 soyağacı; her satırda `git show <sha>:<path>` kanıt yolu |
| B3 | `docs/STRATEGY_INTENT.md` (yeni) | Operatörün tarihli ifadeleri (07 §5.4) + §5 hedef model + her implementasyonun sapma tablosu (canlı S1, `fvg_entry`, `pin_fvg_touch`) |
| B4 | `docs/engineering-rules.md` (yeni, ≤60 satır) | ECC ↔ proje override tablosu: Karpathy > ECC; dosya boyutu kuralı yalnız yeni kod; kapı = regression ledger + TESTS.md; commit biçimi `collab/README §2`; hayalet agent referansları yok |
| B5 | `docs/runbooks/backtest-gate.md` (yeni) | Sabit pencere ucu, sembol başı paralel `single`, `backtest:` bloğu yoksa BRÜT koşar uyarısı, Windows standby notu |
| B6 | `HERMES.md` → `docs/runbooks/operator-runbook.md` | §2/§5b/§5c/§13/§14 çıkarılır (history'ye); `docs/OPERATOR_GUIDE.md` ile birleştirilir; kökte 10 satırlık yönlendirme |
| B7 | `CLAUDE.md` | §7'deki iskelete indirgenir; Cowork uyarısı ve TV MCP bölümü runbook/skill'e |
| B8 | `TESTS.md` | "missing" satırları: verify algo-fetch reprodüksiyonu, re-emit reprodüksiyonu, v1-only anahtar sözleşmesi, 3 config breaker kalibrasyonu, docs↔config drift, ledger hook v2 erişimi |
| B9 | Kanıt kurtarma | SL/TP NO-GO raporu (`073a485`) ve ICT/sweep değerlendirme raporları (`4b626ff`) `docs/history/`'ye doküman olarak alınır. Not: ikisi de yalnız operatör makinesindeki lokal branch'lerde; taşımayı operatör/ana oturum yapar |

### 6.2 GATED — trade mantığı / execution / ölçüm önerileri (bu turda canlıya GİTMEZ)

Her biri: failing test → cerrahi diff → risk-ops → (edge ise) NET-cost gate → operatör onayı. Yeni davranış default-OFF.

| Ö | Değişiklik | Beklenen etki | Gerekli kapı | Flag önerisi |
|---|---|---|---|---|
| 1 | `_fetch_protection_order_ids`: algo okuma hatasında `ok=False` (`exchange/__init__.py:1842-1850`) | Korumalı pozisyonun yanlış kapatılması / çift SL riski kalkar; guard güçlenir | Reprodüksiyon testi + risk-ops + operatör | Bug fix; flag gerekmez |
| 2 | CONFIRMED sonrası yeniden-emit / bayat teyit (`setup_state.py:121-126`, `confirmation.py:72-97`) | Reddedilen setup'ın tekrar denemesi ve TP sonrası bayat fiyatla yeniden giriş engellenir | Önce reprodüksiyon (hata doğrulanmadı); sonra NET A/B (işlem kümesini değiştirir) | `smc_v2.block_reemit_after_confirm: false` |
| 3 | Journal'a `engine_path`, kırılım türü, lux etiketleri, bias; ledger hook'unu v2 emir yoluna taşıma | Setup bazında edge atfı; forward ölçüm | TDD + byte-identical trade çıktısı | Mevcut `signal_ledger.enabled` |
| 4 | Tek maliyet kaynağı + `DEFAULT_GATES`'e NET/OOS kapısı + CLI `--end` | Karşılaştırılabilir, tekrar üretilebilir kararlar | TDD (araç kodu) | — |
| 5 | FVG gölgesi: SL varyant B (%0.2 yapısal) yan yana log; kanonik maliyetle `net_r`; gölge defterinin kalıcılığı | Gölge operatörün asıl setup'ını ölçer; örneklem deploy'da kaybolmaz | TDD; emir yolu yok | `smc_v2.fvg_entry_sl_shadow_variants: [atr]` |
| 6 | Ölçümsüz gevşetmelerin tek tek NET A/B'si (entry-dist 12, overshoot 6, cap 6, recency 168, BOS, Po3) | Hangi gevşetmenin zarar ürettiği görülür | NET-cost gate; değer değişikliği operatör kararı | Mevcut anahtarlar |
| 7 | Mitige-OB / breaker retest: ≥180g ölçüm → gölge | Tek pozitif adayın doğrulanması veya elenmesi | ADR-0011 kriteri | `smc_v2.mitigated_ob_entry: off` (`off|shadow`) |
| 8 | Maliyet bütçesi kapısı (maliyet/R > eşik → setup alınmaz), önce gölge | Maliyetin yediği işlemleri eler; frekansı düşürür | Offline tarama + gölge | `smc_v2.max_cost_r: null` |
| 9 | FVG limit giriş için canlı emir yolu (limit + iptal/timeout + kısmi dolum yönetimi) | Hedef modelin canlıya alınabilmesi | 5 ve ADR-0011 forward kapısı geçildikten sonra; risk-ops; ayrı PR | `smc_v2.fvg_entry: live` (bugün kodda yok) |
| 10 | Max-hold 36h ↔ 0 uzun pencere ölçümü | Funding yükü ve kuyruk riski netleşir | NET-cost gate | Mevcut `max_holding_hours` |
| 11 | Exposure / sizing / `max_open_positions` uyumu: (b) notional'ı düşür veya (c) `max_open_positions`'ı fiili tavana indir | Kapasite ile doküman uyumu; reddedilen teyitler azalır (b) | Risk-ops + operatör. **(a) exposure artırma önerilmez** | — |
| 12 | Mutlak taban: bakiye eşiği altında "TRIP + Telegram" (kalıcı HALT değil) | Çok haftalı yavaş erimeye karşı taban; operatörün "kalıcı HALT olmasın" isteğiyle uyumlu | TDD + risk-ops + operatör | `safety.balance_floor_trip_usdt: null` |
| 13 | Start'ta kaldıraç GET-teyidi (fail-closed); CLI yolunda margin hatası fatal; `test_phase_configs` 3 config'e genişletme; V2/V3 breaker kalibrasyonu | Likidasyon kapısı doğru ölçekte; V2/V3 tutarlı | TDD + risk-ops | — |
| 14 | Long/scalp: `v2_use_real_atr`, Po3, BT-23/25 paritesi; alerter/canary kapsamı | Restart'ta mid'de düzeltilmiş kusurlar tekrar etmez | Profil başına backtest + operatör; restart ön koşulu | Mevcut anahtarlar |
| 15 | Deploy/yorum hijyeni: `deploy/Caddyfile` ölü hostlar, `deploy.sh` servis argümanı, panel compose, config/compose/docstring yorumları, Pine lab `maxHoldHours` 0=off + config-eşitlik testi, docs-drift testi | Operasyonel doğruluk | Ayrı PR'lar; operatör onayı (Caddy reload / bot deploy penceresi) | — |

Sıra gerekçesi: 1–2 sermaye koruması (olası hata), 3–4 ölçüm ön koşulu, 5–9 hedef modelin doğrulanması, 10–14 risk çerçevesi, 15 hijyen.

### 6.3 NO — yapılmayacaklar ve neden

| # | Yapılmayacak | Neden |
|---|---|---|
| N1 | Lux kapılarını (12h trend, premium/discount, recency, confluence) gevşetmek | Elenen her kategori NET −0.17…−0.32 R (counterfactual `:44-51`) |
| N2 | `max_total_exposure` artırmak / "10 pozisyon"u gerçekleştirmek | Negatif beklentili akışta riski büyütür; guard zayıflatma |
| N3 | Teyitsiz giriş (`require_confirmation:false`) veya `touch_entry`'yi canlıya almak | Baz −0.75 R; Haziran PF 0.62 |
| N4 | `fvg_entry`'yi kapı geçmeden canlıya almak veya go-live'ı "canlı v2'den iyi" ile sınırlamak | ≈0.00 R, n=85, iyimser maliyet; baz negatif olduğu için göreli kıyas anlamsız |
| N5 | Ölçümsüz yeni gevşetme (overshoot, entry-dist, cap, recency, timeout) | Mevcutlar zaten ölçümsüz (X19) |
| N6 | TV LuxAlgo kutularını motora girdi yapmak; Kronos/LLM'i gating yapmak; `structure_validation` açmak | #274/#275 NO-GO; Kronos için 0 forward kapanış; 23.085/23.085 fallback |
| N7 | v1 girişlerini geri açmak; Pine strategy ürününü canlandırmak | Operatör kararı `b2154c5`; ADR-0005 |
| N8 | `safe_orchestrator.py` / `exchange/__init__.py` refactor'u; ölü kodun silinmesi | Karpathy-3: işaretle, silme; canlı mainnet dosyası |
| N9 | Acil HALT'ı sessizce eski haline döndürmek | Operatör kararı; alternatif Ö12 default-OFF |
| N10 | Bu turda config yorumu, compose, Caddyfile, Pine kaynağı değiştirmek | Operatör kararı 1: yalnız doküman PR'ı |
| N11 | Long/scalp botlarını mevcut config'lerle başlatmak | Proxy ATR, kapısız, tutarsız breaker kalibrasyonu, alarm kapsamı yok (X29) |
| N12 | LuxAlgo türevi Pine'ı Protected/ticari yayımlamak | CC BY-NC-SA 4.0 (`THIRD_PARTY_NOTICES.md`) |

---

## 7. Önerilen yeni doküman mimarisi

**Roller (her bilgi tek yerde yaşar):**

| Rol | Dosyalar | Kural |
|---|---|---|
| Constitution (kalıcı kural) | `CLAUDE.md`, `docs/adr/*`, `docs/engineering-rules.md`, `THIRD_PARTY_NOTICES.md` | Tarih, SHA, sayı, "şu an" cümlesi içermez |
| Map (nerede ne var) | `CONTEXT.md` (sözlük + setup matrisi + etkili/inert anahtarlar), `AGENTS.md` (≤50 satır giriş), `README.md` (public vitrin), `TESTS.md`, `REGRESSION.md`, `pine/PINE_SPEC.md`, `docs/STRATEGY_INTENT.md` | Değer yazmaz; `config:satır` / `path:line` gösterir |
| Status (şu an) | `collab/STATUS.md` | Tek "anlık durum" kaynağı; her deploy log'unda güncellenir |
| History (ne oldu) | `collab/log/*`, `CHANGELOG.md`, `docs/research/DECISIONS.md`, `docs/history/*`, `docs/handoff/*`, `docs/superpowers/*` | Append-only; düzeltme yeni satırla |
| Runbook | `docs/runbooks/*` (operator-runbook, backtest-gate, cowork-git-pitfalls) | Komut + doğrulama adımı |

**Yeni CLAUDE.md iskeleti (≤70 satır):**
1. `# EFloud-Bot` — 3 satır: ne (Binance USD-M SMC botu + Pine indikatörü + panel/site), repo PUBLIC, canlı MAINNET.
2. `## Okuma sırası` — CONTEXT.md → AGENTS.md → collab/STATUS.md → docs/adr/README.md → docs/STRATEGY_INTENT.md.
3. `## Değişmez kurallar` — emri yalnız motor verir; secret yok; master'a doğrudan push yok; guard zayıflatılmaz; mainnet trade mantığı = ADR-0003 kapısı; canlı davranış iddiası yalnız `config:satır` + kod yolu ile yazılır.
4. `## Geliştirme sözleşmesi (Karpathy 4 ilke)` — mevcut metin; ilke 4'te gate = `backtest.cli` + ADR-0011.
5. `## Kapılar ve komutlar` — pytest, `regression_ledger run`, `canary.py`, `backtest.cli`, `build_pine_lab.py --check`.
6. `## Pine kuralları` — v6; ürün indikatör (ADR-0005); kaynak `pine/lab/*`; üretilen dosyaya dokunma; RE10045 tuzakları için skill işaretçisi.
7. `## Commit / PR biçimi` — `collab/README §2`.
8. `## Harness haritası` — `agents/` (desk), `scripts/ci/agents/` (CI), `engine/agents/` (runtime, advisory), `skills/`, `hooks/live_write_gate.py`.
9. `## Kalıcı yapı notları` — u2algo-site Railway kökü; sosyal hat skill'i.

**README iskeleti:** What it is → Canlı motor (5 satır + CONTEXT linki) → Safety defaults (formüllerle, sayı yerine config referansı) → Quick start → Repository layout → Indicator (TV yayın durumu tek yerde) → Licence.

**AGENTS.md rolü:** AI giriş haritası — "önce bunları oku" listesi, harness tablosu, test komutu. Algoritma durumu, parametre değeri, kurulum tekrarı içermez.

**Drift'e karşı (GATED, Ö15):** `tests/ci/test_docs_roles.py` — CLAUDE.md satır tavanı, STATUS "VPS HEAD" == log'daki son `DEPLOYED <sha>`, dokümanlardaki `path` referanslarının varlığı, map/constitution dosyalarında tarihli "şu an" başlığı yasağı.

---

## 8. Operatöre açık sorular (karar gerektiren)

1. **Canlı akış:** Ölçülmüş NET negatif LuxAlgo akışı mainnet'te sürecek mi? Seçenekler: (a) aynen devam + "20-30 işlem" kontrol noktasının sahibi ve rapor tarihi belirlenir; (b) `EFLOUD_PAUSE_NEW_ENTRIES` ile yeni girişler durdurulur, gölgeler ölçmeye devam eder; (c) pozisyon büyüklüğü düşürülerek devam. Bu rapor seçim yapmaz; (b) ve (c) guard zayıflatmaz.
2. **Bias:** Kalıcı niyet 4h mı (11-13), yoksa bias yok mu (11-08)? Canlı 12h, 4h kanıtlanana dek kalsın mı?
3. **SL tanımı:** "OB mumunun biraz ötesi" ile "SSL/BSL'nin %0.2 ötesi" aynı nokta mı? ATR tabanı (2 ATR) hedef modelde tamamen kalksın mı, yoksa maliyet bütçesi kapısı (Ö8) kabul edilir mi?
4. **Sweep:** CHoCH/BOS öncesi likidite süpürmesi zorunlu mu? Kanonik implementasyon efloud `fvg_entry` mi, u2Algo-Trade `pin_fvg_touch` mi?
5. **GO kriteri:** ADR-0011 eşikleri (OOS NET PF ≥ 1.30, n ≥ 30 forward / ≥ 100 offline, IS+OOS > 0, ≥ %60 sembol, mutlak eşik) FVG go-live kapısı olarak kabul ediliyor mu?
6. **Exposure / bakiye:** Güncel V1 bakiyesi nedir; `starting_balance 403.55` hâlâ doğru mu? Efektif ≤4 pozisyon bilinçli mi (Ö11-c), yoksa notional mı düşürülsün (Ö11-b)? Mutlak taban için "TRIP + uyarı" (Ö12) istenir mi?
7. **V2/V3 ve yüzeyler:** Long/scalp botları şu an işlem yapıyor mu? Yapıyorsa alarm kapsamı ve breaker kalibrasyonu önceliklidir. Panel (reviewer probe'unda 502) ve eski IP'ye bakan alan adı için karar; ana checkout'un güncellenmesi ve düz metin testnet anahtarının rotasyonu.
