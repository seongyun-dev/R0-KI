#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
environment_file="${AIOT_ROBOT_ENV_FILE:-/opt/aiot/secrets/robot.env}"
serial_device="${ESP32_PORT:-/dev/roki_esp32}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo so the protected robot.env can be loaded." >&2
  exit 1
fi
if [[ ! -t 0 ]]; then
  echo "Manual demo requires an interactive SSH terminal." >&2
  exit 1
fi
if systemctl is-active --quiet aiot-robot.service; then
  echo "aiot-robot.service already owns the runtime; stop it first." >&2
  exit 1
fi
if [[ ! -r "${environment_file}" ]]; then
  echo "Robot environment is missing: ${environment_file}" >&2
  exit 1
fi
for service in aiot-ai.service aiot-ros.service; do
  if ! systemctl is-active --quiet "${service}"; then
    echo "Required service is not active: ${service}" >&2
    exit 1
  fi
done
if command -v fuser >/dev/null 2>&1 && fuser "${serial_device}" >/dev/null 2>&1; then
  echo "ESP32 Serial is already owned: ${serial_device}" >&2
  fuser -v "${serial_device}" >&2 || true
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${environment_file}"
set +a

if [[ -z "${ROBOT_KEY:-}" || "${ROBOT_KEY}" == replace-* ]]; then
  echo "ROBOT_KEY must be the backend-registered robot key." >&2
  exit 1
fi

echo "Manual patrol demo: robotKey=${ROBOT_KEY}"
echo "The robot remains stopped until the frontend START succeeds and W/S is pressed."
exec runuser -u e103 --preserve-environment -- \
  "${robot_root}/scripts/run.sh" --manual-keyboard "$@"
