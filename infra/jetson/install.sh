#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo bash infra/jetson/install.sh" >&2
  exit 1
fi

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
enable_services=false
if [ "${1:-}" = "--enable" ]; then
  enable_services=true
elif [ -n "${1:-}" ]; then
  echo "usage: sudo bash infra/jetson/install.sh [--enable]" >&2
  exit 2
fi

getent group aiot >/dev/null || groupadd --system aiot
if ! id aiot >/dev/null 2>&1; then
  useradd --system --gid aiot --home-dir /opt/aiot --shell /usr/sbin/nologin aiot
fi
for device_group in dialout video render; do
  if getent group "${device_group}" >/dev/null; then
    usermod -a -G "${device_group}" aiot
  fi
done
if id e103 >/dev/null 2>&1; then
  usermod -a -G aiot e103
else
  echo "Warning: e103 user is missing; aiot-ai.service cannot start yet." >&2
fi

install -d -m 0755 -o root -g root /opt/aiot /opt/aiot/bin
install -d -m 0750 -o aiot -g aiot \
  /opt/aiot/iot \
  /opt/aiot/iot/releases \
  /opt/aiot/iot/.staging \
  /opt/aiot/iot/state \
  /opt/aiot/logs
install -d -m 0700 -o root -g root /opt/aiot/secrets
install -d -m 2770 -o aiot -g aiot \
  /var/lib/aiot \
  /var/lib/aiot/evidence \
  /var/lib/aiot/outbox
install -m 0755 -o root -g root "${source_dir}/aiot-update.sh" /opt/aiot/bin/aiot-update
install -m 0755 -o root -g root "${source_dir}/aiot-ai-preflight.sh" \
  /opt/aiot/bin/aiot-ai-preflight
install -m 0755 -o root -g root "${source_dir}/aiot-ai-run.sh" \
  /opt/aiot/bin/aiot-ai-run
install -m 0755 -o root -g root "${source_dir}/aiot-ai-wait-ready.sh" \
  /opt/aiot/bin/aiot-ai-wait-ready
install -m 0755 -o root -g root "${source_dir}/aiot-ai-wait-ready.py" \
  /opt/aiot/bin/aiot-ai-wait-ready.py
install -m 0644 -o root -g root "${source_dir}/aiot-update.service" \
  /etc/systemd/system/aiot-update.service
install -m 0644 -o root -g root "${source_dir}/aiot-ai.service" \
  /etc/systemd/system/aiot-ai.service
install -m 0644 -o root -g root "${source_dir}/aiot-robot.service" \
  /etc/systemd/system/aiot-robot.service

if [ ! -e /opt/aiot/secrets/package-read.env ]; then
  install -m 0600 -o root -g root "${source_dir}/package-read.env.example" \
    /opt/aiot/secrets/package-read.env.example
  echo "Create /opt/aiot/secrets/package-read.env from the example before enabling OTA."
fi
if [ ! -e /opt/aiot/secrets/ai.env ]; then
  install -m 0600 -o root -g root "${source_dir}/ai.env.example" \
    /opt/aiot/secrets/ai.env.example
  echo "Review /opt/aiot/secrets/ai.env.example before starting AI."
fi

systemctl daemon-reload
if command -v systemd-analyze >/dev/null 2>&1; then
  verify_units=(
    /etc/systemd/system/aiot-update.service
    /etc/systemd/system/aiot-ai.service
  )
  if [ -x /opt/aiot/iot/current/robot/scripts/run.sh ]; then
    verify_units+=(/etc/systemd/system/aiot-robot.service)
  fi
  systemd-analyze verify "${verify_units[@]}"
fi
if [ "${enable_services}" = true ]; then
  systemctl enable aiot-update.service aiot-ai.service aiot-robot.service
  echo "Jetson services enabled. Start them only after environment review."
else
  echo "Jetson units installed but not newly enabled."
  echo "After manual validation: sudo bash infra/jetson/install.sh --enable"
fi
echo "Credentials and existing AI runtime files were not created or overwritten."
