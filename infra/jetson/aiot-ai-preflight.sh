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
camera_left="${AIOT_AI_CAMERA_LEFT_DEVICE:-${AIOT_AI_CAMERA_FRONT_DEVICE:-${AIOT_AI_CAMERA_DEVICE:-}}}"
camera_right="${AIOT_AI_CAMERA_RIGHT_DEVICE:-${AIOT_AI_CAMERA_REAR_DEVICE:-}}"
camera_devices=("${camera_left}" "${camera_right}")

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
if [ "${AIOT_AI_REQUIRE_DUAL_CAMERAS:-false}" = true ]; then
  if [ -z "${camera_left}" ] || [ -z "${camera_right}" ] || \
     [ "${camera_left}" = "${camera_right}" ]; then
    echo "Two distinct AI camera devices are required" >&2
    exit 1
  fi
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

engine_arguments=()
if [ -n "${required_engines}" ]; then
  IFS=: read -r -a engine_arguments <<<"${required_engines}"
fi
"${python_bin}" - "${pipeline_main}" "${robot_adapter}" \
  "${AIOT_AI_VALIDATE_TRT_ENGINES:-true}" "${engine_arguments[@]}" <<'PY'
import py_compile
import sys

import rclpy
import cv2
import tensorrt
import aiot_robot.ai_runtime
from std_msgs.msg import String

pipeline_main, robot_adapter, validate_engines, *engine_paths = sys.argv[1:]
for path in (pipeline_main, robot_adapter):
    py_compile.compile(path, doraise=True)
if validate_engines == "true":
    logger = tensorrt.Logger(tensorrt.Logger.ERROR)
    for path in engine_paths:
        with open(path, "rb") as stream, tensorrt.Runtime(logger) as runtime:
            engine = runtime.deserialize_cuda_engine(stream.read())
        if engine is None:
            raise RuntimeError(f"TensorRT engine cannot be deserialized: {path}")
print("AI preflight passed: ROS 2, TensorRT and script entrypoints are ready")
PY

rm -f "${ready_file}"
