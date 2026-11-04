---
id: T-20261105-03
title: "VPS ↔ GitHub master ↔ laptop eşitleme (deploy ticket'ı, abacus yazmaz)"
from: abacus
to: claude-code
status: open
claimed_by: null
reviewer: operator
parent: T-20261104-08
created: 2026-11-05
touches_live: true
---

## Amaç
Operatör: "Sunucu VPS ile GitHub reposu ve local klasörün eşitlemesini sağla." abacus VPS'e/deploy'a yazamaz
(kalıcı kural); bu yüzden durum tespiti + deploy ticket'ı. Uygulama claude-code (+ Risk PASS + operatör onayı).

## Girdi (abacus salt-okuma tespiti, 2026-11-05)
- GitHub `origin/master` = `2fe79b7` (#283 WS Faz 1 merge edildi).
- VPS `/opt/efloud-bot` HEAD = `b6c6bd1`, çalışma ağacı temiz, master'ın **16 commit gerisinde**. Container'lar: efloud-bot,
  -scalp, -long (healthy), alerter, routines, overseer up. `EFLOUD_AUTOSTART=0`; mid elle başlatılmıştı, scalp/long boşta
  (T-07: şimdilik böyle kalsın — operatör kararı).
- VPS ↔ master çalışma-zamanı farkı (collab/docs/tests hariç): `backend/bot_runner.py`, `engine/safe_orchestrator.py`
  (#275 near-alert log satırı + `_v2_state_lock`'sız eski hâl), `exchange/ws_klines.py` (yeni, default OFF),
  `ops/alerter/alerter.py`, `ops/alerter/rules.py`, `.env.example`, `.dockerignore`, `AGENTS.md`, `HERMES.md`.
- Laptop ana klon: `master` @ `d4d737a`, `origin/master`'ın **24 commit gerisinde**; 12 commit'siz değişiklik (başkasına ait)
  ve bunların 11'i upstream'de de değişen dosyalar (config*.yaml, engine/agents/llm.py, scripts/desk/*, ...) →
  düz `git pull` çakışır. abacus ana klona dokunmadı.

## Beklenen çıktı (Definition of Done)
- [ ] Laptop: commit'siz değişiklikler sahibince commit/stash edilir; sonra `git pull --ff-only origin master`.
- [ ] VPS: `deploy/deploy.sh` ile master'a alınır (`git fetch && git checkout`/ff; 3 container rebuild). Yalnız default-OFF
      kod gelir; config değişmez. Deploy öncesi/sonrası: `docker ps`, `/healthz`, son 15 dk log, açık pozisyon yok mu kontrolü.
- [ ] Alerter (#275) açılacaksa ayrı adım: `.env` → `EFLOUD_ALERTER_LUX_ALERTS=1`; yaklaşma için config `near_alert_atr` (config PR).
- [ ] WS (#283) açılacaksa ayrı config PR: `data_feed.ws.enabled: true` (gölge). #280 merge sonrası `event_scan` ve `touch_entry: shadow`.
- [ ] Sonrası: VPS HEAD = master HEAD, `git status` temiz; `collab/STATUS.md` + log `- VPS: DEPLOYED <sha>`.

## Kısıtlar
- `risk:` / `safety:` blokları değişmez. Deploy anında açık pozisyon varsa operatöre sor. Force-push/reset --hard yok.
- #280, #272, #276 merge sırası bu ticket'tan bağımsız.

## Log
- 2026-11-05 abacus: ticket yazıldı (salt-okuma tespit). Not: tespit sırasında VPS'te `git fetch` çalıştırıldı (yalnız uzak ref güncellemesi, çalışma ağacı/HEAD değişmedi).

## Review
