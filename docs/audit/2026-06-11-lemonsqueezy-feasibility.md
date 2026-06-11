# GÖREV B: Lemon Squeezy Fizibilite + Railway Env (2026-06-11)

> **Görev:** P-003 W2 öncesi zorunlu fizibilite doğrulaması.
> LS AUP, TR payout, tüzel kişilik, transactional e-posta, Railway deploy kaynağı.

---

## 1. Lemon Squeezy AUP / Store Aktivasyonu

**Ürün:** u2algo TradingView indicator (ücretsiz) + strategy script (premium)
**Kategori:** Dijital yazılım ürünü, SaaS/araç kategorisi

**LS Prohibited Products listesi** (docs.lemonsqueezy.com/help/getting-started/prohibited-products):
- Kripto para, NFT minting, ICO → ❌
- Trading sinyal servisi, yatırım tavsiyesi → ❌
- Yetişkin içerik, kumar, uyuşturucu → ❌

**u2algo konumlandırması:**
- "TradingView indicator/strateji script'i" = **yazılım ürünü**
- Finansal tavsiye/sinyal satışı DEĞİL
- Disclaimer: "Bu bir analiz aracıdır, yatırım tavsiyesi değildir"

**Karar:** ✅ DÜŞÜK RİSK — TradingView yazılım eklentisi olarak konumlandırılırsa LS AUP'yi ihlal etmez. Store aktivasyonu "software" kategorisinde sorunsuz olmalı.

**Fallback (risk durumunda):** Paddle — benzer MoR modeli, daha geniş ürün kabulü.

---

## 2. Türkiye Satıcı Payout Rayı

**Mevcut durum:**
- PayPal TR'de satıcı hesabı YOK (sadece alıcı)
- LS, MoR olarak küresel ödeme alır → satıcıya banka havalesi ile öder
- LS Supported Countries listesinde **Turkey VAR** (MoR modeli, dünya geneli)

**Payout yöntemi:** LS → Wise/Payoneer → TR banka hesabı
Alternatif: Wise Business hesabı (USD/TRY, düşük kur farkı)

**Karar:** ✅ LS TR satıcıya payout yapabiliyor. Wise Business hesabı önerilir.

---

## 3. Tüzel Kişilik + Vergi

**Gerekli:**
- TR'de şahıs şirketi veya limited şirket
- Vergi levhası (LS identity verification ister)
- Hizmet ihracı → KDV istisnası (KDV 0%)
- Wise/Payoneer → gelir transferi → TR banka → gelir vergisi beyanı

**Operatör aksiyonu:** Tüzel kişilik durumu netleştir. Şahıs firması yeterli (düşük ciroda).

---

## 4. Transactional E-posta Sağlayıcısı

**Gereksinimler:**
- T-016: Satın alma onay e-postası
- T-019: Müşteri destek e-postası
- Domain: SPF/DKIM/DMARC yapılandırması (M12 domain kararıyla birlikte)

**Adaylar:**

| Sağlayıcı | Ücretsiz tier | API | TR teslimat |
|---|---|---|---|
| **Resend** | 100 email/gün | ✅ REST | ✅ |
| SendGrid | 100 email/gün | ✅ REST | ✅ |
| AWS SES | 62K email/ay (ücretli) | ✅ SDK | ⚠️ Sandbox limitleri |

**Öneri:** Resend — modern API, React Email entegrasyonu, ücretsiz tier MVP için yeterli.

---

## 5. Railway Deploy Kaynağı Teyidi

**Repo yapısı:**
- `u2algo-site/` bu repoda **vendored kopya** olarak duruyor
- Railway deploy konfigürasyonu bu repoda değil

**Bilinmeyenler (operatöre sorulacak):**
- Railway `u2algo-site` servisi hangi repodan deploy ediliyor?
- Bu repo mu, ayrı bir `u2algo-site` reposu mu?
- `railway.json` / `railway.toml` nerede?

**Karar:** ⚠️ T-010/T-011/T-016 PR'ları başlamadan ÖNCE deploy kaynağı teyit edilmeli. PR'lar doğru hedef repoya açılacak.

---

## Özet

| Madde | Durum | Aksiyon |
|---|---|---|
| LS AUP (trading yazılım) | ✅ Uygun | "Analiz aracı" pozisyonu |
| TR satıcı payout | ✅ Mümkün | Wise Business hesabı |
| Tüzel kişilik | ⚠️ Operatör | Şahıs/Ltd şirket kararı |
| E-posta sağlayıcı | ✅ Resend önerildi | Domain + SPF/DKIM |
| Railway deploy kaynağı | ❓ Operatör | Hangi repo? |
