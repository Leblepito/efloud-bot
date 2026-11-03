---
name: llm-advisory-backend
description: Advisory LLM katmanını (agent team, sentiment, structure validation) sağlayıcı/anahtar açısından doğrula veya değiştir. Sağlayıcı değişikliği, "kararlar boş geliyor", yeni LLM sağlayıcısı ekleme, anahtar rotasyonu işlerinde kullan.
---

# Advisory LLM backend — sağlayıcı, anahtar, sessiz arıza

Botun LLM katmanı **tamamen danışma (advisory)**dır ve **fail-safe**'tir: anahtar
yoksa, HTTP hata verirse veya cevap JSON değilse `complete_json()` **sessizce
`{}`** döner. Trade mantığı, sizing, SL/TP ve confluence bu katmandan etkilenmez.
Bu yüzden katman bozukken bot **sağlıklı görünür** — arıza yalnızca boş kararlarla
kendini belli eder. Teşhis sırası bunu varsaymalı.

## Sağlayıcı çözümleme sırası (tek kaynak: `engine/agents/llm.py`)

1. `config["provider"]` — hangi blok okunuyorsa o blok (`llm:` / `agent_team:` / per-feature)
2. `LLM_PROVIDER` env — yalnız config'te `provider` YOKSA devreye girer
3. varsayılan: `claude`

⚠️ **Config'te `provider` yazılıysa `LLM_PROVIDER` onu EZMEZ.** Sağlayıcı değiştirmek
istiyorsan ilgili config bloklarını da düzenle. Üç canlı profil ayrı dosyada:
`configs/config.phase2_1k.yaml` (mid), `config.phase2_long_1k.yaml`, `config.phase2_scalp_1k.yaml`.

## Anahtar → env eşlemesi

`engine/agents/llm.py:PROVIDER_KEY_ENV` tek kaynaktır:

| provider | env |
|---|---|
| `openrouter` | `OPENROUTER_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |
| `minimax` | `MINIMAX_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |

**Yeni sağlayıcı eklerken bu sözlüğe de ekle** — eklemezsen `provider_key_present()`
o sağlayıcıyı "yapılandırılmamış" sayar ve bot çağrıyı tamamen atlar. Test bekçisi:
`tests/config/test_agent_team_observation.py::test_every_pinned_llm_provider_is_key_registry_aware`.

## Aktif karar (2026-11-03)

Canlı üç profil de **`openrouter` + `deepseek/deepseek-v4.1-flash`** kullanır.
Sebep: canlı VPS'te Anthropic/MiniMax anahtarı **yok**; `claude-*` pin'i her çağrıda
401 → boş karar demekti. OpenRouter tek anahtarla tüm modelleri açar.
Danışma katmanı için hızlı/ucuz tier yeterli; ağır akıl yürütme için daha güçlü
model istersen `model:` satırını değiştir (ör. `deepseek/deepseek-v4-pro`).

## Her instance'ın KENDİ env dosyası var

`docker-compose.prod.yml` üç ayrı env dosyası okur:

| servis | env_file |
|---|---|
| `efloud-bot` (mid) | `.env.production` |
| `efloud-bot-long` | `.env.production.long` |
| `efloud-bot-scalp` | `.env.production.scalp` |

Anahtar **üç dosyada da** bulunmalı; yalnız birine koymak diğer iki botu sessizce
sessiz bırakır. Şablonlar: `deploy/.env.production*.example`.

## Doğrulama (secret yazdırmadan)

```bash
# 1) Container'da anahtar ADI var mı (değeri yazdırma)
ssh root@2.28.139.82 'docker exec efloud-bot printenv | cut -d= -f1 | grep -c OPENROUTER_API_KEY'

# 2) Bot hangi sağlayıcıyı/modeli gerçekten kullanıyor (endpoint provider+model döner)
curl -sk -b /tmp/c.txt https://2-28-139-82.nip.io/api/ai/agents | head -c 300

# 3) Karar üretimi: journal satırlarında agent_review alanı
ssh root@2.28.139.82 'docker exec efloud-bot tail -n 5 /app/state_1k/trade_journal.jsonl' | \
  python -c "import sys,json;[print(json.loads(l).get('symbol'), bool(json.loads(l).get('agent_review'))) for l in sys.stdin if l.strip()]"
```

`GET /api/ai/agents` `{"enabled": true, "provider": "...", "model": "...", "reviews": []}`
dönerken `reviews` boşsa: katman açık ama ya hiç trade açılmamıştır (gözlem modu
**açılan trade başına** bir kez çağrılır) ya da anahtar/çağrı hatası vardır — log'da
`OpenRouterClient.complete_json failed` satırını ara (ilk hata WARNING, sonra her 20'de bir).

## Yapma

- Anahtar değerini komut satırına, loga, commit'e veya rapora yazma; yalnız süreç içi oku.
- `gating: true` yapma — gözlem modu kayıtlı shadow periyodu + operatör onayı ister
  (`tests/config/test_agent_team_observation.py` bekçilik eder).
- Fail-safe'i "hata yutuyor" diye kaldırma: `{}` dönüşü kasıtlıdır, bot LLM yüzünden durmamalı.
- Anahtar yokken katmanı kapatma; teşhis et → anahtarı ekle (kapalı bırakmak sessiz arızayı gizler).
