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
