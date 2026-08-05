#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" != "--confirm-idle" ]; then
  echo "Usage: sudo aiot-prepare-mapping --confirm-idle" >&2
  echo "Confirm in the Frontend that no patrol or mapping session is active." >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "This command must run as root." >&2
  exit 2
fi

ros_env=/opt/aiot/secrets/ros.env
current_map_env=/var/lib/aiot/config/current-map.env
for required in "${ros_env}" "${current_map_env}"; do
  if [ ! -f "${required}" ]; then
    echo "Required environment file is missing: ${required}" >&2
    exit 1
  fi
done
if [ -e /dev/input/js0 ] && fuser /dev/input/js0 >/dev/null 2>&1; then
  echo "Refusing preparation: the mapping gamepad is already in use." >&2
  fuser -v /dev/input/js0 >&2 || true
  exit 1
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="/var/lib/aiot/backups/prepare-mapping-${timestamp}"
install -d -m 0700 "${backup_dir}"
cp -a "${ros_env}" "${backup_dir}/ros.env"
cp -a "${current_map_env}" "${backup_dir}/current-map.env"

# Stop the only Serial owner before changing its ROS lifecycle. This emits the
# normal fail-closed STOP path and prevents a stale patrol from surviving the
# operator-confirmed mode change.
systemctl stop aiot-robot.service

set_mode() {
  local file="$1"
  if grep -q '^AIOT_ROS_MODE=' "${file}"; then
    sed -i 's/^AIOT_ROS_MODE=.*/AIOT_ROS_MODE="mapping"/' "${file}"
  else
    printf '\nAIOT_ROS_MODE="mapping"\n' >> "${file}"
  fi
}
set_mode "${ros_env}"
set_mode "${current_map_env}"

systemctl restart aiot-ros.service
systemctl start aiot-robot.service
systemctl is-active --quiet aiot-ros.service
systemctl is-active --quiet aiot-robot.service

slam_ready=false
for _ in $(seq 1 20); do
  if pgrep -f '/slam_toolbox/async_slam_toolbox_node' >/dev/null; then
    slam_ready=true
    break
  fi
  sleep 1
done
if [ "${slam_ready}" != true ]; then
  echo "SLAM Toolbox did not become ready." >&2
  exit 1
fi
if [ -e /dev/input/js0 ] && fuser /dev/input/js0 >/dev/null 2>&1; then
  echo "Gamepad was claimed before START_MAPPING; refusing readiness." >&2
  exit 1
fi

echo "MAPPING_STANDBY_READY"
echo "BACKUP=${backup_dir}"
echo "Start mapping from the Frontend; this script never sends movement."
