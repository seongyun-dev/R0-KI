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
lidar_device="${ROKI_LIDAR_DEVICE:-/dev/roki_lidar}"

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

# 두 운행이 같은 노드 집합으로 도므로 요구 패키지도 하나다.
required_packages=(
  ydlidar_ros2_driver rf2o_laser_odometry tf2_ros slam_toolbox
  nav2_bringup nav2_bt_navigator nav2_controller nav2_smac_planner
)
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
  "${robot_root}/config/ros/nav2_fixed_path.xml" \
  "${robot_root}/config/ros/nav2_mapping_replan.xml"; do
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

# 지도가 지정돼 있으면 두 산출물이 다 있어야 한다.
#
# .pgm/.yaml 은 프론트가 웨이포인트를 그리는 이미지이고, .posegraph/.data 는
# slam_toolbox 가 위치추정에 쓰는 그래프다. 서로 대체하지 못한다. 그리고
# DeserializePoseGraph 는 빈 응답을 주는 서비스라 적재 실패를 알려주지 않으므로
# (2026-08-07 실기 확인) 없는 그래프로 순찰을 시작해도 아무도 모른다.
# 여기서 막는다.
#
# 지도가 아예 없는 상태는 정상이다 -- 첫 매핑 전이 그렇다. 그때는 slam_toolbox
# 가 기본값인 매핑 모드로 뜬다.
map_yaml="${ROKI_MAP_YAML:-}"
if [ -n "${map_yaml}" ]; then
  if [[ "${map_yaml}" != /* ]] || [ ! -s "${map_yaml}" ]; then
    echo "ROKI_MAP_YAML must point to a readable absolute map YAML" >&2
    exit 1
  fi
  # 경고만 한다. 여기서 막으면 부팅이 잠긴다: 포즈그래프 없는 지도로는
  # 순찰할 수 없지만, 스택이 안 뜨면 새로 매핑해서 만들 수도 없다.
  # 실제 차단은 순찰 진입 시점의 LocalizationModeController 가 한다
  # (POSEGRAPH_MISSING). 여기서는 다음 사람이 알아채게만 한다.
  posegraph_base="$(dirname "${map_yaml}")/posegraph"
  for artifact in "${posegraph_base}.posegraph" "${posegraph_base}.data"; do
    test -s "${artifact}" || {
      echo "WARNING: pose graph artifact is missing: ${artifact}" >&2
      echo "WARNING: this map can be displayed but not localized against;" >&2
      echo "WARNING: patrol will refuse until a new mapping run produces one." >&2
      break; }
  done
fi

ROKI_NAV2_MAPPING_BT_XML="${robot_root}/config/ros/nav2_mapping_replan.xml" \
"${python_bin}" -m aiot_robot.ros_config \
  --template "${robot_root}/config/ros/nav2.params.yaml.template" \
  --output "${AIOT_NAV2_RENDERED_CONFIG:-/run/aiot/nav2.params.yaml}"
echo "ROS preflight passed without opening the ESP32 serial device"
