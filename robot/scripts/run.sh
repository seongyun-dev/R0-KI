#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
slam_reset_setup="${AIOT_SLAM_TOOLBOX_RESET_SETUP_FILE:-/home/e103/slam-toolbox-2610-reset-backport-ws/install/setup.bash}"

if [ ! -r "${ros_setup}" ]; then
  echo "ROS 2 setup is missing: ${ros_setup}" >&2
  exit 1
fi
if [ ! -r "${slam_reset_setup}" ]; then
  echo "slam_toolbox Reset overlay is missing: ${slam_reset_setup}" >&2
  exit 1
fi

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
# shellcheck disable=SC1090
source "${slam_reset_setup}"
set -u

python_bin="${robot_root}/.venv/bin/python"
if [ ! -x "${python_bin}" ]; then
  python_bin="$(command -v python3)"
fi

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export ROS_HOME="${ROS_HOME:-/var/lib/aiot/ros}"
export ROS_LOG_DIR="${ROS_LOG_DIR:-${ROS_HOME}/log}"
mkdir -p "${ROS_LOG_DIR}"
export PYTHONPATH="${robot_root}/src:${robot_root}/roki:${robot_root}/roki-iot${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1
exec "${python_bin}" -B "${robot_root}/roki-iot/run_integrated.py" "$@"
