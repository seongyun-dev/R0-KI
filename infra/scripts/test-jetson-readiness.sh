#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d /tmp/aiot-readiness-test.XXXXXX)"
cleanup() {
  if [[ "${test_root}" == /tmp/aiot-readiness-test.* ]]; then
    find "${test_root}" -depth -delete
  fi
}
trap cleanup EXIT

grep -q 'SYMLINK+="roki_camera_left"' \
  "${repository_root}/infra/jetson/99-roki-cameras.rules"
grep -q 'SYMLINK+="roki_camera_right"' \
  "${repository_root}/infra/jetson/99-roki-cameras.rules"
grep -q 'ATTR{index}=="0"' \
  "${repository_root}/infra/jetson/99-roki-cameras.rules"
grep -q 'ConditionPathExists=/opt/aiot/secrets/ros.env' \
  "${repository_root}/infra/jetson/aiot-ros.service"
grep -Eq '^Wants=.*aiot-ros.service' \
  "${repository_root}/infra/jetson/aiot-robot.service"
grep -q '^User=e103$' \
  "${repository_root}/infra/jetson/aiot-robot.service"
grep -Eq '^SupplementaryGroups=.*aiot' \
  "${repository_root}/infra/jetson/aiot-robot.service"
grep -q 'fixed_resolution: true' \
  "${repository_root}/robot/config/ros/ydlidar.yaml"
grep -q 'support_motor_dtr: false' \
  "${repository_root}/robot/config/ros/ydlidar.yaml"
grep -q 'frequency: 10.0' \
  "${repository_root}/robot/config/ros/ydlidar.yaml"
grep -q -- '-r __node:=rf2o_laser_odometry' \
  "${repository_root}/robot/scripts/run-ros.sh"
grep -q 'use_rotate_to_heading: false' \
  "${repository_root}/robot/config/ros/nav2.params.yaml.template"
grep -q 'motion_model_for_search: DUBIN' \
  "${repository_root}/robot/config/ros/nav2.params.yaml.template"
grep -q 'export PYTHONPATH="${robot_root}/src' \
  "${repository_root}/robot/scripts/ros-preflight.sh"
grep -q 'export PYTHONPATH="${robot_root}/src' \
  "${repository_root}/robot/scripts/mqtt-e2e-check.sh"
! grep -qE 'ROKI_(WHEELBASE_M|ROBOT_RADIUS_M)=[0-9]' \
  "${repository_root}/infra/jetson/ros.env.example"

install -d "${test_root}/bin" "${test_root}/ai/yolo_pipeline" "${test_root}/current"
install -m 0644 /dev/null "${test_root}/ros-setup.bash"
install -m 0644 /dev/null "${test_root}/ai/yolo_pipeline/main.py"

cat >"${test_root}/bin/v4l2-ctl" <<'SH'
#!/usr/bin/env bash
printf 'v4l2 %s\n' "$*" >>"${V4L2_LOG:?}"
SH
cat >"${test_root}/bin/python" <<'SH'
#!/usr/bin/env bash
printf 'python %s\n' "$*"
SH
chmod 0755 "${test_root}/bin/v4l2-ctl" "${test_root}/bin/python"

output="$(
  PATH="${test_root}/bin:${PATH}" \
  AIOT_AI_ROOT="${test_root}/ai" \
  AIOT_AI_PYTHON="${test_root}/bin/python" \
  AIOT_AI_PIPELINE_MAIN="${test_root}/ai/yolo_pipeline/main.py" \
  AIOT_IOT_CURRENT="${test_root}/current" \
  ROS_SETUP_FILE="${test_root}/ros-setup.bash" \
  AIOT_AI_CAMERA_LEFT_DEVICE=/dev/roki_camera_left \
  AIOT_AI_CAMERA_RIGHT_DEVICE=/dev/roki_camera_right \
  AIOT_AI_CAPTURE_WIDTH=640 \
  AIOT_AI_CAPTURE_HEIGHT=480 \
  AIOT_AI_CAPTURE_FPS=30 \
  AIOT_AI_CAPTURE_FOURCC=MJPG \
  AIOT_AI_CAPTURE_BUFFER_SIZE=1 \
  V4L2_LOG="${test_root}/v4l2.log" \
  bash "${repository_root}/infra/jetson/aiot-ai-run.sh"
)"
printf '%s\n' "${output}" | grep -q -- '--source-a /dev/roki_camera_left'
printf '%s\n' "${output}" | grep -q -- '--source-b /dev/roki_camera_right'
printf '%s\n' "${output}" | grep -q -- '--capture-width 640'
grep -q -- 'pixelformat=MJPG' "${test_root}/v4l2.log"

echo "Jetson camera, ROS, and field-gate readiness tests passed"
