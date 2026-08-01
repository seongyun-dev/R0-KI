#!/usr/bin/env bash
set -euo pipefail

BASE="${HOME}/robot-hw-test"
PYTHON="${BASE}/.venv/bin/python"
PORT_GLOB="/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_"'*'"-if00-port0"

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

compgen -G "${PORT_GLOB}" >/dev/null || {
  echo "ERROR: stable ESP32 by-id path is missing." >&2
  exit 2
}

ls -l ${PORT_GLOB}

echo
echo "===== SAFE FIRMWARE HANDSHAKE ====="
"${PYTHON}" "${BASE}/hw_test.py" preflight

echo
echo "PREFLIGHT_PASS_NO_MOVEMENT"
