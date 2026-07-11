# Karpathy Guidelines — efloud-bot Yerel Kopyası

> Kaynak: `andrej-karpathy-skills` plugin (Andrej Karpathy'nin LLM-coding
> pitfalls gözlemleri). Bu dosya 2026-07-11'de repo'ya absorbe edildi —
> plugin kurulu olmayan ortamlarda (VPS, CI, diğer agentlar) da geçerli.
> CLAUDE.md "Geliştirme Sözleşmesi" bölümü bu prensipleri efloud-bot'un
> sert kurallarına (risk-ops, backtest-gate, TDD) bağlar; bu dosya ham
> prensiplerin referans metnidir.

**Trade-off:** Bu kurallar hızdan çok dikkati önceler. Trivial işlerde sağduyu.

## 1. Think Before Coding — Kodlamadan Önce Düşün

**Varsayma. Kafa karışıklığını gizleme. Trade-off'ları açıkça yaz.**

Implementasyondan önce:
- Varsayımlarını açıkça yaz. Emin değilsen sor.
- Birden fazla yorum varsa hepsini sun — sessizce seçme.
- Daha basit bir yaklaşım varsa söyle. Gerektiğinde karşı çık.
- Bir şey belirsizse dur. Neyin belirsiz olduğunu adlandır. Sor.

## 2. Simplicity First — Önce Sadelik

**Problemi çözen minimum kod. Spekülatif hiçbir şey yok.**

- İstenmeyen özellik yok.
- Tek kullanımlık kod için soyutlama yok.
- İstenmemiş "esneklik"/"configurability" yok.
- İmkânsız senaryolar için error handling yok.
- 200 satır yazdıysan ve 50 olabilirdiyse, yeniden yaz.

Kendine sor: "Senior bir mühendis buna over-complicated der mi?" Evetse sadeleştir.

## 3. Surgical Changes — Cerrahi Değişiklikler

**Sadece zorunlu olana dokun. Sadece kendi pisliğini temizle.**

Mevcut kodu düzenlerken:
- Komşu kodu/yorumu/formatı "iyileştirme".
- Bozuk olmayanı refactor etme.
- Mevcut stile uy — kendin farklı yapacak olsan bile.
- İlgisiz dead-code görürsen söyle — silme.

Değişikliklerin orphan yaratırsa:
- SENİN değişikliğinin kullanımdan düşürdüğü import/değişken/fonksiyonu kaldır.
- Önceden var olan dead-code'u istenmedikçe kaldırma.

Test: Değişen her satır kullanıcının talebine doğrudan izlenebilir olmalı.

## 4. Goal-Driven Execution — Hedef Güdümlü Yürütme

**Başarı kriterini tanımla. Doğrulanana kadar döngüde kal.**

Görevleri doğrulanabilir hedeflere çevir:
- "Validasyon ekle" → "Geçersiz girdiler için test yaz, sonra geçir"
- "Bug'ı düzelt" → "Bug'ı reprodüke eden test yaz, sonra geçir"
- "X'i refactor et" → "Testler öncesinde ve sonrasında geçsin"

Çok adımlı işlerde kısa plan yaz:
```
1. [Adım] → doğrula: [kontrol]
2. [Adım] → doğrula: [kontrol]
3. [Adım] → doğrula: [kontrol]
```

Güçlü başarı kriterleri bağımsız döngüye izin verir. Zayıf kriterler
("çalışsın yeter") sürekli açıklama gerektirir.

---

## efloud-bot Eşlemesi (CLAUDE.md sözleşmesinin özeti)

| Karpathy | efloud-bot karşılığı |
|---|---|
| Think Before Coding | risk-ops review + operatör sign-off (mainnet trade mantığı) |
| Simplicity First | confluence/scoring sadeliği; audit M2/H1/M3 bulguları |
| Surgical Changes | atomic-PR + guard koruması; SMC v2 port'unu ezme |
| Goal-Driven Execution | backtest-gate + TDD; toggle default OFF / fail-closed |
