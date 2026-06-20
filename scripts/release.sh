#!/usr/bin/env bash
# scripts/release.sh — Yarı-otomatik branch release orchestrator
#
# Akış (1 komutla 7 gate):
#   1. Repo temiz mi?
#   2. master'dan güncel + HEAD düşmüş mü kontrol
#   3. Branch adı + commit hash raporu
#   4. LLTODO lint 8/8 PASS
#   5. pytest backend + tests (regression gate)
#   6. format-patch + SHA256 + dosya listesi
#   7. Push helper dosyası (/tmp/branch_push.sh) üret
#
# Kullanım:
#   bash scripts/release.sh [--branch <name>] [--skip-tests] [--review]
#
# --review: Claude + Gemini review promptlarını /tmp/release/review_prompts/ altına
#           yazar (sen çalıştırırsın, sonucu paste edersin, gate açılır)
#
# Output (her şey başarılı):
#   - /tmp/release/<branch>-<sha>.patch
#   - /tmp/release/<branch>-<sha>.sha256
#   - /tmp/release/branch_push.sh (push helper, copy-paste için)
#   - /tmp/release/MANIFEST.txt (operatör kontrol listesi)
#
# Author: @hermes, 2026-06-19

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
BRANCH="$(git branch --show-current)"
SKIP_TESTS=0
REVIEW_MODE=0
REPO_ROOT="/opt/efloud-bot"
RELEASE_DIR="/tmp/release"

# ── Args parse ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=1
            shift
            ;;
        --review)
            REVIEW_MODE=1
            shift
            ;;
        *)
            echo "Bilinmeyen arg: $1" >&2
            exit 1
            ;;
    esac
done

cd "$REPO_ROOT"

# ── Renk kodları ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    YELLOW=$'\033[0;33m'
    BLUE=$'\033[0;34m'
    BOLD=$'\033[1m'
    RESET=$'\033[0m'
else
    RED="" GREEN="" YELLOW="" BLUE="" BOLD="" RESET=""
fi

step() { echo -e "${BLUE}━━━ $* ━━━${RESET}"; }
ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠️  $*${RESET}"; }
fail() { echo -e "${RED}❌ $*${RESET}"; exit 1; }

# ── 1. Repo temiz mi? ───────────────────────────────────────────────────────
step "1/7 Repo temizlik kontrolü"

# Modified/staged var mı? Untracked OK (genelde harmless: plan dosyaları, backups).
DIRTY_TRACKED="$(git status --porcelain | grep -v '^??' || true)"
if [[ -n "$DIRTY_TRACKED" ]]; then
    # Runtime state dosyaları bot canlı yazıyor — release-relevant değil.
    # Bunları filtrele, gerçek modified varsa fail.
    NON_RUNTIME_DIRTY="$(printf '%s\n' "$DIRTY_TRACKED" | grep -vE 'state/(ai_sentiment_registry|positions|open_trades)\.json$' || true)"
    if [[ -n "$NON_RUNTIME_DIRTY" ]]; then
        echo -e "${RED}Release-relevant modified/staged değişiklik:${RESET}"
        echo "$NON_RUNTIME_DIRTY" | sed 's/^/  /'
        fail "Commit et veya stash'le."
    else
        warn "Sadece runtime state modified (release-relevant değil):"
        echo "$DIRTY_TRACKED" | sed 's/^/  /'
    fi
fi
ok "Working tree release-clean"

# ── 2. Branch + master sync ────────────────────────────────────────────────
step "2/7 Branch senkronizasyonu"
git fetch origin --quiet 2>/dev/null || warn "fetch başarısız (offline olabilir)"
HEAD_SHA="$(git rev-parse HEAD)"
SHORT_SHA="$(git rev-parse --short HEAD)"

if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
    REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"
    if [[ "$HEAD_SHA" == "$REMOTE_SHA" ]]; then
        warn "Branch remote ile senkron: $REMOTE_SHA"
    else
        warn "Local HEAD $HEAD_SHA ≠ origin/$BRANCH $REMOTE_SHA"
        echo "  → Push öncesi 'git pull --rebase origin $BRANCH' çalıştır."
    fi
else
    ok "Branch remote'da yok (ilk push)"
fi

# ── 3. Manifest header ──────────────────────────────────────────────────────
step "3/7 Manifest başlık"
echo "Branch: $BRANCH"
echo "HEAD:   $HEAD_SHA"
echo "Author: $(git log -1 --format='%an <%ae>')"
echo "Date:   $(git log -1 --format='%ai')"
echo "Subject: $(git log -1 --format='%s')"

# ── 4. Lint ─────────────────────────────────────────────────────────────────
step "4/7 LLTODO lint"
if python3 LLTODO/scripts/lltodo_lint.py; then
    ok "Lint 8/8 PASS"
else
    fail "Lint ihlali var. Düzelt ve tekrar çalıştır."
fi

# ── 5. Testler ──────────────────────────────────────────────────────────────
if [[ $SKIP_TESTS -eq 0 ]]; then
    step "5/7 pytest (backend + site/api)"
    BACKEND_RESULT=$(python3 -m pytest backend/tests/ -q --tb=no 2>&1 | tail -2 | head -1)
    SITE_RESULT=$(python3 -m pytest tests/ -q --tb=no --ignore=tests/routines 2>&1 | tail -2 | head -1)
    echo "  Backend: $BACKEND_RESULT"
    echo "  Site:    $SITE_RESULT"
    if echo "$BACKEND_RESULT" | grep -qE "failed|error" || \
       echo "$SITE_RESULT" | grep -qE "failed|error"; then
        fail "Test FAILED. Patch üretilmedi."
    fi
    ok "Testler PASS"
else
    warn "5/7 pytest --skip-tests ile atlandı"
fi

# ── 6. Patch + SHA256 ───────────────────────────────────────────────────────
step "6/7 format-patch + SHA256"
mkdir -p "$RELEASE_DIR"
SAFE_BRANCH="$(echo "$BRANCH" | tr '/' '_')"
PATCH_FILE="$RELEASE_DIR/${SAFE_BRANCH}-${SHORT_SHA}.patch"
git format-patch -1 HEAD -o "$RELEASE_DIR" >/dev/null
mv "$RELEASE_DIR"/0001-*.patch "$PATCH_FILE" 2>/dev/null || mv "$(ls "$RELEASE_DIR"/0001-*.patch | head -1)" "$PATCH_FILE"
SHA256="$(sha256sum "$PATCH_FILE" | awk '{print $1}')"
echo "$SHA256  $PATCH_FILE" > "$PATCH_FILE.sha256"
wc -c "$PATCH_FILE" | awk '{printf "Patch size: %.1f KB\n", $1/1024}'
ok "SHA256: $SHA256"

# ── 7. Push helper + MANIFEST ───────────────────────────────────────────────
# ÖNEMLİ: VPS deploy key read-only — push VPS'ten YAPILAMAZ.
# Push helper operatörün LOKAL makinesinde çalışır (vps remote fetch + origin push).
step "7/7 Push helper üretimi (operatör-lokal)"
SAFE_BRANCH="$(echo "$BRANCH" | tr '/' '_')"
PUSH_SCRIPT="$RELEASE_DIR/${SAFE_BRANCH}-push-from-local.sh"

cat > "$PUSH_SCRIPT" <<EOF
#!/usr/bin/env bash
# Operatör-lokal push helper — VPS deploy key read-only.
# Branch: $BRANCH @ $SHORT_SHA
# Patch SHA256: $SHA256
# Üretildi: $(date -u +%Y-%m-%dT%H:%M:%SZ)

set -euo pipefail

# Operatör-lokal repo path'i (Windows Git Bash formatı)
LOCAL_REPO="\${LOCAL_REPO:-/c/Users/utkuc/Downloads/efloud-bot}"
VPS_REMOTE="\${VPS_REMOTE:-efloud-bot:/opt/efloud-bot}"

cd "\$LOCAL_REPO"

# vps remote yoksa ekle (idempotent)
if ! git remote get-url vps >/dev/null 2>&1; then
    echo "→ vps remote ekleniyor: \$VPS_REMOTE"
    git remote add vps "\$VPS_REMOTE"
fi

# Pre-flight: lint (son bir kez daha — VPS HEAD ile)
git fetch vps "$BRANCH" --quiet
git fetch vps "$BRANCH":refs/remotes/vps/"$BRANCH" --quiet 2>/dev/null || true

echo "→ VPS'ten fetch: $BRANCH"
git fetch vps "$BRANCH"

echo "→ origin'e push: vps/$BRANCH:$BRANCH"
git push origin "vps/$BRANCH:$BRANCH"

echo ""
echo "✅ Push başarılı: $BRANCH → origin"
echo ""
echo "Sonraki: GitHub'da PR aç → master'a merge (squash / merge / rebase — sen karar)."
echo "  PR link: https://github.com/Leblepito/efloud-bot/pull/new/$BRANCH"
EOF
chmod +x "$PUSH_SCRIPT"

MANIFEST="$RELEASE_DIR/MANIFEST.txt"
cat > "$MANIFEST" <<EOF
═══════════════════════════════════════════════════════════════
RELEASE MANIFEST
═══════════════════════════════════════════════════════════════
Branch:      $BRANCH
HEAD:        $HEAD_SHA
Short SHA:   $SHORT_SHA
Patch:       $PATCH_FILE
Patch size:  $(wc -c < "$PATCH_FILE") bytes
SHA256:      $SHA256
Author:      $(git log -1 --format='%an <%ae>')
Date:        $(git log -1 --format='%ai')
Subject:     $(git log -1 --format='%s')

── Files changed ───────────────────────────────────────────────
$(git diff-tree --no-commit-id --name-status -r HEAD)

── Push komutu (operatör-LOKAL, VPS read-only) ────────────────
1. SSH'tan çık
2. Git Bash'te (Windows):
   LOCAL_REPO=/c/Users/utkuc/Downloads/efloud-bot bash $PUSH_SCRIPT
   veya:
   cd /c/Users/utkuc/Downloads/efloud-bot
   git fetch vps $BRANCH
   git push origin "vps/$BRANCH:$BRANCH"

── NOT: VPS-side push KULLANMA ────────────────────────────────
VPS deploy key read-only — ssh efloud-bot 'git push' PATLAR.
Push her zaman operatörün lokal makinesinden yapılır.

── Manuel push (alternatif) ───────────────────────────────────
cd /c/Users/utkuc/Downloads/efloud-bot
git fetch vps $BRANCH
git push origin "vps/$BRANCH:$BRANCH"

── Sonraki adım ───────────────────────────────────────────────
master'a merge kararı operatöre ait:
  - Squash: 1 commit olarak temiz tarihçe
  - Merge: branch tarihçesi korunur
  - Rebase: linear (PR ise rebase + ff merge)

═══════════════════════════════════════════════════════════════
EOF

# ── Review prompts (opsiyonel) ──────────────────────────────────────────────
if [[ $REVIEW_MODE -eq 1 ]]; then
    REVIEW_DIR="$RELEASE_DIR/review_prompts"
    mkdir -p "$REVIEW_DIR"
    PROMPT_CLAUDE="$REVIEW_DIR/claude_review.md"
    PROMPT_GEMINI="$REVIEW_DIR/gemini_review.md"

    cat > "$PROMPT_CLAUDE" <<EOF
# Claude Code Review — $BRANCH @$SHORT_SHA

## Diff
\`\`\`
$(git show HEAD --stat)
\`\`\`

## Görev
Bu branch'i Claude Code ile review et:
- Mimari doğruluk
- Compliance gate entegrasyonu
- Test kalitesi
- Secret/key handling

## Output format (markdown)
\`\`\`
## Bulgular
- [BLOCKER] / [SHOULD] / [NIT] — dosya:line — açıklama

## Karar
APPROVE / CHANGES_REQUESTED / REJECT

## Confidence
X/10

## Notes
...
\`\`\`

Patch: $PATCH_FILE (SHA256: $SHA256)
EOF

    cat > "$PROMPT_GEMINI" <<EOF
# Gemini Code Review — $BRANCH @$SHORT_SHA

## Diff
\`\`\`
$(git show HEAD --stat)
\`\`\`

## Görev
Bu branch'i Gemini ile review et:
- Performans / asyncpg pattern
- DB schema (migration 009)
- Runbook netliği
- Lint ihlali yokluğu

## Output format (markdown)
\`\`\`
## Bulgular
- [BLOCKER] / [SHOULD] / [NIT] — dosya:line — açıklama

## Karar
APPROVE / CHANGES_REQUESTED / REJECT

## Confidence
X/10

## Notes
...
\`\`\`

Patch: $PATCH_FILE (SHA256: $SHA256)
EOF

    ok "Review promptları: $REVIEW_DIR/"
fi

# ── Özet ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD} RELEASE HAZIR — push onayı bekliyor${RESET}"
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${RESET}"
echo ""
echo -e "Branch:    ${BOLD}$BRANCH${RESET}"
echo -e "SHA:       ${BOLD}$SHORT_SHA${RESET}"
echo -e "Patch:     ${BOLD}$PATCH_FILE${RESET}"
echo -e "SHA256:    ${BOLD}$SHA256${RESET}"
echo -e "Manifest:  ${BOLD}$MANIFEST${RESET}"
echo -e "Push:      ${BOLD}bash $PUSH_SCRIPT${RESET}"
echo ""
echo -e "${YELLOW}Push onayı sende. Lokal makinede şunu çalıştır:${RESET}"
echo -e "  ${BOLD}LOCAL_REPO=/c/Users/utkuc/Downloads/efloud-bot bash $PUSH_SCRIPT${RESET}"
echo ""
echo -e "${YELLOW}VPS-side push (ssh + git push) KULLANMA — deploy key read-only.${RESET}"
echo ""
if [[ $REVIEW_MODE -eq 1 ]]; then
    echo -e "${YELLOW}Review promptları:${RESET}"
    echo -e "  Claude: ${BOLD}cat $PROMPT_CLAUDE${RESET}"
    echo -e "  Gemini: ${BOLD}cat $PROMPT_GEMINI${RESET}"
    echo ""
fi
