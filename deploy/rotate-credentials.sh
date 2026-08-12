#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# rotate-credentials.sh — VPS üzerinde dashboard/panel kimlik bilgisi rotasyonu
#
# Ne yapar:
#   1. Güçlü yeni DASHBOARD_PASSWORD üretir (40 char alfanumerik) ve TÜM bot
#      env dosyalarında (.env.production, .env.production.long,
#      .env.production.scalp) senkron günceller — birleşik panel üç bota da
#      TEK şifreyle login olduğu için şifreler AYNI kalmak zorundadır.
#   2. Her env dosyası için AYRI yeni SESSION_SECRET üretir (bot oturumları
#      birbirinden izole kalır; birinin sızması diğerini etkilemez).
#   3. İstenirse DASHBOARD_USERNAME set eder (panel Basic auth kullanıcı adı).
#   4. Değişen env dosyalarını yedekler (chmod 600) ve konteynerleri
#      YENİDEN OLUŞTURUR (docker restart env_file'ı yeniden OKUMAZ;
#      `up -d --force-recreate` gerekir).
#
# Kullanım (VPS'te repo kökünde):
#   ./deploy/rotate-credentials.sh                      # şifre+secret rotasyonu
#   ./deploy/rotate-credentials.sh --username efloud    # + kullanıcı adı set et
#   ./deploy/rotate-credentials.sh --password 'Explicit40CharPw...'
#   ./deploy/rotate-credentials.sh --dry-run            # dosya/konteyner dokunma
#   ./deploy/rotate-credentials.sh --no-restart         # env yaz, konteyner elle
#
# Rotasyon sonrası etkiler:
#   - Tarayıcı oturumları ve mobil Bearer token'lar GEÇERSİZLEŞİR (SESSION_SECRET
#     değişti) → yeni şifreyle tekrar login.
#   - Panel Basic auth anında yeni şifreyi ister.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."   # repo kökü

USERNAME=""
PASSWORD=""
DRY_RUN=0
NO_RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username)   USERNAME="${2:?--username değer ister}"; shift 2 ;;
    --password)   PASSWORD="${2:?--password değer ister}"; shift 2 ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --no-restart) NO_RESTART=1; shift ;;
    -h|--help)    grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "bilinmeyen argüman: $1 (bkz. --help)"; exit 2 ;;
  esac
done

# ── girdi doğrulama ──────────────────────────────────────────────────
if [[ -n "$PASSWORD" ]]; then
  if [[ ${#PASSWORD} -lt 20 ]]; then
    echo "HATA: --password en az 20 karakter olmalı (32+ önerilir)"; exit 2
  fi
  if [[ "$PASSWORD" == *$'\n'* || "$PASSWORD" == *'|'* ]]; then
    echo "HATA: şifre newline veya '|' içeremez (env dosya formatı)"; exit 2
  fi
else
  # Hex → sed/env-file/Basic-auth hepsinde güvenli; 40 char = 160 bit entropi.
  # (tr|head pipeline'ı pipefail+SIGPIPE ile sessiz ölürdü — openssl tek komut.)
  PASSWORD="$(openssl rand -hex 20)"
fi
if [[ -n "$USERNAME" && ! "$USERNAME" =~ ^[A-Za-z0-9_.-]{3,32}$ ]]; then
  echo "HATA: --username 3-32 karakter, sadece [A-Za-z0-9_.-]"; exit 2
fi

ENV_FILES=()
for f in .env.production .env.production.long .env.production.scalp; do
  [[ -f "$f" ]] && ENV_FILES+=("$f")
done
if [[ ${#ENV_FILES[@]} -eq 0 ]]; then
  echo "HATA: repo kökünde hiç .env.production* dosyası yok."
  echo "Önce deploy/.env.production*.example şablonlarından oluşturun."
  exit 1
fi

upsert() {  # upsert KEY VALUE FILE — satır varsa değiştir, yoksa ekle
  local key="$1" val="$2" file="$3"
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$file"
  else
    printf '%s=%s\n' "$key" "$val" >> "$file"
  fi
}

echo "Güncellenecek env dosyaları: ${ENV_FILES[*]}"
if [[ $DRY_RUN -eq 1 ]]; then
  echo "[dry-run] DASHBOARD_PASSWORD=<40-char>  (tüm dosyalarda AYNI)"
  echo "[dry-run] SESSION_SECRET=<64-hex>       (her dosyada FARKLI)"
  if [[ -n "$USERNAME" ]]; then echo "[dry-run] DASHBOARD_USERNAME=$USERNAME"; fi
  exit 0
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
for f in "${ENV_FILES[@]}"; do
  cp -p "$f" "$f.bak.$STAMP"
  chmod 600 "$f.bak.$STAMP" "$f"
  upsert DASHBOARD_PASSWORD "$PASSWORD" "$f"
  upsert SESSION_SECRET "$(openssl rand -hex 32)" "$f"
  if [[ -n "$USERNAME" ]]; then upsert DASHBOARD_USERNAME "$USERNAME" "$f"; fi
  echo "✓ $f güncellendi (yedek: $f.bak.$STAMP)"
done

# ── konteynerleri yeniden oluştur ────────────────────────────────────
if [[ $NO_RESTART -eq 0 ]]; then
  COMPOSE_ARGS=(-f docker-compose.prod.yml)
  if [[ -f docker-compose.panel.yml ]]; then COMPOSE_ARGS+=(-f docker-compose.panel.yml); fi
  SERVICES=()
  for svc in efloud-bot efloud-bot-long efloud-bot-scalp panel; do
    if docker compose "${COMPOSE_ARGS[@]}" config --services 2>/dev/null | grep -qx "$svc" \
       && docker ps -a --format '{{.Names}}' | grep -q "^efloud"; then
      SERVICES+=("$svc")
    fi
  done
  if [[ ${#SERVICES[@]} -gt 0 ]]; then
    echo "Konteynerler yeniden oluşturuluyor: ${SERVICES[*]}"
    docker compose "${COMPOSE_ARGS[@]}" up -d --force-recreate --no-deps "${SERVICES[@]}"
  else
    echo "UYARI: compose servisleri bulunamadı — konteynerleri elle yeniden oluşturun:"
    echo "  docker compose -f docker-compose.prod.yml -f docker-compose.panel.yml \\"
    echo "    up -d --force-recreate --no-deps efloud-bot efloud-bot-long efloud-bot-scalp panel"
  fi
else
  echo "(--no-restart: konteynerleri elle yeniden oluşturmayı unutma —"
  echo " docker restart env_file değişikliğini OKUMAZ)"
fi

echo
echo "─────────────────────────────────────────────────"
echo "YENİ KİMLİK BİLGİLERİ — şifre yöneticine kaydet, bu çıktı tekrar gösterilmez:"
if [[ -n "$USERNAME" ]]; then echo "  Kullanıcı adı : $USERNAME"; fi
echo "  Şifre         : $PASSWORD"
echo "─────────────────────────────────────────────────"
echo "Not: mevcut tarayıcı oturumları ve mobil token'lar geçersizleşti."
