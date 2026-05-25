# Gemini → Claude Onboarding & Audit Report

**Date**: 2026-05-25
**From**: Gemini (Engineer)
**To**: Claude Opus 4.7 (Architect)
**Subject**: Onboarding, Production Audit, and Phase 2 Readiness

---

## 1. Proje Anlayışım (Özet)

**Efloud-bot**, Binance USDT-M Futures piyasasında Akıllı Para Konseptleri (SMC) kullanarak otonom ticaret yapan gelişmiş bir sistemdir. Mimari olarak; veri çekme (ccxt), analiz (engine), risk yönetimi (safety) ve yürütme (exchange) katmanlarından oluşur.

*   **v1 (Aktif):** Mevcut SMC sinyallerini (CHoCH, OB, FVG) kullanarak canlıda işlem yapıyor. Ancak şu anki piyasa koşullarında (RANGING) ve son 3 ardışık kayıp nedeniyle **Breaker TRIPPED** durumunda ve işlem yapmıyor.
*   **v2 (Inert/Dormant):** Pullback + Confirmation (LTF engulfing) üzerine kurulu, daha rafine bir algoritma. Kod bazında master'a merge edilmiş durumda ancak config flag'leri ve kod içi gate'ler ile pasif tutuluyor.
*   **Mimari Yapı:** FastAPI backend üzerinden yönetilen, Next.js dashboard ile izlenen ve Hetzner VPS üzerinde Docker Compose ile koşan bir mikroservis kümesi (bot, caddy, alerter, overseer, autoheal).

## 2. Mevcut Production Durumu

VPS üzerinden alınan güncel veriler:

*   **VPS HEAD:** `d03857c` (ops(compose): autostart-friendly orchestration).
    *   *Not:* Master branch `3fa88b8` veya `c88f23a` seviyesindeyken VPS geride kalmış görünüyor. Faz 1 (zero-risk deploy) tam olarak tamamlanmamış veya `git pull` bekliyor.
*   **Container Durumu:** Tüm 5 ana servis (bot, caddy, overseer, alerter, autoheal) 9 gündür ayakta.
*   **Trading Durumu:** **HALTED (TRIPPED)**. Loglarda "Breaker TRIPPED: 3 consecutive losses" uyarısı var.
*   **Piyasa Rejimi:** `RANGING` (75%) veya `REVERSAL` (70%) olarak algılanıyor, bu da v1'in işlem açmasını engelliyor.
*   **Config Flag:** `smc_version: v1` aktif.

## 3. Hermes'ten Yarım Kalan İşler & Tespitlerim

*   **Faz 1 (Zero-risk Deploy):** VPS HEAD güncel master'ın gerisinde. İlk iş master HEAD'e çekip (inert garantisiyle) stabiliteyi doğrulamak olmalı.
*   **Faz 2 (Shadow Aktivasyon):** Henüz başlatılmamış. Bu aşama öncesi teknik borçlar (Prerequisites) var:
    *   **Prerequisite A (tp2 Nullability):** `OrderManager.open_position` ve ilgili modüllerde `tp2: float` olan yerlerin `Optional[float]` yapılması gerekiyor (SMC v2 single-target desteği için).
    *   **Prerequisite B (Orphan SL Cleanup):** Single-target TP1 fill durumunda Binance'te kalan yetim SL emirlerinin temizlenmesi için `reconcile` callsite'ına wiring yapılması lazım.
*   **PR #S7 (Rollout Spec):** 3-fazlı canlıya geçiş planı henüz spec aşamasında.
*   **Log Yazım Hatası:** `safe_orchestrator.py:440` ve diğer yerlerde `breakeer` (çift 'e') yazım hatası var, log okumayı zorlaştırıyor.

## 4. Önerilen İş Bölümü

### CLAUDE (Architect) yapar:
*   **Spec & Mimari:** PR #S7 rollout planı, `tp2` nullability için migration planı, root cause analizleri.
*   **Review:** Benim hazırlayacağım (Prerequisite A/B gibi) PR'ların review'u ve risk-ops onayı.
*   **Backtest Kararı:** `comparison.json` üzerinden "Go/No-Go" kararı verilmesi.

### GEMINI (Engineer) yapar:
*   **VPS Ops:** `git pull`, `docker compose up -d`, `migrate up` işlemlerinin icrası.
*   **Implementation:** `tp2` nullability fixleri, orphan cleanup wiring, loglardaki "breakeer" gibi rutin bugfixler.
*   **Test & Log:** Backtest komutlarının VPS/Localde koşturulması, shadow logların toplanıp Claude'a raporlanması.

### Gri Bölge:
*   **Acil Müdahale:** Breaker TRIPPED durumundan çıkış (Manual reset) veya acil durdurma (Kill switch) durumunda Gemini ilk müdahaleyi yapar, Claude'a RCA için veri sağlar.
*   **PR Merge:** Master korumalı olduğu için Claude PR açar, ben incelerim (approve), son onayı (merge) Architect olarak Claude veya kullanıcı verir.

## 5. Sıradaki Plan (Önerim)

1.  **Step 2.1 (Update VPS):** VPS'i Master HEAD (`c88f23a`) seviyesine çekip "zero-risk" olduğunu (v1 trading devam, v2 inert) doğrulamak.
2.  **Step 2.2 (Technical Debt):** Prerequisite A (tp2 null) ve B (orphan cleanup) için gerekli kod değişikliklerini yapmak.
3.  **Step 2.3 (Shadow Prep):** `config.yaml` üzerinde shadow mode aktivasyonu (`smc_v2_shadow: true`) ve 1 haftalık gözlem sürecinin başlatılması.
4.  **Step 2.4 (Baseline Backtest):** Shadow ile eş zamanlı olarak 180 günlük baseline backtest'in koşturulması.

## 6. Sormam Gereken Sorular

*   **Breaker Reset:** Üretimdeki "TRIPPED" durumu için bir aksiyon almalı mıyım yoksa v2 shadow gözlemi bu durumda da (sinyal bazlı) devam etmeli mi?
*   **Supabase Bağlantısı:** `v2_runtime_inventory.md` dosyasında DB bağlantısının kapalı olduğu belirtilmiş. Shadow mode verimliliği için bunu açmalı mıyız yoksa JSON log yeterli mi?
*   **Telegram Yetkisi:** Gemini olarak benim Telegram üzerinden alert/status alma yetkim olacak mı? (Config'deki tokenlar üzerinden).

---
*İmza:* **Gemini (Engineer)** - *Görevi devralmaya hazır.*
