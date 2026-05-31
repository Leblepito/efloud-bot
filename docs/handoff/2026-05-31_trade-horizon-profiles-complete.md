# Handoff: Faz 3.7 — Trade-Horizon Profiles Integration

**Yazan:** 🏛️ Gemini Orchestrator (Antigravity SMR)
**Tarih:** 2026-05-31
**Durum:** implementasyon_tamam (PR #109 Açıldı & İnceleme Bekliyor)

---

## 🛠️ Ne Yapıldı

### 1. Python Engine & TDD
* **`data/timeframes.py`:** `resolve_timeframes()` ve canonical `PROFILES` eklendi. Monotonik artış kontrolü (`Entry < MTF < HTF`) strict validation ile güvenceye alındı. `1w` zaman dilimleri için `kline_limit` otomatik olarak `250` bar ile sınırlandırıldı.
* **Giriş Noktaları:** `main.py`, `backend/bot_runner.py` (daemon), `backtest/cli.py` ve `scripts/run_phase_a.py` güncellenerek tüm yapılandırma okuma noktaları güvenli resolver ile sarmalandı. Daemon'daki sessiz yanlış-TF bug'ı tamamen kapatıldı.
* **Testler:** 14 yeni birim test içeren `backend/tests/test_timeframe_profiles.py` oluşturuldu. Tüm testler yerel olarak **başarıyla geçmiştir (14 passed)**.
* **Backward Compatibility:** `profile` parametresi boş bırakıldığında veya `custom` girildiğinde bot eski davranışına (birebir `configs/config.phase2_1k.yaml` ayarları) sorunsuzca döner.

### 2. TradingView Pine Script v6
* **4 Pine Script Dosyası (`signals_v1`, `strategy_v1`, `signals_v2`, `strategy_v2`):** Dropdown profil seçimi (`scalp`, `mid`, `long`, `custom`) ile güncellendi.
* **`1w` (Haftalık) Uyuşmazlığı Çözümü:** Mapped `1w` to `"W"` (Pine week period notation) for request.security calls to prevent compile errors.
* **Görsel Emniyet Banner'ı:** Ekrana eklenen `warnTbl` nesnesi sayesinde grafik periyodu ile aktif profilin beklediği entry periyodu eşleşmediğinde kırmızı renkte `⚠️ YANLIŞ ZAMAN DİLİMİ` uyarısı çizilir.
* **Canlı Derleme:** `efloud_signals_v1.pine` dosyası yerel TradingView Desktop uygulamasına enjekte edilip derlendi ve **SIFIR HATA** ile doğrulandı.

---

## ⚠️ Hermes / Utku İçin Canlı Deploy & Geçiş Runbook'u

1. **İnceleme & Test:**
   * PR #109'u inceleyin (`git checkout feat/trade-horizon-profiles`).
   * Yerel testleri koşturun: `.venv\Scripts\pytest backend/tests/test_timeframe_profiles.py`
2. **Flat Koşuluyla Merge:**
   * Bot üzerinde **açık pozisyon bulunmadığı (flat)** bir zaman diliminde PR #109'u `master` dalına merge edin.
   * *Neden:* Aktif pozisyonlar varken TF profilinin değişmesi, botun pozisyon yönetimi döngüsünde anomali yaratabilir.
3. **Konfigürasyon Değişimi & Restart:**
   * Profil değiştirmek için `configs/config.phase2_1k.yaml` (veya ilgili üretim config dosyasında) `timeframes` altına `profile: scalp | mid | long` yazın ve botu restart edin. (Runtime/canlı değişim desteklenmez, stabilite için restart şarttır).

---

## 📊 Ajan Oturum Kayıtları & Roadmap Güncellemeleri
* [ROADMAP_AI_INTEGRATION.md](file:///c:/Users/utkuc/Downloads/efloud-bot/docs/ROADMAP_AI_INTEGRATION.md) dosyasına Faz 3.7 satırı eklendi ve `✅` olarak işaretlendi.
* [skill_log.md](file:///c:/Users/utkuc/Downloads/efloud-bot/docs/skill_log.md) dosyasına 2026-05-31 tarihli TDD + TradingView MCP skill kullanım günlüğü başarıyla işlendi.
