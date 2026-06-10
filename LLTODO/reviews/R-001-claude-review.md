# R-001: P-001 Review — @claude

**Tarih:** 2026-06-08
**Reviewer:** @claude (Architect/Reviewer)
**Epic:** P-001 (u2algo Wave 1 TradingView)
**Confidence:** 7/10
**Sonuç:** CHANGES_REQUESTED

## 1. Genel Değerlendirme

Plan sağlam bir temele oturuyor. Python SMC mantığının Pine Script v6'ya çevirisi teknik olarak mümkün ve doğru scope'ta başlamış. Ancak üç alanda iyileştirme şart.

## 2. Güçlü Yönler
- Parametre eşleme tablosu net, Python→Pine tek tek karşılık bulmuş
- v6 sözdizimi zorunluluğu doğru (legacy `study()` uyarısı yerinde)
- Repaint riski farkındalığı var, `barstate.isconfirmed` doğru yönde
- İki versiyon (indikatör + strateji) ayrımı net

## 3. Bulgular

### 3a. Kritik (Blocker)
*Bulunamadı.*

### 3b. Önemli (Should-Fix)

| ID | Bulgu | Öneri |
|---|---|---|
| S-1 | **Kapsam daraltma gerekli.** Tüm MTF zincirini (4h+1h+15m+Daily) tek Wave'de yapmaya çalışmak riskli. Önce en kritik iki timeframe ile başla. | Wave 1: sadece 1h bias + 15m trigger. 4h ve Daily'yi Wave 2'ye ertele. |
| S-2 | **Görsel standartlar eksik.** Plan renk paleti, çizgi kalınlıkları, opacity tanımlamamış. TradingView dark mode uyumlu palette olmalı. Ayrıca renk körü dostu alternatif opsiyonu eklenmeli. | Bölüm 4 ekle: tam renk paleti tablosu (hex kodlarıyla), çizgi stilleri, renk körü palette. |
| S-3 | **CAC / iş modeli yok.** Ücretsiz/premium ayrımı doğru ama CAC hesabı, gelir modeli, conversion funnel yok. | Bölüm 5b ekle: CAC hesaplama, gelir modeli, conversion hedefi. |

### 3c. İyileştirme (Nice-to-Have)

| ID | Bulgu | Öneri |
|---|---|---|
| N-1 | FVG (Fair Value Gap) görselleştirmesi plana eklenebilir | Wave 1'e dahil edilebilir, düşük efor |
| N-2 | `pine/PINE_SPEC.md` için template hazır olabilir | T-001 ile paralel yazılabilir |

## 4. Kapsam Değerlendirmesi

Mevcut kapsam fazla geniş. 4 timeframe'i tek seferde çevirmek, Pine v6'nın dizi/line limitleri düşünüldüğünde sorun çıkarabilir. **Öneri:** Wave 1 = 1h bias + 15m trigger. Gerisi Wave 2.

## 5. Teknik Doğruluk

Parametre eşleme doğru. SL/TP formülleri Python'dakiyle tutarlı. `request.security()` repaint konusuna dikkat çekilmemiş — `lookahead=barmerge.lookahead_off` zorunlu olmalı.

## 6. İş Modeli Uyumu

Ücretsiz indikatör + premium strateji ayrımı doğru. Ama CAC/gelir hesabı yapılmadan "premium" demek eksik kalır. Hedef kitle, fiyatlandırma, conversion beklentisi belirtilmeli.

## 7. Karar

**Sonuç:** CHANGES_REQUESTED
**Gerekçe:** Kapsam daraltma, görsel standartlar, CAC/gelir gate'leri eklenmeli. Teknik olarak plan doğru ama eksik.
