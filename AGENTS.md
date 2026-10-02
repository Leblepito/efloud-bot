# AGENTS.md — AI Agent Context (efloud-bot)

> Her AI modeli (Claude, Gemini, Hermes, Codex) bu dosyayı okuyarak projeye
> sıfırdan giriş yapabilir. Kapsamlı referans için `skills/social-publishing/SKILL.md`.

## Proje: efloud-bot

Binance USDT-M futures üzerinde SMC doktriniyle otonom trade botu.
Python (CCXT, FastAPI) + TradingView Pine Script v6.

## Güncel Algoritma Durumu (2026-10-02)

- **v2 AKTİF (canlı emir):** `smc_version=v2`, `smc_v2_symbols` dolu, `smc_v2_shadow=false`.
- **Giriş akışı:** LTF (15m) **CHoCH veya BOS** kırılımı → HTF bias uyumu →
  kırılımı yapan OB/BB bölgesi → geri çekilmede retest → engulfing teyidi →
  limit emir (SL likidite çizgisinde). Kırılım anında market emri YOK.
- **v1 susturma:** v2'nin sahiplendiği sembollerde v1 sinyal girişleri
  `_v2_entry_active()` ile susturulur (`engine/safe_orchestrator.py`).
- **Acil bakiye HALTI kaldırıldı:** `emergency_balance_threshold=0` — koruma
  günlük %10 / haftalık %25 kayıp limitleriyle.
- **Volatil rejim:** `allow_volatile_entries=true` — volatil piyasada girişler açık.
- **Bölge aşım toleransı:** `max_zone_overshoot_atr=2.0`.

## Kritik Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `HERMES.md` | Operatör kılavuzu (deploy, config, incident) |
| `CLAUDE.md` | Proje bellek, mimari, Pine Script kuralları |
| `skills/social-publishing/SKILL.md` | Sosyal medya pipeline'ı (HER modele) |
| `AGENTS.md` | Bu dosya — AI giriş noktası |
| `configs/config.phase2_1k.yaml` | Production config (risk/safety/engine) |
| `engine/smc_v2/triggers.py` | v2 trigger (CHoCH+BOS → SetupCandidate) |
| `engine/safe_orchestrator.py` | Ana orchestrator (v1 susturma + v2 entry) |

## Sosyal Medya Pipeline'ı (YENİ 2026-07-26)

Tek komut: `python -m scripts.daily_social_run --date $(date -u +%F)`

Bot sinyali → chart PNG (ENTRY/SL/TP) → MP4 klip → X/IG/YT paketleri.
Üç güvenlik kapısı (hepsi default KAPALI): onay, live, platform flag'leri.

Detay: `skills/social-publishing/SKILL.md`

## Test

```bash
python -m pytest --ignore=external_repos --import-mode=importlib -q
```
