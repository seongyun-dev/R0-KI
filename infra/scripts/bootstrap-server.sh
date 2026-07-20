#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "bootstrap-server.sh must run as root" >&2
  exit 1
fi

source_root="${1:-}"
if [ -z "${source_root}" ] || [ ! -d "${source_root}/infra" ]; then
  echo "usage: bootstrap-server.sh <repository-root>" >&2
  exit 1
fi

getent group aiot >/dev/null || groupadd --system aiot

for user_name in ubuntu gitlab-runner; do
  if id "${user_name}" >/dev/null 2>&1; then
    usermod -aG aiot "${user_name}"
  fi
done

install -d -m 2770 -o root -g aiot \
  /srv/aiot/compose \
  /srv/aiot/config/nginx \
  /srv/aiot/config/mosquitto \
  /srv/aiot/data/mysql \
  /srv/aiot/data/mosquitto \
  /srv/aiot/data/uploads \
  /srv/aiot/data/maps \
  /srv/aiot/secrets \
  /srv/aiot/deploy \
  /srv/aiot/logs \
  /srv/aiot/backups/runtime

install -d -m 0750 -o 1883 -g 1883 /srv/aiot/certs/mqtt

install -m 0640 -o root -g aiot \
  "${source_root}/infra/compose/compose.infrastructure.yaml" \
  /srv/aiot/compose/compose.infrastructure.yaml
install -m 0640 -o root -g aiot \
  "${source_root}/infra/compose/compose.application.yaml" \
  /srv/aiot/compose/compose.application.yaml
install -m 0644 -o root -g root \
  "${source_root}/infra/nginx/aiot.conf.template" \
  /srv/aiot/config/nginx/aiot.conf.template
install -m 0640 -o root -g aiot \
  "${source_root}/infra/mosquitto/mosquitto.conf" \
  /srv/aiot/config/mosquitto/mosquitto.conf

for script_name in \
  backup.sh \
  deploy.sh \
  deploy-infrastructure.sh \
  health-check.sh \
  initialize-secrets.sh \
  install-nginx.sh \
  rollback.sh \
  sync-certificates.sh; do
  install -m 0750 -o root -g aiot \
    "${source_root}/infra/scripts/${script_name}" \
    "/srv/aiot/deploy/${script_name}"
done

# The Eclipse Mosquitto image runs as UID/GID 1883.
chown 1883:aiot /srv/aiot/data/mosquitto
chmod 2770 /srv/aiot/data/mosquitto
chmod 0644 /srv/aiot/config/mosquitto/mosquitto.conf

install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat >/etc/letsencrypt/renewal-hooks/deploy/aiot-mqtt-cert-sync <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
/srv/aiot/deploy/sync-certificates.sh
EOF
chmod 0750 /etc/letsencrypt/renewal-hooks/deploy/aiot-mqtt-cert-sync

cat >/etc/systemd/system/aiot-backup.service <<'EOF'
[Unit]
Description=AIoT local runtime backup
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
ExecStart=/srv/aiot/deploy/backup.sh
EOF

cat >/etc/systemd/system/aiot-backup.timer <<'EOF'
[Unit]
Description=Run AIoT local backup every day

[Timer]
OnCalendar=*-*-* 03:30:00 Asia/Seoul
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now aiot-backup.timer

if systemctl is-active --quiet gitlab-runner; then
  systemctl restart gitlab-runner
fi

docker network inspect aiot-network >/dev/null 2>&1 || docker network create aiot-network >/dev/null

echo "Server skeleton installed under /srv/aiot"
