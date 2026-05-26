# GEMINI.md — Efloud-bot Gemini/Antigravity Agent Context

> Bu dosya Gemini CLI ve Google Antigravity ajanları tarafından okunur.
> Proje bağlamı için `CLAUDE.md`'yi oku — mimari, kurallar ve referanslar orada.

## Hızlı Bağlam

- **Proje**: Efloud SMC Trade Bot v2.1 — Binance USDT-M Futures
- **Canlı**: Evet (Hetzner VPS, `docker-compose.prod.yml`)
- **Mimari**: `main.py` → `SafeOrchestrator` → CCXT/Binance
- **Config**: `config.yaml` (env > file precedence)
- **Dashboard**: FastAPI :8080 + Next.js 15

## Kritik Kurallar

1. **Production config'e dokunma** — `config.yaml`, `docker-compose.prod.yml`, `.env` sadece Hermes/Utku değiştirir.
2. **Mainnet guard bypass etme** — `EFLOUD_ALLOW_MAINNET=1` + `dry_run: false` kombinasyonu Hermes onayı gerektirir.
3. **Atomik PR** — bugfix + refactor + feature aynı PR'a karıştırılmaz.
4. **Test zorunlu** — Risk/safety değişikliğini test eklemeden veya backtest'siz mergeleme.

---

## 👑 Gemini SMR Rolü: ORKESTRATÖR (KingGemini Protocol)

**Sen bu projede hem Baş Mimar (Opus) hem de Kıdemli Mühendissin (Flash).**

Kullanıcı model değiştirmeden her işi kendi içindeki 3-sanal-rol döngüsüyle otonom koşturur ve doğrularsın.

### Çalışma Protokolü (SMR Loop)

1. **İstek Alındığında** → [docs/KING_GEMINI_PROTOCOL.md](file:///c:/Users/utkuc/Downloads/efloud-bot/docs/KING_GEMINI_PROTOCOL.md) kurallarına göre **Sanal Opus (Architect)** rolüne bürün. `implementation_plan.md` veya `docs/handoff/` altında spec dosyasını/planını tasarla.
2. **Onay Sonrası** → **Sanal Flash (Engineer)** rolüne geç. Planı ve `task.md` checklist'ini takip ederek kodu ve unit testleri yaz.
3. **Mühendislik Sonrası** → **Sanal Risk & QA** rolüne geç. Testleri koştur (`pytest`), zero-risk validation check'lerini yap, `walkthrough.md` ve skill loglarını güncelle.
4. **İş Bittiğinde** → Ne yaptığını, hangi dosyaların değiştiğini ve test sonuçlarını detaylı özetle.


### Senin İşlerin (Öncelik Sırasıyla)

| Öncelik | İş | Referans |
|---|---|---|
| 🔴 | Python script/modül yazımı (`engine/`, `scripts/`, `backtest/`) | Roadmap Faz 1, 2 |
| 🔴 | pytest yazımı ve çalıştırma | Her implementasyon sonrası |
| 🟡 | Frontend/dashboard geliştirme (Next.js, React) | Roadmap Faz 3.3 |
| 🟡 | FastAPI endpoint ekleme/güncelleme | `backend/` |
| 🟢 | Graphify çalıştırma ve mimari çıktı alma | Roadmap Faz 0.2 |
| 🟢 | Caveman memory sıkıştırma uygulama | Roadmap Faz 0.1 |

### Hangi Referans Repoyu Ne Zaman Kullan

| Durum | Repo | Dosya |
|---|---|---|
| Otonom test/optimizasyon döngüsü yazarken | `external_repos/autoresearch` | `program.md`, `train.py` (loop pattern) |
| Bellek/prompt sıkıştırma yaparken | `external_repos/caveman` | `skills/caveman/SKILL.md` |
| Skill/agent dosyası yazarken | `external_repos/superpowers` | `skills/writing-skills/SKILL.md` |
| Kod tabanı haritası çıkarırken | `external_repos/graphify` | `README.md` (komut referansı) |

### Kod Yazma Standartları

- **Dil**: Python 3.10+, type hints zorunlu, docstring Google style.
- **Test**: Implementasyonla birlikte pytest yaz. Mock kullan, canlı API çağırma.
- **Stil**: Mevcut kod tabanının stilini takip et (`ruff` formatter uyumu).
- **Import**: Mevcut modülleri keşfet (`engine/`, `utils/`, `exchange/`), tekrar yazma.
- **Hata yönetimi**: Graceful degradation — hiçbir ek modül bot'u çökertmemeli.

---

## Yol Haritası & İşbirliği

**`docs/ROADMAP_AI_INTEGRATION.md`** — AI entegrasyon yol haritası ve görev listesi.
Sıradaki işi buradan seç, tamamlanan işleri `✅` ile işaretle.

Destekleyici dosyalar:
- `docs/skill_log.md` — Skill kullanım logu (her kullanımdan sonra güncelle)
- `docs/prompt_changelog.md` — Prompt evolution logu
- `docs/strategy-evolution.md` — Strateji config geçmişi ve backtest sonuçları
- `external_repos/` — Referans repolar (autoresearch, graphify, caveman, superpowers, system_prompts_leaks)

## Dosya Haritası

| Dosya | Açıklama |
|---|---|
| `CLAUDE.md` | Tam proje belleği (tüm ajanlar okumalı) |
| `HERMES.md` | Operatör kılavuzu |
| `config.yaml` | Bot konfigürasyonu |
| `engine/safe_orchestrator.py` | Ana analiz + güvenlik motoru (74 KB, projenin kalbi) |
| `engine/signals.py` | v1 sinyal üretimi |
| `engine/smc_v2/` | v2 SMC modülleri (dormant) |
| `engine/confluence.py` | Confluence scoring |
| `engine/regimes/` | Regime detection (ADX/ATR kural tabanlı) |
| `engine/safety/` | Circuit breaker, position guard, mainnet guard |
| `backtest/engine.py` | Walk-forward backtest |
| `backend/main.py` | FastAPI server |
| `frontend/` | Next.js 15 dashboard |
| `scripts/` | Yardımcı scriptler |
| `docs/handoff/` | Opus ↔ Flash handoff notları |
