---
id: T-20261107-02
title: Composio reel çalışma klasörünü gitignore'a ekle
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: T-20261106-06
created: 2026-11-07
touches_live: false
---

## Amaç
Güvenlik denetimi takibi. Ana klonda takip dışı `Composio İnstagram_Youtube_X/` klasörü
(reel üretim araçları + mp4/wav/png çıktıları) gitignore'lu değildi; içindeki `.env.local`
API anahtarı barındırıyor. Yanlışlıkla `git add -A` ile public repoya girme riski kapatılır.
`data/lab/` zaten `.gitignore:137`'de ignore'lu (ana klon eski commit'te olduğu için görünmüyordu).

## Beklenen çıktı (Definition of Done)
- [x] `.gitignore`'a `Composio*/` kuralı
- [x] `git check-ignore -v --no-index` ile Türkçe karakterli yol doğrulandı; takip edilen kod etkilenmiyor
- [x] Repoda bu yolda takip edilen dosya yok (0)

## Kısıtlar
- Yalnız `.gitignore` + collab dosyaları.

## Log
- 2026-11-07 claude-code: kural eklendi + doğrulandı.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
