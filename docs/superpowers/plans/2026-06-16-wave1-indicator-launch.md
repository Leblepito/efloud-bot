# Wave-1 İndikatör Ticari Launch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** u2algo-site'a Wave-1 SMC indikatörünü "karar-destek aracı" olarak satan, getiri-iddiası-içermeyen, build-in-public şeffaflıklı bir `premium.html` ürün sayfası + landing CTA + Lemon Squeezy checkout entegrasyonu eklemek.

**Architecture:** Statik `premium.html` (mevcut Express `server.js` ile servis edilir), `smoke.js` compliance-gate'i ile test edilir. LS hosted checkout linki + zaten-kurulu webhook (`/api/purchase-webhook` → entitlements → manuel TV grant). Şeffaflık verisi statik snapshot JSON (G-P3-1 sınırlı). Hiçbir bot config/compose/.env'e dokunulmaz (yalnız `u2algo-site/`).

**Tech Stack:** Node.js (vanilla http server.js), statik HTML/CSS, `scripts/smoke.js` (node test gate), `scripts/test_consent_and_webhook.js` (node test), Lemon Squeezy hosted checkout.

**Spec:** `docs/superpowers/specs/2026-06-16-wave1-indicator-commercial-launch-design.md`

---

## Önkoşullar (OPERATÖR — kod görevi DEĞİL, ama launch'tan önce gerekir)

- **P1 [BLOCKER]:** Railway u2algo-site servisi nixpacks builder'a alınmalı (Settings → Config-as-code path = `u2algo-site/railway.json` veya Builder=Nixpacks) + "Clear build cache" + Redeploy. Doğrulama (Claude): `POST https://u2algo.com/api/purchase-webhook` → `503 disabled_by_config`. Bu olmadan kod canlıya çıkmaz.
- **P2:** LS ürün 1148317 → fiyat ~$39'a çekilir + **Publish**. `buy_now_url` zaten: `https://u2algo.lemonsqueezy.com/checkout/buy/cd9f3019-0fe5-4836-a730-3b985306bd72`.
- **P3:** Webhook aktivasyonu (Claude, CLI): LS webhook oluştur + `LEMONSQUEEZY_WEBHOOK_SECRET` (Railway `u2algo-site` env, `--stdin`) + `LS_WEBHOOK_ENABLED=true`. **Sadece P1 doğrulandıktan + kod merge edildikten sonra.**

> Kod görevleri (Task 1-7) P1/P2'den BAĞIMSIZ yazılıp merge edilebilir; sadece CANLI doğrulama P1'e bağlı.

---

## File Structure

| Dosya | Sorumluluk | İşlem |
|---|---|---|
| `u2algo-site/premium.html` | Ürün/satış sayfası (7 bölüm) | Create |
| `u2algo-site/assets/premium/*.png` | Annotated indikatör görselleri (3-5) | Create (içerik) |
| `u2algo-site/premium_proof.json` | Şeffaflık snapshot (dürüst kapanmış-trade stats, %-normalize) | Create |
| `u2algo-site/index.html` | Landing'e Founding CTA bölümü | Modify |
| `u2algo-site/sitemap.xml` | premium.html girişi | Modify |
| `u2algo-site/server.js` | `LS_PRODUCT_MAP[1148317]` | Modify (~line 327) |
| `u2algo-site/scripts/smoke.js` | premium.html compliance gate | Modify |
| `u2algo-site/scripts/test_consent_and_webhook.js` | product-map resolve testi | Modify |

**Forbidden-phrase listesi (compliance, smoke.js'de zaten var — premium.html'e de uygulanır):** "garantili kazanç", "guaranteed profit", "kesin kâr", "zengin ol", "risksiz" vb. (mevcut listeyi kullan).

---

## Task 1: smoke.js — premium.html compliance gate (TDD)

**Files:**
- Modify: `u2algo-site/scripts/smoke.js`
- (Test harness'ın kendisi — `npm run smoke` ile koşar)

- [ ] **Step 1: Mevcut smoke.js'i oku, T-010 gate kalıbını bul**

Run: `grep -n "compliance\|forbidden\|terms.html\|privacy.html" u2algo-site/scripts/smoke.js`
Amaç: terms/privacy gate'inin nasıl yazıldığını gör (aynı kalıbı premium.html'e uygula).

- [ ] **Step 2: premium.html gate'ini ekle (önce FAIL etmeli — dosya yok)**

`smoke.js` içinde, mevcut compliance kontrollerinin yanına ekle:

```javascript
// --- premium.html gate (Track 1 launch) ---
const premiumPath = path.join(__dirname, '..', 'premium.html');
if (!fs.existsSync(premiumPath)) {
  console.error('SMOKE FAIL: premium.html missing');
  process.exit(1);
}
const premium = fs.readFileSync(premiumPath, 'utf8');
const premiumRequired = [
  'yatırım tavsiyesi değildir',      // disclaimer
  'getiri garantisi',                // "getiri garantisi yoktur"
  'geçmiş performans',               // past-performance disclaimer
  'founding',                        // founding offer marker
  'checkout/buy',                    // LS buy CTA link
  '/privacy.html',                   // legal links
  '/terms.html'
];
for (const token of premiumRequired) {
  if (!premium.toLowerCase().includes(token.toLowerCase())) {
    console.error(`SMOKE FAIL: premium.html missing required token: "${token}"`);
    process.exit(1);
  }
}
// forbidden phrases (reuse existing FORBIDDEN list variable from this file)
for (const bad of FORBIDDEN) {
  if (premium.toLowerCase().includes(bad.toLowerCase())) {
    console.error(`SMOKE FAIL: premium.html forbidden phrase: "${bad}"`);
    process.exit(1);
  }
}
console.log('[INFO] premium.html compliance gate passed');
```

> NOT: `FORBIDDEN` mevcut değişken adı değilse, smoke.js'deki gerçek forbidden-liste değişken adını kullan (Step 1'de bulundu).

- [ ] **Step 3: Gate'in FAIL ettiğini doğrula**

Run: `cd u2algo-site && node scripts/smoke.js`
Expected: `SMOKE FAIL: premium.html missing` (Task 2 bunu geçirecek).

- [ ] **Step 4: Commit**

```bash
git add u2algo-site/scripts/smoke.js
git commit -m "test(launch): add premium.html compliance gate to smoke.js (failing)"
```

---

## Task 2: premium.html — ürün sayfası (gate'i geçir)

**Files:**
- Create: `u2algo-site/premium.html`

- [ ] **Step 1: premium.html'i oluştur (site dark-theme uyumlu, privacy.html stilini taban al)**

`privacy.html`'in `<head>`/stil bloğunu taban al (Inter/Outfit, `--accent:#00f0ff`, dark). Body, spec §3.1'deki 7 bölümü içersin. Compliance-kritik bloklar LİTERAL olmalı (gate bunları arar):

```html
<!-- Bölüm 5: Şeffaflık — ZORUNLU çerçeve metni -->
<section class="transparency">
  <h2>Şeffaflık — Build in Public</h2>
  <p class="frame">Geçmiş performans gelecek garantisi değildir. Aşağıdaki istatistikler
  tek-config naif bir oto-execution botuna aittir — indikatörün kendisi veya bir getiri
  vaadi değildir. Yatırım tavsiyesi değildir; kendi araştırmanı yap (DYOR).</p>
  <div id="proofStats">Yükleniyor…</div>
</section>

<!-- Bölüm 6: Founding teklif -->
<section class="offer">
  <h2>Founding Member — Lifetime</h2>
  <p>Erken erişim fiyatı. Track record büyüdükçe fiyat artacak; founding üyeler lifetime kilitler.</p>
  <p class="price">$39 <span>tek seferlik / lifetime</span></p>
  <a class="btn btn-primary" href="https://u2algo.lemonsqueezy.com/checkout/buy/cd9f3019-0fe5-4836-a730-3b985306bd72" target="_blank" rel="noopener">Founding Member Ol →</a>
</section>

<!-- Bölüm 7 footer: zorunlu disclaimer + legal -->
<footer>
  <p class="muted">u2algo bir analiz/karar-destek aracıdır. <strong>Yatırım tavsiyesi değildir.
  Getiri garantisi yoktur. Geçmiş performans gelecek garantisi değildir.</strong></p>
  <p><a href="/privacy.html">Gizlilik</a> · <a href="/terms.html">Kullanım Koşulları</a> · hello@u2algo.com</p>
</footer>
```

Bölüm 1-4 (hero / ne-ne-değil / annotated örnekler / metodoloji) spec §3.1'e göre yazılır. Annotated görseller `assets/premium/ornek-1.png … ornek-5.png` (Task 6'da üretilecek) `<img>` ile referanslanır. **Copy operatör tarafından rafine edilebilir** — yapı + compliance token'ları sabit kalır.

- [ ] **Step 2: smoke gate'in geçtiğini doğrula**

Run: `cd u2algo-site && node scripts/smoke.js`
Expected: `[INFO] premium.html compliance gate passed` + `smoke OK`.

- [ ] **Step 3: node --check (server.js etkilenmedi) + render kontrolü**

Run: `cd u2algo-site && node --check server.js && node -e "const f=require('fs').readFileSync('premium.html','utf8'); if(!f.includes('Founding')) process.exit(1); console.log('premium.html OK', f.length, 'bytes')"`
Expected: OK.

- [ ] **Step 4: Commit**

```bash
git add u2algo-site/premium.html
git commit -m "feat(launch): premium.html product page (tool positioning, founding $39, compliance gate green)"
```

---

## Task 3: Şeffaflık snapshot + render (TDD)

**Files:**
- Create: `u2algo-site/premium_proof.json`
- Modify: `u2algo-site/premium.html` (proofStats render script)
- Test: `u2algo-site/scripts/smoke.js` (proof JSON validity)

- [ ] **Step 1: premium_proof.json oluştur (dürüst, %-normalize, G-P3-1 uyumlu — mutlak bakiye YOK)**

```json
{
  "as_of": "2026-06-16",
  "period_days": 9,
  "closed_trades": 83,
  "win_rate_pct": 24.1,
  "return_pct": -5.3,
  "max_drawdown_pct": 6.9,
  "note": "Tek-config naif oto-execution botu. Kapanmış trade bazlı, %-normalize. Mutlak bakiye paylaşılmaz."
}
```

> Değerler §1 gerçek verisinden. Negatif değerler GİZLENMEZ. Bu dosya periyodik (≥günlük) elle/cron güncellenir; gerçek-zamanlı feed DEĞİL.

- [ ] **Step 2: smoke.js'e proof JSON geçerlilik testi ekle**

`smoke.js` premium gate'ine ekle:

```javascript
const proof = JSON.parse(fs.readFileSync(path.join(__dirname,'..','premium_proof.json'),'utf8'));
for (const k of ['as_of','period_days','closed_trades','win_rate_pct','return_pct','max_drawdown_pct']) {
  if (!(k in proof)) { console.error(`SMOKE FAIL: premium_proof.json missing ${k}`); process.exit(1); }
}
if ('balance' in proof || 'equity_usdt' in proof) { console.error('SMOKE FAIL: proof must NOT contain absolute balance (G-P3-1)'); process.exit(1); }
console.log('[INFO] premium_proof.json valid');
```

- [ ] **Step 3: premium.html'e fetch-fail-safe render script ekle**

`premium.html` `</body>` öncesi:

```html
<script>
fetch('/premium_proof.json').then(r=>r.json()).then(p=>{
  document.getElementById('proofStats').innerHTML =
    `<ul><li>Dönem: ${p.period_days} gün (${p.as_of})</li>`+
    `<li>Kapanmış trade: ${p.closed_trades} · Win-rate: ${p.win_rate_pct}%</li>`+
    `<li>Getiri: ${p.return_pct}% · Maks drawdown: ${p.max_drawdown_pct}%</li></ul>`+
    `<p class="muted">${p.note}</p>`;
}).catch(()=>{ document.getElementById('proofStats').innerHTML='<p class="muted">İstatistikler şu an gösterilemiyor.</p>'; });
</script>
```

- [ ] **Step 4: smoke + render doğrula**

Run: `cd u2algo-site && node scripts/smoke.js`
Expected: `premium_proof.json valid` + gate green.

- [ ] **Step 5: Commit**

```bash
git add u2algo-site/premium_proof.json u2algo-site/premium.html u2algo-site/scripts/smoke.js
git commit -m "feat(launch): honest transparency snapshot + fetch-fail-safe render (G-P3-1)"
```

---

## Task 4: Landing CTA + sitemap

**Files:**
- Modify: `u2algo-site/index.html`
- Modify: `u2algo-site/sitemap.xml`

- [ ] **Step 1: index.html'e Founding CTA bölümü ekle (waitlist bozulmadan)**

Waitlist bölümünün yakınına (mevcut yapıyı bozmadan) ekle:

```html
<section class="premium-cta">
  <h2>Premium İndikatör — Founding $39 Lifetime</h2>
  <p>SMC karar-destek aracı. Yatırım tavsiyesi değildir; getiri garantisi yoktur.</p>
  <a class="btn btn-primary" href="/premium.html">Detaylar &amp; Founding Üyelik →</a>
</section>
```

- [ ] **Step 2: sitemap.xml'e premium.html ekle**

```xml
<url><loc>https://u2algo.com/premium.html</loc><priority>0.8</priority></url>
```

- [ ] **Step 3: Regresyon — waitlist + consent + smoke**

Run: `cd u2algo-site && node scripts/smoke.js && node scripts/test_consent_and_webhook.js`
Expected: smoke OK + `13 PASS, 0 FAIL` (consent/webhook regresyon yok).

- [ ] **Step 4: Commit**

```bash
git add u2algo-site/index.html u2algo-site/sitemap.xml
git commit -m "feat(launch): landing founding CTA + premium.html in sitemap"
```

---

## Task 5: server.js LS_PRODUCT_MAP (TDD)

**Files:**
- Modify: `u2algo-site/server.js` (LS_PRODUCT_MAP, ~line 327)
- Modify: `u2algo-site/scripts/test_consent_and_webhook.js`

- [ ] **Step 1: test_consent_and_webhook.js'e product-map resolve testi ekle (FAIL)**

```javascript
// T-016b: product map resolves 1148317 → wave1-indicator
const LS_PRODUCT_MAP = { '1148317': 'wave1-indicator' };
function resolveProduct(pid){ return LS_PRODUCT_MAP[String(pid)] || 'wave1-unknown'; }
assert('product 1148317 → wave1-indicator', resolveProduct(1148317), 'wave1-indicator');
assert('unknown product → wave1-unknown', resolveProduct(999), 'wave1-unknown');
```

(Test dosyası mock kalıbını kullanıyor — server.js'i import etmiyor; map'i ayna olarak doğrular.)

- [ ] **Step 2: Testi koş — yeni assert'ler geçer, eski 13 korunur**

Run: `cd u2algo-site && node scripts/test_consent_and_webhook.js`
Expected: `15 PASS, 0 FAIL`.

- [ ] **Step 3: server.js'de LS_PRODUCT_MAP'i doldur**

`server.js` içinde mevcut boş `LS_PRODUCT_MAP` objesini bul (~line 327) ve doldur:

```javascript
const LS_PRODUCT_MAP = {
  '1148317': 'wave1-indicator',   // u2Algo SMC BB — Wave-1 indikatör (founding lifetime)
};
```

- [ ] **Step 4: node --check + test**

Run: `cd u2algo-site && node --check server.js && node scripts/test_consent_and_webhook.js`
Expected: syntax OK + `15 PASS`.

- [ ] **Step 5: Commit**

```bash
git add u2algo-site/server.js u2algo-site/scripts/test_consent_and_webhook.js
git commit -m "feat(launch): map LS product 1148317 → wave1-indicator (+test)"
```

---

## Task 6: Annotated indikatör görselleri (içerik — TV MCP)

**Files:**
- Create: `u2algo-site/assets/premium/ornek-1.png` … `ornek-5.png`

- [ ] **Step 1: TV'de Wave-1 indikatörünü canlı grafiklere uygula**

TradingView MCP ile: `tv_health_check` → `chart_set_symbol` (örn. BTCUSDT) → `chart_set_timeframe` (15m/1h) → Wave-1 indikatörü (`wave1_signals.pine` v1.2.0) chart'ta görünür olmalı → `capture_screenshot region=chart`. 3-5 farklı sembol/TF/setup için tekrarla (OB, FVG, EQH-EQL, SL/TP görünür örnekler).

- [ ] **Step 2: Görselleri kaydet + premium.html'de referansların doğru olduğunu doğrula**

Görselleri `u2algo-site/assets/premium/ornek-N.png` olarak kaydet. Run: `cd u2algo-site && node -e "['1','2','3'].forEach(n=>{if(!require('fs').existsSync('assets/premium/ornek-'+n+'.png'))throw new Error('missing ornek-'+n)});console.log('assets OK')"`

> Operatör görselleri kendi alıp koyabilir (TV MCP erişimi yoksa). Bu task içerik bağımlılığı; kod gate'ini bloklamaz ama launch öncesi tamamlanmalı.

- [ ] **Step 3: Commit**

```bash
git add u2algo-site/assets/premium/
git commit -m "content(launch): annotated Wave-1 indicator screenshots"
```

---

## Task 7: Entegrasyon doğrulama + PR

**Files:** (yok — doğrulama)

- [ ] **Step 1: Tüm gate'ler yeşil**

Run: `cd u2algo-site && node scripts/smoke.js && node scripts/test_consent_and_webhook.js && node --check server.js`
Expected: smoke OK (premium gate + proof valid) + `15 PASS` + syntax OK.

- [ ] **Step 2: PR aç (efloud-code-reviewer ile review)**

```bash
git push -u origin feat/track1-premium-launch
gh pr create -R Leblepito/efloud-bot --base master --title "feat(launch): Wave-1 indicator commercial launch (premium.html + LS + transparency)" --body "Spec: docs/superpowers/specs/2026-06-16-...; u2algo-site only, G-P3-5 untouched; getiri iddiası YOK; smoke+webhook+consent green."
```

- [ ] **Step 3: CI yeşil → merge → deploy doğrula (P1 sonrası)**

P1 (Railway nixpacks fix) tamamsa: merge sonrası `https://u2algo.com/premium.html` → 200 + Founding CTA + proof bölümü; `POST /api/purchase-webhook` → 503 (inert). P1 yoksa merge edilir ama canlı doğrulama P1'i bekler.

---

## Aktivasyon (P1+P2+P3 sonrası — Claude+operatör)

- [ ] LS webhook oluştur (API) → `LEMONSQUEEZY_WEBHOOK_SECRET` Railway u2algo-site env (`--stdin`) + `LS_WEBHOOK_ENABLED=true`.
- [ ] LS **test-mode** order → webhook 200 → `entitlements(pending)` → manuel TV grant (T-017 runbook) → `granted`.
- [ ] Operatör: LS API key sil (kurulum bitti).
- [ ] 🟢 Canlı.

---

## Self-Review (writing-plans)

- **Spec coverage:** §3.1 premium.html → Task 2/3; §3.2 landing CTA → Task 4; §3.3 transparency → Task 3; §3.4 LS → Task 5 + Aktivasyon; §3.5 içerik → Task 6; §3.6 compliance → Task 1 gate; §5 publish sırası → Önkoşullar + Task 7 + Aktivasyon. ✓ Boşluk yok.
- **Placeholder scan:** Kod adımları gerçek kod içeriyor; HTML copy "operatör rafine" olarak işaretli ama compliance token'ları + offer + CTA literal. ✓
- **Type/isim tutarlılığı:** `LS_PRODUCT_MAP` / `resolveProduct` / `premium_proof.json` alan adları Task 3↔5↔smoke arasında tutarlı. `FORBIDDEN` değişken adı Step 1'de doğrulanacak (smoke.js'deki gerçek adla eşle). ✓
