#!/usr/bin/env bash
set -euo pipefail

BASE="${HOME}/robot-hw-test"
PYTHON="${BASE}/.venv/bin/python"
PORT="${ESP32_PORT:-/dev/roki_esp32}"

echo "===== POWER SAFETY ====="
echo "Battery B must remain disconnected for this preflight."
echo "This script does not send a movement command."

echo
echo "===== JETSON ====="
cat /etc/nv_tegra_release | head -n 2
python3 --version
df -h /

echo
echo "===== ESP32 USB ====="
lsusb | grep -E "10c4:ea60|CP210" || {
  echo "ERROR: CP2102 ESP32 is not detected." >&2
  exit 2
}

test -e "${PORT}" || {
  echo "ERROR: stable ESP32 path is missing: ${PORT}" >&2
  exit 2
}

ls -l "${PORT}"

echo
echo "===== SAFE FIRMWARE HANDSHAKE ====="
"${PYTHON}" "${BASE}/hw_test.py" --port "${PORT}" preflight

echo
echo "PREFLIGHT_PASS_NO_MOVEMENT"
