#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

SPEED="${1:-15}"
BURST_SECONDS="${2:-1.5}"

exec ./.venv/bin/python steering_drive_demo.py \
  --speed "$SPEED" \
  --burst-seconds "$BURST_SECONDS" \
  --confirm AREA_CLEAR
