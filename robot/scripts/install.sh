#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
python_command="${PYTHON_COMMAND:-python3}"

if [ ! -r "${ros_setup}" ]; then
  echo "ROS 2 Humble is required: ${ros_setup}" >&2
  exit 1
fi

"${python_command}" -m venv --system-site-packages "${robot_root}/.venv"

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

"${robot_root}/.venv/bin/python" -c \
  'import rclpy; from std_msgs.msg import String; print("Robot ROS dependencies OK")'

if [ "$(id -u)" -eq 0 ] && id aiot >/dev/null 2>&1; then
  install -d -m 0750 -o aiot -g aiot /var/lib/aiot/outbox
fi

echo "Robot runtime installed without sending movement commands"
