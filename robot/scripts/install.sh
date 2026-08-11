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

"${robot_root}/.venv/bin/python" -m pip install \
  --disable-pip-version-check \
  -r "${robot_root}/requirements.txt"

"${robot_root}/.venv/bin/python" -c \
  'import rclpy; from std_msgs.msg import String; print("Robot ROS dependencies OK")'

"${robot_root}/scripts/build-explore-overlay.sh"

if [ "$(id -u)" -eq 0 ] && id aiot >/dev/null 2>&1; then
  install -d -m 2770 -o aiot -g aiot \
    /var/lib/aiot/config \
    /var/lib/aiot/evidence \
    /var/lib/aiot/maps \
    /var/lib/aiot/outbox \
    /var/lib/aiot/secrets \
    /var/lib/aiot/state
fi

# Generic USB gamepads are normally root:input 0660. The deployed runtime
# currently runs as e103, while local development may override the user.
if [ "$(id -u)" -eq 0 ]; then
  runtime_user="${AIOT_RUNTIME_USER:-e103}"
  if id "${runtime_user}" >/dev/null 2>&1 && getent group input >/dev/null 2>&1; then
    usermod -a -G input "${runtime_user}"
  fi

  install -d -m 0755 -o root -g root \
    /opt/aiot/bin \
    /etc/systemd/system/aiot-ros.service.d \
    /etc/systemd/system/aiot-robot.service.d
  install -m 0644 -o root -g root \
    "${robot_root}/config/systemd/aiot-current-map.conf" \
    /etc/systemd/system/aiot-ros.service.d/20-current-map.conf
  install -m 0644 -o root -g root \
    "${robot_root}/config/systemd/aiot-current-map.conf" \
    /etc/systemd/system/aiot-robot.service.d/20-current-map.conf
  # 지도 활성화가 더 이상 서비스를 재시작하지 않으므로 그 감시 유닛을 걷어낸다.
  # 남겨두면 없는 마커 파일을 계속 기다리는 유닛이 활성 상태로 남는다.
  systemctl disable --now aiot-map-activate.path 2>/dev/null || true
  rm -f /etc/systemd/system/aiot-map-activate.path \
        /etc/systemd/system/aiot-map-activate.service \
        /opt/aiot/bin/aiot-map-activate
  systemctl daemon-reload
fi

echo "Robot runtime installed without sending movement commands"
