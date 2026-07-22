#!/usr/bin/env bash
set -euo pipefail

deploy_dir="${DEPLOY_DIR:-/srv/aiot/deploy}"
compose_file="${COMPOSE_TARGET:-/srv/aiot/compose/compose.application.yaml}"
current_env="${deploy_dir}/current.env"
previous_env="${deploy_dir}/previous.env"
previous_compose="${deploy_dir}/previous-compose.yaml"
health_check_script="${HEALTH_CHECK_SCRIPT:-${deploy_dir}/health-check.sh}"

if [ ! -f "${previous_compose}" ]; then
  echo "No previous Compose configuration is available" >&2
  exit 1
fi

enabled_services_from_env() {
  local env_file="$1"
  local services=()
  local FRONTEND_ENABLED=false
  local BACKEND_ENABLED=false

  if [ -f "${env_file}" ]; then
    # shellcheck disable=SC1090
    source "${env_file}"
  fi
  if [ "${FRONTEND_ENABLED:-false}" = true ]; then services+=(frontend); fi
  if [ "${BACKEND_ENABLED:-false}" = true ]; then services+=(backend); fi
  if [ "${#services[@]}" -gt 0 ]; then
    printf '%s\n' "${services[@]}"
  fi
}

mapfile -t failed_services < <(enabled_services_from_env "${current_env}")

if [ ! -f "${previous_env}" ]; then
  if [ -f "${current_env}" ] && [ "${#failed_services[@]}" -gt 0 ]; then
    docker compose --env-file "${current_env}" -f "${compose_file}" \
      rm -sf "${failed_services[@]}" || true
  fi
  cp "${previous_compose}" "${compose_file}"
  rm -f "${current_env}"
  echo "Failed first deployment was removed"
  exit 0
fi

mapfile -t previous_services < <(enabled_services_from_env "${previous_env}")

for failed_service in "${failed_services[@]}"; do
  keep=false
  for previous_service in "${previous_services[@]}"; do
    if [ "${failed_service}" = "${previous_service}" ]; then
      keep=true
      break
    fi
  done
  if [ "${keep}" != true ]; then
    docker compose --env-file "${current_env}" -f "${compose_file}" \
      rm -sf "${failed_service}" || true
  fi
done

cp "${previous_compose}" "${compose_file}"
cp "${previous_env}" "${current_env}"

if [ "${#previous_services[@]}" -gt 0 ]; then
  docker compose --env-file "${current_env}" -f "${compose_file}" \
    up -d "${previous_services[@]}"
  bash "${health_check_script}" application "${previous_services[@]}"
else
  echo "Previous deployment did not contain application components"
fi

echo "Rollback completed"
