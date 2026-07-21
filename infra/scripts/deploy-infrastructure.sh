#!/usr/bin/env bash
set -euo pipefail

runtime_env=/srv/aiot/secrets/runtime.env
compose_file=/srv/aiot/compose/compose.infrastructure.yaml

test -r "${runtime_env}"
test -r "${compose_file}"

docker compose --env-file "${runtime_env}" -f "${compose_file}" pull
docker compose --env-file "${runtime_env}" -f "${compose_file}" up -d
/srv/aiot/deploy/health-check.sh infrastructure
docker compose --env-file "${runtime_env}" -f "${compose_file}" ps
