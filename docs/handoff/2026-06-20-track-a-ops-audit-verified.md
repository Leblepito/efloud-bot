# Track-A Bot-Ops Audit — Kodda Doğrulanmış Bulgular + Ölçeğe-Uygun Fix Backlog

> **Tarih:** 2026-06-20 · **Üreten:** Claude (Opus 4.8) — 3 domain-uzmanı advisory agent (fund-manager / market-microstructure / live-ops) read-only doğrulaması.
> **Girdi:** `docs/handoff/2026-06-20-next-session-frontend-marketing-u2algo-rebuild-plan.md` §3 Track-A (institutional-lens audit PART-1).
> **Ölçek filtresi (Karpathy Simplicity-First):** tek-operatör bot, ~$1035 × 2 paralel cüzdan, 10 majör. PART-2 blueprint (C++/FPGA/co-lo/KDB+/HSM) **kuzey-yıldızı = PARK.** Yakın-vade orantılı, düşük-maliyetli, default-OFF fix'ler.

---

## 1. Doğrulanmış Bulgular (her biri kodda file:line ile)

| # | Bulgu | Durum | Kanıt | Ölçek verdict |
|---|-------|-------|-------|---------------|
| **R1** | Correlation sizing INACTIVE | ✅ CONFIRMED | `engine/risk/correlation.py` tam implement ama YALNIZ kendi testinde import; canlı sizing yolu (`safe_orchestrator.py:1905` → `position_guard.py:207-357`) her sembolü bağımsız bahis sayar, haircut YOK | **Low-cost fix** (tek in-scope item) |
| R2 | Daily-loss reset TZ riski | ⛔ OUTDATED/REFUTED | `breaker.py:213-221` her iki taraf naive UTC; midnight-UTC calendar **kasıtlı fix** (bug-hunt #11); regresyon testi `test_breaker_daily_window.py` | Aksiyon YOK |
| R3 | Dynamic portfolio risk (VaR/beta) yok | ✅ CONFIRMED ama OVER-SCALE | sizing per-trade; portföy katmanı sadece `max_total_exposure:1.0` + `max_open_positions` (position_guard.py:269-280) | **PARK** — $1k'da VaR gereksiz; R1 haircut doğru-boy cevap |
| R4 | Breaker default `starting_balance=10000` footgun | ⚠️ CONFIRMED (latent) | `breaker.py:71` + `safe_orchestrator.py:215` default 10000; canlı config 1035 set ediyor ama config'i atlayan yol ~%5x mis-scale (C1 ailesi) | **Low-cost fix** (fail-closed/safe sentinel) |
| **X1** | REST execution, private WS fill stream yok | ✅ CONFIRMED | `exchange/__init__.py:1246-1285` REST-poll; TP1-hit "algoId yokluğundan" çıkarsama; user-data WS yok | **PARK** — 15m/$103'te latency önemsiz; SL/TP server-side |
| X2 | Execution algo (SOR/TWAP/VWAP) yok | ✅ CONFIRMED | `exchange/__init__.py:1084` tek market order | **PARK kalıcı** — $103 majörde impact ihmal |
| X3 | Backtest statik slippage | ✅ CONFIRMED | `backtest/slippage.py:7-9` sabit 5/10/5 bp | Çoğunlukla **PARK**; opsiyonel sl_slip kalibrasyonu |
| **X4** | Funding cost simplified + default OFF | ⚠️ PARTIALLY-TRUE | `backtest/metrics.py:77-106` scalar model **default 0.0** (kapalı!); `backtest/funding.py` time-series VAR ama UNWIRED | **Low-cost honesty fix** (makul default rate) |
| X5 | Binance-coupling (forex adapter olgunlaşmamış) | ✅ CONFIRMED nuance | `exchange/adapter.py` Protocol var ama `OrderManager` Binance-only; MT5/OANDA skeleton | **PARK** (2. borsa hedeflenmedikçe) |
| **S1** | Plaintext `.env` secrets | ✅ CONFIRMED + mitigation | `main.py:78-104` flat .env; mitigant: canWithdraw=false + gitleaks CI (`ci.yml:109-120`) | KMS **PARK**; **low-cost:** `.env.production` chmod 600 deploy runbook'a |
| **S2** | FastAPI auth zayıf | ⚠️ PARTIALLY-TRUE | `backend/auth.py` aslında signed-cookie + rate-limit 5/15dk + `hmac.compare_digest` + httponly/secure/samesite. AMA `SESSION_SECRET` unset→`"dev-only-secret..."` fallback → cookie forge edilebilir | **Low-cost fix** (prod'da SESSION_SECRET fail-closed); CSRF/OAuth PARK |
| S3 | Local file state, centralized telemetry yok | ✅ CONFIRMED | `engine/safety/state.py:29-116`; otel/datadog/prometheus = 0 match | **PARK** — healthz + Telegram + opsiyonel Supabase equity orantılı |
| S4 | Single-thread polling loop + CPU-bound SMC | ✅ CONFIRMED | `bot_runner.py:419-516` sequential; reconcile desync'i mitige eder | **PARK rewrite** — 5-10 sembolde orantılı; minor: çift `smc.analyze()` (safe_orchestrator `:958` v2 + `:1045` v1) |

---

## 2. Ölçeğe-Uygun Fix Backlog (öncelikli; her biri Karpathy contract: failing test + cerrahi diff + gate)

### Quick wins (düşük maliyet / yüksek değer — additive, default-OFF/fail-closed)
| ID | Fix | Dosya | Gate | Efor |
|----|-----|-------|------|------|
| **SEC-1** | `SESSION_SECRET` prod'da fail-closed (unset/dev-default ise auth reddet veya başlatma) — forge edilebilir cookie kapanır | `backend/auth.py:34-40` | TDD + operatör prod'da SESSION_SECRET set olduğunu doğrula (yoksa fail-closed prod'u kırar) | XS |
| **SEC-2** | `.env.production` chmod 600 (bot user) — deploy runbook + setup-server.sh kontrolü | `deploy/setup-server.sh` / `deploy/deploy.sh` | doc/ops, risk yok | XS |
| **BT-1** | Backtest funding default'u makul rate'e çek (0.0→~0.01%/8h) → backtest'ler funding-kapalı koşmasın (dürüstlük) | `backtest/metrics.py` / `backtest/engine.py:291-296` | NET-cost karşılaştırma (Edge Core); default değişimi mevcut sonuçları etkiler → backtest-gate | S |
| **CFG-1** | Breaker `starting_balance` default footgun (10000) → safe sentinel / fail-closed (config eksikse mis-scale yok; C1 ailesi) | `engine/safety/breaker.py:71`, `safe_orchestrator.py:215` | TDD + risk-ops (safety default) | S |

### Medium (gerçek değer ama backtest-gated)
| ID | Fix | Dosya | Gate | Efor |
|----|-----|-------|------|------|
| **R1** | Correlation sizing haircut'ı canlı sizing call-site'a bağla, **default-OFF flag**, deterministik (rho matrisi 10 sembol son getirileri → haircut). VaR DEĞİL. | `engine/risk/correlation.py` → `safe_orchestrator.py:1905` | **NET-cost backtest gate ZORUNLU** (correlation.py docstring'in kendi şartı) + risk-ops + operatör. Default-OFF ship → backtest → enable | M |

### Park (kuzey-yıldızı / over-scale — UYGULAMA)
WS user-data fill stream (X1) · SOR/TWAP/VWAP (X2) · orderbook-depth slippage (X3) · historical funding series (X4-üst) · multi-exchange OrderManager (X5) · VaR/beta engine (R3) · KMS/Vault (S1-üst) · OTel/Datadog (S3) · async/worker-per-symbol rewrite (S4) · CSRF/OAuth/SSO (S2-üst). Çift `smc.analyze()` (S4) = perf micro-opt, sadece compute darboğazı olursa.

---

## 3. Sıra önerisi
1. **SEC-1 + SEC-2** (güvenlik quick-win; SEC-1 prod SESSION_SECRET doğrulamasına gated).
2. **CFG-1** (safety footgun; C1 ailesi, risk-ops).
3. **BT-1** (backtest dürüstlüğü; gate'li — R1'i de besler).
4. **R1** (correlation haircut; default-OFF ship → backtest gate → operatör enable). Edge backlog'la (C4/H1/...) aynı NET-cost gate disiplini.

> Hiçbiri trade-path'i zayıflatmaz; hepsi additive/flag-OFF veya fail-closed. R1 + BT-1 backtest-gated, SEC-1/CFG-1 risk-ops/operatör-gated. PART-2 institutional blueprint kuzey-yıldızı kalır.

## 4. Referanslar
- Audit girdisi: `docs/handoff/2026-06-20-next-session-frontend-marketing-u2algo-rebuild-plan.md` §3
- Karpathy contract: `CLAUDE.md` → "Geliştirme Sözleşmesi"
- Edge Measurement Core (NET-cost gate): PR #227 · C1 fix: `7c35f5b`
- İlgili: `engine/risk/correlation.py`, `engine/safety/breaker.py`, `backend/auth.py`, `backtest/{slippage,metrics,funding}.py`, `exchange/adapter.py`
