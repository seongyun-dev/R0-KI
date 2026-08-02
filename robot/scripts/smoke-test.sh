#!/usr/bin/env bash
set -euo pipefail

phase="${1:-pre-activate}"
case "${phase}" in
  pre-activate|post-activate) ;;
  *) echo "usage: smoke-test.sh [pre-activate|post-activate]" >&2; exit 2 ;;
esac

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
python_bin="${robot_root}/.venv/bin/python"

test -r "${ros_setup}"
test -x "${python_bin}"
test -x "${robot_root}/scripts/run.sh"

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export ROS_HOME="${ROS_HOME:-/var/lib/aiot/ros}"
export ROS_LOG_DIR="${ROS_LOG_DIR:-${ROS_HOME}/log}"
mkdir -p "${ROS_LOG_DIR}"
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1
"${python_bin}" -B -m aiot_robot.smoke
"${python_bin}" -B -m aiot_robot.ros_smoke
echo "Robot ${phase} smoke passed; no actuator command was sent"
