#!/usr/bin/env bash
set -euo pipefail

ai_root="${AIOT_AI_ROOT:-/home/e103/yolo-pipeline}"
python_bin="${AIOT_AI_PYTHON:-${ai_root}/venv/bin/python}"
pipeline_main="${AIOT_AI_PIPELINE_MAIN:-${ai_root}/yolo_pipeline/main.py}"
robot_root="${AIOT_IOT_CURRENT:-/opt/aiot/iot/current}/robot"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
camera_front="${AIOT_AI_CAMERA_FRONT_DEVICE:-${AIOT_AI_CAMERA_DEVICE:-}}"
camera_rear="${AIOT_AI_CAMERA_REAR_DEVICE:-}"
pipeline_extra_args="${AIOT_AI_PIPELINE_EXTRA_ARGS:---no-show}"

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export PYTHONUNBUFFERED=1
umask 0007

cd "${ai_root}"
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
args=()
if [ -n "${camera_front}" ]; then
  args+=(--source-a "${camera_front}")
fi
if [ -n "${camera_rear}" ]; then
  args+=(--source-b "${camera_rear}")
fi
if [ -n "${pipeline_extra_args}" ]; then
  read -r -a extra_args <<<"${pipeline_extra_args}"
  args+=("${extra_args[@]}")
fi
exec "${python_bin}" -m aiot_robot.ai_runtime \
  --pipeline-main "${pipeline_main}" "${args[@]}"
