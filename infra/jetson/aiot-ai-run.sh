#!/usr/bin/env bash
set -euo pipefail

ai_root="${AIOT_AI_ROOT:-/home/e103/yolo-pipeline}"
python_bin="${AIOT_AI_PYTHON:-${ai_root}/venv/bin/python}"
pipeline_main="${AIOT_AI_PIPELINE_MAIN:-${ai_root}/yolo_pipeline/main.py}"
robot_root="${AIOT_IOT_CURRENT:-/opt/aiot/iot/current}/robot"
ros_setup="${ROS_SETUP_FILE:-/opt/ros/humble/setup.bash}"
camera_left="${AIOT_AI_CAMERA_LEFT_DEVICE:-${AIOT_AI_CAMERA_FRONT_DEVICE:-${AIOT_AI_CAMERA_DEVICE:-}}}"
camera_right="${AIOT_AI_CAMERA_RIGHT_DEVICE:-${AIOT_AI_CAMERA_REAR_DEVICE:-}}"
capture_width="${AIOT_AI_CAPTURE_WIDTH:-640}"
capture_height="${AIOT_AI_CAPTURE_HEIGHT:-480}"
capture_fps="${AIOT_AI_CAPTURE_FPS:-30}"
capture_fourcc="${AIOT_AI_CAPTURE_FOURCC:-MJPG}"
capture_buffer_size="${AIOT_AI_CAPTURE_BUFFER_SIZE:-1}"
pipeline_extra_args="${AIOT_AI_PIPELINE_EXTRA_ARGS:---no-show}"

for integer_value in "${capture_width}" "${capture_height}" "${capture_buffer_size}"; do
  if [[ ! "${integer_value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "AI capture dimensions and buffer size must be positive integers" >&2
    exit 1
  fi
done
if [[ ! "${capture_fps}" =~ ^[0-9]+([.][0-9]+)?$ ]] || \
   [[ ! "${capture_fourcc}" =~ ^[[:alnum:]]{4}$ ]]; then
  echo "AI capture FPS or FOURCC is invalid" >&2
  exit 1
fi

configure_camera() {
  local device="$1"
  [ -n "${device}" ] || return 0
  if ! command -v v4l2-ctl >/dev/null 2>&1; then
    echo "v4l2-ctl is required for configured USB cameras" >&2
    exit 1
  fi
  v4l2-ctl --device "${device}" \
    --set-fmt-video="width=${capture_width},height=${capture_height},pixelformat=${capture_fourcc}" \
    --set-parm="${capture_fps}" >/dev/null
}

configure_camera "${camera_left}"
configure_camera "${camera_right}"

set +u
# shellcheck disable=SC1090
source "${ros_setup}"
set -u

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export PYTHONUNBUFFERED=1
umask 0007

cd "${ai_root}"
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
args=()
if [ -n "${camera_left}" ]; then
  args+=(--source-a "${camera_left}")
fi
if [ -n "${camera_right}" ]; then
  args+=(--source-b "${camera_right}")
fi
if [ -n "${pipeline_extra_args}" ]; then
  read -r -a extra_args <<<"${pipeline_extra_args}"
  args+=("${extra_args[@]}")
fi
exec "${python_bin}" -m aiot_robot.ai_runtime \
  --pipeline-main "${pipeline_main}" \
  --capture-width "${capture_width}" \
  --capture-height "${capture_height}" \
  --capture-fps "${capture_fps}" \
  --capture-fourcc "${capture_fourcc}" \
  --capture-buffer-size "${capture_buffer_size}" \
  "${args[@]}"
