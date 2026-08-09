#!/usr/bin/env bash
set -euo pipefail

BASE="${HOME}/robot-hw-test"
SPEED="${1:-15}"

cd "${BASE}"
exec ./.venv/bin/python drive_demo.py \
  --speed "${SPEED}" \
  --confirm AREA_CLEAR
