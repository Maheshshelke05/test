#!/usr/bin/env bash
# Build the web apps on this machine and deploy everything to an Ubuntu server.
#
#   SERVER=ubuntu@3.110.189.207 SSH_KEY=~/Downloads/test.pem ./deploy/deploy.sh
#
# Optional:
#   PUBLIC_URL=http://3.110.189.207    what users open (default: http://<server host>)
#   DOMAIN=food.example.com            enables HTTPS with Let's Encrypt (DNS must point here)
#   CERTBOT_EMAIL=you@example.com      required with DOMAIN
#   BUILD_ONLY=1                       build deploy/.release without uploading (SERVER not needed)
#
# Safe to run again for every release: data, secrets and the database are kept.
set -euo pipefail

BUILD_ONLY=${BUILD_ONLY:-}
if [ -n "$BUILD_ONLY" ]; then SERVER=${SERVER:-local}; else SERVER=${SERVER:?set SERVER=user@host}; fi
SSH_KEY=${SSH_KEY:-}
DOMAIN=${DOMAIN:-}
CERTBOT_EMAIL=${CERTBOT_EMAIL:-}
if [ -n "$DOMAIN" ]; then
  [ -n "$CERTBOT_EMAIL" ] || { echo "CERTBOT_EMAIL is required with DOMAIN" >&2; exit 1; }
  PUBLIC_URL=${PUBLIC_URL:-https://$DOMAIN}
else
  PUBLIC_URL=${PUBLIC_URL:-http://${SERVER#*@}}
fi
PUBLIC_URL=${PUBLIC_URL%/}

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/deploy/.release"
SSH=(ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)
[ -n "$SSH_KEY" ] && SSH+=(-i "$SSH_KEY")

if [ -z "$BUILD_ONLY" ]; then
  echo "==> Checking SSH access to $SERVER"
  "${SSH[@]}" -o BatchMode=yes -o ConnectTimeout=15 "$SERVER" true
fi

echo "==> Building web apps for $PUBLIC_URL"
rm -rf "$OUT"
mkdir -p "$OUT/web"
# Sub-paths are given without a leading slash (Git Bash would turn "/kitchen" into a Windows path).
(cd "$ROOT/apps/student" && [ -d node_modules ] || npm install --no-audit --no-fund)
(cd "$ROOT/apps/student" && EXPO_PUBLIC_API_URL="$PUBLIC_URL" npx expo export --platform web --clear --output-dir "$OUT/student")
(cd "$ROOT/apps/kitchen" && [ -d node_modules ] || npm install --no-audit --no-fund)
(cd "$ROOT/apps/kitchen" && EXPO_PUBLIC_API_URL="$PUBLIC_URL" WEB_SUBPATH=kitchen npx expo export --platform web --clear --output-dir "$OUT/kitchen")
(cd "$ROOT/apps/admin" && [ -d node_modules ] || npm install --no-audit --no-fund)
(cd "$ROOT/apps/admin" && VITE_API_URL="$PUBLIC_URL" WEB_SUBPATH=admin npx vite build --outDir "$OUT/admin" --emptyOutDir)
cp -a "$OUT/student/." "$OUT/web/"
cp -a "$OUT/kitchen" "$OUT/web/kitchen"
cp -a "$OUT/admin" "$OUT/web/admin"

echo "==> Packaging backend"
mkdir -p "$OUT/release"
tar -C "$ROOT" -cf - \
  --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude='*.db' --exclude='*.db-*' \
  --exclude=.env --exclude=tests \
  backend deploy/server-setup.sh deploy/nginx-campusbite.conf deploy/nginx-headers.conf \
  | tar -C "$OUT/release" -xf -
cp -a "$OUT/web" "$OUT/release/web"

if [ -n "$BUILD_ONLY" ]; then
  echo "==> Release built in $OUT/release (not uploaded)"
  exit 0
fi

echo "==> Uploading release"
tar -C "$OUT/release" -czf - . | "${SSH[@]}" "$SERVER" \
  'rm -rf /tmp/campusbite-release && mkdir -p /tmp/campusbite-release && tar -xzf - -C /tmp/campusbite-release'

echo "==> Installing on the server (this takes a few minutes the first time)"
"${SSH[@]}" "$SERVER" "sudo PUBLIC_URL='$PUBLIC_URL' DOMAIN='$DOMAIN' CERTBOT_EMAIL='$CERTBOT_EMAIL' bash /tmp/campusbite-release/deploy/server-setup.sh"

rm -rf "$OUT"
echo "==> Done: $PUBLIC_URL"
