#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"

if [ ! -r "${ros_setup}" ]; then
  echo "ROS 2 setup is missing: ${ros_setup}" >&2
  exit 1
fi

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

python_bin="${robot_root}/.venv/bin/python"
if [ ! -x "${python_bin}" ]; then
  python_bin="$(command -v python3)"
fi

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${python_bin}" -m aiot_robot.main "$@"
