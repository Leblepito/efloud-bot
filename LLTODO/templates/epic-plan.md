# Template: Epic Plan

> Kopyalayıp `LLTODO/plans/P-XXX-<slug>.md` olarak kaydedin.

```markdown
# P-XXX: <Epic Başlığı>

**Başlangıç:** YYYY-AA-GG
**Sahip:** @agent (implementor), @agent (reviewer)
**Branch:** `feat/<branch-adı>`

## 1. Hedef
<Tek cümle: Bu epic neyi başaracak?>

## 2. Kapsam
### 2a. Dahil
- <Kapsam maddesi 1>
- <Kapsam maddesi 2>

### 2b. Hariç (Kapsam Daraltma)
- <Hariç tutulan 1>
- <Hariç tutulan 2>

## 3. Teknik Tasarım
### 3a. Mimari
<Yüksek seviye mimari diyagramı veya açıklaması>

### 3b. Veri Akışı
<Input → Process → Output zinciri>

### 3c. Bağımlılıklar
- <Bağımlılık 1>
- <Bağımlılık 2>

## 4. Görsel Standartlar
### 4a. Renk Paleti
| Eleman | Renk | Hex |
|---|---|---|
| <Eleman> | <Açıklama> | `#XXXXXX` |

### 4b. Çizgi Stilleri
| Eleman | Kalınlık | Stil |
|---|---|---|
| <Eleman> | <px> | <solid/dashed/dotted> |

## 5. Kalite Gate'leri
### 5a. Teknik Gate'ler
- [ ] <Gate 1: örn. lint yeşil>
- [ ] <Gate 2: örn. repaint kontrolü>
- [ ] <Gate 3: örn. min 100 trade backtest>

### 5b. İş Gate'leri (CAC/Gelir)
- [ ] <Gate 1: örn. CAC hesabı yapıldı>
- [ ] <Gate 2: örn. Gelir modeli onaylandı>
- [ ] <Gate 3: örn. Premium/ücretsiz ayrımı net>

## 6. Görevler

| ID | Açıklama | Tahmini Süre | Bağımlılık |
|---|---|---|---|
| T-001 | <Görev 1> | <süre> | — |
| T-002 | <Görev 2> | <süre> | T-001 |
| T-003 | <Görev 3> | <süre> | T-002 |

## 7. Riskler
| Risk | Olasılık | Etki | Mitigasyon |
|---|---|---|---|
| <Risk 1> | Düşük/Orta/Yüksek | Düşük/Orta/Yüksek | <Çözüm> |

## 8. Revizyon Geçmişi
| Tarih | Revizyon | Yazar |
|---|---|---|
| YYYY-AA-GG | İlk sürüm | @agent |
```
