# Efloud-bot — AI Entegrasyon & Platform Yol Haritası
# ════════════════════════════════════════════════════
# Son güncelleme: 2026-05-26
# Hedef kitle: Tüm AI ajanları (Gemini, Claude, Antigravity) + Utku/Hermes
# ────────────────────────────────────────────────────
# Bu dosya projenin `docs/` klasöründedir — ajanlar sıradaki işi seçerken
# buraya bakmalı, skill geliştirirken buraya not bırakmalıdır.
# ────────────────────────────────────────────────────

---

## 0. Mevcut Durum Özeti (Bağlam)

| Konu | Durum |
|------|-------|
| **Bot versiyonu** | v2.1 — CANLI (Hetzner VPS, Binance USDT-M Futures) |
| **Strateji** | SMC v1 aktif, v2 dormant (3 katmanlı inert guard) |
| **Config** | `aggressive_v1`: 10 sembol, tier-based confluence (70/80/85) |
| **Dashboard** | FastAPI :8080 + Next.js 15 (static export) |
| **Alerts** | Telegram (ops/ modülü) |
| **Backtest** | `backtest/engine.py` — walk-forward, `compare` modu var |
| **Exchange** | Binance-only (CCXT), forex adapter roadmap açık |
| **Klonlanan referanslar** | `external_repos/` altında: autoresearch, graphify, caveman, superpowers, system_prompts_leaks |

---

## 1. Öncelik Sıralaması (Faz → Eylem → Gerekçe)

### Faz 0 — Temel Hijyen (Maliyet & Hız — 0 Risk)

> **Hedef:** Ajan oturum maliyetini düşür, proje haritasını çıkar.

| # | İş | Kaynak Repo | Etki | Detay |
|---|---|---|---|---|
| ✅ 0.1 | `CLAUDE.md` ve `HERMES.md` dosyalarını caveman-tarzı sıkıştır | `caveman` | Token girdisi ↓%40-50 | Teknik doğruluğu koruyarak, her oturum başında yüklenen ~22 KB belleği ~12 KB'a indirir. Kod referansları, path'ler ve config key'leri byte-seviyesinde korunmalı. |
| ✅ 0.2 | Proje bilgi grafiğini çıkar (`graphify`) | `graphify` | Mimari görünürlük | `graphify extract .` → `graphify-out/graph.json` + `GRAPH_REPORT.md`. Forex adapter refaktörü öncesi bağımlılık haritası. |
| 0.3 | Bu roadmap'i `CLAUDE.md` §7'ye referans olarak ekle | — | Ajan keşfedilebilirliği | Tüm ajanlar bu dosyayı sıradaki iş listesi olarak kullanır. |

### Faz 1 — Otonom Strateji Optimizasyonu (Yüksek Değer, Orta Risk)

> **Hedef:** Autoresearch mantığıyla backtest parametrelerini otonom optimize et.

| # | İş | Detay |
|---|---|---|
| ✅ 1.1 | `scripts/optimize_strategy.py` oluştur (2026-05-26) | Karpathy'nin autoresearch yaklaşımı: ajan, `config.yaml` içindeki şu parametreleri sistematik olarak değiştirir ve her kombinasyon için `backtest.cli compare` koşturur: `min_confluence` (50-90), `risk_per_trade_pct` (0.5-3.0), `recency_bars` (20-60), `min_rr` (1.2-2.5) |
| ✅ 1.2 | Optimizasyon hedef fonksiyonu (2026-05-26) | `max(sharpe_like) subject to max_drawdown_pct ≤ 12%` — tek metrik yerine çok-amaçlı Pareto front |
| ✅ 1.3 | Sonuçları `reports/optimization/` altına kaydet (2026-05-26) | Her koşturma: parametre seti + backtest metrikleri JSON. En iyi 5 kombinasyonu `docs/results/` altına summary olarak yaz. |
| ✅ 1.4 | **GÜVENLİK:** Otonom script asla canlı config'i değiştirmez (2026-05-26) | Sadece `configs/candidate_*.yaml` dosyaları üretir. Production'a promote etmek Hermes onayı gerektirir. |

**Bağımlılık:** Efloud backtest motoru (`backtest/engine.py`) çalışır durumda olmalı. Cache'd OHLCV verisi gerekli (`scripts/prefetch_data`).

### Faz 2 — Google AI Entegrasyonu (Yüksek Değer, Düşük Risk)

> **Hedef:** Gemini API'yi strateji karar desteği olarak entegre et.

| # | İş | Platform | Detay |
|---|---|---|---|
| ✅ 2.1 | **Gemini API — Makro Duygu Analizi Layer'ı** | Google AI Studio / Gemini API | Yeni modül: `engine/ai/sentiment.py`. Gemini'nin 2M+ token bağlam penceresi ile son 30 günlük daily OHLCV + Fear&Greed Index + funding rate verilerini analiz ederek "RISK-ON / RISK-OFF / NEUTRAL" makro skoru üretir. Bu skor `SafeOrchestrator.run_cycle()` içinde confluence skoruna ±5 puan bonus/penalty olarak eklenir. (2026-05-26) |
| 2.2 | **Gemini API — SMC Yapı Doğrulama** | Google AI Studio / Gemini API | `engine/signals.py` içindeki sinyal üretiminden sonra, Gemini'ye HTF+MTF+Entry TF'nin son 200 mumunu göndererek "Bu BOS/CHoCH gerçekten kurumsal akış mı, yoksa noise mı?" sorusunun yanıtını alır. Confidence ≥70 olmayan sinyalleri filtreler. |
| 2.3 | **Vertex AI — Regime Detection ML** | Vertex AI AutoML | `engine/regimes/__init__.py`'deki kural tabanlı ADX/ATR rejim algılayıcısını, geçmiş verilerle eğitilmiş bir XGBoost/TabNet modeli ile zenginleştirir. Günlük otomatik yeniden eğitim pipeline'ı. |
| 2.4 | **Firebase Genkit — Yapılandırılmış Çıktı** | Firebase Genkit | Telegram bildirimleri ve ajan yanıtları için structured JSON output. `ops/` modülündeki Telegram formatter'ı Genkit ile sarmalanır. |

**Kritik Kural:** Gemini API çağrıları **asla trade blocker olmamalı**. API timeout veya hata durumunda mevcut SMC sinyali olduğu gibi kullanılır (graceful degradation). Ek gecikme bütçesi: max 2 saniye/sembol.

### Faz 3 — Altyapı Güçlendirme (Uzun Vadeli)

| # | İş | Platform | Öncelik |
|---|---|---|---|
| 3.1 | Sinyal kuyruğu: Ualgo_bot ↔ Orchestrator arası | Google Cloud Pub/Sub | YÜKSEK — sinyal kaybını sıfırlar |
| 3.2 | Trade log warehouse | BigQuery veya Supabase (mevcut) genişletme | ORTA — büyük veri analizi |
| 3.3 | Canlı dashboard | Looker Studio (BigQuery'ye bağlı) veya mevcut Next.js geliştirme | DÜŞÜK — mevcut dashboard çalışıyor |
| 3.4 | Serverless cron | Cloud Scheduler + Functions | DÜŞÜK — Hetzner cron yeterli şimdilik |
| 3.5 | Forex adapter | `ExchangeAdapter` protocol + MT5/OANDA concrete impl | AÇIK — broker kararı bekliyor |

### Faz 4 — Ajan Kendini Geliştirme Döngüsü (Sürekli)

> **Hedef:** Her ajan oturumunda sistem biraz daha iyi olsun.

| # | Mekanizma | Detay |
|---|---|---|
| 4.1 | **Skill Feedback Loop** | Her skill kullanımından sonra ajan, skill'in etkinliğini `docs/skill_log.md` dosyasına not eder: hangi skill kullanıldı, ne kadar sürdü, sonuç başarılı mı. Zaman içinde düşük performanslı skill'ler revize edilir. |
| 4.2 | **Prompt Evolution** | `.claude/agents/` altındaki ajan prompt'ları, `system_prompts_leaks` referanslarından öğrenilen best-practice'lerle periyodik olarak güncellenir. Her güncelleme `docs/prompt_changelog.md`'ye loglanır. |
| 4.3 | **Backtest-Driven Config** | Faz 1 optimization script'inin sonuçları, Faz 2 Gemini sentiment layer'ının doğruluğu ile cross-validate edilir. Her ayın sonunda "config review" skill'i tetiklenir. |
| 4.4 | **Graphify Otomatik Güncelleme** | Git hook ile her commit sonrası `graphify update .` çalıştırılarak bilgi grafiği güncel tutulur. Ajanlar her oturumda `graphify query` ile kod tabanını sorgular. |

---

## 2. Google AI/Cloud Platformları — Kullanım Kılavuzu

### Doğrudan Entegre Edilebilir (Kısa Vadeli)

| Platform | Efloud'daki Rolü | Nereye Entegre | Maliyet Tahmini |
|---|---|---|---|
| **Gemini API (Flash)** | Makro duygu analizi + SMC doğrulama | `engine/ai/sentiment.py` (yeni) | ~$5-10/ay (günde ~1000 istek, Flash tier) |
| **Google AI Studio** | Geliştirici prototyping & prompt test | Lokal geliştirme | Ücretsiz |
| **Firebase Genkit** | Structured LLM output | `ops/telegram_formatter.py` | Ücretsiz (OSS) |

### Orta Vadeli (VPS Sınırları Zorlanınca)

| Platform | Efloud'daki Rolü | Tetikleyici |
|---|---|---|
| **Cloud Pub/Sub** | Telegram sinyal kuyruğu | Ualgo_bot sinyal kaybı yaşandığında |
| **Vertex AI** | Regime detection ML modeli | Kural tabanlı regime detector %60+ false positive verdiğinde |
| **Cloud Run** | Backend serverless migration | VPS bakım maliyeti > Cloud Run maliyeti olduğunda |

### Uzun Vadeli (Ölçeklenme Aşamasında)

| Platform | Efloud'daki Rolü | Tetikleyici |
|---|---|---|
| **BigQuery** | Tarihsel trade analytics | 100K+ trade kaydı biriktiğinde |
| **Looker Studio** | Profesyonel P&L dashboard | Yatırımcı raporlama gerektiğinde |
| **Cloud Spanner** | Multi-region state | Birden fazla VPS/exchange olduğunda |
| **Secret Manager** | API key yönetimi | Takım büyüdüğünde |

---

## 3. Ajan-Arası İşbirliği Protokolü

Bu dosya hem **Gemini (Antigravity)** hem **Claude Code** hem de **Hermes** tarafından okunur.

### Kurallar

1. **İş seçimi:** Ajan bu dosyadaki faz/iş numarasını referans vererek çalışır (örn: "Faz 1.1 üzerinde çalışıyorum").
2. **Durum güncellemesi:** Tamamlanan işler bu dosyada `✅` ile işaretlenir, tarih eklenir.
3. **Çakışma önleme:** Aynı anda iki ajan aynı faz üzerinde çalışmamalı. Aktif çalışma `🔄` ile işaretlenir.
4. **Güvenlik sınırı:** Hiçbir ajan canlı `config.yaml`'ı, `docker-compose.prod.yml`'i veya `.env`'i doğrudan değiştirmez. Bu Hermes/Utku işidir.
5. **Skill geliştirme:** Yeni skill yazıldığında `.claude/skills/` veya Gemini skill dizinine eklenir + bu dosyanın Faz 4.1'ine loglanır.

### Dosya Referans Haritası

| Dosya | Kim Okur | Kim Yazar |
|---|---|---|
| `docs/ROADMAP_AI_INTEGRATION.md` (bu dosya) | Herkes | Herkes (consensus ile) |
| `CLAUDE.md` | Claude | Claude (Utku onayıyla) |
| `GEMINI.md` | Gemini/Flash | Opus veya Utku |
| `HERMES.md` | Hermes | Claude (Utku onayıyla) |
| `config.yaml` | Herkes | **SADECE Hermes/Utku** (canlı) |
| `.claude/agents/*.md` | Claude | Claude |
| `.claude/skills/*.md` | Claude | Claude |
| `docs/skill_log.md` | Herkes | Herkes |
| `docs/prompt_changelog.md` | Herkes | Herkes |
| `docs/handoff/*.md` | Herkes | Opus ve Flash |

---

## 4. Referans Repolar — Ne Zaman Başvurulur

| Repo | Ne Zaman Kullan |
|---|---|
| `external_repos/autoresearch` | Faz 1 (otonom optimizasyon scripti) yazarken `program.md` ve `train.py` loop mantığını referans al |
| `external_repos/graphify` | Faz 0.2'de ve sürekli: mimari görselleştirme, ajan bağlam güçlendirme |
| `external_repos/caveman` | Faz 0.1'de: memory sıkıştırma. Sonra: Telegram sinyal formatı kısaltma |
| `external_repos/superpowers` | Ajan skill/agent yazarken: TDD, brainstorming, subagent-driven-development pattern'leri |
| `external_repos/system_prompts_leaks` | Faz 4.2'de: ajan prompt evolution referansı. Özellikle `Google/gemini-3.5-flash.md` ve `Anthropic/claude-opus-4.7.md` |

---

## 5. Skill Kullanım Logu (Faz 4.1)

> Her skill kullanımı buraya loglanır. Zaman içinde düşük değerli skill'ler revize edilir.

| Tarih | Ajan | Skill | Sonuç | Not |
|---|---|---|---|---|
| 2026-05-26 | Antigravity (Opus) | İlk roadmap oluşturma | ✅ | Bu dosya oluşturuldu. |
| 2026-05-26 | Antigravity (Opus) | Model dispatch sistemi | ✅ | §6-7 eklendi, GEMINI.md mühendis rolüyle yeniden yazıldı. |
| — | — | — | — | — |

---

## 6. Model Dispatch Tablosu (🏛️ Opus Mimar / 🔧 Flash Mühendis)

> **Kural:** Kullanıcı model seçtiğinde, aktif model bu tabloyu okuyarak kendi
> sorumluluğundaki işleri otomatik seçer. Karşı model'in işine dokunmaz.

### Rol Tanımları

| Model | Rol | Güçlü Yanı | İş Tipleri |
|---|---|---|---|
| **🏛️ Claude Opus 4.6** | **Mimar (Architect)** | Derin analiz, karmaşık tasarım, uzun bağlam muhakemesi, risk değerlendirme | Mimari tasarım, spec yazma, code review, prompt optimizasyonu, güvenlik analizi, strateji değerlendirme |
| **🔧 Gemini 3.5 Flash** | **Mühendis (Engineer)** | Hızlı kod üretimi, implementasyon, test yazma, script çalıştırma | Python modül yazımı, pytest, frontend geliştirme, backtest çalıştırma, graphify/caveman uygulama |

### Görev Dağılım Tablosu

#### Faz 0 — Temel Hijyen

| # | İş | Model | Referans Repo | Gerekçe |
|---|---|---|---|---|
| ✅ 0.1 | Caveman memory sıkıştırma | 🔧 FLASH | `caveman` | Mekanik uygulama — dosya oku, sıkıştır, yaz |
| ✅ 0.2 | Graphify mimari harita çıkar | 🔧 FLASH | `graphify` | Komut çalıştırma + çıktı toplama |
| 0.3 | CLAUDE.md referans güncelleme | 🏛️ OPUS | — | Bellek dosyası tasarımı — tutarlılık kritik |

#### Faz 1 — Otonom Strateji Optimizasyonu

| # | İş | Model | Referans Repo | Gerekçe |
|---|---|---|---|---|
| 1.1 | `optimize_strategy.py` spec yazımı | 🏛️ OPUS | `autoresearch` | Hedef fonksiyonu, parametre aralıkları, güvenlik sınırları tasarımı |
| 1.2 | `optimize_strategy.py` implementasyonu | 🔧 FLASH | `autoresearch` | Opus spec'ine göre Python kodu yaz |
| 1.3 | Sonuç raporlama formatı | 🤝 ORTAK | — | Opus format tasarlar, Flash template'i implemente eder |
| 1.4 | Güvenlik guard'ları (canlı config koruması) | 🏛️ OPUS | — | Risk analizi ve guard tasarımı |

#### Faz 2 — Google AI Entegrasyonu

| # | İş | Model | Referans Repo | Gerekçe |
|---|---|---|---|---|
| ✅ 2.1 | Gemini sentiment layer **tasarımı** | 🏛️ OPUS | — | API akışı, hata yönetimi, graceful degradation spec (2026-05-26) |
| ✅ 2.1i | Gemini sentiment layer **implementasyonu** | 🔧 FLASH | — | `engine/ai/sentiment.py` kodunu yaz, test yaz (2026-05-26) |
| 2.2 | SMC yapı doğrulama **tasarımı** | 🏛️ OPUS | — | Prompt engineering, doğruluk metrikleri |
| 2.2i | SMC yapı doğrulama **implementasyonu** | 🔧 FLASH | — | Kodu yaz, backtest ile valide et |
| 2.3 | Vertex AI regime detection | 🤝 ORTAK | — | Opus ML mimarisi, Flash eğitim pipeline'ı |
| 2.4 | Firebase Genkit formatter | 🔧 FLASH | — | Mekanik implementasyon |

#### Faz 3 — Altyapı

| # | İş | Model | Gerekçe |
|---|---|---|---|
| 3.1 | Pub/Sub tasarımı | 🏛️ OPUS | Mimari karar |
| 3.1i | Pub/Sub implementasyonu | 🔧 FLASH | Kodu yaz |
| 3.3 | Dashboard UI geliştirme | 🔧 FLASH | Frontend kodu |
| 3.5 | Forex adapter **protocol tasarımı** | 🏛️ OPUS | `ExchangeAdapter` abstract class tasarımı |
| 3.5i | Forex adapter **concrete impl** | 🔧 FLASH | `BinanceAdapter`, `MT5Adapter` kodu |

#### Faz 4 — Kendini Geliştirme

| # | İş | Model | Referans Repo | Gerekçe |
|---|---|---|---|---|
| 4.1 | Skill etkinlik analizi | 🏛️ OPUS | — | Pattern tanıma, meta-analiz |
| 4.2 | Prompt evolution | 🏛️ OPUS | `system_prompts_leaks` | Prompt stratejisi tasarımı |
| 4.3 | Config review | 🤝 ORTAK | — | Opus analiz, Flash backtest koşturma |
| 4.4 | Graphify hook kurulumu | 🔧 FLASH | `graphify` | Git hook implementasyonu |

### Otomatik Referans Repo Seçimi

> Model şu algoritmayı takip eder:

```
GÖREV al → dispatch tablosundan model etiketini kontrol et
  → kendi etiketimse → BAŞLA
  → karşı modelin etiketiyse → ATLA, handoff notu bırak
  → ORTAK ise → spec var mı kontrol et
      → spec varsa → implemente et
      → spec yoksa ve ben OPUS isem → spec yaz
      → spec yoksa ve ben FLASH isem → handoff notu bırak, OPUS'a bırak

BAŞLARKEN referans repo gerekli mi?
  → dispatch tablosundaki "Referans Repo" sütununa bak
  → repo belirtilmişse → external_repos/{repo}/README.md oku
  → ilgili dosyayı (program.md, SKILL.md, vb.) referans al
  → repo belirtilmemişse → direkt çalış

BİTİRİRKEN:
  → docs/handoff/{tarih}_{görev}.md yaz (ne yapıldı, test sonuçları)
  → docs/skill_log.md güncelle
  → bu dosyadaki görev satırını ✅ işaretle
```

---

## 7. Handoff Protokolü (Opus ↔ Flash)

### Handoff Dosya Formatı

`docs/handoff/YYYY-MM-DD_faz-X-Y_{özet}.md` formatında:

```markdown
# Handoff: Faz X.Y — {Görev Adı}

**Yazan:** 🏛️ Opus / 🔧 Flash
**Tarih:** YYYY-MM-DD
**Durum:** spec_hazır / implementasyon_tamam / review_bekliyor

## Ne Yapıldı
- ...

## Karşı Model İçin Not
- Flash: şu dosyaları implemente et → ...
- Opus: şu tasarım kararını al → ...

## Dosya Değişiklikleri
- `engine/ai/sentiment.py` — yeni (spec tamamlandı, impl bekliyor)
- ...

## Test Sonuçları (varsa)
- `pytest tests/test_xxx.py` → PASSED/FAILED
```

### Çalışma Akışı Diyagramı

```
Utku/Hermes: "Şu feature'ı yapalım"
        │
        ▼
    ┌─────────┐
    │ OPUS    │ ← Mimari tasarım, spec, risk analizi
    │ Mimar   │ → docs/handoff/{spec}.md yazar
    └────┬────┘
         │ Spec hazır
         ▼
    ┌─────────┐
    │ FLASH   │ ← Spec'i okur, kodu yazar, test yazar
    │ Mühendis│ → docs/handoff/{impl}.md yazar
    └────┬────┘
         │ İmplementasyon tamam
         ▼
    ┌─────────┐
    │ OPUS    │ ← Code review, güvenlik analizi
    │ Reviewer│ → Onay veya revizyon talebi
    └────┬────┘
         │ Onaylandı
         ▼
    Hermes/Utku: Deploy kararı
```

---

*Bu dosya yaşayan bir dokümandır. Her ajan oturumunda güncellenir.*

