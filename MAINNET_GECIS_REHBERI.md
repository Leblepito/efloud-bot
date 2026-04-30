# Mainnet Geçiş Rehberi — Faz 1 → Faz 2

## ⚠️ Önce Güvenlik

Bu rehbere başlamadan önce **testnet API key'ini Binance'den sil** (daha önce paylaşmıştın — silinmedi mi?):
- https://testnet.binancefuture.com → Profile → API Management → Delete

---

## FAZ 1 — Mainnet Data + Dry Run

**Amaç:** Gerçek piyasada sinyal kalitesini 2-3 gün gözle, fon riski yok.

### Adım 1: Mainnet API Key Oluştur

1. Binance mainnet hesabına gir: https://www.binance.com/
2. Profile → API Management → **Create API**
3. İsim: `efloud-bot-readonly`
4. **İzinler çok önemli:**
   - ✅ Enable Reading
   - ❌ Enable Futures (KAPALI)
   - ❌ Enable Spot & Margin Trading (KAPALI)
   - ❌ Enable Withdrawals (KAPALI)
5. **IP whitelist ekle:** Sadece kendi public IP'in
   - IP'ini öğrenmek: https://www.whatismyip.com/
6. Key ve Secret'ı kopyala, **hemen `.env` dosyasına yaz**:

```
BINANCE_API_KEY=senin_mainnet_readonly_key
BINANCE_API_SECRET=senin_mainnet_readonly_secret
```

### Adım 2: Botu Faz 1 Config'i ile Çalıştır

PowerShell'de (her satır ayrı Enter):

```powershell
cd $env:USERPROFILE\Downloads\efloud-bot
```

```powershell
python main.py configs/config.phase1.yaml
```

Bot başlarken şunu görmelisin:
```
Mode:    DRY RUN | MAINNET
```

### Adım 3: 2-3 Gün Gözle

- `./reports_phase1/` klasöründe her cycle'ın markdown raporu birikir
- `./logs/efloud_phase1.log` — tüm cycle kayıtları
- Ne kadar "✅ Opened" satırı var → hipotetik trade sayısı
- Hangi coinlerde daha çok sinyal çıkıyor

### Faz 1 Başarı Kriterleri

Faz 2'ye geçmeden önce bunların sağlanması lazım:

| Kriter | Hedef |
|---|---|
| Bot kesintisiz çalışma | 72 saat sorunsuz |
| Sinyal sayısı | Günde min 3-5 sinyal |
| "✅ Opened" oranı | Sinyallerin en az %50'si pozisyon açmış olmalı (geri kalanı regime veya dedup ile bloklanır) |
| "BREAKER HALTED" | **HİÇ olmamalı** |
| ERROR log | Minimum (<5 kritik hata) |
| Win rate simülasyon | Raporlarda TP1/TP2 hit sayıları > SL hit sayısı |

Kriterler tutmazsa → parametre ayarı, Faz 2 ertelenir.

---

## FAZ 2 — Mainnet LIVE

**Amaç:** Küçük bakiyeyle gerçek trading, bot'un gerçek performansını ölçmek.

### Adım 1: Yeni API Key (Trading Yetkili)

Faz 1'in read-only key'ini BIRAK (o güvenli kalsın), yeni trading-enabled key oluştur:

1. Binance → API Management → Create API
2. İsim: `efloud-bot-live`
3. **İzinler:**
   - ✅ Enable Reading
   - ✅ Enable Futures
   - ❌ Enable Spot & Margin Trading (KAPALI — bot futures kullanıyor)
   - ❌ Enable Withdrawals (MUTLAKA KAPALI — bot fon çekemesin)
4. IP whitelist: kendi IP'in (Faz 1'dekiyle aynı)
5. **2FA aktif olmalı**

Key ve secret'ı `.env`'de **güncelle** (Faz 1'inkinin üstüne yaz).

### Adım 2: Bakiye Transfer

Binance futures cüzdanına sadece **$100-200** transfer et. Asla fazla.
- Bu para "kaybolabilecek" para olmalı
- İlk 7 gün %20'ye kadar kayıp normal kabul edilmeli (öğrenme aşaması)

### Adım 3: config.phase2.yaml'da Bakiyeyi Güncelle

```yaml
safety:
  starting_balance: 200   # Senin gerçek bakiyene eşitle
```

### Adım 4: Environment Variable Set Et

Mainnet LIVE bot EFLOUD_ALLOW_MAINNET=1 olmadan çalışmaz (güvenlik).

```powershell
$env:EFLOUD_ALLOW_MAINNET = "1"
```

Bu env var **sadece o oturuma özeldir** — terminal kapanınca sıfırlanır. İyi, koruyucu özellik.

### Adım 5: Faz 2'yi Başlat

```powershell
python main.py configs/config.phase2.yaml
```

Bot başlarken şunu göreceksin:
```
🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨
🚨 MAINNET LIVE TRADING — REAL MONEY AT RISK
🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨
🚨 Starting in 5 seconds... (Ctrl+C to abort)
```

5 saniye geri sayımdan sonra canlı başlar. Bu pencerede **Ctrl+C** ile iptal edebilirsin.

### Adım 6: İlk 24 Saat Sıkı Gözlem

- Her 1-2 saatte logları kontrol et
- İlk pozisyon açıldığında Binance web'ten gerçekten açılmış mı bak
- SL/TP emirleri set edildi mi Binance'de kontrol et
- **Herhangi bir acayiplikte bot'u durdur (Ctrl+C)**

Bot durdurulsa da, state `./state_phase2/` klasöründe saklıdır. Açık pozisyonlar Binance'de kalır — manuel kapatabilirsin.

---

## Çalışırken İzleme

### Günlük rutin (otomatik rapor)

Bot çalışırken her sabah Claude Code'a şunu çalıştırt (daha önce önerdiğim routine):

```
Name: efloud-daily-report
Description: Efloud bot 24 saatlik performans
Prompt:
  C:\Users\utkuc\Downloads\efloud-bot\reports_phase2 klasöründeki
  son 24 saatlik markdown dosyalarını oku. Aşağıdaki özeti çıkar:
  1. Kaç pozisyon açıldı (✅ Opened)
  2. Kaç pozisyon kapandı (by exit reason: TP1, TP2, SL, weakness)
  3. Net PnL
  4. En çok işlem gören coin
  5. Sinyal geldi ama açılmadı (regime/dedup/guard sebebi)
  6. Circuit breaker tetiklendi mi
  Türkçe özet yaz, 500 kelime max.

Frequency: Daily
Time: 09:00 AM
```

---

## Acil Durum: Bot'u Durdurma

### Yumuşak durdurma (pozisyonları koruyarak)
Terminal'de **Ctrl+C** bas. Bot mevcut cycle'ı bitirir, state'i kaydeder, çıkar.
Açık pozisyonlar **Binance'de kalır** — bot yeniden başlatılana kadar SL/TP orderları Binance tarafında aktif.

### Acil durdurma (her şey)
1. Ctrl+C (bot durur)
2. Binance web → Futures → Positions → **Close All**
3. Binance web → Orders → **Cancel All** (SL/TP orderları)

### API key'i devre dışı bırak
Bir şey şüpheli görürsen:
1. Binance → API Management → key'i **Disable**
2. Bot bir sonraki cycle'da "Invalid API key" alır, çalışmayı durdurur

---

## Faz 2 Başarı / Fail Kriterleri

**7 gün sonra değerlendirme:**

| Durum | Kriter | Aksiyon |
|---|---|---|
| ✅ İyi | Net PnL > +%1 | Bakiye 2x artır, Faz 3'e geç |
| 🟡 Orta | Net PnL -%1 ile +%1 arası | Parametre fine-tune, 1 hafta daha |
| 🔴 Kötü | Net PnL < -%1 | Faz 1'e dön, strateji gözden geçir |
| ⛔ Kritik | Weekly DD -%5 HALT | Bot'u durdur, manual analiz, büyük değişiklik |

Hiçbir zaman duygusal karar verme — her şey sayıya dayalı olsun.
