#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${robot_root}/.venv/bin/python"
test -x "${python_bin}" || { echo "Robot venv is missing" >&2; exit 1; }
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

if [ "${MQTT_USE_TLS:-true}" != true ]; then
  echo "MQTT E2E verification requires TLS" >&2
  exit 1
fi
if [ -z "${MQTT_HOST:-}" ] || [ -z "${ROBOT_KEY:-}" ]; then
  echo "Load the root-only robot.env before running this check" >&2
  exit 1
fi
exec "${python_bin}" -m aiot_robot.mqtt_probe "$@"
