---
skill: efloud-smc-concepts
author: hermes
status: in-review
version: 645a5dc
---

# Review — efloud-smc-concepts

> Düzenleme notu (claude-code, 2026-11-04): `skills/` → incubator taşındı (`git mv`), SKILL.md'ye INCUBATOR banner'ı eklendi, içerik değişmedi.

## claude-code — 2026-11-04 — VERDICT: CHANGES

**Kapsam:** taslak 35 mesaja (2023-08-01 → 08-13) dayanıyor; export 892 mesaj (2023-08 → 2025-11).
Kural ağırlıkları bu yüzden yanıltıcı. Tam veri üzerinde anahtar kelime frekansı (mesaj sayısı,
büyük/küçük harf duyarsız): confirmation 129 · stop 123 · entry 106 · range 50 · swing 31 ·
likidite 22 · PWO 21 · imbalance 20 · breaker 13 · mitigation 12 · SFP 4 · **RL Zone 2**.
→ RL Zone "zorunlu kural" değil; confirmation açık ara baskın.

**Motor eşlemesi (doğrulandı):**
| Taslak iddiası | Gerçek |
| --- | --- |
| `BreakerBlock` / `MitigationBlock` sınıfları | YOK. `OrderBlock.mitigated` / `became_breaker` alanları — `engine/smc.py:57` (`mitigated`), `:58` (`became_breaker`), geçiş `engine/smc.py:249-255` |
| WO/MO/PWO "Injected Levels" | VAR — `engine/levels.py:94-114` (`LevelEngine`), signals'ta major level seti `engine/signals.py:714` |
| FVG, EQH/EQL | VAR — `engine/smc.py:38` (FVG), `engine/smc.py:91` (EqLevel) |
| Confirmation = mLTF CHoCH/BOS | **FARKLI.** Canlıda `smc_v2.luxalgo.enabled: true` (`configs/config.phase2_1k.yaml:182-183`, 2026-11-01): setup'ları LuxAlgo BOS/CHoCH üretir (`engine/smc_v2/luxalgo.py`, çağrı `engine/safe_orchestrator.py:1212-1220`); efloud `triggers.py` yolu bu modda devre dışı. Giriş teyidi her iki modda entry-TF **engulfing** (`engine/smc_v2/confirmation.py:23`; mid=15m, scalp=5m). Telegram kuralı = 5m/15m yapı kırılımı. → hipotez H-TG1: "LuxAlgo setup + engulfing" vs "LuxAlgo setup + mLTF BOS/CHoCH teyidi". |
| Renkli kutular (mavi/yeşil/kırmızı/mor) | Kanalın grafik çizim konvansiyonu; motorda karşılığı OB/FVG/range bölgeleri. Görseller export'ta yok → renk↔zone eşlemesi doğrulanamaz, "operatörün notu" olarak işaretle. |

**İstenen değişiklikler (v2):**
1. T-20261104-01 rulebook'una dayan: her kural için frekans + yıl dağılımı + örnek mesaj id.
2. Sınıf adlarını gerçek koda çevir (yukarıdaki tablo).
3. "Mandatory rules" listesinden RL Zone'u çıkar / frekansa göre ağırlıklandır.
4. `setup-rules` ile tek skill'de birleşmeye hazırla (çok örtüşüyor).


## abacus — 2026-11-04 — VERDICT: CHANGES

Bağımsız ilk inceleme (Claude değerlendirmeleri okunmadan):

- **Aktif giriş teyidi yanlış eşlenmiş:** Skill mLTF CHoCH/BOS'u zorunlu son teyit/giriş tetikleyicisi olarak tanımlıyor (SKILL.md:69-76, 126-129, 169-170). Canlı LuxAlgo yolu CHoCH/BOS ile OB'ye bağlı setup adayı üretir (`engine/smc_v2/luxalgo.py:516-570`), ardından entry-TF engulfing mumunu zone içinde arar (`engine/smc_v2/confirmation.py:1-14, 80-95`). Config LuxAlgo'yu etkinleştiriyor (`configs/config.phase2_1k.yaml:175-198`). Ayrım (setup trigger vs. retest confirmation) skill'de netleştirilmeli.
- **"RL Zone" isim çakışması:** Skill `RL Zone`'u Resistance Level/purple supply box diye tanımlıyor (SKILL.md:29, 37, 98), ancak repo `LevelEngine`'de `RL` 200 günlük range'in *low* seviyesidir (`engine/levels.py:129-136`). Üretim LuxAlgo portunda `RL Zone` adlı bu mor bölge eşlemesi de görünmüyor (`engine/smc_v2/luxalgo.py:104-115` veri modelleri; canlı kullanım `:1212-1237`). Kavramın kaynak terminolojisi ve kod alanı ayrı yazılmalı.
- **Motor referansları fazla iddialı:** `Confirmation → mLTF CHoCH/BOS in SignalEngine` ve renkli kutu → engine OB eşlemesi (SKILL.md:167-171) canlı LuxAlgo yolu için doğru değil; v1 `SMCEngine` OB/FVG hesapları ayrı uygulama (`engine/smc.py:191-256, 380-405`), canlı setup ise LuxAlgo'nun kendi OB'sini kullanıyor.
- **Desteklenmeyen kurallar:** Mor bölge kırılımında hacim şartı ve "no new longs" gibi kesin kurallar (SKILL.md:35-37, 103-105) kodla doğrulanmıyor. Kavram/Telegram özeti olarak kalabilir, deterministik motor kuralı izlenimi vermemeli.

**Claude karşılaştırması:** VERDICT ve canlı confirmation farkı aynı; ikimiz de renk-kutu semantiğinin motor eşlemesi olmadığını / doğrulanamadığını ve 35 mesajlık örneklemin 892 mesajın tamamı olmadığını vurguluyoruz. Claude'un ek kanıtları: kaynak export'ta confirmation/stop tekrarlarının frekansı, `BreakerBlock`/`MitigationBlock` sınıflarının bulunmayıp `OrderBlock` alanlarının kullanılması ve WO/MO/PWO'nun gerçekten `LevelEngine`'de bulunması. Benim farklı ek bulgum: kanalın `RL Zone` (resistance) terimi repo'daki `RL` (200 günlük range low) ile ad çakışması yaratıyor; ayrıca mor bölge için hacimle kırılım / yeni long açmama iddialarının canlı deterministik kapıyla eşleşmediğini belirttim. Kural frekansı ve yıl dağılımı T-01 rulebook'ta hesaplanmalı.
