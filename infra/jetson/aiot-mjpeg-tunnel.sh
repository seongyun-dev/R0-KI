#!/usr/bin/env bash
set -euo pipefail

config_file="${AIOT_STREAM_ENV:-/opt/aiot/secrets/stream.env}"
credential_dir="${CREDENTIALS_DIRECTORY:-}"
key_file="${MJPEG_TUNNEL_KEY_FILE:-${credential_dir:+${credential_dir}/stream_tunnel_ed25519}}"
known_hosts_file="${MJPEG_TUNNEL_KNOWN_HOSTS:-${credential_dir:+${credential_dir}/stream_known_hosts}}"
key_file="${key_file:-/opt/aiot/secrets/stream_tunnel_ed25519}"
known_hosts_file="${known_hosts_file:-/opt/aiot/secrets/stream_known_hosts}"

if [ "${AIOT_STREAM_CONFIG_LOADED:-false}" != true ]; then
  test -r "${config_file}" || {
    echo "MJPEG tunnel config is missing: ${config_file}" >&2
    exit 1
  }
  # shellcheck disable=SC1090
  source "${config_file}"
fi

tunnel_user="${MJPEG_TUNNEL_USER:-}"
tunnel_host="${MJPEG_TUNNEL_HOST:-}"
remote_port="${MJPEG_TUNNEL_REMOTE_PORT:-}"
local_host="${MJPEG_LOCAL_HOST:-127.0.0.1}"
local_port="${MJPEG_LOCAL_PORT:-8090}"

[[ "${tunnel_user}" =~ ^[a-z_][a-z0-9_-]*$ ]] || {
  echo "MJPEG_TUNNEL_USER is invalid" >&2
  exit 1
}
[[ "${tunnel_host}" =~ ^[A-Za-z0-9.-]+$ ]] || {
  echo "MJPEG_TUNNEL_HOST is invalid" >&2
  exit 1
}
for port in "${remote_port}" "${local_port}"; do
  [[ "${port}" =~ ^[0-9]+$ ]] && [ "${port}" -ge 1 ] && [ "${port}" -le 65535 ] || {
    echo "MJPEG tunnel port is invalid: ${port}" >&2
    exit 1
  }
done
test -r "${key_file}" || {
  echo "MJPEG tunnel private key is missing: ${key_file}" >&2
  exit 1
}
test -r "${known_hosts_file}" || {
  echo "MJPEG tunnel known_hosts is missing: ${known_hosts_file}" >&2
  exit 1
}

exec /usr/bin/ssh -NT \
  -i "${key_file}" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="${known_hosts_file}" \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=3 \
  -R "127.0.0.1:${remote_port}:${local_host}:${local_port}" \
  "${tunnel_user}@${tunnel_host}"
