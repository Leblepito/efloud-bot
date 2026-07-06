<p align="center">
  <img src="docs/assets/banner.svg" alt="Efloud Bot" width="100%"/>
</p>

<p align="center">
  <a href="README.md">🇬🇧 English</a> ·
  <a href="README.tr.md">🇹🇷 Türkçe</a> ·
  <a href="README.ru.md">🇷🇺 Русский</a>
</p>

<p align="center">
  <img src="https://github.com/Leblepito/efloud-bot/actions/workflows/ci.yml/badge.svg" alt="CI"/>
  <img src="https://img.shields.io/badge/python-3.11-blue.svg" alt="Python 3.11"/>
  <img src="https://img.shields.io/badge/borsa-Binance%20USDT--M%20Futures-f0b90b.svg" alt="Binance"/>
  <img src="https://img.shields.io/badge/strateji-Smart%20Money%20Concepts-6366f1.svg" alt="SMC"/>
  <img src="https://img.shields.io/badge/test-2.000%2B-2ea44f.svg" alt="Testler"/>
  <img src="https://img.shields.io/badge/TradingView-Pine%20v6-26a69a.svg" alt="Pine v6"/>
  <img src="https://img.shields.io/badge/lisans-Tescilli-lightgrey.svg" alt="Lisans"/>
</p>

<p align="center"><b>Binance USDT-M Futures için kurumsal sınıf Smart Money Concepts trading sistemi — deterministik çok katmanlı güvenlik motoru, canlı NET-maliyet edge ölçümü, TradingView göstergeleri ve fail-safe LLM danışma ekibi.</b></p>

---

## ✨ Genel Bakış

**Efloud Bot**, çoklu zaman dilimi zinciri (HTF yön → MTF onay → giriş tetikleyici) üzerinde **Smart Money Concepts (SMC)** — Break of Structure (BoS), Change of Character (CHoCH), Order Block (OB), Fair Value Gap (FVG) ve Optimal Trade Entry (OTE) — etrafında kurulmuş otomatik bir vadeli işlem sistemidir.

Onu farklı kılan sinyaller **değil**, sinyallerin etrafındaki **disiplindir**:

- Her emri süzen **deterministik 7 katmanlı güvenlik motoru** (devre kesici, pozisyon koruyucuları, yetim pozisyon koruması, kârda-ters-çevir koruması, fail-closed giriş-kayması koruması, düz-defter ön kontrolü, izole marjin).
- **Borsa-gerçeği mutabakatı** — gerçekleşen K/Z, yerel tahminlere değil Binance income kayıtlarına (`realizedPnl − komisyon − funding`) dayanır.
- Yerleşik **Canlı Edge Ölçüm Çekirdeği** — her sinyal ilk görüldüğü anda kaydedilir, gerçek piyasa verisiyle gölge-çözümlenir ve **maliyet düşülmüş, istatistiksel eşikli** edge metrikleri olarak raporlanır. Bot kendi edge'ini üretimde, dürüstçe ölçer.
- **7/24 izleme yardımcısı** (routines watcher) — devre kesici izleme, marjin izleme, pozisyon denetimi, config-sapma tespiti ve piyasa verisi toplama, trade döngüsünden bağımsız kendi ritimlerinde çalışır.
- **TradingView eş göstergeleri** (Pine v6) — aynı SMC durum makinesi, grafik üzerinde, repaint'siz; manuel teyit veya bağımsız kullanım için.
- Deterministik korumaları asla ezemeyen, yalnızca *danışmanlık yapan* **fail-safe çoklu-ajan LLM katmanı**. API anahtarı yoksa bot aynen çalışır.

> ⚠️ **Risk uyarısı.** Bu yazılım kaldıraçlı türevlerde gerçek parayla işlem yapar. Vadeli işlemler **sermayenin tamamının kaybına** yol açabilir. Buradaki hiçbir şey yatırım tavsiyesi değildir. Önce testnet'te çalıştırın; riski size aittir.

---

## 🏗 Mimari

Ana akış: **Piyasa verisi → SafeOrchestrator → SMC motoru (v1+v2) → Sinyal + Confluence → Risk/Boyutlandırma → Güvenlik Yığını → OrderManager → Binance**. LLM ajan ekibi hattın *yanında* danışman olarak durur; edge ölçüm katmanı (**SignalLedger → Gölge Çözümleyici → edge_report**) salt-okunur ve varsayılan KAPALI'dır (`signal_ledger.enabled` / `EFLOUD_SIGNAL_LEDGER_ENABLED`); izleme yardımcısı (routines watcher) her şeyi dışarıdan gözler. Mermaid diyagramları için İngilizce README'ye bakın.

Trade kararı her zaman deterministik `can_trade` kapısından ve güvenlik yığınından geçer — LLM katmanı istendiği an sıfır davranış değişikliğiyle kapatılabilir.

---

## 🛡 Güvenlik Yığını

| Katman | Ne yapar |
|---|---|
| **Devre Kesici** | Günlük / haftalık zarar limitleri + ardışık zarar duraklaması → HALT (yeniden başlatmalarda kalıcı) |
| **Pozisyon Koruyucuları** | İşlem başına notional tavanı, toplam maruziyet tavanı, SL-mesafe sınırları (max ATR üstünde opsiyonel sert RED), max tutma süresi, piramit tavanı |
| **Yetim Pozisyon Koruması** | Yerel state'in bilmediği borsa pozisyonlarını tespit eder; koruyucu SL koyabilir |
| **Kârda-Ters-Çevir Koruması** | Mevcut pozisyon komisyon+kayma tamponunun üzerinde kârda değilse ters sinyale dönüşü engeller |
| **Giriş-Kayması Koruması (fail-closed)** | Canlı fiyat sinyal çapasından kaydıysa veya TP1'i geçtiyse girişi reddeder — **fiyat verisi alınamazsa da girişi engeller** |
| **SL/TP Hassasiyet + Yerleşim Doğrulama** | Fiyatlar borsa hassasiyet kurallarıyla yuvarlanır (PRICE_FILTER reddi yok); girişten sonra yeniden sorgular, eksik bacakları onarır; SL doğrulanamazsa pozisyonu kapatır |
| **İzole Marjin + Tek Yön** | Başlangıçta ISOLATED marjin + one-way mod zorlanır; mod değişikliği öncesi düz-defter `[5/5]` ön kontrolü |
| **V2 Gölge Fail-Closed** | Yeni nesil SMC v2 motoru varsayılan gölge moddadır — config anahtarı düşse bile *gözlemler*, asla işlem açmaz |

Her katman **güvenli tarafa düşer**: yanlış yapılandırmanın en kötü sonucu *iptal edilen bir başlangıçtır* (işlem yok), asla korumasız canlı pozisyon değildir.

---

## 📏 Canlı Edge Ölçümü

Her bot satıcısının kaçındığı soru: *sinyal, maliyetler düşüldükten sonra gerçekten işlem edilebilir bir edge taşıyor mu?* Efloud Bot bunu kendisi hakkında, sürekli olarak yanıtlar:

- **SignalLedger** — her ilk-görüş sinyali (işlem açılan *ve* salt-izlenen) onay anında idempotent bir JSONL defterine yazılır.
- **Gölge Çözümleyici** (5 dk ritim) — varsayımsal dolumu tekrar oynatır, 1 dakikalık veride SL/TP yarışını muhafazakâr aynı-bar=SL kuralıyla çözer ve **komisyon + funding + kayma** maliyetlerini R-birimi cinsinden düşer.
- **Edge Raporu** (saatlik) — NET beklenti, Wilson güven aralıklı kazanma oranı, kâr faktörü, timeout sağlamlık paneli, boyut bazında kırılımlar — örneklem yeterli olana kadar dürüst `INSUFFICIENT EVIDENCE` etiketiyle.

Tamamı bayrakla kapılıdır (`signal_ledger.enabled: false` varsayılan) ve salt-okunurdur. Kalibrasyon kararları (confluence eşikleri, TP modelleri) histen değil, bu veriden verilir.

---

## 📈 TradingView Eş Paketi (Pine v6)

Bot'un SMC v2 mantığını birebir yansıtan iki grafik betiği — **EFloud Signals v2** (gösterge) ve **EFloud Strategy v2** (backtest):

- Tam **bekle-onayla durum makinesi**: CHoCH tetik → pullback bölgesi (FVG > OB > OTE) → engulfing teyidi.
- Opsiyonel kapılı **0–100 confluence skoru** (MTF CHoCH, HTF FVG, Order Block retest, OTE, SFP, premium/discount, günlük yön, AI-sentiment girdisi).
- **Yapısal olarak repaint'siz** — tüm üst zaman dilimi verisi son *kapanmış* barı kullanır (`[1]`-kaydırma + `lookahead_on`); canlı sinyal backtest ile birebir aynıdır.
- İşlem-ufku profilleri — scalp = 5m/1h/4h, mid = 15m/4h/12h, long = 1h/8h/1d (giriş / SMC-yapı / trend; tek kaynak: `data/timeframes.py` `PROFILES`) — volatilite-hizalı SL tamponu, TP1/TP2 merdiveni, grafik üstü gösterge paneli ve yanlış-zaman-dilimi uyarısı.

Kaynaklar [`pine/`](pine/) klasöründe; tam çeviri spesifikasyonu [`pine/PINE_SPEC.md`](pine/PINE_SPEC.md) dosyasındadır.

---

## 🤖 Ajan Sistemi

İkisi de **eklemeli ve fail-safe** iki bağımsız katman:

- **Çalışma-zamanı ekibi** (`engine/agents/`) her sinyali **gölge modda** inceler (`gating: false`). Kararlar loglanır ve `GET /api/ai/agents` ucundan izlenir. `GEMINI_API_KEY` yoksa her ajan `NEUTRAL` döner ve bot etkilenmez; *başarısız olan* (yapılandırılmamış değil) ajan `ERROR` döner ve ekip **güvenli tarafa kapanır**.
- **Geliştirme-zamanı ekibi** (`.claude/agents/`) kod bakımı **ve** trading uzmanlığı için uzman panelidir — SMC incelemesi, risk denetimi, kantitatif analiz, fon-yöneticisi seviyesinde gözetmen ve canlı-operasyon nöbetçisi. Hepsi **danışmandır**; hiçbiri deterministik korumaları zayıflatamaz.

---

## 🧰 Teknoloji Yığını

`Python 3.11` · `CCXT` · `pandas` / `numpy` · `FastAPI` + `uvicorn` · `asyncpg` (PostgreSQL / Supabase) · `pytest` (**2.000+ test**) · Pine Script v6 · Gemini / Anthropic (yalnızca danışma) · Docker Compose · Caddy (TLS) · GitHub Actions CI.

---

## 🚀 Hızlı Başlangıç

```bash
# 1. Kurulum
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Yapılandırma (önce testnet!)
cp .env.example .env          # BINANCE_API_KEY / SECRET gir
# config.yaml düzenle: testnet: true, dry_run: true

# 3. Çalıştır
python main.py                # CLI (config.yaml okur)

# 4. Dashboard / API
uvicorn backend.main:app --reload   # /healthz, /api/*, web paneli

# 5. İzleme yardımcısı (opsiyonel, önerilir)
python -m scripts.routines.runner watch
```

> **Canlıya geçiş** `EFLOUD_ALLOW_MAINNET=1` ve geçen bir ön kontrol gerektirir:
> `EFLOUD_ALLOW_MAINNET=1 EFLOUD_CONFIG_PATH=configs/config.phase2_1k.yaml python preflight.py` → **düz defterde** `[5/5]` geçmelidir.

---

## ⚙️ Yapılandırma

- `config.yaml` — CLI varsayılan profili.
- `configs/config.phase2_1k.yaml` — **üretimde aktif** profil (backend `EFLOUD_CONFIG_PATH` ile okur).
- `configs/config.phase2_long_1k.yaml` — ikinci-örnek profili (çoklu bot kurulumları).
- Ana bloklar: `exchange` (marjin/kaldıraç/mod), `risk`, `safety` (yukarıdaki yığın), `smc_v2` (gölge-kapılı v2 motoru), `signal_ledger` (edge ölçümü, varsayılan KAPALI — prod'da `EFLOUD_SIGNAL_LEDGER_ENABLED=1` ile açılır), `agent_team` (danışman LLM; varsayılan `gating: false`).

---

## ✅ Test & CI

```bash
python -m pytest -q              # tam paket (2.000+ geçiyor)
```

GitHub Actions her PR'da tüm paketi çalıştırır (Python 3.11, hermetik — secret yok, ajan katmanı NEUTRAL'a düşer). CI sert bir kapıdır: "testler geçiyor" iddiaları push edilen commit üzerinde yeniden doğrulanır. Trade-mantığı değişiklikleri ayrıca merge öncesi **NET-maliyet backtest / edge kapısı** gerektirir.

---

## 📦 Dağıtım

Çok servisli **Docker Compose** yığını; **Caddy** (otomatik TLS) arkasında Hetzner VPS üzerinde üretimde kanıtlanmıştır:

| Servis | Rol |
|---|---|
| `efloud-bot` | V1 trading örneği + FastAPI paneli |
| `efloud-bot-long` | ikinci örnek (kendi cüzdanı, kendi config/env'i) |
| `routines-watcher` | 7/24 izleme + edge çözümleyici/rapor |
| `alerter` / `overseer` / `daily-report` | log-izleme uyarıları, gözetim, raporlama |
| `caddy` | paneller için TLS ters-proxy |

Canlı marjin/mod değişiklikleri **düz-defter bakım penceresi runbook'unu** izler (durdur → düzle → dağıt → ön kontrol `[5/5]` → başlat → doğrula). Bkz. [`deploy/HETZNER_GUIDE.md`](deploy/HETZNER_GUIDE.md) ve [`docs/deployment_guide.md`](docs/deployment_guide.md).

---

## 🗂 Proje Yapısı

```
engine/            SMC çekirdeği (v1 + smc_v2/), orkestratör, safety/, risk/, agents/,
                   signal_ledger, edge_costs, edge_metrics
exchange/          CCXT istemci + OrderManager (giriş, SL/TP hassasiyet+doğrulama, mutabakat, K/Z)
backend/           FastAPI uygulaması, bot_runner, db, tests/
scripts/routines/  izleme yardımcısı: breaker/marjin/pozisyon denetimi, çözümleyici, edge raporu
pine/              TradingView Pine v6 — EFloud Signals & Strategy v2 (+ PINE_SPEC.md)
preflight.py       mainnet hazırlık + düz-defter kapısı
configs/           üretim profilleri  ·  config.yaml  varsayılan profil
deploy/            docker-compose.prod.yml varlıkları, Caddyfile, kılavuzlar
.claude/agents/    geliştirme-zamanı bakım + kantitatif ajan ekibi
.github/workflows/ CI
```

---

## 🗺 Yol Haritası

- **Edge-güdümlü kalibrasyon** — canlı NET-maliyet verisinden confluence-eşiği taraması ve TP-modeli kararları (zamanlandı).
- Korelasyon-farkındalıklı pozisyon boyutlandırma (bayrak-kapılı, backtest-kapılı).
- Genişletilmiş backtest analitiği · danışma ekibi için kapı arbitrajı (skor / çoğunluk).
- Ürünleştirme: paketlenmiş kurulum, müşteri-başına örnekler, lisanslama.

---

## 💼 Ticari

Efloud Bot özel olarak geliştirilmektedir ve **ticari kullanılabilirliğe doğru ilerlemektedir** (yönetilen örnekler / lisanslama). Erken erişim, ortaklık veya lisanslama için geliştiriciyle iletişime geçin veya bir tartışma açın. TradingView göstergesi ayrıca sunulur.

---

## 📄 Lisans

Tescilli — tüm hakları saklıdır. Yeniden dağıtılamaz. **Trading önemli ölçüde kayıp riski içerir; geçmiş performans gelecekteki sonuçları garanti etmez.**
