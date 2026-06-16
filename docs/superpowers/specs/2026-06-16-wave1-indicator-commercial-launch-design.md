# Track 1 — Wave-1 İndikatör Ticari Launch — Design Spec

**Date:** 2026-06-16
**Status:** Approved (brainstorm) → ready for implementation plan
**Scope:** Track 1 only. Track 2 (Wave-2 redesign + dedicated Hetzner server + proven-edge premium tier) is a SEPARATE initiative with its own spec.

---

## 1. Amaç & Konumlandırma

Wave-1 SMC indikatörünü (TradingView invite-only) bir **karar-destek / analiz aracı** olarak satışa açmak. Konumlandırma kararları (operatör, 2026-06-16 brainstorm):

- **B — Araç-değeri, getiri iddiası YOK.** Ürün = SMC yapısal analiz aracı (OB / FVG / EQH-EQL / CHoCH-BOS / confluence / SL-TP görseli). Getiri vaadi, sinyal servisi, oto-trade veya yatırım tavsiyesi DEĞİL.
- **C — Erken/dürüst launch, premium proof sonra.** Kanıtlanmış edge yok (canlı bot −%5.3 / 9 gün, %24 win-rate; Wave-1 STRATEGY backtest NO-GO). Bu yüzden "getiriye göre fiyat" YAPILMAZ. Founding fiyatla başla, gerçek track record (Track 2 / Wave-2) biriktikçe fiyat/proof güçlendir.
- **Proof modeli C (katmanlı):** indikatörün **analitik çıktısı** = ana değer önermesi; **şeffaflık bölümü** = dürüst canlı stats (drawdown dahil), doğru çerçeveyle güven sinyali — headline değil.

### Neden bu konumlandırma (gerçeklik kontrolü)
- Canlı track record (Supabase, 2026-06-07→16): 2269.83→2150.33 USDT (−%5.3), 88 trade / 20W-63L (~%24 WR), net −142.47 USDT.
- Wave-1 STRATEGY backtest = NO-GO (negatif edge); entry-slippage backtest = FAIL.
- → Gösterilebilir kâr yok; dürüst + compliant tek yol "araç olarak sat + şeffaf ol".

---

## 2. Fiyatlandırma

- **Founding member, ~$39 lifetime** (tek-seferlik; G-P3-B5 = lifetime kararıyla uyumlu).
- Mesaj: *"Erken erişim fiyatı — track record büyüdükçe fiyat artacak; founding üyeler lifetime kilitler."*
- LS ürün 1148317 fiyatı $39'a (≈ uygun TRY karşılığı) çekilir; mevcut TRY 9.999 ileride *kanıtlı* premium tier için saklanır.

---

## 3. Bileşenler

### 3.1 `u2algo-site/premium.html` (YENİ ürün sayfası)
Mevcut site dark-theme (Inter/Outfit, `--accent:#00f0ff`) ile uyumlu, self-contained. Bölümler (sıra):

1. **Hero** — başlık + tek-cümle değer önermesi + Founding $39 lifetime CTA.
2. **Bu ne / ne DEĞİL** — iki kolon: ✅ karar-destek aracı (işaretlediği yapılar) · ❌ sinyal servisi / oto-trade / yatırım tavsiyesi / getiri garantisi.
3. **Annotated örnekler** — 3-5 gerçek-grafik ekran görüntüsü (indikatörün OB/FVG/zone/SL-TP işaretlemesi), kısa açıklamalı.
4. **Metodoloji** — SMC kavramlarının kısa anlatımı (aracın ciddiyeti).
5. **Şeffaflık (build-in-public)** — dürüst canlı stats (kapanmış-trade-bazlı, %-normalize, drawdown dahil). Çerçeve metni zorunlu: *"Geçmiş performans gelecek garantisi değildir. Bu istatistikler tek-config naif bir oto-execution botuna aittir — indikatörün kendisi veya bir getiri vaadi değildir. Yatırım tavsiyesi değildir."* Negatif değerler gizlenmez.
6. **Founding teklif** — $39 lifetime + erken-erişim/fiyat-artışı mesajı + LS checkout CTA.
7. **SSS + disclaimer + footer** — privacy.html / terms.html linkleri.

**Arayüz:** statik HTML; LS checkout linki dış bağlantı; şeffaflık verisi (§3.3) build-time/periyodik enjekte veya client-side fetch (fetch-fail-safe).

### 3.2 Landing (`u2algo-site/index.html`) eklemesi
- Mevcut waitlist + içerik KORUNUR (regresyon yok).
- Eklenir: "Premium İndikatör — Founding $39 →" CTA bölümü/banner → `premium.html`.
- Waitlist lead'leri = founding-member dönüşüm kohortu.

### 3.3 Şeffaflık veri kaynağı
- Mevcut proof altyapısı (T-012 `proof_export.py` / snapshot, T-014 uptime) kaynak.
- **G-P3-1 cadence sınırı korunur:** ≥ günlük çözünürlük, yalnız KAPANMIŞ trade, mutlak bakiye/pozisyon büyüklüğü YOK (% normalize) — gerçek-zamanlı sinyal beslemesine / strateji reverse-engineering'e dönüşmez.
- premium.html'e statik snapshot (örn. `updates.json` benzeri) veya periyodik besleme; fetch başarısızsa bölüm zarifçe gizlenir/placeholder.

### 3.4 Lemon Squeezy entegrasyonu (kod zaten master'da, T-016/T-017)
- `server.js` `LS_PRODUCT_MAP[1148317] = 'wave1-indicator'` (veya seçilen iç ad).
- premium.html buy CTA → LS `buy_now_url` (hosted checkout).
- Akış: `order_created` webhook → `entitlements` satırı `pending` → operatör manuel TV invite grant (T-017 runbook) → `granted`. `order_refunded` → `revoked`.
- Aktivasyon: Railway env `LEMONSQUEEZY_WEBHOOK_SECRET` + `LS_WEBHOOK_ENABLED=true` (deploy fix sonrası).

### 3.5 İçerik üretimi (bağımlılık)
- **Annotated görseller:** TV'de Wave-1 indikatörü gerçek grafiklere uygulanıp 3-5 ekran görüntüsü (TV MCP ile Claude veya operatör).
- **Metinler:** hero + metodoloji + SSS taslağı (Claude) → operatör rafine.

### 3.6 Compliance
- Her sayfada net: "yatırım tavsiyesi değildir · getiri garantisi yoktur · DYOR · geçmiş performans gelecek garantisi değildir".
- terms.html / privacy.html linkli; LS AUP "analiz aracı" pozisyonuyla uyumlu.

---

## 4. Veri Akışı (özet)

```
Ziyaretçi → index.html (waitlist + Founding CTA) → premium.html (proof + offer)
   → LS hosted checkout ($39) → order_created webhook → /api/purchase-webhook (HMAC)
   → entitlements(pending) → operatör manuel TV grant → granted
Şeffaflık: bot → proof_export/snapshot → (G-P3-1 filtre) → premium.html şeffaflık bölümü
```

---

## 5. Publish Sırası & Bağımlılıklar

1. 🔴 **[BLOCKER] Railway deploy fix** — u2algo-site servisi nixpacks builder'a alınmalı (config-path `u2algo-site/railway.json` veya Builder=Nixpacks) + Clear build cache + redeploy. (Operatör dashboard adımı. Şu an servis root `Dockerfile`'ı kullanıp fail ediyor / bayat kod serve ediyor → consent + webhook + premium.html canlı olamaz.)
2. LS ürün publish + fiyat $39 (operatör).
3. Kod PR: premium.html + landing CTA + `LS_PRODUCT_MAP` + buy CTA + şeffaflık bölümü → review → merge → deploy (Claude).
4. İçerik: annotated görseller + metinler.
5. Webhook aktivasyon (secret + `LS_WEBHOOK_ENABLED=true`) + LS **test-mode** order doğrulama (Claude + operatör).
6. 🟢 Canlı.

---

## 6. Başarı Kriterleri / Acceptance

- [ ] premium.html canlıda render; tüm bölümler + disclaimer'lar mevcut; buy CTA LS checkout'u açıyor.
- [ ] index.html'e Founding CTA eklendi; **waitlist + consent 3-fallback REGRESYON YOK**.
- [ ] Şeffaflık bölümü gerçek proof verisini gösteriyor; G-P3-1 sınırlarına uygun (kapanmış-trade, %-normalize, mutlak bakiye yok); negatif değerler dürüstçe gösteriliyor; çerçeve metni mevcut.
- [ ] LS test-mode order → webhook 200 → `entitlements(pending)` → manuel grant → `granted` (T-017 runbook).
- [ ] Hiçbir bot config/compose/.env'e dokunulmadı (G-P3-5); yalnız u2algo-site/.
- [ ] Compliance metinleri tüm sayfalarda; getiri iddiası YOK.

---

## 7. Test

- premium.html statik render + buy CTA → LS checkout (manuel + smoke).
- smoke.js: premium.html için legal/compliance gate (forbidden-phrase taraması, disclaimer varlığı) — mevcut T-010 gate kalıbını genişlet.
- Webhook test-mode order entegrasyon doğrulaması (mevcut 13/13 + canlı test).
- Waitlist + consent regresyon (mevcut test).

---

## 8. Riskler / Açık Maddeler

- **R1 — Negatif şeffaflık verisi conversion'ı düşürebilir.** Mitigasyon: headline değil, doğru çerçeveli ayrı bölüm; ana satış = araç değeri. Operatör nihai görseli onaylar.
- **R2 — Railway deploy fix çözülmezse hiçbir şey canlı olmaz.** §5 adım 1 hard blocker.
- **R3 — Annotated görsel üretimi TV MCP'ye bağlı** (render-doğrulama gerekebilir).
- **R4 — Founding fiyat hukuki/iade çerçevesi** B.1-B.4 + terms iade bölümüyle tutarlı olmalı (operatör).

---

## 9. Kapsam Dışı (Track 2 — ayrı initiative)

- Wave-2 CHoCH/BOS redesign (yeni edge) — tasarım → implement → backtest gate → canlı.
- Yeni Hetzner server (Wave-2 izole track record).
- Kanıtlı premium tier + fiyat artışı (founding → premium geçiş).
- Resend otomatik onay e-postası (MVP'de manuel grant yeterli; opsiyonel).
