#!/usr/bin/env bash
# T-020 (P-003 W-R): efloud-bot state volume backup — read-only snapshot,
# encrypt, off-VPS upload, retention prune. Runs on the VPS host via cron.
#
# SAFETY INVARIANTS (UR-003 / G-P3-6):
#   * Volumes are mounted READ-ONLY (:ro) into a throwaway container — this
#     script can never write to live state.
#   * trade_journal.jsonl is append-only; a snapshot taken mid-write may carry
#     a torn last line. This is tolerated by design (see runbook).
#   * The encryption key lives at BACKUP_KEY_FILE on the VPS *and* in the
#     operator's password manager (escrow — VPS total-loss must not take the
#     key with the data). The key NEVER enters this repo.
#
# Usage: backup_state.sh [--dry-run]
# Config: /etc/efloud-backup.env (optional) or environment. See runbook:
#   docs/runbooks/backup-restore.md

set -euo pipefail

CONFIG_FILE="${EFLOUD_BACKUP_CONFIG:-/etc/efloud-backup.env}"
if [ -f "$CONFIG_FILE" ]; then
  cfg_perms="$(stat -c %a "$CONFIG_FILE")"
  case "$cfg_perms" in
    600|400) ;;
    *) echo "FATAL: $CONFIG_FILE holds the Telegram token — chmod 600 required (got $cfg_perms)" >&2; exit 1;;
  esac
  . "$CONFIG_FILE"
fi

STAGING_DIR="${BACKUP_STAGING_DIR:-/var/backups/efloud}"
KEY_FILE="${BACKUP_KEY_FILE:-/root/.efloud_backup.key}"
# rclone remote (e.g. "storagebox:efloud-backups"). Empty = local-only + WARN.
REMOTE="${BACKUP_REMOTE:-}"
RETENTION_LOCAL_DAYS="${BACKUP_RETENTION_LOCAL_DAYS:-7}"
RETENTION_REMOTE_DAYS="${BACKUP_RETENTION_REMOTE_DAYS:-30}"
# Volumes are matched by suffix against `docker volume ls` so the compose
# project prefix (e.g. efloud-bot_efloud_state) resolves automatically.
VOLUME_SUFFIXES="${BACKUP_VOLUMES:-efloud_state efloud_state_1k efloud_state_aggressive}"
MIN_FREE_MB="${BACKUP_MIN_FREE_MB:-1024}"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

TS="$(date -u +%Y%m%dT%H%M%SZ)"
STATUS_FILE="$STAGING_DIR/last_backup_status.json"

alert() {
  # Failure alert via Telegram (reuses the alerter's env vars). Best-effort.
  local msg="$1"
  echo "ALERT: $msg" >&2
  if [ -n "${EFLOUD_TELEGRAM_TOKEN:-}" ] && [ -n "${EFLOUD_TELEGRAM_CHAT_ID:-}" ]; then
    curl -sS -m 10 "https://api.telegram.org/bot${EFLOUD_TELEGRAM_TOKEN}/sendMessage" \
      -d chat_id="${EFLOUD_TELEGRAM_CHAT_ID}" \
      --data-urlencode text="🔴 efloud backup FAILED: ${msg}" >/dev/null || true
  fi
}

fail() {
  printf '{"ts":"%s","ok":false,"error":"%s"}\n' "$TS" "$1" > "$STATUS_FILE" 2>/dev/null || true
  alert "$1"
  exit 1
}

# ── Preflight ────────────────────────────────────────────────────────────
command -v docker >/dev/null || fail "docker not found"
command -v openssl >/dev/null || fail "openssl not found"
[ -f "$KEY_FILE" ] || fail "key file missing: $KEY_FILE (see runbook: key setup + ESCROW)"
key_perms="$(stat -c %a "$KEY_FILE")"
case "$key_perms" in 600|400) ;; *) fail "key file must be chmod 600/400 (got $key_perms): $KEY_FILE";; esac
mkdir -p "$STAGING_DIR"

# Disk hygiene: refuse to run if staging is low on space (a full disk would
# indirectly hit the live journal writer — blast-radius guard).
free_mb=$(df -Pm "$STAGING_DIR" | awk 'NR==2 {print $4}')
[ "$free_mb" -ge "$MIN_FREE_MB" ] || fail "staging low on disk: ${free_mb}MB < ${MIN_FREE_MB}MB"

# ── Resolve volumes ─────────────────────────────────────────────────────
resolved=()
for suffix in $VOLUME_SUFFIXES; do
  match=$(docker volume ls -q | grep -E "(^|_)${suffix}$" || true)
  if [ -z "$match" ]; then
    fail "volume not found for suffix: $suffix"
  fi
  if [ "$(echo "$match" | wc -l)" -ne 1 ]; then
    fail "ambiguous volumes for suffix $suffix: $(echo "$match" | tr '\n' ' ')"
  fi
  resolved+=("$match")
done

echo "Backing up volumes: ${resolved[*]}"
[ "$DRY_RUN" = "1" ] && { echo "(dry-run — stopping before snapshot)"; exit 0; }

# ── Snapshot + encrypt ──────────────────────────────────────────────────
manifest="$STAGING_DIR/efloud_backup_${TS}.manifest"
: > "$manifest"
for vol in "${resolved[@]}"; do
  plain="$STAGING_DIR/${vol}_${TS}.tar.gz"
  enc="${plain}.enc"
  # READ-ONLY mount — the container cannot touch live state. Plaintext tar is
  # removed on EVERY exit path (risk-ops: no unencrypted state lingers on disk).
  docker run --rm \
    -v "${vol}:/src:ro" \
    -v "${STAGING_DIR}:/dst" \
    alpine:3 tar czf "/dst/$(basename "$plain")" -C /src . \
    || { rm -f "$plain"; fail "tar failed for $vol"; }
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
    -in "$plain" -out "$enc" -pass "file:${KEY_FILE}" \
    || { rm -f "$plain" "$enc"; fail "encrypt failed for $vol"; }
  rm -f "$plain"
  # Manifest records BASENAMES so `sha256sum -c` works from any directory.
  (cd "$STAGING_DIR" && sha256sum "$(basename "$enc")") >> "$manifest"
done

# ── Upload ──────────────────────────────────────────────────────────────
if [ -n "$REMOTE" ]; then
  command -v rclone >/dev/null || fail "rclone not found but BACKUP_REMOTE set"
  # Flat copy of EVERYTHING local that the remote doesn't have yet — this
  # backfills days when upload failed before local retention ages them out
  # (risk-ops MED: TS-only upload left permanent off-VPS gaps).
  rclone copy "$STAGING_DIR" "$REMOTE" \
    --include "*.tar.gz.enc" --include "*.manifest" \
    || fail "rclone upload failed"
  # Remote retention prune — scoped to our artifact patterns only; REMOTE
  # must be a DEDICATED path (runbook config step, ZORUNLU).
  rclone delete "$REMOTE" --min-age "${RETENTION_REMOTE_DAYS}d" \
    --include "*.tar.gz.enc" --include "*.manifest" 2>/dev/null \
    || alert "remote retention prune failed (backup itself OK)"
else
  echo "WARN: BACKUP_REMOTE not set — backup is LOCAL-ONLY (VPS loss loses it)." >&2
fi

# ── Local retention prune (plaintext *.tar.gz included as defense-in-depth) ──
find "$STAGING_DIR" -name "*.tar.gz.enc" -mtime "+${RETENTION_LOCAL_DAYS}" -delete
find "$STAGING_DIR" -name "*.tar.gz" -mtime "+${RETENTION_LOCAL_DAYS}" -delete
find "$STAGING_DIR" -name "*.manifest" -mtime "+${RETENTION_LOCAL_DAYS}" -delete

printf '{"ts":"%s","ok":true,"volumes":"%s","remote":"%s"}\n' \
  "$TS" "${resolved[*]}" "${REMOTE:-local-only}" > "$STATUS_FILE"
echo "OK: backup ${TS} complete (${resolved[*]})"
