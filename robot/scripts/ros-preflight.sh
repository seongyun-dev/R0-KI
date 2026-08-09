#!/usr/bin/env bash
set -euo pipefail

software_only=false
if [ "${1:-}" = "--software-only" ]; then
  software_only=true
elif [ -n "${1:-}" ]; then
  echo "usage: ros-preflight.sh [--software-only]" >&2
  exit 2
fi

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
ydlidar_setup="${AIOT_YDLIDAR_SETUP_FILE:-/home/e103/ydlidar_ws/install/setup.bash}"
rf2o_setup="${AIOT_RF2O_SETUP_FILE:-/home/e103/rf2o_ws/install/setup.bash}"
mode="${AIOT_ROS_MODE:-patrol}"
lidar_device="${ROKI_LIDAR_DEVICE:-/dev/roki_lidar}"

case "${mode}" in
  mapping|patrol) ;;
  *) echo "AIOT_ROS_MODE must be mapping or patrol" >&2; exit 1 ;;
esac
for setup_file in "${ros_setup}" "${ydlidar_setup}" "${rf2o_setup}"; do
  if [ ! -r "${setup_file}" ]; then
    echo "Required ROS setup is missing: ${setup_file}" >&2
    exit 1
  fi
  set +u
  # shellcheck disable=SC1090
  source "${setup_file}"
  set -u
done

required_packages=(ydlidar_ros2_driver rf2o_laser_odometry tf2_ros)
if [ "${mode}" = mapping ]; then
  required_packages+=(slam_toolbox)
else
  required_packages+=(nav2_bringup nav2_bt_navigator nav2_controller nav2_smac_planner)
fi
for package in "${required_packages[@]}"; do
  if ! ros2 pkg prefix "${package}" >/dev/null 2>&1; then
    echo "Required ROS package is missing: ${package}" >&2
    exit 1
  fi
done

for config in \
  "${robot_root}/config/ros/ydlidar.yaml" \
  "${robot_root}/config/ros/rf2o.yaml" \
  "${robot_root}/config/ros/slam_toolbox.yaml" \
  "${robot_root}/config/ros/nav2.params.yaml.template" \
  "${robot_root}/config/ros/nav2_fixed_path.xml"; do
  test -s "${config}" || { echo "ROS config is missing: ${config}" >&2; exit 1; }
done

python_bin="${robot_root}/.venv/bin/python"
test -x "${python_bin}" || { echo "Robot venv is missing: ${python_bin}" >&2; exit 1; }
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
if [ "${software_only}" = true ]; then
  "${python_bin}" -m aiot_robot.ros_config \
    --template "${robot_root}/config/ros/nav2.params.yaml.template" \
    --software-only
  echo "ROS software preflight passed without opening LiDAR or actuator devices"
  exit 0
fi

if [ ! -r "${lidar_device}" ]; then
  echo "LiDAR device is not readable: ${lidar_device}" >&2
  exit 1
fi
for transform_name in \
  ROKI_LIDAR_X_M ROKI_LIDAR_Y_M ROKI_LIDAR_Z_M ROKI_LIDAR_YAW_RAD; do
  transform_value="${!transform_name:-}"
  if [[ ! "${transform_value}" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
    echo "Field measurement is missing or invalid: ${transform_name}" >&2
    exit 1
  fi
done

if [ "${mode}" = patrol ]; then
  map_yaml="${ROKI_MAP_YAML:-}"
  if [[ "${map_yaml}" != /* ]] || [ ! -s "${map_yaml}" ]; then
    echo "ROKI_MAP_YAML must point to a readable absolute map YAML" >&2
    exit 1
  fi
  "${python_bin}" -m aiot_robot.ros_config \
    --template "${robot_root}/config/ros/nav2.params.yaml.template" \
    --output "${AIOT_NAV2_RENDERED_CONFIG:-/run/aiot/nav2.params.yaml}"
fi
echo "ROS ${mode} preflight passed without opening the ESP32 serial device"
