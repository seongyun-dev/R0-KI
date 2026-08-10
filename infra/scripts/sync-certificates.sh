#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "sync-certificates.sh must run as root" >&2
  exit 1
fi

certificate_dir="${1:-/etc/letsencrypt/live/p.ssafy.io}"
target_dir=/srv/aiot/certs/mqtt

test -r "${certificate_dir}/fullchain.pem"
test -r "${certificate_dir}/privkey.pem"

install -d -m 0750 -o 1883 -g 1883 "${target_dir}"
install -m 0644 -o 1883 -g 1883 "${certificate_dir}/fullchain.pem" "${target_dir}/fullchain.pem"
install -m 0600 -o 1883 -g 1883 "${certificate_dir}/privkey.pem" "${target_dir}/privkey.pem"

if docker ps --format '{{.Names}}' | grep -qx aiot-mosquitto; then
  docker restart aiot-mosquitto >/dev/null
fi

if systemctl is-active --quiet nginx; then
  nginx -t
  systemctl reload nginx
fi

echo "TLS certificates synchronized"
