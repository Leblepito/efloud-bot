# 07 — Konuşma ve Memory Geçmişi (operatör niyeti) İnceleme Raporu (2026-11-14)

> Kapsam: `~/.claude/projects/C--Users-utkuc-Downloads-efloud-bot/memory/*.md` (62 dosya), `collab/**` karar logları,
> `docs/handoff/**` (worktree'de tek dosya kaldı), transcript'ler (50 jsonl, yalnız 2026-11-01 → 11-14 aralığını
> kapsıyor; Python ile yalnız `type=user` metin mesajları + AskUserQuestion cevapları süzüldü, secret-benzeri
> içerik maskelendi). İnceleme kökü `C:/tmp/wt-ecc-audit` @ `81c2cf7`. SALT OKUMA.
>
> Etiketler: **KANITLI** = NET-cost ölçümü pozitif ve kapıyı geçti · **KANITSIZ** = ölçüm yok / n yetersiz /
> başa baş · **ÇÜRÜTÜLMÜŞ** = NET-cost ölçümü negatif veya kapıyı geçemedi · **DOĞRULANMADI** = kanıt bulunamadı.

---

## 1. Envanter (ne var, ne işe yarıyor, canlı mı/ölü mü/shadow mu)

### 1.1 Niyet kaynakları

| Kaynak | Kapsadığı dönem | Durum / güvenilirlik |
|---|---|---|
| Memory topic dosyaları (62) | 2025-01 → 2026-11-14 | Karışık: bazıları güncel (`fvg_entry_shadow.md`, `u2algo_forward_ab.md`), bazıları bayat (bkz. §3, §4) |
| `MEMORY.md` indeks | — | Etiketlerin bir kısmı içerikle çelişiyor (örn. "backtest subsystem retired" ↔ içerik "restored #335") |
| `collab/log/claude-code.md` | 2026-11-04 → 11-14 | Güncel, deploy + karar kayıtları (EF-/T- kimlikli). En güvenilir yazılı karar kaydı |
| `collab/STATUS.md` | son güncelleme 2026-11-07 | **BAYAT** (master `3acea5c`, gerçek `81c2cf7`; VPS satırı `3acea5c`, gerçek `bf464d0` — `collab/log/claude-code.md:331-334`) |
| `docs/handoff/` | yalnız `2026-11-03-multi-agent-desk-design.md` | 2026-05→10 handoff'ları `f96b7d8`'de silindi; yalnız git geçmişinde |
| `docs/history/claude-md-status-archive.md` | ≤ 2026-10-02 | Tarihsel; kendisi "bazı bilgiler bayat" diyor (satır 5-7) |
| Transcript'ler | **yalnız 2026-11-01 → 11-14** | Mayıs–Ekim niyeti transcript'te YOK; yalnız memory + commit mesajlarından |
| Lokal branch `feat/pine-lab-mpa-wick-setup` (`4b626ff`) | 2026-11-08 | **origin'de yok, master'a merge edilmemiş** — 3 değerlendirme raporu yalnız burada |
| Ayrı repo `C:\tmp\u2Algo-Trade` | 2026-11-09 → 13 | Bu repo dışında; memory `u2algo_forward_ab.md` üzerinden. DOĞRULANMADI (bu turda okunmadı) |

### 1.2 Setup/algoritma varyantları (geçmişte görünen) — özet durum

| # | Varyant | Nerede | Durum |
|---|---|---|---|
| S1 | SMC v1 confluence (signals.py) | `engine/signals.py` | Kod çalışıyor ama v2 canlı sembollerde MARKET girişi susturuldu (`b2154c5`) → fiilen ölü |
| S2 | SMC v2 efloud triggers (CHoCH→OB/BB/OTE/FVG→engulfing) | `engine/smc_v2/triggers.py` | `luxalgo.enabled: true` iken devre dışı (`configs/config.phase2_1k.yaml:180-186`) |
| S3 | **SMC v2 LuxAlgo modu** (12h bias, OB/BB + 15m engulfing → MARKET) | `engine/smc_v2/luxalgo.py`, `safe_orchestrator.py:1245-1270` | **CANLI** (mainnet, 10 sembol) |
| S4 | touch_entry (fitil/temas, teyitsiz) | `smc_v2.touch_entry: shadow` (`config:209`) | SHADOW (yalnız log) |
| S5 | **FVG pullback entry** (4h bias, FVG limit, OB SL, OB/BB TP1, likidite TP2) | `engine/smc_v2/fvg_entry.py`, `config:216` | SHADOW (#343, `bf464d0`); `live` değeri kodda yok |
| S6 | u2algo ICT — MPA "Kılçık" (wick 4h) | Pine lab (branch, merge'siz) | Yalnız indikatör, default mod |
| S7 | u2algo ICT — Sweep CHoCH (4h/1h) | Pine lab (branch) | Opt-in, gate FAIL |
| S8 | All-15m Sweep CHoCH (SL %0.2 sweep ötesi) | `ee1dd9e` (branch) | Değerlendirme, gate FAIL |
| S9 | Pin(1h) → 15m sweep → 5m CHoCH → FVG | `d538c34`, `4b626ff` (branch) | Değerlendirme, gate FAIL |
| S10 | `pin_fvg_touch` ± Kronos forward A/B | u2Algo-Trade repo, VPS testnet/paper | Forward test, 0 kapanış (memory 2026-11-14) |
| S11 | Mitige-OB retest | yalnız ölçüm (#277) | Takip adayı, kod yok |
| S12 | SL/TP redesign bayrakları (`sl_structural_swing`, `tp_intermediate`) | `feat/smc-sl-tp-redesign` | Directional NO-GO, default OFF |

---

## 2. Canlı gerçek (şu an prod'da fiilen çalışan davranış, kanıtlı)

**Kaynak hiyerarşisi:** config + kod (repo `81c2cf7`) > `collab/log` deploy kaydı > memory.

| Konu | Canlı değer | Kanıt |
|---|---|---|
| Deploy edilen kod | `bf464d0` (2026-11-14, FVG shadow) | `collab/log/claude-code.md:331-334` ("VPS: DEPLOYED bf464d0"); memory `fvg_entry_shadow.md` aynı |
| Prod config | `configs/config.phase2_1k.yaml` (mid) | `config:84-88` yorum + `.env.production EFLOUD_CONFIG_PATH` (secret var: VPS `.env.production`, okunmadı) |
| Motor | `smc_version: v2`, 10 sembol whitelist, `smc_v2_shadow: false` | `config:90-95` (operatör onayı 2026-07-07, `444cd11`) |
| Setup üretimi | LuxAlgo modu: `enabled: true`, `kinds: [CHoCH, BOS]`, `require_premium_discount: true`, `min_confluence: 1` (konsept sayısı) | `config:187-205`; operatör kararı 2026-11-01 "luxalgo mantığını kullanalım" (`38508f7`) — commit notu: "NET-cost backtest yapılmadı" |
| Bias | **12h** LuxAlgo swing trend (profil mid HTF) | `safe_orchestrator.py:1255-1257` (`_lx.analyze(df_htf…).swing_trend`), `data/timeframes.py:26` (`"mid": ("15m","4h","12h")`) |
| Giriş tetiği | Bölgeye pullback → 15m **engulfing kapanışı** → MARKET | `engine/smc_v2/confirmation.py:4-5,81-93`; spec `docs/superpowers/specs/2026-11-14-fvg-entry-shadow-design.md` tablo |
| SL | calc_sl: OB ucu ± 0.5 ATR, taban 2 ATR, tavan 5 ATR (reject) | `config:294` (`sl_atr_buffer 0.5`), `config:412-413` (`min_sl_atr 2.0`, `max_sl_atr 5.0`), `v2_use_real_atr: true` (`config:107`) |
| R:R | `min_rr: 1.8` | `config:273` |
| Gölgeler | `touch_entry: shadow`, `fvg_entry: shadow`, WS kline `enabled`/`event_scan: false` | `config:209,216,221-224` |
| Risk | kaldıraç 10x (`config:71`, operatör 2026-07-24), `emergency_balance_threshold: 0` (halt kapalı, `config:424`), `allow_volatile_entries: true` (`config:385`), `max_holding_hours: 0` (kapalı, `config:407`, #339), daily %10 / weekly %25 | ilgili satırlar |
| LLM | yapı doğrulama kapalı (`config:99-100`, #332); sentiment yalnız telemetri (#334) | `collab/log/claude-code.md:290-299` |
| Alerter | LUX/TP/SL alarmları açık | `docker-compose.prod.yml:157-163` |
| scalp/long botlar | idle (AUTOSTART=0), eski imaj | `collab/STATUS.md` (11-07), memory `ecc_skills_install.md` ("long/scalp still on old image 2a8fd644") — güncelliği DOĞRULANMADI |

**Canlı edge ölçümü (canlı mantığa ait):** iki bağımsız NET ölçüm negatif →
- #277: 60 gün, 217 işlem, **−0.30 R/işlem, PF 0.65** (brüt −0.03 R; maliyet ~0.27 R) — `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:12-17`.
- #335 parite: 41 gün × 10 sembol, 137 işlem, **PF 0.69, NET −%0.91** — `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:21-24`.
- Canlı huni 11-08→13: 215 setup → 77 dokunuş → 22 teyit → 9 emir (11 pos_guard, 2 breaker, Po3 25 blok) — spec `2026-11-14-fvg-entry-shadow-design.md` §Live behaviour.

### 2.1 Memory ↔ repo çelişkileri (canlı gerçek açısından)

| Memory iddiası | Repo gerçeği | Karar |
|---|---|---|
| `trade_horizon_profiles.md`: "mid 15m/1h/4h (mevcut)", "scalp 5m/1h/12h", "long 1h/8h/1w" | `data/timeframes.py:26-27` mid 15m/4h/12h, long 1h/8h/1d; CONTEXT.md:15,43 | Memory bayat (chain redesign `3c96029`, 2026-07-06) |
| `reference_dashboard_access.md`: `bot.ualgotrade.com` / `178-104-122-91.nip.io` | `CLAUDE.md:3` → `2-28-139-82.nip.io`; ana checkout CLAUDE.md → `bot.u2algo.com` (silindi, `collab/log:206`) | Üç farklı URL; hangisinin canlı olduğu DOĞRULANMADI |
| `discovery_rr_clamp_bug.md`: "active: config smc_version=v1" | `config:90` `smc_version: v2` | Bayat (v2 2026-07-07'den beri canlı) |
| `pine_translation_state.md`: "V1 = üretimdeki mantık" | Canlı = v2 LuxAlgo | Bayat |
| `algorithm_setup_audit_2026_06_20.md`: "C2 live balance ~$2070" | `config:375` `starting_balance: 403.55` | Zamanla değişti; memory'de "as-of" uyarısı yok |
| MEMORY.md indeks: "backtest subsystem retired" | `backtest/` restore edildi (#335 `aace1fa`) | İndeks etiketi yanlış, topic dosyası doğru |
| `fvg_entry_shadow.md`, `u2algo_forward_ab.md` | Repo `c05260c`/`bf464d0` ile tutarlı | Güncel ✔ |

---

## 3. Çelişkiler

| # | Çelişki | Kanıt A | Kanıt B | Etki | Önerilen çözüm |
|---|---|---|---|---|---|
| C1 | **FVG shadow SL'i operatörün SL tarifini ölçmüyor** | Operatör 11-07 21:28: "SL ATR'ye göre konulmamalı SSL BSL noktalarından biraz uzak"; 11-08 01:37/01:50: "SSL/BSL noktasının %0.2 uzağına… entry noktasının değil"; AskUserQuestion cevabı "Fiyatın %'si" | `fvg_entry.py` SL = `calc_sl` (0.5 ATR buffer, taban 2 ATR, tavan 5 ATR) — spec `2026-11-14-fvg-entry-shadow-design.md` §Setup rules 5 | Shadow sonucu (≥30 kapanış) operatörün asıl setup'ını değil, ATR-tabanlı bir hibriti doğrular/çürütür | Shadow'a ikinci SL varyantı (likidite/OB ucu + %0.2) log-only eklensin — yalnız öneri, backtest-gate + operatör onayı |
| C2 | Bias TF'si üç kez yön değiştirdi | 11-07 16:27: "1 günlük… ana trend"; 11-08 01:37: "ana trend'e bakmayalım"; 11-13 21:02: "15m işleme girecekse 4h bias" | Canlı 12h (`safe_orchestrator.py:1255`) | Her turda farklı hipotez test edildi; hiçbiri canlıya bağlanmadı | Operatöre tek soru: "Kalıcı bias TF'si 4h mı?" — cevabı ADR'ye yaz |
| C3 | Sweep ön koşulu belirsiz | 11-07 21:28 "likidasyon sonra choch"; 11-08 02:05 "15m sweep… 5m choch… FVG" | 11-13 21:02 tarifinde sweep yok; FVG shadow sweep aramıyor (spec §Setup rules) | "Asıl setup" iki ayrı şekilde yorumlanıyor (u2Algo-Trade `pin_fvg_touch` sweep'li, efloud `fvg_entry` sweep'siz) | Operatörden sweep zorunlu mu teyidi |
| C4 | İki paralel "operatör setup" implementasyonu | u2Algo-Trade `recipes/pin_fvg_touch.yaml` (5m, sweep SL, Kronos) — memory `u2algo_forward_ab.md` | efloud `fvg_entry.py` (15m, 4h bias, OB SL) — `c05260c` | Aynı niyetin iki farklı ölçümü; hangisi kanonik belirsiz | Tek kanonik "setup intent" dokümanı + her implementasyonun sapma tablosu |
| C5 | Maliyet modelleri değerlendirmeler arası farklı | backtest: komisyon %0.04 + funding %0.01/8h (`parity.md:39`) | FVG shadow: %0.07 round-trip (spec §Shadow lifecycle); ICT eval: %0.12 round-trip (`4b626ff` rapor satır 3) | NET R'ler karşılaştırılamaz | Tek NET maliyet tanımı (CLAUDE.md "Kanonik kaynaklar") |
| C6 | ADR-0009 gerekçesi güncel kanıtla çelişiyor | ADR-0009: teyitli PF 1.41 (2026-06-15) → "edge'i korur" (`docs/adr/0009…md:8-10,31`) | #277: teyitli canlı akış PF 0.65; teyitsiz limit (P2) −0.04 R, PF 0.95 (`lux-gate-counterfactual.md:21-22`) | ADR artık "teyit edge taşır" iddiasını kanıtlamıyor | ADR-0009'a "2026-11 yeniden değerlendirme" notu (doküman PR) |
| C7 | CONTEXT.md "Confirmation" tanımı yanlış | `CONTEXT.md:18` "zone touch" | `confirmation.py:4-5` 15m engulfing kapanışı | Yeni ajan canlı giriş tetiğini yanlış anlar | CONTEXT.md düzelt |
| C8 | CONTEXT.md sipariş akışı v1'e göre | `CONTEXT.md:36` "confluence ≥ min_confluence → guards → breaker → confirmation" | v2 LuxAlgo: `luxalgo.min_confluence: 1` konsept sayısı (`safe_orchestrator.py:1269`), `risk.min_confluence: 50` yalnız v1 yolunda (`:1357`) | "50 puan eşiği" canlıyı yönetiyor sanılıyor | CONTEXT.md'ye v2 akışını yaz |
| C9 | CLAUDE.md iç çelişki: strategy ürünü | `CLAUDE.md:3` "Pine strategy ADR-0005 ile rafa kalktı" | `CLAUDE.md:17` "hem INDIKATÖR hem STRATEGY"; `:21,26` strategy dosyası + senkron kuralı | Ajanlar rafa kalkmış strategy'yi senkronlamaya çalışabilir | `:17,21,26` ADR-0005'e hizala |
| C10 | Config yorumları değerlerle çelişiyor | `config:2,13` "cüzdan ~$1363"; `:48-49` "$136/$341"; `:271` "$20 risk ($2000×1%)"; `:371` "$200" | `config:375` `starting_balance: 403.55` | Risk kalibrasyonu okuyan biri yanlış dolar değerleri görür | Yalnız yorum düzeltmesi (prod config dosyası → risk-ops görsün) |
| C11 | Config yorumları eski kapı değerlerini anlatıyor | `config:121-128` "6.0 seçildi"; `:140-150` "8→24 bar", "recency_bars: 40"; `:165` "0.5 = yarım ATR" | `max_entry_dist_atr: 12.0` (`:129`), `pullback_timeout_bars: 12` (`:151`), `recency_bars: 168` (`:293`), `max_zone_overshoot_atr: 6.0` (`:168`) | Gevşetme geçmişi okunurken yanlış eşik | Aynı |
| C12 | CLAUDE.md arşivi bölge toleransını 2.0 diyor | `docs/history/claude-md-status-archive.md:10` "0.5→2.0 ATR" | `config:168` 6.0 (`ad41004`, 2026-10-03) | Tarihsel; ana checkout CLAUDE.md hâlâ bu satırı başlıkta taşıyor | Ana checkout'u güncelle (operatör WIP'i nedeniyle dokunulmadı) |
| C13 | collab/STATUS.md ↔ deploy logu | `STATUS.md` master `3acea5c`, VPS `3acea5c` | `collab/log/claude-code.md:331-334` VPS `bf464d0` | "Anlık durum" kaynağı (CLAUDE.md "Kanonik kaynaklar") 1 hafta bayat | Deploy log adımına STATUS satırı güncellemesini zorunlu ekle |
| C14 | Operatör "daha çok işlem" isteği ↔ ölçülmüş kanıt | 2026-06-04 conf 80→50 "increase trade frequency" (`38ec7cc`); 10-01..10-03 kapı gevşetmeleri (`228382d`, `4417e90`, `ad41004`, `2b5ca9a`); 11-04 "grafikteki bölgelerden girsin" | #277: gevşetilecek her kapı NET negatif (−0.17…−0.32 R) | Gevşetmeler negatif edge'li akışı büyütüyor | Gevşetme önerilerini ADR-0003 kapısına bağla (zaten var) — memory `lux_ob_entry_gap` "how to apply" |
| C15 | Önerilen seçenek operatör ifadesiyle çelişti | AskUserQuestion: "Gövde ≥ 1.5×ATR, 1 mum (Önerilen)" seçildi | Operatör 11-08 03:11: "1.5xATR olan şartı kaldıralım… FVG boşluğu veren bir mum yapısı" | Asistan çerçevesi niyeti saptırdı, düzeltme 1 saat sonra geldi | Kural: seçenek metinleri operatörün kendi ifadesini birebir içersin (§6) |

---

## 4. Bayat / yanlış dokümantasyon

1. **`CLAUDE.md:58-68` "Efloud Çekirdek Mantığı"** — tamamen v1 confluence yolu: "Confluence Threshold 55/50", "SL = son 20 mum + ATR×0.5, min %0.1", "TP1 … Min R:R 1.5", "HTF Bias Fallback … signals.py:308-328". Canlı v2 LuxAlgo'da: bias 12h LuxAlgo swing trend, SL calc_sl (2–5 ATR), `min_rr 1.8`, konsept-sayısı confluence. v1 değerleri "LEGACY (v1, canlıda susturulmuş)" diye işaretlenmeli.
2. **`CLAUDE.md:17,21,26`** strategy ürünü/senkron kuralı ↔ ADR-0005 (C9).
3. **Ana checkout `C:/Users/utkuc/Downloads/efloud-bot/CLAUDE.md`** (81 commit geride) hâlâ 2026-10-02 başlığını, `bot.u2algo.com` panelini, `u2algo-site-production.up.railway.app` URL'sini ve Supabase "PGRST205" notunu taşıyor — oturum açılışında bu metin yükleniyor (bu oturumun system-reminder'ı kanıt). Ajanlar bayat anayasa ile başlıyor.
4. **`CONTEXT.md:18,36`** (C7, C8).
5. **`collab/STATUS.md`** (C13); "Model durumu" satırları 11-04/11-05'te kalmış.
6. **`README.md:155`** "filtered by 12h bias" — canlı için doğru, ama operatörün güncel niyeti 4h (11-13); niyet değişikliği gölgede olduğundan README'yi değiştirmeye gerek yok, yalnız not.
7. **`docs/adr/0009`** gerekçesi (C6).
8. **Config yorumları** (C10, C11).
9. **Memory**: `trade_horizon_profiles.md`, `reference_dashboard_access.md`, `discovery_rr_clamp_bug.md` ("active v1"), `pine_translation_state.md`, MEMORY.md indeks etiketi "backtest subsystem retired", `efloud_state.md` (indeks: "newer state in ecc_skills_install" — durum iki dosyaya bölünmüş). Ayrıca `reference_dashboard_access.md` eski bir dev şifresini düz metin içeriyor → **secret var: memory/reference_dashboard_access.md** (değer alıntılanmadı).
10. **`docs/handoff/`** — CLAUDE.md iki silinmiş handoff'a `git show f96b7d8^:` ile atıf yapıyor (çalışıyor ama keşfedilebilirlik düşük); memory dosyaları (`smc_sl_tp_redesign_initiative.md`, `wave2_dropped_falsification.md`, `entry_slippage_initiative.md`) hâlâ silinmiş `docs/handoff/*.md` yollarını düz yol olarak veriyor.

---

## 5. Trade mantığı / setup modelleri

### 5.1 (a) Niyet kronolojisi

| Tarih | Operatör ifadesi (özet / kısa alıntı) | Kaynak |
|---|---|---|
| 2026-05-14 | Açık pozisyon varken kontra sinyal: zararda REDDET, ≥%0.2 kârda reverse, TP1 sonrası asla | memory `reverse_position_guard_policy.md` |
| 2026-05-23 | ETH SHORT R:R orantısız; bot CHoCH barında giriyor. İstenen: **pullback-to-FVG/OTE + LTF teyit, yapısal SL + ATR buffer, likidite-öncelikli TP1, FVG-fill TP2** | memory `smc_v2_rework_initiative.md` ("Why") |
| 2026-06-02 → 06-04 | conf 50→80 (S1), iki gün sonra 80→50 "to increase trade frequency" | `6f1231f`, `38ec7cc` |
| 2026-06-05 | Discovery clamp: "sadece clamp", min_rr 1.8→1.5 backtest'e ertelendi | memory `discovery_rr_clamp_bug.md` |
| 2026-06-15 | `require_confirmation` true kalır (gate FAIL) | ADR-0009; memory `entry_slippage_initiative.md` |
| 2026-06-17 | Premium strateji DROP, **indicator-only ürün** | memory `wave2_dropped_falsification.md`, ADR-0005 |
| 2026-07-06/07 | TF merdiveni (mid 15m/4h/12h); v2 canlı (shadow:false) | `3c96029`, `444cd11` |
| 2026-07-24 | Kaldıraç 5x→10x (operatör talebi) | `1c20e22`, `config:71` |
| 2026-09-30 | CHoCH sonrası giriş **kırılımı yapan OB/BB'den** (operatör onayı); "Efloud price-action notları" | `242cef3`, `a2f7890`, `config:119-122` |
| 2026-10-01 | Acil bakiye HALT'ı kaldır; volatil rejimde giriş aç; v1 MARKET susturuldu | `b2154c5`, `228382d` |
| 2026-10-02/03 | BOS da setup üretsin; cap 6, timeout 12; recency 168; overshoot 6.0; zone pad 0.5 ATR ("EQ'lar alan olarak") | `658a905`, `4417e90`, `ad41004`, `2b5ca9a` |
| 2026-11-01 | **"luxalgo mantığını kullanalım"** → LuxAlgo modu canlı (NET backtest yok) | `38508f7` gövdesi |
| 2026-11-04 | Grafikteki LuxAlgo OB/BB bölgelerinde bot girmiyor → daha çok giriş | memory `lux_ob_entry_gap_2026_11_04.md` |
| 2026-11-05 16:09 | "telegram'dan mesaj gelecek mi? işleme girdiğinde veya fiyat giriş bölgesine yaklaştığında?" | transcript `f585c5a3` |
| 2026-11-06 00:46 | "BTC/ETH/SOL … bizim stratejimize göre zarar etmiş… **setup değiştirmemiz lazım**" | transcript `59d1fece` |
| 2026-11-06 01:34 | "strateji kısmını şimdilik es geçelim… **indicatöre** önem verelim… OB, BB, MB, FVG, likidasyon ve OTE bölgelerini düzgün göstersin" | `59d1fece` |
| 2026-11-06 01:46 | OTE: range içinde tepe–dip arası, **fib 0.705**; yeni mum ekstremi aşmadıkça değişmesin | `59d1fece` |
| 2026-11-07 16:27 | "**15m trade, 1h CHoCH-BOS, 1d ana trend**; 12h yaygın değil." Kılçık setup: 4h CHoCH/BOS sonrası küçük gövde/uzun fitil → 15m kırılım mumunun **OB/BB'sine temas veya %50**, SL 4h fitilin biraz ötesi, TP ters FVG/OB/BB, **R:R ≥ 1:1.5** | `2e1d15e1`, `69ca35d6` |
| 2026-11-07 20:17 | "bot bu şekilde hiç işleme girmiyor… algoritmada problem var" (indikatör) | `69ca35d6` |
| 2026-11-07 21:28 | "pozisyonlar genelde SL olmuş… **likidasyon sonra CHoCH** → geri çekilmede **OB'den giriş**, **SL ATR'ye göre değil, SSL/BSL'den biraz uzak**" | `69ca35d6` |
| 2026-11-07 22:19 | "botun işlemlerini izleyeceğim, **20-30 işlem sonra hâlâ negatifse** birlikte değiştiririz" | `e9527d49` |
| 2026-11-07 22:51 | 36 saat zorla kapatmayı kaldır | `e9527d49` → #339 |
| 2026-11-08 01:37 | "1d/4h sweep-choch'u **15m içinde** yapalım, **ana trend'e bakmayalım**… SL **SSL/BSL'nin %0.2 ötesi**, R:R>1.5; bu daha kârlıysa indikatör ve bot canlıda böyle çalışsın" | `69ca35d6` |
| 2026-11-08 01:50 | "SL … SSL/BSL noktasının %0,2 uzağına… **entry noktasının değil**" | `69ca35d6` |
| 2026-11-08 02:05 | 1h küçük gövde+uzun iğne → 15m sweep + ters yönde büyük mumlar → 5m CHoCH → **FVG'ye geri çekilmede giriş**, SL sweep ucundan %0.2, TP1 OB/BB, TP2 sonraki OB/BB, **R:R>1.8**; "farklı strateji olarak backtest" | `69ca35d6` |
| 2026-11-08 03:11 | "**1.5×ATR şartını kaldıralım**, FVG boşluğu veren mum yapısı yeterli" | `69ca35d6` |
| 2026-11-09 12:30/14:09 | Kronos repo'suna setup'ı inşa et, agent'lı otomasyon (u2Algo Trade); 3m/5m/15m test et, en iyisini entegre et | `69ca35d6` |
| 2026-11-13 10:52 | "Bütün sonuçların negatif gelmesi imkânsız… **FVG boşluğundan işleme girecek, SL likidasyon noktasının biraz uzağına atılacak, bütün mesele bu. Neden bu kadar zorlaştırdın**"; Kronos onaylarsa gir | `69ca35d6` |
| 2026-11-13 21:02 | "**15m işleme girecekse 4h bias**; CHoCH-BOS sonrası **FVG**'ye geri çekilme(de) gir; SL **kırılımı yapan OB mumunun biraz uzağı**; **TP1 bir sonraki OB-BB**, **TP2 yön likiditesi**" | `69ca35d6` |
| 2026-11-14 | Seçim: "Geri çekilmede FVG limit", "**Önce gölge, sonra canlı**" | AskUserQuestion cevabı `69ca35d6`; spec 2026-11-14 başlığı |

### 5.2 (b) Operatör kararları (onay/ret)

| Tarih | Karar | Tür | Kanıt |
|---|---|---|---|
| 05-23 | SMC v2 rework spec | ONAY | memory `smc_v2_rework_initiative.md` |
| 06-05 | Yalnız clamp; min_rr düşürme ertelendi | ONAY/ERTELE | memory `discovery_rr_clamp_bug.md` |
| 06-15 | Teyitsiz market girişi | RET | ADR-0009 |
| 06-17 | Premium strateji | RET (DROP) | ADR-0005 |
| 06-20 | Audit edge bulguları (C4/H1/H5–H7/M1/M2) "later" | ERTELE | memory `algorithm_setup_audit_2026_06_20.md` |
| 07-07 | v2 canlı | ONAY | `444cd11` |
| 09-30 | OB/BB'den giriş | ONAY | `config:119` |
| 10-01 | Acil halt kaldır, volatil aç | ONAY | `config:385,424` |
| 11-01 | LuxAlgo modu | ONAY (backtest'siz) | `38508f7` |
| 11-05 | touch_entry shadow, WS shadow, bölge uyarıları | ONAY | `collab/log:102-112` |
| 11-06 | Pine strategy'yi es geç, indikatöre odaklan; yeni zonlar **display-only** | ONAY | transcript + AskUserQuestion "Display-only (Recommended)" |
| 11-07 | TF zinciri değişikliği **yalnız indikatöre** (bot değil); kılçık ayrı mod default açık | ONAY | AskUserQuestion "Sadece indikatör (Önerilen)" |
| 11-07 | Sweep CHoCH için 1d trend korunsun | ONAY → 11-08'de operatör kendisi tersine çevirdi ("ana trend'e bakmayalım") | AskUserQuestion + 11-08 01:37 |
| 11-07 | A1/A2 sentiment telemetri, yapı doğrulama kapalı, backtest restore, CLAUDE.md anayasa | operatör kararı spec üzerinden delege | `collab/log:283-299` |
| 11-08 | Sweep CHoCH gate FAIL → "Kılçık default, Sweep seçilebilir" | ONAY | AskUserQuestion |
| 11-08 | Max-hold kaldır + deploy | ONAY | #339 |
| 11-09 | Setup araştırma döngüsü Claude Code içinde; u2Algo Trade yeni repo + Kronos submodule | ONAY | AskUserQuestion |
| 11-13 | Backtest döngüsünü durdur → "A: Basit setup + Kronos, ileri test"; 30 likit coin; ileri teste kol ekle | ONAY | AskUserQuestion + memory `u2algo_forward_ab.md` |
| 11-14 | FVG limit yorumu + önce gölge | ONAY | spec 2026-11-14 |

**Gözlem:** transcript'teki ~30 AskUserQuestion cevabının **tamamı "(Önerilen)" seçeneği**. Kararların çerçevesi büyük ölçüde asistan tarafından çiziliyor; operatör ifadesiyle çelişen önerilen seçenek en az bir kez kabul edilip sonra geri alındı (C15).

### 5.3 (c) Tekrar eden şikayetler / istekler

1. **"Bot girmiyor / az işlem"** — 06-04, 10-01..03, 11-04, 11-07 20:17, 11-13 21:02. Her seferinde kapı gevşetildi; #277 gevşetmenin NET negatif olduğunu ölçtü.
2. **"Pozisyonlar SL oluyor / sonuçlar hep negatif"** — 11-06 00:46, 11-07 21:28, 11-13 10:52. Ölçümler bunu doğruluyor (−0.30 R, PF 0.65–0.69).
3. **"SL ATR ile değil, likiditenin (SSL/BSL/sweep/OB) biraz ötesine"** — 11-07 16:27, 21:28; 11-08 01:37, 01:50, 02:05; 11-13 21:02. **Altı kez**; canlıda da FVG shadow'da da ATR tabanlı (C1).
4. **"FVG'den gir"** — 05-23, 11-08 02:05, 11-13 10:52, 11-13 21:02.
5. **"Süreç çok karmaşık"** — 11-13 10:52 ("neden bu kadar zorlaştırdın").
6. **"Telegram bildirimi"** — 11-05, 11-06 11:39, 11-07 23:44 (çözüldü #341).
7. **"12h yaygın değil"** — 11-07 16:27 (canlıda hâlâ 12h).
8. **Grafikte pozisyon/bölge görmek** — 11-06 01:34, 11-07 20:52.

### 5.4 (d) "Asıl istenen setup" taslağı — operatörün kendi ifadeleriyle

> **Zaman dilimi:** "15m işleme girecekse 4h bias bakmalı." (11-13) — *açık soru: 11-08'de "ana trend'e bakmayalım" demişti.*
> **Tetik:** "choch-bos kırılımı sonrasında" (11-13); daha önce "likidasyon sonra choch kırılımı" (11-07) — *sweep ön koşulu açık soru.*
> **Giriş:** "Fvg boşluğuna geri çekilme[de] işleme girmeli" (11-13; seçim: "Geri çekilmede FVG limit"). "FVG boşluğu veren bir mum yapısı oluşmuş olsun… büyük mum kısıtlaması kalkmış olur" (11-08).
> **SL:** "kırılımı gerçekleştiren Order block mumunun biraz uzağına SL atmalı" (11-13). "SL ATR'ye göre konulmamalı, SSL BSL noktalarından biraz uzak mesafeye" (11-07). "SSL/BSL noktasının 0,2% uzağına… entry noktasının değil" (11-08).
> **TP1:** "bir sonraki TP1 OB-BB olabilir" (11-13).
> **TP2:** "pozisyona girilen yöndeki likidite noktası olmalıdır" (11-13).
> **R:R:** "min 1:1.5" (11-07, 11-08 01:37) / "R:R>1.8" (11-08 02:05) — canlı `min_rr 1.8`.
> **Özün özü:** "FVG boşluğundan işleme girecek, SL likidasyon noktasının biraz uzağına atılacak, bütün mesele bu." (11-13)

FVG shadow (S5) bu taslağın bias/giriş/TP1/TP2 kısmını karşılıyor; **SL kısmını karşılamıyor** (ATR buffer + 2 ATR taban).

### 5.5 Setup kanıt tablosu (NET filtre)

| # | Setup | NET kanıt | Etiket |
|---|---|---|---|
| S1 | v1 confluence | Wave-2 falsifikasyonu OOS PF 1.165 < 1.30, 2/5 pozitif (memory `wave2_dropped_falsification.md`) | ÇÜRÜTÜLMÜŞ |
| S2 | v2 efloud triggers | BT-sweep v2 R/trade −0.257 (`config:412` yorumu) | ÇÜRÜTÜLMÜŞ |
| S3 | **v2 LuxAlgo (CANLI)** | −0.30 R, PF 0.65 (60g, n=217); PF 0.69, NET −%0.91 (41g, n=137) | **ÇÜRÜTÜLMÜŞ — ama canlı** |
| S4 | touch_entry | Yeniden hesap ~−0.30 R, 3× işlem (transcript `2bd281b8` 11-04 23:07); P2 limit −0.04 R, PF 0.95, n=407 | ÇÜRÜTÜLMÜŞ / başa baş |
| S5 | FVG pullback (shadow) | Offline 45g/10 sembol: 85 kapanış, WR %30.6, NET ≈ +0.00 R (memory `fvg_entry_shadow.md`); forward 0 | KANITSIZ |
| S6 | ICT Kılçık (wick 4h) | brüt +0.130 R, **net −0.089 R**, n=70 (`feat/pine-lab-mpa-wick-setup:…ict-sweep-eval.md`) | ÇÜRÜTÜLMÜŞ (NET) |
| S7 | Sweep CHoCH 4h / 1h | net −0.276 / −0.094 R (n=117 / 256) | ÇÜRÜTÜLMÜŞ |
| S8 | All-15m Sweep CHoCH (SL %0.2) | 4 varyant net −0.218…−0.333 R (n 166–698) | ÇÜRÜTÜLMÜŞ |
| S9 | Pin→sweep→5m CHoCH→FVG | net −0.319 / −0.203 R (n=27 / 35) | ÇÜRÜTÜLMÜŞ (düşük n) |
| S10 | pin_fvg_touch ± Kronos | holdout #1 net −0.50, #2 net −0.85 (n=19); forward 0 kapanış | ÇÜRÜTÜLMÜŞ (holdout) / KANITSIZ (forward) |
| S11 | Mitige-OB retest | +0.24 R, PF 1.42, IS +0.23 / OOS +0.25, n=30 (`lux-gate-counterfactual.md:52`) | KANITSIZ (sınırda, tek pozitif aday) |
| S12 | SL/TP redesign bayrakları | net PF ≤ 1.25 < 1.30 (memory `smc_sl_tp_redesign_initiative.md`) | ÇÜRÜTÜLMÜŞ (directional) |
| — | Teyitsiz market girişi | PF 0.62, n=26 (ADR-0009) | ÇÜRÜTÜLMÜŞ |

**KANITLI etiketli hiçbir setup yok.** Ortak tema (#277): brüt ≈ 0, maliyet (dar SL → yüksek maliyet/R) edge'i öldürüyor. Bu, operatörün "SL likiditenin ötesine" isteğiyle (daha geniş, yapısal SL → R başına daha düşük maliyet) aslında uyumlu bir araştırma yönü — ama S8 (%0.2 sweep ötesi SL) NET negatif çıktı.

---

## 6. ECC revizyon adayları

1. **Kanonik "Operatör setup niyeti" dokümanı** (ör. `docs/STRATEGY_INTENT.md` veya `CONTEXT.md` yeni bölüm): §5.4'teki alıntılar + tarih + kaynak + her implementasyonun (canlı S3, shadow S5, u2Algo-Trade S10) sapma tablosu. CLAUDE.md "Kanonik kaynaklar"a bağla. (Doküman PR — bu turda canlıya gidebilecek tür.)
2. **CLAUDE.md:58-68** "Efloud Çekirdek Mantığı" → başlığı "v1 LEGACY (canlıda susturulmuş, `b2154c5`)" yap, canlı v2 LuxAlgo özetini + `config:187-216` pointer'ını ekle; **CLAUDE.md:17,21,26** ADR-0005'e hizala.
3. **CONTEXT.md:18,36** confirmation = 15m engulfing kapanışı; v2 sipariş akışı (LuxAlgo konsept-confluence, Po3, pos_guard, breaker, confirm, MARKET).
4. **ADR-0009'a yeniden değerlendirme notu**: 2026-11 NET ölçümleri teyitli akışın da negatif olduğunu gösteriyor; karar "teyit edge taşır" değil "teyitsiz daha kötü değil/başa baş" (P2 −0.04 R). Yeni ADR adayı: "FVG entry shadow go-live kapısı + SL yöntemi".
5. **Tek NET maliyet tanımı** (C5): CLAUDE.md "Kanonik kaynaklar"a "NET R = backtest config maliyet modeli; eval araçları aynı sabiti kullanır" kuralı.
6. **`.claude/rules` veya skill — "operatör-niyet eşlemesi" checklist'i**: bir operatör setup'ı implement edilmeden önce her kuralı (bias TF, tetik, giriş, SL yöntemi, TP1, TP2, R:R) koddaki parametreye eşle ve sapmaları spec'te "Operatör ↔ Uygulama" tablosunda göster (2026-11-14 spec'indeki tablo iyi örnek ama SL sapmasını işaretlememiş).
7. **AskUserQuestion kuralı** (C15 + §5.2 gözlemi): seçenek metni operatörün açık ifadesiyle çelişiyorsa "(Önerilen)" etiketi konmaz; operatörün kendi ifadesi bir seçenek olarak birebir sunulur. Memory'ye feedback olarak da yazılmalı.
8. **collab/STATUS.md güncelliği**: deploy log şablonuna (EF-…) "STATUS.md Sistem satırları güncellendi" maddesi; `tests/collab/test_collab_layout.py` zaten log sözlüğünü denetliyor — benzer hafif bir tarih kontrolü düşünülebilir (Simplicity: önce yalnız şablon maddesi).
9. **Memory hijyeni** (doküman dışı, operatör/oturum işi): §2.1 ve §4.9 listesindeki dosyalara "as-of" başlığı + düzeltme; MEMORY.md indeks etiketi "backtest restored"; düz metin dev şifresini memory'den çıkar; memory'deki silinmiş `docs/handoff/` yollarını `git show f96b7d8^:` formuna çevir.
10. **Ana checkout CLAUDE.md bayatlığı**: ana klasör 81 commit geride ve oturumlar orada açılıyor → bayat anayasa yükleniyor. Operatör WIP'i nedeniyle pull yapılamıyorsa en azından oturumların `C:/tmp/wt-*` worktree'lerinden açılması kuralı (memory `feedback_never_stash_shared_checkout.md` ile uyumlu).
11. **Kaybolma riski olan kanıt**: `feat/pine-lab-mpa-wick-setup` yalnız lokal; 3 değerlendirme raporu (S6–S9) origin'de yok → push veya raporları bir doküman PR'ıyla `docs/superpowers/reports/`'a taşı.
12. **Config yorum hijyeni** (C10, C11): yalnız yorum, değer değişmez; ama prod config dosyası olduğu için risk-ops gözüyle ayrı küçük PR.

---

## 7. Riskler ve açık sorular

**Riskler**
- **R1 — Canlı strateji ölçülmüş NET negatif ve risk tamponları gevşetilmiş:** S3 canlıda (−0.30 R/işlem, PF 0.65–0.69) iken kaldıraç 10x, acil halt kapalı (`config:424`), volatil girişler açık, max-hold kapalı. Operatörün 11-07 22:19 "20-30 işlem sonra hâlâ negatifse değiştiririz" kontrol noktası: 11-08→13 arası 9 emir (spec 2026-11-14) — eşiğe ulaşılmadı; takip eden yok.
- **R2 — Shadow yanlış soruyu cevaplayabilir:** S5 ≥30 kapanışta "operatör setup'ı" diye go-live'a gidebilir ama SL yöntemi operatörün tarifi değil (C1).
- **R3 — Niyet sürüklenmesi:** bias TF 12h→1d→yok→4h, giriş OB→OB %50→FVG, R:R 1.5↔1.8 iki haftada değişti; her değişiklik yeni bir değerlendirme turu açtı, hiçbiri KANITLI olmadı. Operatör yorgunluğu açık ("neden bu kadar zorlaştırdın").
- **R4 — Paralel implementasyon:** efloud `fvg_entry` ve u2Algo-Trade `pin_fvg_touch` aynı niyetin farklı yorumları; sonuçlar çelişirse hangisinin geçerli olacağı tanımsız.
- **R5 — Secret maruziyeti:** **secret var: `~/.claude/projects/C--Users-utkuc-Downloads-efloud-bot/69ca35d6-03ca-4acf-aebf-2f795b58cf95.jsonl`** (2026-11-12T12:17 operatör mesajında testnet API key + secret düz metin; değer alıntılanmadı) → rotasyon önerilir. **secret var: memory/reference_dashboard_access.md** (eski dev şifresi). Ayrıca 2026-11-07'de Railway token sohbette verildi (transcript `e9527d49`, değer görülmedi/maskeli kontrol edilmedi — DOĞRULANMADI).
- **R6 — Lisans:** canlı/indikatör yapı motoru LuxAlgo'dan uyarlanmış, **CC BY-NC-SA 4.0** (`README.md:164-165`); 11-06 AskUserQuestion'da "LuxAlgo-derived engine must stay private and non-commercial" denmiş. P-003 ticari MVP (memory `p002_marketing_growth.md`) ile gerilim — bu kategoride doğrulanmadı.
- **R7 — STATUS.md bayat** → çok-modelli (Hermes/Abacus) ekip yanlış canlı durumdan iş planlayabilir.

**Açık sorular (operatöre)**
1. Bias: kalıcı olarak **4h** mı (11-13), yoksa bias yok mu (11-08)?
2. Sweep (likidite alımı) CHoCH'tan önce **zorunlu** mu?
3. SL: "OB mumunun biraz ötesi" ile "SSL/BSL'nin %0.2 ötesi" aynı nokta mı; ATR tabanı/tavanı (2–5 ATR) tamamen kalksın mı?
4. Kanonik implementasyon efloud `fvg_entry` mi, u2Algo-Trade `pin_fvg_touch` mi?
5. R1 kontrol noktası: 20-30 canlı işlem sonrası değerlendirmeyi kim, hangi raporla yapacak?
6. Go-live kapısı yalnız "net avg R > 0 ve canlı v2'den iyi" mi — canlı v2 negatif olduğu için ikinci koşul zayıf; mutlak eşik (ör. NET PF ≥ 1.30, ADR-0003 çizgisi) eklensin mi?

---

## 8. Fable'a özet (en önemli 10 madde)

1. **Canlıda çalışan (S3, v2 LuxAlgo: 12h bias, OB/BB + 15m engulfing → MARKET) iki bağımsız NET ölçümde negatif** (−0.30 R/işlem PF 0.65; 41g PF 0.69 NET −%0.91) — `lux-gate-counterfactual.md:12-17`, `backtest-live-parity.md:21-24`. 2026-11-01'de backtest'siz canlıya alındı (`38508f7`).
2. **Hiçbir setup KANITLI değil**; 13 varyantın 10'u ÇÜRÜTÜLMÜŞ, kalanlar KANITSIZ (S5 FVG shadow ≈ 0.00 R; S11 mitige-OB retest +0.24 R n=30 tek sınırda pozitif).
3. **Operatörün özü (11-13 kendi ifadesi):** "FVG boşluğundan işleme girecek, SL likidasyon noktasının biraz uzağına atılacak, bütün mesele bu" + 15m giriş / 4h bias / TP1 sonraki OB-BB / TP2 yön likiditesi.
4. **En büyük niyet↔uygulama sapması SL:** operatör altı kez "ATR değil, likiditenin (SSL/BSL/OB) biraz ötesi, %0.2" dedi; canlı ve FVG shadow ATR tabanlı (`calc_sl`, 2–5 ATR). Shadow go-live sonucu operatörün setup'ını ölçmeyecek.
5. **Niyet iki haftada 4 kez değişti** (bias 12h→1d→yok→4h; giriş OB→OB%50→FVG; R:R 1.5↔1.8); sweep ön koşulu belirsiz. Operatöre 3 netleştirme sorusu gerekli (§7).
6. **Operatör kararlarının ~tamamı asistanın "(Önerilen)" seçeneği**; en az bir kez operatör ifadesiyle çelişen öneri kabul edilip geri alındı (1.5×ATR) → AskUserQuestion kuralı önerisi.
7. **Tekrarlayan "az işlem" şikâyeti ↔ kanıt:** her gevşetme NET negatif (#277); kaldıraç 10x + acil halt kapalı + max-hold kapalı ile birleşince risk yüksek. Operatörün "20-30 işlem sonra değerlendir" kontrol noktası takipsiz.
8. **Doküman bayatlığı:** CLAUDE.md:58-68 v1 mantığını "çekirdek" diye anlatıyor; CLAUDE.md:17/21/26 rafa kalkmış strategy'yi şart koşuyor; CONTEXT.md:18 teyidi "zone touch" diyor; collab/STATUS.md 1 hafta geride; ana checkout CLAUDE.md 81 commit geride ve oturumlara bayat anayasa yüklüyor.
9. **Memory↔repo çelişkileri:** TF profilleri (mid 15m/1h/4h ↔ 15m/4h/12h), dashboard URL (3 farklı), "v1 aktif" ifadesi, MEMORY.md "backtest retired" etiketi; değerlendirme kanıtları (S6–S9) yalnız lokal, push'lanmamış branch'te.
10. **Secret işaretleri:** transcript `69ca35d6…jsonl` (11-12, testnet API key/secret düz metin) ve `memory/reference_dashboard_access.md` (eski dev şifresi) — değerler alıntılanmadı; rotasyon + memory temizliği önerilir.
