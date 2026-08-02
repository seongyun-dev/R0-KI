#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
ydlidar_setup="${AIOT_YDLIDAR_SETUP_FILE:-/home/e103/ydlidar_ws/install/setup.bash}"
rf2o_setup="${AIOT_RF2O_SETUP_FILE:-/home/e103/rf2o_ws/install/setup.bash}"
mode="${AIOT_ROS_MODE:-patrol}"

"${robot_root}/scripts/ros-preflight.sh"
for setup_file in "${ros_setup}" "${ydlidar_setup}" "${rf2o_setup}"; do
  set +u
  # shellcheck disable=SC1090
  source "${setup_file}"
  set -u
done

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export RCUTILS_LOGGING_BUFFERED_STREAM=1

declare -a child_pids=()
stopping=false
start_component() {
  "$@" &
  child_pids+=("$!")
}
stop_components() {
  if [ "${stopping}" = true ]; then
    return
  fi
  stopping=true
  if [ "${#child_pids[@]}" -gt 0 ]; then
    kill -INT "${child_pids[@]}" 2>/dev/null || true
    for child_pid in "${child_pids[@]}"; do
      wait "${child_pid}" 2>/dev/null || true
    done
  fi
}
trap stop_components INT TERM EXIT

start_component ros2 run ydlidar_ros2_driver ydlidar_ros2_driver_node \
  --ros-args --params-file "${robot_root}/config/ros/ydlidar.yaml"
start_component ros2 run tf2_ros static_transform_publisher \
  --x "${ROKI_LIDAR_X_M}" --y "${ROKI_LIDAR_Y_M}" \
  --z "${ROKI_LIDAR_Z_M}" --yaw "${ROKI_LIDAR_YAW_RAD}" \
  --pitch 0 --roll 0 --frame-id base_link --child-frame-id laser_frame
start_component ros2 run rf2o_laser_odometry rf2o_laser_odometry_node \
  --ros-args --params-file "${robot_root}/config/ros/rf2o.yaml"

if [ "${mode}" = mapping ]; then
  start_component ros2 launch slam_toolbox online_async_launch.py \
    use_sim_time:=false \
    slam_params_file:="${robot_root}/config/ros/slam_toolbox.yaml"
else
  start_component ros2 launch nav2_bringup bringup_launch.py \
    slam:=False use_sim_time:=false autostart:=true use_composition:=False \
    map:="${ROKI_MAP_YAML}" \
    params_file:="${AIOT_NAV2_RENDERED_CONFIG:-/run/aiot/nav2.params.yaml}"
fi

set +e
wait -n "${child_pids[@]}"
component_status=$?
set -e
if [ "${component_status}" -eq 0 ]; then
  echo "A required ROS component exited unexpectedly" >&2
  component_status=1
fi
exit "${component_status}"
