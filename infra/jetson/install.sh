#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo bash infra/jetson/install.sh" >&2
  exit 1
fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

getent group aiot >/dev/null || groupadd --system aiot
if ! id aiot >/dev/null 2>&1; then
  useradd --system --gid aiot --home-dir /opt/aiot --shell /usr/sbin/nologin aiot
fi
for device_group in dialout video; do
  if getent group "${device_group}" >/dev/null; then
    usermod -a -G "${device_group}" aiot
  fi
done

install -d -m 0755 -o root -g root /opt/aiot /opt/aiot/bin
install -d -m 0750 -o aiot -g aiot \
  /opt/aiot/releases \
  /opt/aiot/.staging \
  /opt/aiot/state \
  /opt/aiot/logs
install -d -m 0700 -o root -g root /opt/aiot/secrets
install -m 0755 -o root -g root "${source_dir}/aiot-update.sh" /opt/aiot/bin/aiot-update
install -m 0644 -o root -g root "${source_dir}/aiot-update.service" \
  /etc/systemd/system/aiot-update.service
install -m 0644 -o root -g root "${source_dir}/aiot-robot.service" \
  /etc/systemd/system/aiot-robot.service

if [ ! -e /opt/aiot/secrets/package-read.env ]; then
  install -m 0600 -o root -g root "${source_dir}/package-read.env.example" \
    /opt/aiot/secrets/package-read.env.example
  echo "Create /opt/aiot/secrets/package-read.env from the example before enabling OTA."
fi

systemctl daemon-reload
systemctl enable aiot-update.service aiot-robot.service
echo "Jetson OTA units installed; credentials were not created or overwritten."
