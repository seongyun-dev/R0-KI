#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "map activation must run as root" >&2
  exit 1
fi

request_file="${AIOT_MAP_ACTIVATION_REQUEST_FILE:-/var/lib/aiot/state/map-activation.pending}"
environment_file="${AIOT_ACTIVE_MAP_ENV_FILE:-/var/lib/aiot/config/current-map.env}"

# Path units can fire again after a successful removal. Treat no request as done.
[ -e "${request_file}" ] || exit 0
test -s "${request_file}"
test -s "${environment_file}"

for required_name in \
  AIOT_ROS_MODE \
  ROKI_MAP_YAML \
  ROKI_MAP_ID \
  ROKI_MAP_VERSION \
  ROKI_MAP_SHA256; do
  grep -Eq "^${required_name}=\"[^\"]+\"$" "${environment_file}"
done
grep -q '^AIOT_ROS_MODE="patrol"$' "${environment_file}"

# Give the mapping worker enough time to publish its successful command ACK
# before this script intentionally restarts its owning Robot process.
sleep "${AIOT_MAP_ACTIVATION_GRACE_SEC:-2}"

# Robot depends on the ROS stack, so quiesce it before replacing mapping with Nav2.
systemctl stop aiot-robot.service
systemctl restart aiot-ros.service
systemctl is-active --quiet aiot-ros.service
systemctl restart aiot-robot.service
systemctl is-active --quiet aiot-robot.service

# Retain the marker on any failure so systemd retries the same accepted map.
rm -f -- "${request_file}"
echo "Accepted map activated; Nav2 and Robot services are running"
