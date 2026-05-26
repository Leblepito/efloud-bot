# Handoff: Sistem Kurulumu — Model Dispatch Protokolü

**Yazan:** 🏛️ Opus (Claude Opus 4.6)
**Tarih:** 2026-05-26
**Durum:** tamamlandı

## Ne Yapıldı

Efloud-bot projesi için çoklu-model (Opus Mimar + Flash Mühendis) işbirliği
sistemi kuruldu:

1. **GEMINI.md** — Flash'ın Kıdemli Mühendis rolü tanımlandı: çalışma protokolü,
   kod yazma standartları, referans repo kullanım tablosu.
2. **CLAUDE.md §7** — Opus'un Mimar rolü tanımlandı: spec yazımı, code review,
   prompt optimizasyonu, strateji değerlendirme.
3. **ROADMAP §6** — Model Dispatch Tablosu: her görev 🏛️ OPUS / 🔧 FLASH / 🤝 ORTAK
   etiketiyle işaretlendi.
4. **ROADMAP §7** — Handoff Protokolü: dosya formatı, çalışma akışı diyagramı.
5. **Referans repo eşlemesi** — Hangi görevde hangi external_repos/ kullanılacağı
   dispatch tablosunda belirtildi.

## Karşı Model İçin Not (Flash)

Sıradaki işlerin:
- **Faz 0.1** → `external_repos/caveman` referansıyla CLAUDE.md ve HERMES.md
  dosyalarını caveman-tarzı sıkıştır
- **Faz 0.2** → `external_repos/graphify` referansıyla proje bilgi grafiğini çıkar

Bu görevlere başlamadan önce `docs/ROADMAP_AI_INTEGRATION.md` §6'daki dispatch
tablosunu ve ilgili referans reponun README'sini oku.

## Dosya Değişiklikleri

| Dosya | Değişiklik |
|---|---|
| `GEMINI.md` | Tamamen yeniden yazıldı — mühendis rolü eklendi |
| `CLAUDE.md` | §7'ye mimar rolü eklendi |
| `docs/ROADMAP_AI_INTEGRATION.md` | §6 Model Dispatch + §7 Handoff Protokolü eklendi |
| `docs/handoff/` | Bu dizin oluşturuldu |
| `docs/skill_log.md` | Dispatch sistemi log'landı |
