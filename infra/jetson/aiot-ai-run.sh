#!/usr/bin/env bash
set -euo pipefail

ai_root="${AIOT_AI_ROOT:-/home/e103/yolo-pipeline}"
python_bin="${AIOT_AI_PYTHON:-${ai_root}/venv/bin/python}"
entrypoint="${AIOT_AI_ENTRYPOINT:-yolo_pipeline.main}"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export PYTHONUNBUFFERED=1
umask 0007

cd "${ai_root}"
exec "${python_bin}" -m "${entrypoint}"
