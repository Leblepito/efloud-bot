#!/usr/bin/env bash
# T-020 (P-003 W-R): restore an encrypted state backup into a volume.
#
# DEFAULT MODE = DRILL: restores into a FRESH scratch volume
# (efloud_restore_drill_<ts>) and verifies content. This is what the
# quarterly drill (G-P3-6) runs.
#
# RESTORE-TO-LIVE IS OPERATOR-GATED (risk-ops review 2026-06-11):
#   * refuses any PRE-EXISTING target volume in non-forced mode (docker
#     volume create is a silent no-op on existing volumes → tar would MERGE)
#   * refuses while ANY container has the target volume mounted — not just
#     efloud-bot: alerter/overseer/routines mount efloud_state RW 24/7
#   * forced live mode CLEARS the target before extract (stale sqlite -wal/
#     -shm siblings corrupt a merged restore) — mandatory pre-restore copy
#     is in the runbook
#
# Usage:
#   restore_state.sh <backup.tar.gz.enc> [target-volume]
#   (no target → fresh scratch drill volume)

set -euo pipefail

KEY_FILE="${BACKUP_KEY_FILE:-/root/.efloud_backup.key}"
ENC_FILE="${1:?usage: restore_state.sh <backup.tar.gz.enc> [target-volume]}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${2:-efloud_restore_drill_${TS}}"
FORCED=0

[ -f "$ENC_FILE" ] || { echo "no such file: $ENC_FILE" >&2; exit 1; }
[ -f "$KEY_FILE" ] || { echo "key file missing: $KEY_FILE (escrow copy is in the operator password manager)" >&2; exit 1; }
key_perms="$(stat -c %a "$KEY_FILE")"
case "$key_perms" in 600|400) ;; *) echo "key file must be chmod 600/400 (got $key_perms): $KEY_FILE" >&2; exit 1;; esac

# ── Live-volume guard (lock 1: name pattern + sentinel) ─────────────────
if echo "$TARGET" | grep -qE "(^|_)efloud_state(_1k|_aggressive)?$"; then
  if [ "${EFLOUD_RESTORE_FORCE_LIVE:-}" != "YES_I_UNDERSTAND" ]; then
    echo "REFUSED: '$TARGET' matches a LIVE volume. Restore-to-live is operator-gated:" >&2
    echo "  1) stop the FULL stack (docker compose -f docker-compose.prod.yml stop)" >&2
    echo "     — alerter/overseer/routines also mount this volume RW" >&2
    echo "  2) take the mandatory pre-restore copy (runbook §4)" >&2
    echo "  3) re-run with EFLOUD_RESTORE_FORCE_LIVE=YES_I_UNDERSTAND" >&2
    exit 2
  fi
  FORCED=1
fi

# ── Mount guard (lock 2: NOTHING may have the target mounted) ───────────
# Generalizes beyond efloud-bot: catches alerter/overseer/routines or any
# future container. Applies to every restore target, drill or live.
mounted="$(docker ps -q --filter "volume=${TARGET}" || true)"
if [ -n "$mounted" ]; then
  echo "REFUSED: volume '$TARGET' is mounted by running container(s):" >&2
  docker ps --filter "volume=${TARGET}" --format '  {{.Names}} ({{.ID}})' >&2
  echo "Stop the full stack first (docker compose -f docker-compose.prod.yml stop)." >&2
  exit 2
fi

# ── Pre-existing volume guard (lock 3) ──────────────────────────────────
exists=0
docker volume ls -q | grep -Fxq -- "$TARGET" && exists=1
if [ "$exists" = "1" ] && [ "$FORCED" != "1" ]; then
  echo "REFUSED: volume '$TARGET' already exists — docker volume create would" >&2
  echo "silently no-op and tar would MERGE into existing content. Use a fresh" >&2
  echo "scratch name (default), or for live restore follow runbook §4." >&2
  exit 2
fi

# ── Manifest verification (AES-CBC is unauthenticated — verify sha256) ──
enc_dir="$(cd "$(dirname "$ENC_FILE")" && pwd)"
enc_base="$(basename "$ENC_FILE")"
manifest_line=""
for m in "$enc_dir"/efloud_backup_*.manifest; do
  [ -f "$m" ] || continue
  # Match both GNU text-mode ("hash  name") and binary-mode ("hash *name")
  manifest_line="$(grep -F -e " $enc_base" -e " *$enc_base" "$m" || true)"
  [ -n "$manifest_line" ] && break
done
if [ -n "$manifest_line" ]; then
  (cd "$enc_dir" && echo "$manifest_line" | sha256sum -c -) \
    || { echo "REFUSED: sha256 mismatch for $enc_base — backup corrupt or tampered." >&2; exit 1; }
  echo "manifest sha256: OK"
else
  echo "WARN: no manifest found next to $enc_base — integrity rests on gzip CRC only." >&2
fi

# ── Decrypt ─────────────────────────────────────────────────────────────
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
plain="$work/restore.tar.gz"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in "$ENC_FILE" -out "$plain" -pass "file:${KEY_FILE}"

# ── Extract ─────────────────────────────────────────────────────────────
docker volume create "$TARGET" >/dev/null
if [ "$FORCED" = "1" ] && [ "$exists" = "1" ]; then
  echo "!!! LIVE RESTORE: clearing '$TARGET' before extract (pre-restore copy is on you — runbook §4) !!!"
  docker run --rm -v "${TARGET}:/dst" alpine:3 \
    sh -c 'rm -rf /dst/* /dst/.[!.]* /dst/..?* 2>/dev/null || true'
fi
docker run --rm \
  -v "${TARGET}:/dst" \
  -v "${work}:/work:ro" \
  alpine:3 tar xzf /work/restore.tar.gz -C /dst

# ── Verify ──────────────────────────────────────────────────────────────
echo "── Restored '$enc_base' → volume '$TARGET'. Contents:"
docker run --rm -v "${TARGET}:/dst:ro" alpine:3 sh -c \
  'find /dst -maxdepth 2 -type f | head -40 && echo "── total files:" && find /dst -type f | wc -l'

cat <<EOF

Drill checklist (record the result in the T-020 card / runbook):
  [ ] positions.json / breaker.json present and parse as JSON
  [ ] trade_journal.jsonl present; tail -1 may be a torn line (tolerated —
      append-only journal snapshotted mid-write)
  [ ] transient *.json.tmp files may appear (atomic-write leftovers; harmless)
  [ ] file count plausible vs live volume
Cleanup after drill: docker volume rm $TARGET
EOF
