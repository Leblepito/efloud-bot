---
task_id: T-003
assigned_by: hermes
assigned_to: gemini
priority: P2
status: PENDING
skill: vision (chart screenshots)
deadline: "after:T-001"
dependencies: [T-001]
created: 2026-06-09T11:00:00+03:00
---

# Görev: Pine Script Görsel Doğrulama

## Ne Yapılacak
TradingView'de yayınlanan SMC v2 indikatörünün screenshot'larını al ve görsel olarak doğrula:
- CHoCH/BOS işaretleri doğru yerde mi?
- FVG zone'ları doğru çiziliyor mu?
- Entry/SL/TP1/TP2 seviyeleri mantıklı mı?
- Renkler, etiketler okunabilir mi?

## Skill Pipeline
1. TradingView chart link'ini aç (Hermes T-001'den gelecek)
2. Farklı timeframe'lerde screenshot al (15m, 1h, 4h)
3. Her screenshot için görsel analiz yap
4. Varsa hata/iyileştirme önerilerini raporla

## Çıktı
- `LLTODO/reports/gemini/2026-06-09-pine-visual-review.md`
- Varsa düzeltme önerileri (Hermes'e görev)

## Bittiğinde
1. Bu dosyayı `LLTODO/tasks/DONE/` altına taşı
2. Raporu yaz
3. Varsa Hermes için düzeltme görevi oluştur
