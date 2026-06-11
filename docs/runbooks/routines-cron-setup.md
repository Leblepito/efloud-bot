# Routines & Watcher — Hetzner Setup & Operations Runbook

This runbook guides you through deploying the `routines-watcher` always-on daemon and setting up the scheduled cron tasks for the advisory routines layer.

---

## 1. Prerequisites

1. **Routines Scaffolding & Code Deployed:** Ensure that `scripts/routines/` and the updated `docker-compose.prod.yml` are pulled onto the VPS host.
2. **Environment Variables:** `.env.production` must be present and contain:
   - `BINANCE_API_KEY` & `BINANCE_API_SECRET` (Read-only API access is sufficient and recommended)
   - `EFLOUD_TELEGRAM_TOKEN` & `EFLOUD_TELEGRAM_CHAT_ID` (For alert notifications)
3. **Timezone:** Ensure the system timezone on the host is UTC (verify using `timedatectl`).

---

## 2. Deploying the Watcher Daemon

The `routines-watcher` container runs the fast-tier monitoring tasks (R1, R2, R3, M3, D1) on their defined cadences (1m - 5m) in a persistent loop.

### Start the Watcher Service:
Execute on the Hetzner host:
```bash
cd /opt/efloud-bot
docker compose -f docker-compose.prod.yml up -d routines-watcher
```

### Verify Status and Logs:
Check that the service is running and not in a crash loop:
```bash
docker compose -f docker-compose.prod.yml ps routines-watcher
docker compose -f docker-compose.prod.yml logs -f routines-watcher
```

Verify that the heartbeat snapshot is generated:
```bash
docker compose -f docker-compose.prod.yml exec routines-watcher cat state/routines_watcher_heartbeat.json
```

---

## 3. Scheduling Cron Routines

Slow-tier routines (such as the daily `equity_report`) are executed on-demand using the one-shot `routines-scheduled` service.

### Manual Smoke Test (Before Automation)

Run the daily equity report manually inside the scheduled container profile to confirm it works:
```bash
cd /opt/efloud-bot
docker compose -f docker-compose.prod.yml --profile routines-scheduled run --rm -e ROUTINE=equity_report routines-scheduled
```

**Expected outcome:**
* The command outputs the report summary and exits `0`.
* A markdown report is generated at `/app/reports/equity_report.md` (shared volume).

---

### Installing the Crontab Entries

Edit the `efloud` user's crontab on the host:
```bash
crontab -e
```

Add the following daily job definition (run daily at 08:00 UTC):
```cron
# efloud-bot Scheduled Routines
0 8 * * * cd /opt/efloud-bot && (docker compose -f docker-compose.prod.yml --profile routines-scheduled run --rm -e ROUTINE=equity_report routines-scheduled >> /var/log/efloud-routines-scheduled.log 2>&1 || (TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "[$TS] ROUTINE equity_report FAILED" >> /var/log/efloud-cron-errors.log; source /opt/efloud-bot/.env.production; curl -s "https://api.telegram.org/bot${EFLOUD_TELEGRAM_TOKEN}/sendMessage" --data-urlencode "chat_id=${EFLOUD_TELEGRAM_CHAT_ID}" --data-urlencode "text=⚠️ scheduled routine equity_report FAILED at $TS — check /var/log/efloud-cron-errors.log on Hetzner" >> /var/log/efloud-cron-errors.log 2>&1))
```

> [!NOTE]
> **Future Routines (Phase 3 & 4):**
> When future analytics/strategy routines are implemented, they can be scheduled similarly by defining additional cron entries:
> * `symbol_perf` (A3) / `confluence_calib` (A4): weekly (e.g. `0 9 * * 1`)
> * `backtest_revalidate` (S1): bi-weekly (e.g. `0 10 */14 * *`)

---

## 4. Verification and Troubleshooting

### Inspecting Log Files
* **Watcher Loop Logs:** `docker compose logs routines-watcher`
* **Cron Execution Logs:** `/var/log/efloud-routines-scheduled.log`
* **Cron Error Logs:** `/var/log/efloud-cron-errors.log`

### Disabling in an Emergency
To stop scheduled cron reports, open the crontab editor (`crontab -e`) and comment out (`#`) or remove the daily job lines. To stop the watcher daemon, run:
```bash
docker compose -f docker-compose.prod.yml stop routines-watcher
```

---

## 5. proof_export (T-012 / P-003 W1) — Public Proof Snapshot

Günlük şifresiz ama **whitelist-only** snapshot üretir (`state/proof_snapshot.json`):
trade_count, win_rate_pct, profit_factor, max_dd_pct + normalize edilmiş günlük equity
eğrisi. Mutlak bakiye / pozisyon / sembol / PnL değeri İÇERMEZ (G-P3-1; runtime guard +
test ile zorlanır). Yan etki: her koşuda bir healthz örneği `state/uptime_samples.jsonl`'a
eklenir (bkz. `docs/runbooks/healthz-contract.md` §3).

### Kurulum (operatör adımı — bir kez)

```bash
# Baseline referansı (operatör kararı 2026-06-11: gerçek %DD için başlangıç bakiyesi).
# Bu dosya state/'te kalır, snapshot'a ASLA girmez; yayınlanan eğri 1.0'dan başlar.
docker compose -f docker-compose.prod.yml exec efloud-bot sh -c \
  'cat > /app/state/proof_baseline.json <<EOF
{"baseline_equity_usdt": <BAŞLANGIÇ_BAKİYESİ>, "since": "YYYY-MM-DD"}
EOF'
```

### Cron (günlük 1× — G-P3-1 cadence sınırı: daha sık KOŞMA; §3'teki pattern ile)

```cron
30 0 * * * cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml --profile routines-scheduled run --rm -e ROUTINE=proof_export routines-scheduled >> /var/log/efloud-routines-scheduled.log 2>&1
```

### Yayın (G-P3-B4 — operatör onayı olmadan YAYINLAMA)

Snapshot'ın u2algo-site'a kopyalanması T-014 kapsamında ve **operatör onaylıdır**;
bot API'si public'e açılmaz, yayın statik dosya kopyasıdır. Baseline eksikse routine
snapshot üretmez ve alerter'a uyarı düşer (`proof_export_baseline_missing`).

> ⚠️ **De-normalizasyon uyarısı:** Normalize eğri matematiksel olarak baseline'ı
> sızdırmaz — AMA herhangi bir mutlak PnL değeri başka kanaldan ifşa edilirse
> (örn. sosyal postta "bugün +$50"), o günün eğri deltasından baseline çözülür ve
> TÜM geçmiş de-normalize olur. İçerik pipeline'ında (P-002 M6/M13) mutlak $ PnL
> paylaşımı zaten compliance-yasak — bu kuralın proof sayfası yaşadıkça istisnası yok.
