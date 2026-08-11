#!/usr/bin/env bash
set -euo pipefail

phase="${1:-pre-activate}"
case "${phase}" in
  pre-activate|post-activate) ;;
  *) echo "usage: smoke-test.sh [pre-activate|post-activate]" >&2; exit 2 ;;
esac

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${robot_root}/.venv/bin/python"
environment_parser="${robot_root}/scripts/parse_systemd_env.py"
robot_env="${AIOT_ROBOT_ENV_FILE:-/opt/aiot/secrets/robot.env}"
ros_env="${AIOT_ROS_ENV_FILE:-/opt/aiot/secrets/ros.env}"
current_map_env="${AIOT_ACTIVE_MAP_ENV_FILE:-/var/lib/aiot/config/current-map.env}"

# OTA smoke runs outside systemd. Load the same files in the same order as
# aiot-robot.service so mapping/patrol mode and geometry are validated against
# the configuration that will actually run after activation.
test -x "${python_bin}"
test -r "${environment_parser}"
shopt -s lastpipe

load_environment_file() {
  local environment_file="$1"
  local required="$2"
  local assignment
  local -a assignments=()

  if [ ! -r "${environment_file}" ]; then
    if [ "${required}" = true ]; then
      echo "Required environment file is not readable: ${environment_file}" >&2
      return 1
    fi
    return 0
  fi

  if ! "${python_bin}" -B "${environment_parser}" "${environment_file}" |
    while IFS= read -r -d '' assignment; do
      assignments+=("${assignment}")
    done
  then
    return 1
  fi

  for assignment in "${assignments[@]}"; do
    export "${assignment}"
  done
}

load_environment_file "${robot_env}" false
load_environment_file "${ros_env}" true
# aiot-robot.service and aiot-ros.service load this drop-in last.  Without it,
# smoke tests can accidentally validate stale mapping mode while systemd starts
# the patrol/Nav2 mode selected by the newly activated Backend map bundle.
load_environment_file "${current_map_env}" false

ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
test -r "${ros_setup}"
test -x "${robot_root}/scripts/run.sh"

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

explore_setup="${AIOT_EXPLORE_SETUP_FILE:-${robot_root}/ros-overlay/install/setup.bash}"
test -r "${explore_setup}"
set +u
# shellcheck disable=SC1090
source "${explore_setup}"
set -u

explore_prefix="$(ros2 pkg prefix explore_lite)"
case "${explore_prefix}" in
  "${robot_root}"/ros-overlay/install*) ;;
  *) echo "Release-local explore overlay is not active: ${explore_prefix}" >&2; exit 1 ;;
esac

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export ROS_HOME="${ROS_HOME:-/var/lib/aiot/ros}"
export ROS_LOG_DIR="${ROS_LOG_DIR:-${ROS_HOME}/log}"
mkdir -p "${ROS_LOG_DIR}"
export PYTHONPATH="${robot_root}/src:${robot_root}/roki:${robot_root}/roki-iot${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONDONTWRITEBYTECODE=1
"${python_bin}" -B -m aiot_robot.smoke
"${python_bin}" -B -m aiot_robot.ros_smoke
"${python_bin}" -B -m aiot_robot.ros_config \
  --template "${robot_root}/config/ros/nav2.params.yaml.template" \
  --software-only
"${python_bin}" -B "${robot_root}/roki-iot/run_integrated.py" --check
echo "Robot ${phase} smoke passed; no actuator command was sent"
