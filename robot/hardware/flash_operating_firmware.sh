#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "${1:-}" != "BATTERY_B_DISCONNECTED" ]]; then
  echo "ERROR: physically disconnect Battery B first." >&2
  echo "Then run: ./flash_operating_firmware.sh BATTERY_B_DISCONNECTED" >&2
  exit 2
fi

echo "Battery B confirmation accepted. Compiling and flashing operating firmware."
./flash_safe_firmware.sh
./.venv/bin/python operating_preflight.py
