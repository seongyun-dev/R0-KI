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
robot_journal_cursor="$({
  journalctl -u aiot-robot.service -n 0 --show-cursor --no-pager 2>/dev/null \
    || true
} | sed -n 's/^-- cursor: //p' | tail -n 1)"
systemctl start aiot-robot.service
systemctl is-active --quiet aiot-ros.service
systemctl is-active --quiet aiot-robot.service

esp32_ready=false
for _ in $(seq 1 20); do
  if [ -n "${robot_journal_cursor}" ]; then
    robot_logs="$(
      journalctl -u aiot-robot.service \
        --after-cursor "${robot_journal_cursor}" --no-pager -o cat 2>/dev/null \
        || true
    )"
  else
    robot_logs="$(
      journalctl -u aiot-robot.service --since '30 seconds ago' \
        --no-pager -o cat 2>/dev/null || true
    )"
  fi
  if grep -q 'ESP32_HANDSHAKE_READY' <<<"${robot_logs}"; then
    esp32_ready=true
    break
  fi
  if grep -q 'ENCODER_ZERO_HANDSHAKE_FAILED' <<<"${robot_logs}"; then
    break
  fi
  sleep 1
done
if [ "${esp32_ready}" != true ]; then
  echo "ESP32 STOP/HELLO/ENCODER_ZERO handshake did not become ready." >&2
  echo "Mapping remains stopped; inspect aiot-robot.service logs." >&2
  exit 1
fi

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
