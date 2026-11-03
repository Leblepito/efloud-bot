# Runbook: Advisory Research Cycle (TradingAgents + LuxAlgo MTF)

> **Operator kararı 2026-11-03.** 5 saatlik araştırma döngüsü ilk sürümde host'ta
> `.venv-research` ile planlanmıştı; Claude denetimi sonrası **konteyner** biçimine
> alındı: host'a hiç paket kurulmaz, Python sürümü CI/bot ile aynı (3.11) kalır ve
> repo konteynere **read-only** mount edilir.
>
> **ADVISORY ONLY.** Üretilen brief'ler emir, pozisyon boyutu, SL/TP, config veya
> gating girdisi DEĞİLDİR. Motor kendi kurallarıyla trade eder. Bir anlaşmazlık
> (disagree) yalnız araştırma sorusudur — tek işleme müdahale gerekçesi değil.

## Ne üretir

`scripts/desk/research_cycle.py`, her sembol için:

1. **Binance USDT-M** kapanmış mumları (15m / 1h / 4h, public klines — anahtar yok),
2. motorun **LuxAlgo-port** yapısı (`engine/smc_v2/luxalgo.py`, canlı config'in
   `smc_v2.luxalgo` parametreleri): swing/internal trend, son BOS/CHoCH, premium/
   discount, aktif OB'ler, üç TF hizalaması,
3. **TradingAgents** brief'i (4h swing trendi engine bias olarak) — quick tier
   `deepseek/deepseek-v4.1-flash`, deep tier `deepseek/deepseek-v4-pro` (OpenRouter),

tek dosyada: `desk/briefs/<YYYY-MM-DD-HHMM>-<SYM>USDT-research.{md,json}`.
`desk/` gitignore'ludur (yerel çıktı).

## Mimari / güvenlik sınırları

| Konu | Karar |
|---|---|
| İmaj | `efloud-research:latest` — `deploy/Dockerfile.research`, `python:3.11-slim` + `requirements-research.txt` |
| Neden ayrı imaj | TradingAgents `pandas>=3.0.6` ister, bot imajı `pandas==3.0.3` pinler (constraints.txt) — paylaşılan ortam bağımlılık kaymasıdır |
| Repo mount | **read-only** (`type=bind,src=/opt/efloud-bot,dst=/app,readonly`) |
| Yazılabilir tek yer | `desk/` (nested bind) — brief'ler ve TradingAgents state'i |
| Anahtar kaynağı | **yalnız `.env.research`**; `.env.production` ASLA verilmez (Binance anahtarları orada, TradingAgents güvenilmeyen haber/sosyal metni LLM'e verir) |
| Konteyner | `--rm`, port publish YOK, `--tmpfs /tmp` |
| Kullanıcı | root (host'taki `desk/` root'a ait); non-root isteniyorsa `chown -R 10002:10002 desk` + `--user 10002:10002` |

## Kurulum

```bash
cd /opt/efloud-bot

# 1) LLM anahtarı — SADECE bu dosya (600, root)
cp deploy/.env.research.example .env.research
chmod 600 .env.research
vi .env.research                      # OPENROUTER_API_KEY=... tek satır

# 2) İmajı build et (ilk seferde ~2-4 dk, ~1.5 GB)
docker build -f deploy/Dockerfile.research -t efloud-research:latest .

# 3) systemd timer
cp deploy/research-cycle.service deploy/research-cycle.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now research-cycle.timer
systemctl list-timers research-cycle.timer
```

Wrapper `requirements-research.txt`'in hash'ini saklar; dosya değişirse bir sonraki
koşuda imajı kendisi yeniden build eder (`desk/.research_image.stamp`).

## İlk koşu protokolü (sırayla, atlamadan)

```bash
# (a) ÜCRETSİZ duman testi — LLM çağrısı yok, yalnız yapı + veri yolu
deploy/research-cycle.sh --no-tradingagents --symbols BTC/USDT

# (b) Tek sembol, tam koşu — ilk gerçek TradingAgents çalışması
deploy/research-cycle.sh --symbols BTC/USDT

# (c) Maliyet kontrolü (koşu başına çağrı sayısı yüksektir):
#     https://openrouter.ai/activity  →  maliyet kabul edilebilirse (d)'ye geç
#     Sembol eklemek maliyeti DOĞRUSAL artırır: BTC+ETH = 2× tek sembol.

# (d) Varsayılan kadansı doğrula
systemctl start research-cycle.service && journalctl -u research-cycle.service -n 30 --no-pager
```

**TradingAgents bugüne kadar yalnız mock testlerle doğrulandı** (`tests/desk/test_*`) —
(a) ve (b) ilk gerçek çalıştırmadır. (b) başarısız olursa sembol **unavailable**
olarak raporlanır ve döngü durmaz; hatayı `desk/briefs/*-research.json` içindeki
`tradingagents.error` alanından oku.

## Doğrulama

```bash
systemctl list-timers research-cycle.timer            # NEXT = +5h
journalctl -u research-cycle.service -n 50 --no-pager
ls -lt desk/briefs/ | head                            # en yeni brief

# Üretilen brief'te model katmanları gerçekten görünüyor mu:
python3 -c "import json,glob;d=json.load(open(sorted(glob.glob('desk/briefs/*-research.json'))[-1]));\
print(d['symbol'], d['mtf']['htf_bias'], d['mtf']['alignment'], d.get('tradingagents',{}).get('llm'))"
```

Beklenen: `llm` alanında `llm_provider: openrouter` + `deepseek/...` modelleri.
`tradingagents.error` varsa anahtar/model/veri kaynağı sorunudur.

## Durdurma / maliyet kontrolü

```bash
systemctl stop research-cycle.timer                   # zamanlayıcıyı durdur (koşu sürüyorsa biter)
systemctl disable research-cycle.timer                # kalıcı kapat
docker rm -f efloud-research-run 2>/dev/null || true   # takılı koşuyu kes
```

Ek önlemler (OpenRouter tarafı, hesap ayarı):
- anahtara **credit limit** koy,
- hesapta **"training on prompts" kapalı** olsun,
- `.env.research` yalnız `600` ve root'a ait kalsın.

## Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| `FATAL: .env.research yok` | Şablonu kopyala: `cp deploy/.env.research.example .env.research` |
| `FATAL: production env dosyası bu runner'a verilemez` | `RESEARCH_ENV_FILE` yanlış; `.env.production*` verme |
| `FATAL: OPENROUTER_API_KEY boş` | Anahtar boş/silinmiş; değer loglanmaz, dosyaya bak |
| `Read-only file system` | Yalnız `desk/` yazılabilir; çıktıyı `--out desk/briefs` altında tut. `--out` repo dışıysa yazılamaz |
| İmaj build hatası (`pandas`/`langchain` derleme) | Python sürümü 3.11 olmalı (`python:3.11-slim`); bir tur eski imajı silip yeniden dene: `docker rmi efloud-research:latest` |
| `docker: conflict ... efloud-research-run` | Önceki koşu takılı: `docker rm -f efloud-research-run` |
| TradingAgents 401 | Yanlış/eksik anahtar ya da `--provider`/`TRADINGAGENTS_LLM_PROVIDER` sapması |
| Yahoo verisi boş | TradingAgents Yahoo spot kullanır (Binance perp değil); geçici vendor kesintisi olabilir — sonraki koşuda düzelir |

## İlgili

- `skills/tradingagents-research/SKILL.md` — araç kullanımı, yorumlama
- `scripts/desk/research_cycle.py` — döngü, `--no-tradingagents` bayrağı
- `scripts/desk/tradingagents_brief.py` — tek sembol brief'i
- `deploy/Dockerfile.research`, `deploy/research-cycle.sh`, `deploy/research-cycle.{service,timer}`
- `skills/luxalgo-smc/SKILL.md` — motorun SMC referansı
- `docs/runbooks/crash-loop-recovery.md` — bot tarafı olay akışı (bu runbook onu etkilemez)
