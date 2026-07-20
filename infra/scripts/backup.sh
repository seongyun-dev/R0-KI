#!/usr/bin/env bash
set -euo pipefail

runtime_env=/srv/aiot/secrets/runtime.env
backup_root=/srv/aiot/backups/runtime
timestamp=$(date +%Y%m%d-%H%M%S)
target="${backup_root}/${timestamp}"

test -r "${runtime_env}"
# shellcheck disable=SC1090
source "${runtime_env}"

install -d -m 0750 "${target}"

docker exec \
  -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" \
  aiot-mysql mysqldump -uroot --single-transaction --routines --events "${MYSQL_DATABASE}" \
  >"${target}/mysql.sql"

tar -C /srv/aiot/data -czf "${target}/files.tar.gz" uploads maps
tar -C /srv/aiot -czf "${target}/mqtt.tar.gz" config/mosquitto data/mosquitto
cp -a /srv/aiot/deploy/current.env "${target}/current.env" 2>/dev/null || true
sha256sum "${target}"/* >"${target}/SHA256SUMS"

find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -mtime +7 -print
echo "Backup created at ${target}; old backups are listed but not deleted automatically"
