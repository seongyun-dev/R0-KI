#!/usr/bin/env bash
set -euo pipefail

echo '===== SYSTEM ====='
hostname
date --iso-8601=seconds
cat /etc/nv_tegra_release 2>/dev/null | head -2 || true
df -h /
free -h

echo '===== USB ====='
lsusb

echo '===== SERIAL BY-ID ====='
ls -l /dev/serial/by-id 2>/dev/null || true

echo '===== SERIAL ATTRIBUTES ====='
for device in /dev/ttyUSB* /dev/ttyACM*; do
  [[ -e "$device" ]] || continue
  echo "--- $device"
  udevadm info --query=property --name="$device" 2>/dev/null \
    | grep -E '^(DEVNAME|ID_VENDOR_ID|ID_MODEL_ID|ID_SERIAL|ID_SERIAL_SHORT|ID_PATH)=' \
    || true
  printf 'ownerPids='
  fuser "$device" 2>/dev/null || true
  echo
done

echo '===== VIDEO DEVICES ====='
v4l2-ctl --list-devices 2>/dev/null || true
for device in /dev/video*; do
  [[ -e "$device" ]] || continue
  echo "--- $device"
  udevadm info --query=property --name="$device" 2>/dev/null \
    | grep -E '^(DEVNAME|ID_VENDOR_ID|ID_MODEL_ID|ID_SERIAL|ID_SERIAL_SHORT|ID_PATH)=' \
    || true
done

echo '===== ROS 2 ====='
if [[ -f /opt/ros/humble/setup.bash ]]; then
  set +u
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
  set -u
  echo "ROS_DISTRO=${ROS_DISTRO:-unknown}"
  ros2 pkg list 2>/dev/null \
    | grep -E 'nav2|slam_toolbox|ydlidar|rf2o|robot_localization|ackermann|steering' \
    | sort || true
fi

echo '===== RELEVANT PROCESSES ====='
ps -eo pid,user,lstart,args --sort=pid \
  | grep -Ei 'roki|robot|mqtt|ros2|ydlidar|slam|nav2|yolo|python' \
  | grep -v grep || true

echo 'FIELD_AUDIT_COMPLETE_NO_MOVEMENT'
