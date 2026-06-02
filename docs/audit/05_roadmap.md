# 05 — Prioritized Roadmap (efloud-bot)

> Phase 5 deliverable. Tüm faz bulgularının (01-04) tek önceliklendirilmiş backlog'u.
> Her madde: Phase · Severity · Effort(S/M/L) · Bağımlılık · TDD başlangıç testi · Kim · Risk.
> İlk 5 madde sıfır-bağlamlı executor için detaylı spec içerir. Tarih: 2026-06-02.
>
> **Çapraz-model iş bölümü:** Claude=mimar+doğrulayıcı+merge (GitHub) · MiniMax=executor (lokal git+pytest+push) · Gemini=deploy operatörü (Railway+Binance) · Operatör=onay+flat-book penceresi.

---

## 0. Backlog (önceliklendirilmiş)

| ID | Bulgu | Phase | Sev | Eff | Bağımlılık | Kim | Canlı risk / flat-book |
|---|---|---|---|---|---|---|---|
| **P0-1 S1** | prod `min_confluence:50` → 80 (ölçülmüş −43.75%→+11.29%) | strateji | **BLOCKER(capital)** | S | re-backtest doğrulama | Gemini(deploy)+operatör | Config-only; **flat-book GEREKMEZ**, restart yeter |
| **P0-2 C1** | Forming-bar repaint (tüm engine kapanmamış bar) | kod | **BLOCKER** | S | yok | MiniMax→Claude | Davranışsal; restart; flat-book önerilir |
| **P0-3 C2** | breaker PnL restart çift-sayım (`_reported_to_breaker` persist yok) | kod | MAJOR | S | yok | MiniMax→Claude | Restart; flat-book gerekmez |
| **P0-4 A1** | `gemini-3.5-flash` geçersiz → advisory ölü | kod | CRITICAL(data) | S | yok | MiniMax→Claude | Advisory shadow; canlı trade riski yok |
| **P0-5 C4** | balance-fetch yutma → fabrike $10k | kod | MAJOR | S | yok | MiniMax→Claude | Restart; flat-book gerekmez |
| P1-1 C3 | persist-before-verify bare-pozisyon penceresi | kod | MAJOR | M | yok | MiniMax→Claude | Restart; flat-book önerilir |
| P1-2 C5 | çift+yanlış-satır trade close (trace_id) | kod | MAJOR | S | migration? | MiniMax→Claude | DB/journal; flat-book gerekmez |
| P1-3 C6 | v2 `since_ts` ordinal-vs-ms birim uyuşmazlığı | kod | MAJOR | S | yok | MiniMax→Claude | v2 shadow; canlı riski yok |
| P1-4 C7 | v2 CONFIRMED→order re-validation yok | kod | MAJOR | M | C1 | MiniMax→Claude | v2 shadow |
| P1-5 C8 | Gemini blocking gate + stale entry | kod | MAJOR | M | A1 | MiniMax→Claude | A1 nedeniyle şu an no-op |
| P1-6 C9 | near_swing future-leak + OB 1-mum invariant | kod | MAJOR | S | yok | MiniMax→Claude | Confluence skoru; flat-book gerekmez |
| P1-7 F3.6 | preflight/bot_runner default arşiv-config landmine | kod | MAJOR | S | yok | MiniMax→Claude | Sessiz başlatma reddi riski |
| P1-8 F3.2 | aggressive_v1 (CROSSED+hedge) DO-NOT-DEPLOY banner | config | MAJOR | S | yok | Claude | Yanlış-config deploy önleme |
| P2-1 S2 | Backtest commission + funding wire | test/infra | MAJOR | M | yok | MiniMax | Yok (offline) |
| P2-2 S3 | Korelasyon-aware sizing / cluster cap | kod | MAJOR | M | S2 | MiniMax→Claude | Sizing; flat-book önerilir |
| P2-3 H1 | binance url-routing test hermetic (vendored markets) | test/CI | MAJOR | S | yok | MiniMax | Yok |
| P2-4 H2 | alerter heartbeat env-config | test/CI | MAJOR | S | yok | MiniMax | Yok |
| P2-5 S6 | OOS split + Monte Carlo gate | test | MAJOR | M | S2 | MiniMax | Yok |
| P2-6 A2 | Gemini hata DEBUG→WARNING + JSONL error alanı | kod | HIGH | S | A1 | MiniMax | Yok |
| P2-7 A3 | sentiment registry freshness guard | kod | MEDIUM | S | yok | MiniMax | Yok |
| P2-8 F1(notional) | 2-pass risk review (notional-blind kaldır) | kod | MEDIUM | M | A1 | MiniMax | Advisory |
| P3-1 A4 | htf_slope_pct orchestrator→ctx | kod | MEDIUM | S | yok | MiniMax | Advisory |
| P3-2 S7 | Regime ML forward-label (dairesellik kır) | kod/ML | MEDIUM | L | S2 | MiniMax | Regime; backtest doğrula |
| P3-3 S5 | EV-ranked slot allocation | kod | MEDIUM | M | S2 | MiniMax→Claude | Sizing |
| P3-4 max_sl_atr | SL≥likidasyon mesafesinde reject (warn değil) | kod | MAJOR | S | yok | MiniMax→Claude | Guard sıkılaştırma (güvenli) |
| P3-5 cleanup | 04_cleanup.md (arşivle/taşı/birleştir) | cleanup | MINOR | S | yok | Claude/MiniMax | Yok |
| P3-6 F2(gating) | gating arbitration + min_team_score + shadow korelasyon | agent-infra | NICE | L | A1+A2+50 trade | Claude+operatör | gating=false kalır |

> **Genel kural:** Hiçbir madde `agent_team.gating:false`'ı, deterministik breaker/guard/orphan/reverse/entry-drift'i ZAYIFLATMAZ. Canlı margin/mode değişimi (yok bu backlog'da) flat-book gerektirir. P3-4 guard'ı SIKILAŞTIRIR (güvenli yön).

---

## 1. İlk 5 madde — detaylı uygulama spec'i (sıfır-bağlamlı executor için)

> Bu 5 madde tek bir "canlı botu stabilize et" batch'i: hepsi S-effort, yüksek etki. Önerilen sıra: S1 (en hızlı capital fix) → A1 → C2 → C4 → C1. Her biri ayrı atomik PR.

### SPEC P0-1 (S1) — min_confluence 50 → 80
- **Dosya:** `configs/config.phase2_1k.yaml:101`
- **Değişiklik:** `min_confluence: 50` → `min_confluence: 80` (yorumu güncelle: "h1c validated +11.29%/2.83%DD").
- **Gerekçe kanıtı:** `docs/results/2026-05-05-phase-A-validation.md` (conf50 = −43.75%/44%DD) vs `2026-05-06...h1c_conf80.md` (conf80 = +11.29%/2.83%DD), aynı 10 sembol.
- **DOĞRULAMA ÖNCESİ (zorunlu):** mevcut engine (v1 path) ile `python -m backtest.cli portfolio --config configs/config.phase2_1k.yaml` conf=50 vs conf=80 365g re-backtest; conf=80'in ≥ conf=50 getiri + ≤ DD verdiğini teyit et (engine değişmiş olabilir).
- **TDD/kanıt:** backtest comparison çıktısı PR'a eklenir; gate `total_return(conf80) > total_return(conf50)` ve `max_dd(conf80) < max_dd(conf50)`.
- **Kim:** Gemini (Railway env restart) + operatör onay. **Risk:** config-only, flat-book gerekmez, 5dk restart. Rollback: değeri geri al.
- **NOT:** Alternatif/üst hamle — aggressive_v1 sembol seti (curated 9) + conf 70/80 (+49% validated). Ama o, sembol+margin profili değiştirir → ayrı karar.

### SPEC P0-4 (A1) — gemini-3.5-flash → gemini-2.0-flash
- **Dosyalar:** `engine/agents/gemini_client.py:36` (`DEFAULT_MODEL`), `engine/agents/team.py:75`, `engine/ai/sentiment.py:56`, `engine/signals.py:236`, `config.yaml:222`, `configs/config.phase2_1k.yaml` (agent_team.model varsa), `backend/api.py:584`, `ops/alerter/formatter.py:73`, `main.py:247` (validate model allow-list).
- **Değişiklik:** tüm `"gemini-3.5-flash"` → `"gemini-2.0-flash"`. `formatter.py` raw httpx → `GeminiClient` kullan. `validate_config`'e geçerli-model allow-list kontrolü ekle.
- **TDD:** (1) `test_gemini_model_valid`: `GeminiClient().model in {gemini-1.5-flash, gemini-2.0-flash, gemini-2.5-flash}`. (2) httpx 404 patch → `complete_json` `{}` döner AMA `log.warning` emit eder (DEBUG değil) — bu A2 ile birleşir.
- **Kim:** MiniMax (kod+test+push) → Claude (review+merge). **Risk:** advisory shadow, canlı trade riski yok. GEMINI_API_KEY prod'da yoksa yine NEUTRAL (fail-safe korunur).
- **NOT:** Bu fix shadow veri toplamayı BAŞLATIR; F2 (gating) ön-koşulu (≥50 geçerli-LLM trade) buradan sayılır.

### SPEC P0-3 (C2) — `_reported_to_breaker` persist
- **Dosyalar:** `engine/lifecycle.py` (`to_full_dict`/`from_full_dict`), `engine/safe_orchestrator.py:778-782` (STEP5).
- **Değişiklik:** (1) `to_full_dict`'e `"_reported_to_breaker": getattr(self,"_reported_to_breaker",False)` ekle; `from_full_dict`'te `pos._reported_to_breaker = bool(d.get("_reported_to_breaker", False))`. (2) Belt-and-suspenders: STEP5 yalnız bu-process'te kapanan pozisyonları saysın (`self._closed_this_session: set` ID'leri).
- **TDD:** open→close→STEP5 (breaker.current_balance pnl kadar 1× oynar, `len(trades_today)==1`) → `to_full_dict`→`from_full_dict` round-trip → STEP5 tekrar → `record_trade` **2. kez çağrılmaz** (balance değişmez).
- **Kim:** MiniMax → Claude. **Risk:** restart davranışı; flat-book gerekmez. Mevcut `test_cli_reconcile_parity.py` dedup testini bozmadığını doğrula.

### SPEC P0-5 (C4) — balance-fetch fail → skip cycle (fabrike $10k YOK)
- **Dosyalar:** `backend/bot_runner.py:431`, `engine/safe_orchestrator.py:916`.
- **Değişiklik:** `bot_runner` balance fetch except'inde `pass` yerine `balance=None` + flag set; `safe_orchestrator` canlı (non-dry-run) cycle'da `balance is None` ise **yeni giriş YOK** (stale gibi davran), `actual_balance = 10000.0` fallback'ini canlıda kullanma. `breaker.sync_balance` fabrike değerle çağrılmaz.
- **TDD:** `get_balance` raise → o cycle `OrderManager.open_position` çağrılmaz; `breaker.sync_balance` fabrike $10k ile çağrılmaz; mevcut pozisyon yönetimi (SL/TP/reconcile) devam eder.
- **Kim:** MiniMax → Claude. **Risk:** restart; flat-book gerekmez. Dikkat: dry_run/backtest yolunda $10k default'u korunabilir (sadece canlı yolda skip).

### SPEC P0-2 (C1) — forming-bar düşür (fetch_ohlcv)
- **Dosya:** `exchange/__init__.py:75-83` (`BinanceClient.fetch_ohlcv`), tek choke point.
- **Değişiklik:** `tf_ms = timeframe_to_ms(timeframe)`; son barın open-time'ı `now_ms - last_open_ms < tf_ms` ise (henüz kapanmamış) son satırı düş (`df = df.iloc[:-1]`). Timestamp-math tercih et (kör `iloc[:-1]` değil — bazı borsalar kapalı bar dönebilir). `backtest/engine.py`'a DOKUNMA (zaten kapalı bar besliyor).
- **TDD:** (1) 60 kapalı bar + bar[-2] close=100 (<swing 101, sinyal yok) + forming bar[-1] close=101.5 → `generate_signals` `[]`. (2) barı "kapat" → sonraki cycle sinyal çıkar. (3) wick 101.5 / close 100.5 forming → sinyal yok. (4) `fetch_ohlcv` çıktısının son barı her zaman kapalı (open_time + tf_ms ≤ now).
- **Kim:** MiniMax → Claude. **Risk:** Tüm sinyal zamanlamasını 1 bar geciktirir (doğru davranış). Backtest parite: kapalı-bar zaten standart, regresyon beklenmez ama tam backtest suite koş (`backtest-runner`). Flat-book önerilir (sinyal davranışı değişir).

---

## 2. Batch / bakım-penceresi planı
- **Batch-1 (config-only, flat-book gerekmez):** S1 → Gemini deploy. EN ACİL (canlı bleed).
- **Batch-2 (kod, atomik PR'lar, master'a #117 + audit fix batch):** A1, C2, C4, C5, C6, C9, F3.6 — flat-book gerekmez, ama deploy = container restart → sakin pencere.
- **Batch-3 (sinyal davranışı değişir, flat-book önerilir):** C1, C3, C7, P3-4, S3.
- **Batch-4 (infra/test, deploy etkisi yok):** S2, H1, H2, S6, A2, A3.
- **Batch-5 (uzun vade):** S7, S5, F2(gating — ancak A1+50-trade shadow sonrası).

> Tüm batch'ler `configs/config.phase2_1k.yaml` (prod) üzerinde; canlı margin/mode değişimi YOK → flat-book yalnız sinyal-davranışı değişiklikleri için önlem. Audit PR #118 master'a otomatik gitmez (DRAFT); kullanıcı #117 + H1/H2 + bu fix'lerle batch-merge eder.
