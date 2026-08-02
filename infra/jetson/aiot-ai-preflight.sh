#!/usr/bin/env bash
set -euo pipefail

ai_root="${AIOT_AI_ROOT:-/home/e103/yolo-pipeline}"
python_bin="${AIOT_AI_PYTHON:-${ai_root}/venv/bin/python}"
pipeline_main="${AIOT_AI_PIPELINE_MAIN:-${ai_root}/yolo_pipeline/main.py}"
robot_root="${AIOT_IOT_CURRENT:-/opt/aiot/iot/current}/robot"
robot_adapter="${robot_root}/src/aiot_robot/ai_runtime.py"
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
if [ ! -r "${pipeline_main}" ]; then
  echo "AI pipeline main.py is missing: ${pipeline_main}" >&2
  exit 1
fi
if [ ! -r "${robot_adapter}" ]; then
  echo "Robot AI adapter is missing: ${robot_adapter}" >&2
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
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

"${python_bin}" - "${pipeline_main}" "${robot_adapter}" <<'PY'
import py_compile
import sys

import rclpy
import cv2
import tensorrt
import aiot_robot.ai_runtime
from std_msgs.msg import String

for path in sys.argv[1:]:
    py_compile.compile(path, doraise=True)
print("AI preflight passed: ROS 2, TensorRT and script entrypoints are ready")
PY

rm -f "${ready_file}"
