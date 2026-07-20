#!/usr/bin/env bash
set -euo pipefail

deploy_dir=/srv/aiot/deploy
compose_file=/srv/aiot/compose/compose.application.yaml
current_env="${deploy_dir}/current.env"
previous_env="${deploy_dir}/previous.env"
previous_compose="${deploy_dir}/previous-compose.yaml"

if [ ! -f "${previous_compose}" ]; then
  echo "No previous Compose configuration is available" >&2
  exit 1
fi

if [ ! -f "${previous_env}" ]; then
  if [ -f "${current_env}" ]; then
    docker compose --env-file "${current_env}" -f "${compose_file}" down || true
  fi
  cp "${previous_compose}" "${compose_file}"
  rm -f "${current_env}"
  echo "Failed first deployment was removed"
  exit 0
fi

cp "${previous_compose}" "${compose_file}"
cp "${previous_env}" "${current_env}"
docker compose --env-file "${current_env}" -f "${compose_file}" up -d
"${deploy_dir}/health-check.sh" application
echo "Rollback completed"
