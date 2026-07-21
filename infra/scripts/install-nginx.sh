#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "install-nginx.sh must run as root" >&2
  exit 1
fi

template=/srv/aiot/config/nginx/aiot.conf.template
target=/etc/nginx/sites-available/aiot
domain=i15e103.p.ssafy.io
certificate=/etc/letsencrypt/live/p.ssafy.io/fullchain.pem
private_key=/etc/letsencrypt/live/p.ssafy.io/privkey.pem

test -r "${template}"
test -r "${certificate}"
test -r "${private_key}"

sed \
  -e "s|__APP_DOMAIN__|${domain}|g" \
  -e "s|__TLS_CERTIFICATE__|${certificate}|g" \
  -e "s|__TLS_PRIVATE_KEY__|${private_key}|g" \
  "${template}" >"${target}"

ln -sfn "${target}" /etc/nginx/sites-enabled/aiot
nginx -t
systemctl reload nginx
echo "Nginx AIoT site enabled"
