#!/usr/bin/env bash
set -euo pipefail

BASE="${HOME}/robot-hw-test"
CLI="${BASE}/tools/arduino-cli/arduino-cli"
CFG="${BASE}/arduino-cli.yaml"
SKETCH="${BASE}/firmware/roki_safe_test"
BUILD="${BASE}/build/roki_safe_test"
PORT="/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"

shopt -s nullglob
FLASH_BACKUPS=("${BASE}"/backups/esp32-full-*.bin)
if (( ${#FLASH_BACKUPS[@]} == 0 )) || [[ ! -s "${FLASH_BACKUPS[0]}" ]]; then
  echo "ERROR: full ESP32 flash backup is missing." >&2
  exit 2
fi

mkdir -p "${BUILD}"

echo "Compiling safe firmware..."
"${CLI}" compile \
  --config-file "${CFG}" \
  --fqbn esp32:esp32:esp32 \
  --output-dir "${BUILD}" \
  "${SKETCH}"

echo "Uploading safe firmware while Battery B is disconnected..."
"${CLI}" upload \
  --config-file "${CFG}" \
  --fqbn esp32:esp32:esp32 \
  --port "${PORT}" \
  --input-dir "${BUILD}" \
  "${SKETCH}"

echo "Upload complete."
