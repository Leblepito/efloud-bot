---
id: T-20261107-07
title: test_xurl_client — yüksek-entropi credential değerini sentetikle değiştir
from: claude-code
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: T-20261106-06
created: 2026-11-07
touches_live: false
---

## Amaç
Güvenlik denetimi (T-20261106-06) fix #5. `backend/tests/test_xurl_client.py`'deki bir yorum
(ve ondan türetilmiş kısaltılmış assert değeri) bilinen sahte kalıplara uymayan, 95 karakterlik
yüksek-entropi bir `sk-…` değeri içeriyordu (2026-06-18'den beri). Değer canlı env'lerde
kullanılmıyor (VPS özet karşılaştırması: eşleşme yok). Test anlamı aynı kalır: uzun bir
credential'ın yalnız son 4 karakteri görünür.

## Beklenen çıktı (Definition of Done)
- [x] Yorum + assert açıkça sentetik değerle (`test-ONLY-not-a-real-credential-0000abcd`)
- [x] `backend/tests/test_xurl_client.py` 24 passed
- [x] Regex tarayıcı + gitleaks değiştirilen satırları artık işaretlemiyor (kalan 2 bulgu önceden var olan sahte değerler, baseline'da)

## Kısıtlar
- Geçmişteki değer git geçmişinde kalır; değer bir servise aitse operatör iptal etmeli (private rapor).

## Log
- 2026-11-07 claude-code: değiştirildi + doğrulandı.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
