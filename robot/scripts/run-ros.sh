#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
ydlidar_setup="${AIOT_YDLIDAR_SETUP_FILE:-/home/e103/ydlidar_ws/install/setup.bash}"
rf2o_setup="${AIOT_RF2O_SETUP_FILE:-/home/e103/rf2o_ws/install/setup.bash}"
slam_reset_setup="${AIOT_SLAM_TOOLBOX_RESET_SETUP_FILE:-/home/e103/slam-toolbox-2610-reset-backport-ws/install/setup.bash}"

"${robot_root}/scripts/ros-preflight.sh"
for setup_file in "${ros_setup}" "${ydlidar_setup}" "${rf2o_setup}" "${slam_reset_setup}"; do
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
# __node:= 리맵을 주지 않는다. rf2o.yaml 이 `/**` 로 받으므로 필요가 없고,
# 그 리맵이 같은 이름 노드를 둘 만들어 ROS 그래프 조회를 어긋나게 했다
# (2026-08-08 실측, rf2o.yaml 주석 참고).
start_component ros2 run rf2o_laser_odometry rf2o_laser_odometry_node \
  --ros-args --params-file "${robot_root}/config/ros/rf2o.yaml"

# Fail-closed boundary for slam_toolbox only. RF2O and Nav2 keep consuming
# raw /scan; mapping/patrol lifecycle code opens this relay explicitly.
start_component env \
  PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}" \
  "${robot_root}/.venv/bin/python" -m aiot_robot.scan_gate

# 매핑과 순찰이 같은 노드 집합으로 돈다. 예전에는 여기서 launch 파일 자체를
# 갈아 끼웠고, 그래서 모드를 바꾸려면 이 서비스를 재시작해야 했다. 그 재시작이
# 시리얼 소유자인 aiot-robot 까지 끌어내리면서 2026-08-07 에 관측된 고장
# 다섯을 만들었다(전환 3분, 시리얼 폭풍, 핸드셰이크 실패, 세션 고아화,
# 낡은 DDS 데몬 캐시). 이제 전환은 프로세스 교체가 아니라 서비스 호출이다.
#
# map_and_localization 노드는 slam_toolbox/set_localization_mode 로 매핑과
# 위치추정을 오간다. 위치추정 모드는 AMCL 을 대체하므로 map_server 와 amcl 을
# 띄우지 않는다 -- /map 과 map->odom 을 slam_toolbox 가 두 모드 모두에서
# 책임진다. 전환은 roki-iot/integration/localization_mode.py 가 수행한다.
start_component ros2 run slam_toolbox map_and_localization_slam_toolbox_node \
  --ros-args --params-file "${robot_root}/config/ros/slam_toolbox.yaml" \
  -p use_sim_time:=false

# navigation_launch.py 는 위치추정 없는 Nav2 다. 이 구성에 정확히 맞는다.
start_component ros2 launch nav2_bringup navigation_launch.py \
  use_sim_time:=false autostart:=true use_composition:=False \
  params_file:="${AIOT_NAV2_RENDERED_CONFIG:-/run/aiot/nav2.params.yaml}"

# explore_lite 는 여기서 띄우지 않는다. enable/disable API 가 없고 목표가
# 실패한 프론티어를 영구 블랙리스트에 올리므로, 이 서비스와 함께 띄우면 모션
# 게이트가 닫힌 동안 모든 프론티어를 소진하고 서비스 수명 내내 죽어 있다.
# 수명은 매핑 세션에 귀속된다 -- roki-iot/integration/explore_supervisor.py 가
# START_MAPPING 이 게이트를 연 뒤 띄우고 세션이 끝나면 정리한다.

# 자식이 죽었는지 직접 묻는다. wait -n 에 기대지 않는다.
#
# 2026-08-08 관측: slam_toolbox 가 사라진 뒤에도 이 스크립트는 계속 살아 있었다.
# aiot-ros 는 active, NRestarts=0, run-ros.sh 는 그대로. /map 도 map->odom 도
# 없는데 서비스는 정상이라고 보고했고, 매핑과 순찰이 둘 다 조용히 불가능해졌다.
# 아무도 알아채지 못하고 아무것도 복구하지 않는 상태가 서비스 수명 내내 남는다.
#
# 좀비도 죽은 것으로 센다. kill -0 은 아직 회수되지 않은 자식에게 성공을
# 돌려주므로 그것만으로는 구분되지 않는다. /proc 의 State 를 직접 본다.
child_alive() {
  local state
  state="$(sed -n 's/^State:[[:space:]]*\(.\).*/\1/p' "/proc/$1/status" 2>/dev/null)"
  [ -n "${state}" ] && [ "${state}" != "Z" ]
}

# 래퍼만 보면 안 된다.
#
# start_component 가 담는 PID 는 `ros2 run` / `ros2 launch` 의 파이썬 래퍼이고,
# 실제 노드는 그 자식이다. 2026-08-08 실측: slam_toolbox 노드가 사라졌는데
# aiot-ros 는 active, NRestarts=0, run-ros.sh 도 그대로였다 -- 래퍼가 살아 있어서
# 앞의 검사가 "정상"이라고 답했기 때문이다. /map 도 map->odom 도 없는데 서비스는
# 정상으로 보이는 부분 고장이 서비스 수명 내내 남았다.
#
# 그래서 "래퍼가 살아 있고 자식도 하나 이상 있다" 를 살아 있음으로 본다.
# 기동 직후에는 자식이 아직 없으므로 유예를 둔다.
component_alive() {
  local wrapper_pid="$1" child
  child_alive "${wrapper_pid}" || return 1
  for child in $(pgrep -P "${wrapper_pid}" 2>/dev/null); do
    if child_alive "${child}"; then
      return 0
    fi
  done
  return 1
}

component_status=0
dead_pid=""
# 자식이 자리를 잡을 시간. Nav2 launch 는 노드 여덟 개를 순차로 띄운다.
supervision_grace_sec="${AIOT_ROS_SUPERVISION_GRACE_SEC:-45}"
sleep "${supervision_grace_sec}"
while [ -z "${dead_pid}" ]; do
  for child_pid in "${child_pids[@]}"; do
    if ! component_alive "${child_pid}"; then
      dead_pid="${child_pid}"
      break
    fi
  done
  [ -n "${dead_pid}" ] && break
  sleep 2
done

set +e
wait "${dead_pid}"
component_status=$?
set -e
if [ "${component_status}" -eq 0 ]; then
  component_status=1
fi
echo "A required ROS component (pid ${dead_pid}) exited; status ${component_status}" >&2
exit "${component_status}"
