# Daily Report Cron — One-Time Hetzner Setup

This runbook installs the 08:00 UTC daily-report cron entry on Hetzner.

## Prerequisites

- Step 5 deployed: `docker-compose.prod.yml` has the `daily-report` service.
- `.env.production` has SMTP credentials:
  - `EFLOUD_SMTP_HOST` (default `smtp.gmail.com`)
  - `EFLOUD_SMTP_PORT` (default `587`)
  - `EFLOUD_SMTP_USERNAME` (e.g. `bot@yourdomain.com`)
  - `EFLOUD_SMTP_PASSWORD` (Gmail app password — see below)
  - `EFLOUD_SMTP_FROM` (default = USERNAME)
  - `EFLOUD_SMTP_TO` (operator's email)
- `EFLOUD_TELEGRAM_TOKEN` and `EFLOUD_TELEGRAM_CHAT_ID` already in env (Step 4).
- Hetzner system timezone is UTC (verify with `timedatectl`). If not UTC, the cron's `0 8 * * *` will fire in local time, NOT 08:00 UTC.

## Gmail app password setup (one-time)

If using Gmail SMTP:
1. Sign in to the Gmail account that will SEND the report.
2. Visit https://myaccount.google.com/apppasswords (requires 2FA enabled).
3. Generate an app password named `efloud-bot daily-report`.
4. Copy the 16-character password (without spaces) into `.env.production` as `EFLOUD_SMTP_PASSWORD`.
5. Set `EFLOUD_SMTP_USERNAME` to the Gmail address.

## Manual smoke test (BEFORE adding cron)

Before automating, verify the report sends correctly when invoked manually:

```bash
ssh efloud@<VPS_IP>
cd /opt/efloud-bot
docker compose -f docker-compose.prod.yml --profile scheduled run --rm daily-report
```

Expected: command exits 0, you receive an email at `EFLOUD_SMTP_TO` within ~30s.
If exit code is non-zero, check the container's stderr for the failure reason
(SMTP auth, DB connection, missing env var, etc.) before proceeding.

## Install crontab entry

Edit the `efloud` user's crontab:

```bash
ssh efloud@<VPS_IP>
crontab -e
```

Add this line (single line in the file — no line breaks):

```
0 8 * * * cd /opt/efloud-bot && (docker compose -f docker-compose.prod.yml --profile scheduled run --rm daily-report >> /var/log/efloud-daily-report.log 2>&1 || (TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "[$TS] daily-report FAILED" >> /var/log/efloud-cron-errors.log; source /opt/efloud-bot/.env.production; curl -s "https://api.telegram.org/bot${EFLOUD_TELEGRAM_TOKEN}/sendMessage" --data-urlencode "chat_id=${EFLOUD_TELEGRAM_CHAT_ID}" --data-urlencode "text=⚠️ daily-report cron FAILED at $TS — check /var/log/efloud-cron-errors.log on Hetzner" >> /var/log/efloud-cron-errors.log 2>&1))
```

What this does:
1. At 08:00 UTC daily, run the daily-report container.
2. Log stdout+stderr to `/var/log/efloud-daily-report.log`.
3. If exit code is non-zero, append to `/var/log/efloud-cron-errors.log` AND ping Telegram with a WARNING message.

**Note on env file values:** if any value in `.env.production` contains shell-special characters (`$`, backticks, `"`), the `source` step in the failure branch may misparse. Quote such values: `EFLOUD_SMTP_PASSWORD="abc$def"`.

## Verify cron is active

```bash
crontab -l | grep daily-report
```

You should see the line above. The next 08:00 UTC run will fire automatically.

## Disable cron in an emergency

```bash
crontab -e
```

Delete the daily-report line (or comment it out with `#` at start). Save and exit.

## Logs to inspect after first run

- `/var/log/efloud-daily-report.log` — stdout/stderr of the most recent run
- `/var/log/efloud-cron-errors.log` — failure log; should be empty in healthy state
- Recipient inbox at `EFLOUD_SMTP_TO` — actual email

## Troubleshooting

**Email never arrives, no error in logs:**
- Check Gmail's "Sent" folder on the sending account
- Check recipient's spam folder
- Verify `EFLOUD_SMTP_TO` is correct (typo)

**SMTPAuthenticationError in log:**
- Re-generate Gmail app password (the existing one may have been revoked)
- Verify 2FA is still enabled on the sending account

**"DB pool init failed" in log:**
- Check Supabase pooler is reachable: `curl -s aws-1-eu-central-1.pooler.supabase.com:6543` (should connect)
- Check `DATABASE_URL` in `.env.production` is correct
