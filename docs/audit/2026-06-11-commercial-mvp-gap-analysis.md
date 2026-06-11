# Kurumsal MVP Boşluk Analizi — "Algoritmik Trade Bot Satan Firma" Perspektifi

**Tarih:** 2026-06-11
**Hazırlayan:** @claude (Architect/Review)
**Ticari çapa:** u2algo ürün hattı (P-001 ile uyumlu — TradingView indicator ücretsiz / strategy premium + u2algo-site funnel)
**Bağlı plan:** `LLTODO/plans/P-002-commercial-mvp.md`

---

## 1. Amaç ve Yöntem

Bu rapor, efloud-bot/u2algo projesini "algoritmik trade bot satan kurumsal bir firmada
olması gereken MVP özellikler" çerçevesinde uçtan uca tarar. Her bulgu repo'daki
dosya/davranış kanıtına dayanır. Rapor, P-002 Commercial MVP epic planının dayanağıdır.

İş modeli kararı (2026-06-11, operatör onaylı): **u2algo ürün hattı** çapa alınır.
Repo'da belgeli iki alternatif yol bilinçli olarak çapa DEĞİLDİR:

- `docs/superpowers/specs/2026-05-05-efloud-roadmap.md` → Binance Copy-Trading Lead
  Trader yolu ("No multi-tenant SaaS, no client API key storage"). Bu yol track-record
  hattı olarak yaşamaya devam eder; P-002'nin W1 (kanıt katmanı) çıktıları bu yola da
  hizmet eder.
- Hosted SaaS / self-host lisans satışı → kapsam DIŞI (aşağıda §5'te gerekçesi).

---

## 2. Mevcut Güçlü Altyapı (Envanter)

Bir "kurumsal firma" iddiasının zaten karşılanan kısımları:

| Alan | Kanıt | Durum |
|---|---|---|
| Trading çekirdeği | `engine/smc.py`, `engine/smc_v2/`, `engine/confluence.py`, `engine/signals.py` — multi-TF SMC + confluence | ✅ Olgun |
| Deterministik güvenlik | `engine/safety/` 7 katman (breaker, position guard, orphan, reverse-on-profit, entry-drift, SL/TP verify, margin isolation) | ✅ Olgun |
| Exchange-truth muhasebe | Realized PnL Binance income'dan reconcile edilir (`safety.enable_pnl_audit`) | ✅ Olgun |
| Backtest & optimizasyon | `backtest/`, `scripts/autoresearch/`, walk-forward configs | ✅ Olgun |
| Ops/observability | `ops/alerter/` (Telegram), `ops/daily_report/` (SMTP), `ops/overseer/`, `backend/healthz.py`, `docs/runbooks/` | ✅ Olgun |
| Operatör dashboard | `frontend/` Next.js — positions, orders, history, equity, kill-switch, breaker reset, AI panel | ✅ Olgun |
| LLM advisory | `engine/agents/` shadow-mode, fail-safe | ✅ Olgun |
| Test disiplini | 1261 test (README badge), CI | ✅ Olgun |
| Marketing funnel başlangıcı | `u2algo-site/` (waitlist + Supabase REST + JSONL fallback), brand kit | 🟡 Kısmi |
| Satılacak ürün | P-001 Pine Wave 1 — T-001 DONE (indicator iskeleti compile PASS), T-002/T-003 backlog | 🟡 Devam ediyor |

---

## 3. Eksik Kümeler (Kanıt-Referanslı)

### G1 — Monetizasyon rayı YOK (kritiklik: satış blokeri)

- Repo genelinde `stripe|gumroad|lemonsqueezy|paddle|license` grep'i yalnız doküman
  bahisleri döndürür (README, roadmap spec, skill dosyaları). Hiçbir ödeme entegrasyonu,
  webhook alıcısı, lisans/entitlement tablosu veya kodu yok.
- `u2algo-site/index.html` §pricing (satır ~503-531): "Şu an satış değil, erken erişim"
  placeholder'ı. Checkout yolu yok.
- `u2algo-site/server.js`: yalnız waitlist kaydı (Supabase REST → direct PG → JSONL
  fallback). Satın alma/entitlement endpoint'i yok.
- P-001 planı "strategy = premium, gelir kapısı" der ama gelir kapısının kendisi
  (ödeme → erişim) hiçbir planda görev olarak tanımlı değil.

**Sonuç:** Ürün hazır olsa bile bugün tek bir satış teknik olarak gerçekleştirilemez.

### G2 — Güven & kanıt katmanı iç tüketimde kilitli (kritiklik: dönüşüm blokeri)

- `ops/daily_report/` çıktısı SMTP ile yalnız operatöre gider; müşteri/ziyaretçi yüzü yok.
- Public track-record sayfası yok; `2026-05-05-efloud-roadmap.md` Epic 5
  ("Investor-grade reporting") açıkça "🔒 Deferred" durumda.
- Aylık statement (PDF/CSV) üretimi yok; `/api/history` ve `/api/equity` auth'lu ve
  operatör-only (`backend/api.py:245-264`).
- Uptime/status göstergesi yok; `backend/healthz.py` yalnız autoheal/alerter içindir.
- Müşteri-yüzlü `CHANGELOG.md` yok (release/changelog disiplini iç commit geçmişinde).

**Sonuç:** "Risk-disiplinli, şeffaf algoritmik trading" konumlandırmasının
(growth planı W3) kamuya dönük tek bir kanıt yüzeyi yok — premium dönüşüm beklenemez.

### G3 — Legal & compliance pack YOK (kritiklik: satış öncesi zorunluluk)

- `u2algo-site/index.html` yalnız bir disclaimer bölümü içerir (satır ~601+).
  Ayrı ToS, Privacy Policy, Risk Disclosure, Refund Policy sayfaları YOK.
- Waitlist formunda KVKK/GDPR consent checkbox'ı ve kayıt payload'ında consent alanı yok
  (`u2algo-site/server.js` waitlist şeması: email + meta).
- Growth planındaki marketing guardrails (getiri vaadi yok, yatırım tavsiyesi yok)
  sözleşme/politika metni olarak hiçbir yerde kurumsallaşmamış.

**Sonuç:** Para almak (G1) legal pack olmadan açılamaz; paid ads gate'i
(growth planı: "compliance-safe landing page") de buna bağlı.

### G4 — Müşteri deneyimi katmanı YOK (kritiklik: P1, müşteri oluşunca)

- `engine/notifications/` içinde tek implementasyon `null_manager.py`
  (`NullNotificationManager` — tüm çağrılar no-op). Müşteri-yüzlü trade/sinyal
  bildirimi altyapısı yok; `ops/alerter/` yalnız operatör Telegram'ı.
- Müşteri dokümantasyonu yok (`docs/runbooks/` iç operasyon içindir; "indicator nasıl
  eklenir, alert nasıl kurulur" tipi quickstart yok).
- Destek kanalı tanımsız (support e-postası, FAQ-destek akışı yok).
- `backend/auth.py`: tek parola + imzalı cookie. 2FA yok — dashboard operatör-only
  olduğu için bu MVP'de P2'dir, müşteri yüzeyi açılırsa öne çekilir.

---

## 4. Öncelik Sırası ve Gerekçesi

```
W0 Legal pack ──────────► W2 Monetizasyon   (satış legal pack'siz açılamaz)
W1 Güven & kanıt ───────► W2                (kanıtsız premium dönüşüm olmaz)
P-001 T-002/T-003 ──────► W2                (satılacak premium ürünün kendisi)
W2 ────────────────────► W3 Müşteri deneyimi (müşteri oluşunca anlamlı)
```

1. **W0 — Legal (önce):** En ucuz iş, ama hem satışın hem paid-ads gate'inin ön şartı.
   Statik sayfa + form alanı; canlı sisteme sıfır temas.
2. **W1 — Kanıt (paralel):** Mevcut `trade_journal.jsonl` + `aggregate.compute_summary()`
   altyapısı yeniden kullanılarak düşük maliyetle public proof yüzeyi üretilebilir.
   Lead Trader yoluna da hizmet eder (çifte değer).
3. **W2 — Monetizasyon:** W0'a ve satılacak ürüne (P-001 T-003) bağımlı; altyapısı
   (webhook + entitlement tablosu) paralel hazırlanır.
4. **W3 — Müşteri deneyimi (sonra):** Bildirim/destek/dokümantasyon, ödeyen ilk müşteri
   kohortu oluşurken devreye girer.

---

## 5. Bilinçli Kapsam Dışı Bırakılanlar

| Konu | Neden hariç |
|---|---|
| Multi-tenant hosted SaaS | Roadmap kararı (2026-05-05): regülasyon + custodial risk + rewrite maliyeti. u2algo çapasıyla çelişir. |
| Müşteri API key vault / kullanıcı başına bot instance | SaaS'a bağlı; çapa dışı. |
| TradingView erişiminde tam otomasyon | TV'nin resmi invite-only otomasyon API'si yok; MVP'de kuyruk destekli manuel grant, otomasyon W4+ araştırma maddesi. |
| Canlı sinyallerin gerçek zamanlı satışı ("sinyal servisi") | Regülasyon çerçevesi riski; W3 bildirimleri gecikmeli/aggregate ve default-OFF tasarlanır. |
| Dashboard çoklu kullanıcı/rol sistemi | Dashboard operatör aracı olarak kalır; müşteri yüzeyi u2algo-site'tır. |

---

## 6. Safety Invariants (P-002'ye aynen taşınır)

1. Canlı `config.yaml`, `.env`, `docker-compose.prod.yml`, VPS deploy bu epic ile değişmez.
2. Hiçbir yeni bileşen trade karar yoluna (`SafeOrchestrator` → guard/breaker → order)
   bağlanmaz — tümü additive, feature-flag'li, default-OFF.
3. Public yüzeylere mutlak bakiye/pozisyon büyüklüğü sızdırılmaz; yalnız oransal/aggregate
   metrik yayınlanır.
4. Marketing/legal metinlerde getiri vaadi, garanti kâr, yatırım tavsiyesi dili yok.
5. Secrets (ödeme webhook secret dahil) yalnız env/VPS/Railway'de; repo'ya girmez.
