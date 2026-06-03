# Kronos × efloud-bot — Profile-Aware Confluence Playbook

Bu, Kronos skill'ini efloud-bot'un **kendi trade profili ve coin listesiyle** uyumlu
şekilde kullanmak için bir **karar rehberidir**. Manuel ritüeldir — bota wire edilmez,
emir vermez. Kronos, botun kendi SMC sinyalinin **üstüne bir teyit/veto katmanıdır**,
birincil tetikleyici DEĞİLDİR.

> **Yatırım tavsiyesi değildir.** Kronos bir olasılık dağılımı üretir, fiyat hedefi değil.
> Tek başına karar aracı olarak kullanma.

---

## 0. Önce bil: kritik kısıtlar

Bu dört gerçek tüm komutları ve yorumu belirler:

1. **yfinance `4h / 8h / 12h` interval'lerini DESTEKLEMEZ.** Geçerli interval'ler:
   `1m, 5m, 15m, 30m, 60m(=1h), 1d, 5d, 1wk, 1mo`. Botun HTF'leri bu listede olmayan
   bir değerse (4h/8h/12h), en yakın makro interval'e (`1d`/`1wk`) eşlenir — zaten o
   katman "bias/makro filtre" olduğu için doğru karşılıktır.
2. **Çıktı deterministik DEĞİL.** Kod `sample_count=1, T=1.0, top_p=0.9` ile çalışır →
   her koşuda farklı sayı gelir. "Confidence band" = o **tek** rastgele yolun min-max'i,
   gerçek bir güven aralığı değil. → **Her katmanı 3 kez çalıştır, konsensüse bak.**
3. **yfinance spot, bot Binance perp trade ediyor.** BTC/ETH/SOL gibi majörlerde basis
   küçük → **yön** analizi için yeterli. Çıktıyı mutlak fiyat hedefi değil, yön + rejim
   sinyali olarak oku.
4. **`max_context=512`** → Kronos her TF'de sadece son ~512 mumu kullanır. `period`
   parametresi sadece 512+ mum verecek kadar olmalı (aşağıdaki tablolar buna göre seçildi).

---

## 1. Sembol kapsamı — config'i aynala

Playbook coin listesini **`config.yaml` → `symbols.fixed_core`**'dan alır. Bot ne trade
ediyorsa Kronos da onu izler. Binance `SYM/USDT` → yfinance `SYM-USD` olur.

Güncel liste (20 coin):

```
BTC ETH XRP BNB SOL TRX DOGE ADA BCH LINK
ZEC LTC AVAX DOT TON NEAR ATOM APT UNI ICP
```

→ `/kronos BTC-USD ...`, `/kronos ETH-USD ...`, `/kronos LINK-USD ...` vb.

**Uyarı:** Majörlerde (BTC/ETH/SOL/BNB/XRP) yfinance verisi sağlam. Daha küçük alt'larda
(APT, ICP, TON, NEAR…) intraday veri seyrek/eksik olabilir → "No data" alırsan o coin'i
o TF'de atla, daha yüksek TF'e (1d) düş. Coin listesini değiştirmek istersen `config.yaml`'ı
düzenle; playbook otomatik uyar.

---

## 2. Profil → Kronos komut haritası

Önce **hangi profil yüklü** onu bul: `config.yaml` → `timeframes.profile`
(`scalp` | `mid` | `long`). Profil yoksa `custom` (entry/mtf/htf elle tanımlı) — o zaman
en yakın profil satırını kullan. `<SYM>` yerine coin'i koy (örn. `BTC-USD`).

Bot profilleri (entry / mtf / htf):
`scalp = 5m/1h/12h` · `mid = 15m/1h/4h` · `long = 1h/8h/1w`

### SCALP — bot 5m / 1h / 12h
| Katman | Bot TF | Kronos komutu | Eşleme |
|--------|--------|---------------|--------|
| HTF bias | 12h | `/kronos <SYM>-USD 6mo 1d 14` | 12h→1d |
| MTF bölge | 1h | `/kronos <SYM>-USD 1mo 1h 24` | native |
| LTF entry | 5m | `/kronos <SYM>-USD 5d 5m 12` | 5m → 60g limiti, 5d yeterli |

### MID — bot 15m / 1h / 4h  *(şu an prod'da yüklü)*
| Katman | Bot TF | Kronos komutu | Eşleme |
|--------|--------|---------------|--------|
| HTF bias | 4h | `/kronos <SYM>-USD 2y 1d 14` | 4h→1d |
| MTF bölge | 1h | `/kronos <SYM>-USD 3mo 1h 24` | native |
| LTF entry | 15m | `/kronos <SYM>-USD 1mo 15m 12` | 15m → 60g limiti |

### LONG — bot 1h / 8h / 1w
| Katman | Bot TF | Kronos komutu | Eşleme |
|--------|--------|---------------|--------|
| HTF bias | 1w | `/kronos <SYM>-USD max 1wk 12` | native |
| MTF bölge | 8h | `/kronos <SYM>-USD 2y 1d 20` | 8h→1d |
| LTF entry | 1h | `/kronos <SYM>-USD 3mo 1h 24` | native |

> Not: SCALP ve MID'in HTF'i (12h/4h) yfinance'te olmadığı için **ikisi de 1d**'ye düşer.
> Bu yüzden scalp ile mid'in HTF bias komutu pratikte benzerdir — fark MTF/LTF
> granülaritesindedir. LONG ise gerçek 1w + 1h kullanır.

---

## 3. Ritüel — çoklu-koşu konsensüsü (ZORUNLU)

`sample_count=1` non-determinism'i yüzünden tek koşuya güvenme:

1. **Her katman için komutu 3 kez çalıştır.**
2. 3 koşunun **≥2'si aynı yön** (UP/DOWN) → o katman **"onaylı"**, yönü kaydet.
3. Yön her koşuda zıplıyorsa (UP/DOWN/FLAT karışık) → **"gürültü"**, o katmanı geçersiz say.
4. Band genişliğini de not al (NARROW <5% / MODERATE 5-10% / WIDE >10%). WIDE = düşük güven.

> Daha sağlam istersen 5 koşu yapabilirsin; karar kuralı aynı (çoğunluk yön).

---

## 4. Karar cascade'i

Sıra önemli — yukarıdan aşağı, herhangi bir adım düşerse **DUR/bekle**:

```
[0] Bot zaten SMC sinyali üretti mi? (birincil tetikleyici)
        └─ hayırsa: Kronos'u tek başına entry için kullanma, sadece analiz.
[1] HTF bias (1d/1wk) yönü == botun bias'ı (4h/8h/12h HTF)?
        └─ zıt veya gürültü → GİRME.
[2] MTF bölge (1h): yön [1] ile aynı VE band NARROW/MODERATE?
        └─ WIDE veya zıt → bekle, bölge net değil.
[3] LTF entry (5m/15m/1h): yön aynı VE band NARROW?
        └─ WIDE veya zıt → entry timing olgunlaşmamış, bekle.
[✓] Üçü de hizalı → operatör manuel giriş yapar VEYA bota güvenip bırakır.
```

**Özet kural:** Kronos botun sinyalini *güçlendiriyorsa* (3 katman + bot bias aynı yön,
bantlar dar) güven artar. Kronos *çelişiyorsa* (herhangi bir katman zıt/WIDE) → o işlemi
atla. Kronos asla botun reddettiği bir işlemi başlatmaz; sadece teyit/veto eder.

---

## 5. Band yorumlama (skill'in kendi kuralı)

- **NARROW (<5%):** model ileri dağılımında tutarlı → araştırmaya değer sinyal. İkinci
  TF'de teyit ara.
- **MODERATE (5-10%):** karışık sinyal → tek başına karar için değil, bağlam için.
- **WIDE (>10%):** model hedge yapıyor → **gürültü, üzerine işlem yapma.** (AAPL örnek
  koşusu WIDE çıkmıştı — tipik kısa-ufuk davranışı.)

---

## 6. Tam akış örneği (MID profili, BTC)

```bash
# 0. config kontrol: timeframes.profile = mid → MID satırını kullan
# 1. HTF bias (3 koşu)
/kronos BTC-USD 2y 1d 14   ×3   → ör. DOWN,DOWN,DOWN  ⇒ bias DOWN (onaylı)
# 2. MTF bölge (3 koşu)
/kronos BTC-USD 3mo 1h 24  ×3   → DOWN,DOWN,UP + MODERATE ⇒ DOWN (onaylı)
# 3. LTF entry (3 koşu)
/kronos BTC-USD 1mo 15m 12 ×3   → DOWN,DOWN,DOWN + NARROW ⇒ DOWN (onaylı)
# ✓ Bot da SHORT sinyali verdiyse → 3 katman + bot hizalı → yüksek-güven short teyidi.
#   Bot LONG diyorsa veya herhangi katman WIDE/zıt → atla.
```

---

## 7. Ne YAPMAZ

- Bota wire edilmez, otomatik emir vermez, config `risk:`/`safety:` bloklarına dokunmaz.
- yfinance spot fiyatını perp giriş fiyatı olarak kullanma — yön/rejim sinyali olarak oku.
- Tek koşuya, tek TF'e veya WIDE banda dayanarak işlem açma.
- Botun reddettiği bir işlemi Kronos "onayladı" diye açma — Kronos sadece filtre.

İleride bunu shadow advisory katmanına (engine/agents/ içinde, Gemini takımı gibi,
non-binding) terfi etmek istersen ayrı bir tasarım turu açarız — bu playbook o kararın
manuel/ölçüm aşamasıdır.
