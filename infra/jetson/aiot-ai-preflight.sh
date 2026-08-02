#!/usr/bin/env bash
set -euo pipefail

ai_root="${AIOT_AI_ROOT:-/home/e103/yolo-pipeline}"
python_bin="${AIOT_AI_PYTHON:-${ai_root}/venv/bin/python}"
entrypoint="${AIOT_AI_ENTRYPOINT:-yolo_pipeline.main}"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
ready_file="${AIOT_AI_READY_FILE:-/run/aiot/ai-ready.json}"
evidence_dir="${AIOT_AI_EVIDENCE_DIR:-/var/lib/aiot/evidence}"
required_engines="${AIOT_AI_REQUIRED_ENGINE_PATHS:-}"
camera_devices=(
  "${AIOT_AI_CAMERA_DEVICE:-}"
  "${AIOT_AI_CAMERA_FRONT_DEVICE:-}"
  "${AIOT_AI_CAMERA_REAR_DEVICE:-}"
)

if [ "${ROS_LOCALHOST_ONLY:-1}" != "1" ]; then
  echo "ROS_LOCALHOST_ONLY must be 1 for Jetson-local AI/Robot traffic" >&2
  exit 1
fi
if [ ! -d "${ai_root}" ]; then
  echo "AI runtime root is missing: ${ai_root}" >&2
  exit 1
fi
if [ ! -x "${python_bin}" ]; then
  echo "AI venv Python is missing: ${python_bin}" >&2
  exit 1
fi
if [ ! -r "${ros_setup}" ]; then
  echo "ROS 2 setup is missing: ${ros_setup}" >&2
  exit 1
fi
if [[ ! "${entrypoint}" =~ ^[A-Za-z_][A-Za-z0-9_.]*$ ]]; then
  echo "AIOT_AI_ENTRYPOINT is not a safe Python module name" >&2
  exit 1
fi
if [ ! -d "${evidence_dir}" ] || [ ! -w "${evidence_dir}" ]; then
  echo "AI evidence directory is not writable: ${evidence_dir}" >&2
  exit 1
fi
if [ ! -d "$(dirname "${ready_file}")" ] || \
   [ ! -w "$(dirname "${ready_file}")" ]; then
  echo "AI readiness directory is not writable: $(dirname "${ready_file}")" >&2
  exit 1
fi
for camera_device in "${camera_devices[@]}"; do
  if [ -n "${camera_device}" ] && [ ! -r "${camera_device}" ]; then
    echo "Configured AI camera device is not readable: ${camera_device}" >&2
    exit 1
  fi
done

if [ -n "${required_engines}" ]; then
  IFS=: read -r -a engine_paths <<<"${required_engines}"
  for engine_path in "${engine_paths[@]}"; do
    if [[ "${engine_path}" != /* ]] || [ ! -s "${engine_path}" ]; then
      echo "Required TensorRT engine is missing: ${engine_path}" >&2
      exit 1
    fi
  done
elif ! find "${ai_root}" -type f -name '*.engine' -size +0c -print -quit | grep -q .; then
  echo "No TensorRT engine was found below ${ai_root}" >&2
  exit 1
fi

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

"${python_bin}" - "${entrypoint}" <<'PY'
import importlib.util
import sys

import rclpy
from std_msgs.msg import String

entrypoint = sys.argv[1]
if importlib.util.find_spec(entrypoint) is None:
    raise SystemExit(f"AI entrypoint module is not importable: {entrypoint}")
print("AI preflight passed: ROS 2 and entrypoint are importable")
PY

rm -f "${ready_file}"
