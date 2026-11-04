---
id: T-20261104-07
title: "İstek: scalp ve long botlar restart sonrası idle — başlatılsın mı?"
from: claude-code
to: operator
status: open
claimed_by: null
reviewer: null
parent: null
created: 2026-11-04
touches_live: true
---

## Amaç
VPS container'ları 2026-11-04 ~14:35 UTC'de yeniden başladı. `EFLOUD_AUTOSTART=0` olduğu için
botlar `/api/bot/start` bekliyor. Mid bot (`efloud-bot`) 14:38'de elle başlatıldı; `efloud-bot-scalp`
ve `efloud-bot-long` başlatılmadı → o andan beri hiç tarama döngüsü yok (healthz 200 olsa da).
Operatörün "bot bölgeye gelince girmiyor" gözleminin bir kısmı bu olabilir.

## Girdi
- `docker logs efloud-bot-scalp|efloud-bot-long --since 6h` → yalnız "Autostart disabled" satırı,
  0 adet `Regime:` satırı; `efloud-bot`'ta 190 adet (gözlem 2026-11-04 ~19:15 UTC).
- Rapor: `collab/outputs/claude-code/2026-11-04-ob-entry-gap.md` §1.

## Beklenen çıktı (Definition of Done)
- [ ] Operatör kararı: scalp/long kasıtlı mı kapalı, yoksa başlatılacak mı?
- [ ] Başlatılacaksa operatör kendisi başlatır (dashboard ya da `/api/bot/start`) ve `Regime:` satırlarının
      aktığını doğrular. Modeller bu adımı UYGULAMAZ.
- [ ] (Opsiyonel karar) Restart sonrası "idle" durumunun Telegram'a uyarı olarak düşmesi
      (alerter kuralı) — ayrı task gerekir.

## Kısıtlar
- Canlı sisteme dokunur → desk-operating-model ticket + operatör onayı. Hiçbir model start/stop yapmaz.

## Log
- 2026-11-04 claude-code: task açıldı (OB-entry-gap teşhisi sırasında bulundu).

## Review
