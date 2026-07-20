#!/usr/bin/env bash
set -euo pipefail

runtime_env="${RUNTIME_ENV:-/srv/aiot/secrets/runtime.env}"
backup_root="${BACKUP_ROOT:-/srv/aiot/backups/runtime}"
timestamp="$(date +%Y%m%d-%H%M%S)"
target="${backup_root}/${timestamp}"
partial="${backup_root}/.partial-${timestamp}"

test -r "${runtime_env}"
# shellcheck disable=SC1090
source "${runtime_env}"

install -d -m 0750 "${backup_root}"
exec 9>"${backup_root}/.backup.lock"
flock -n 9 || { echo "Another backup is running" >&2; exit 1; }

if [ -e "${target}" ] || [ -e "${partial}" ]; then
  echo "Backup target already exists: ${timestamp}" >&2
  exit 1
fi

umask 0027
install -d -m 0750 "${partial}"
cleanup() {
  if [[ "${partial}" == "${backup_root}/.partial-"* ]] && [ -d "${partial}" ]; then
    find "${partial}" -depth -delete
  fi
}
trap cleanup EXIT

docker exec \
  -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" \
  aiot-mysql mysqldump -uroot --single-transaction --routines --events \
  "${MYSQL_DATABASE}" >"${partial}/mysql.sql"

tar -C /srv/aiot/data -czf "${partial}/files.tar.gz" uploads maps
tar -C /srv/aiot -czf "${partial}/mqtt.tar.gz" config/mosquitto data/mosquitto
cp -a /srv/aiot/deploy/current.env "${partial}/current.env" 2>/dev/null || true
printf 'created_at=%s\nhost=%s\ndatabase=%s\n' \
  "$(date --iso-8601=seconds)" "$(hostname)" "${MYSQL_DATABASE}" \
  >"${partial}/METADATA"

(
  cd "${partial}"
  find . -maxdepth 1 -type f ! -name SHA256SUMS ! -name COMPLETED -print0 | \
    LC_ALL=C sort -z | xargs -0 sha256sum >SHA256SUMS
  sha256sum --check --status SHA256SUMS
)
printf 'verified_at=%s\n' "$(date --iso-8601=seconds)" >"${partial}/COMPLETED"

mv "${partial}" "${target}"
latest_next="${backup_root}/.latest.$$"
ln -s "${timestamp}" "${latest_next}"
mv -Tf "${latest_next}" "${backup_root}/latest"

find "${backup_root}" -mindepth 1 -maxdepth 1 -type d \
  -name '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-*' \
  -mtime +7 -print
echo "Verified backup created at ${target}; backups older than 7 days are listed only"
