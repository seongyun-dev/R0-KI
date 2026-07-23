#!/usr/bin/env bash
set -euo pipefail

deploy_dir="${DEPLOY_DIR:-/srv/aiot/deploy}"
compose_file="${COMPOSE_TARGET:-/srv/aiot/compose/compose.application.yaml}"
current_env="${deploy_dir}/current.env"
previous_env="${deploy_dir}/previous.env"
previous_compose="${deploy_dir}/previous-compose.yaml"
current_manifest="${deploy_dir}/release-manifest.json"
previous_manifest="${deploy_dir}/previous-release-manifest.json"
release_history_dir="${deploy_dir}/releases"
health_check_script="${HEALTH_CHECK_SCRIPT:-${deploy_dir}/health-check.sh}"
release_manifest_script="${RELEASE_MANIFEST_SCRIPT:-${deploy_dir}/release-manifest.py}"
action="${1:-automatic}"
shift || true

test -r "${compose_file}"
test -r "${release_manifest_script}"
install -d -m 2770 "${release_history_dir}"

if [ "${ROLLBACK_FROM_DEPLOY:-false}" != true ]; then
  exec 9>"${deploy_dir}/deploy.lock"
  flock -n 9 || { echo "A deployment is running" >&2; exit 1; }
fi
exec 8>"${deploy_dir}/rollback.lock"
flock -n 8 || { echo "Another rollback is running" >&2; exit 1; }

temporary_files=()
cleanup() {
  local path
  for path in "${temporary_files[@]:-}"; do
    rm -f "${path}"
  done
}
trap cleanup EXIT

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

contains_service() {
  local candidate="$1"
  shift
  local existing
  for existing in "$@"; do
    if [ "${candidate}" = "${existing}" ]; then return 0; fi
  done
  return 1
}

resolve_release() {
  local selector="$1"
  local candidate
  if [ -f "${selector}" ]; then
    candidate="${selector}"
  else
    candidate="${release_history_dir}/${selector%.json}.json"
  fi
  test -r "${candidate}" || {
    echo "Release manifest not found: ${selector}" >&2
    return 1
  }
  python3 "${release_manifest_script}" validate "${candidate}" >/dev/null
  printf '%s\n' "${candidate}"
}

restore_manifest_snapshot() {
  if [ -f "${previous_manifest}" ]; then
    cp "${previous_manifest}" "${current_manifest}"
  else
    rm -f "${current_manifest}"
  fi
}

automatic_rollback() {
  local rollback_services=("$@")
  local failed_services=()
  local previous_services=()
  local service

  mapfile -t failed_services < <(enabled_services_from_env "${current_env}")
  if [ "${#rollback_services[@]}" -eq 0 ]; then
    rollback_services=("${failed_services[@]}")
  fi
  for service in "${rollback_services[@]}"; do
    case "${service}" in frontend|backend) ;; *) echo "Unknown component: ${service}" >&2; return 1 ;; esac
  done

  if [ ! -f "${previous_compose}" ]; then
    echo "No previous Compose configuration is available" >&2
    return 1
  fi

  if [ ! -f "${previous_env}" ]; then
    for service in "${rollback_services[@]}"; do
      if contains_service "${service}" "${failed_services[@]}"; then
        docker compose --env-file "${current_env}" -f "${compose_file}" rm -sf "${service}" || true
      fi
    done
    cp "${previous_compose}" "${compose_file}"
    rm -f "${current_env}"
    restore_manifest_snapshot
    echo "Failed first deployment was removed"
    return 0
  fi

  mapfile -t previous_services < <(enabled_services_from_env "${previous_env}")
  for service in "${rollback_services[@]}"; do
    if ! contains_service "${service}" "${previous_services[@]}"; then
      docker compose --env-file "${current_env}" -f "${compose_file}" rm -sf "${service}" || true
    fi
  done

  cp "${previous_compose}" "${compose_file}"
  cp "${previous_env}" "${current_env}"
  restore_manifest_snapshot

  restored_services=()
  for service in "${rollback_services[@]}"; do
    if contains_service "${service}" "${previous_services[@]}"; then
      restored_services+=("${service}")
    fi
  done
  if [ "${#restored_services[@]}" -gt 0 ]; then
    docker compose --env-file "${current_env}" -f "${compose_file}" up -d "${restored_services[@]}"
    bash "${health_check_script}" application "${restored_services[@]}"
  fi
  echo "Automatic component rollback completed: ${rollback_services[*]}"
}

write_env_from_values() {
  local output="$1"
  umask 0027
  cat >"${output}" <<EOF
DEPLOY_BRANCH=${DEPLOY_BRANCH:-manual-rollback}
DEPLOY_COMMIT=${DEPLOY_COMMIT:-}
FRONTEND_ENABLED=${FRONTEND_ENABLED:-false}
FRONTEND_IMAGE=${FRONTEND_IMAGE:-}
FRONTEND_COMMIT=${FRONTEND_COMMIT:-}
FRONTEND_BRANCH=${FRONTEND_BRANCH:-}
BACKEND_ENABLED=${BACKEND_ENABLED:-false}
BACKEND_IMAGE=${BACKEND_IMAGE:-}
BACKEND_COMMIT=${BACKEND_COMMIT:-}
BACKEND_BRANCH=${BACKEND_BRANCH:-}
DATABASE_SCHEMA=${DATABASE_SCHEMA:-}
BACKEND_HEALTH_URL=${BACKEND_HEALTH_URL:-http://127.0.0.1:8080/swagger-ui.html}
FRONTEND_HEALTH_URL=${FRONTEND_HEALTH_URL:-http://127.0.0.1:3000/}
EOF
}

record_manual_release() {
  local components="$1"
  local seed_manifest="${2:-${current_manifest}}"
  local previous_args=()
  local manifest_commit="${CI_COMMIT_SHA:-}"
  if [ -r "${seed_manifest}" ]; then previous_args=(--previous "${seed_manifest}"); fi
  if [ -z "${manifest_commit}" ]; then
    # shellcheck disable=SC1090
    source "${current_env}"
    manifest_commit="${DEPLOY_COMMIT:-}"
  fi
  python3 "${release_manifest_script}" write \
    --env "${current_env}" \
    --output "${current_manifest}" \
    --history-dir "${release_history_dir}" \
    "${previous_args[@]}" \
    --infra-commit "${manifest_commit}" \
    --pipeline-id "${CI_PIPELINE_ID:-manual}" \
    --job-id "${CI_JOB_ID:-$$}" \
    --components "${components}" \
    --integration-status legacy >/dev/null
}

manual_component_rollback() {
  local component="$1"
  local selector="$2"
  local saved_env="${deploy_dir}/.rollback-current.env.$$"
  local target_env="${deploy_dir}/.rollback-target.env.$$"
  local saved_manifest="${deploy_dir}/.rollback-current.manifest.$$"
  local source_manifest=""
  temporary_files+=("${saved_env}" "${target_env}" "${saved_manifest}")
  test -r "${current_env}"
  cp "${current_env}" "${saved_env}"
  if [ -f "${current_manifest}" ]; then cp "${current_manifest}" "${saved_manifest}"; fi

  if source_manifest="$(resolve_release "${selector}" 2>/dev/null)"; then
    python3 "${release_manifest_script}" export-env "${source_manifest}" --output "${target_env}"
  else
    if [ "${component}" = frontend ]; then
      case "${selector}" in
        *:front-[0-9a-f]*) ;;
        *) echo "Frontend rollback requires a front- immutable image tag" >&2; return 1 ;;
      esac
    else
      case "${selector}" in
        *:back-[0-9a-f]*) ;;
        *) echo "Backend rollback requires a back- immutable image tag" >&2; return 1 ;;
      esac
    fi
    cp "${saved_env}" "${target_env}"
  fi

  # shellcheck disable=SC1090
  source "${saved_env}"
  local current_frontend_enabled="${FRONTEND_ENABLED:-false}"
  local current_frontend_image="${FRONTEND_IMAGE:-}"
  local current_frontend_commit="${FRONTEND_COMMIT:-}"
  local current_frontend_branch="${FRONTEND_BRANCH:-}"
  local current_backend_enabled="${BACKEND_ENABLED:-false}"
  local current_backend_image="${BACKEND_IMAGE:-}"
  local current_backend_commit="${BACKEND_COMMIT:-}"
  local current_backend_branch="${BACKEND_BRANCH:-}"

  if [ -n "${source_manifest}" ]; then
    # shellcheck disable=SC1090
    source "${target_env}"
    if [ "${component}" = frontend ]; then
      test "${FRONTEND_ENABLED:-false}" = true
      current_frontend_enabled=true
      current_frontend_image="${FRONTEND_IMAGE}"
      current_frontend_commit="${FRONTEND_COMMIT}"
      current_frontend_branch="${FRONTEND_BRANCH}"
    else
      test "${BACKEND_ENABLED:-false}" = true
      current_backend_enabled=true
      current_backend_image="${BACKEND_IMAGE}"
      current_backend_commit="${BACKEND_COMMIT}"
      current_backend_branch="${BACKEND_BRANCH}"
    fi
  else
    local short_commit="${selector##*-}"
    if [ "${component}" = frontend ]; then
      current_frontend_enabled=true
      current_frontend_image="${selector}"
      current_frontend_commit="${short_commit}"
      current_frontend_branch=manual-rollback
    else
      current_backend_enabled=true
      current_backend_image="${selector}"
      current_backend_commit="${short_commit}"
      current_backend_branch=manual-rollback
    fi
  fi

  # Reload common values, then deliberately replace only the selected component.
  # shellcheck disable=SC1090
  source "${saved_env}"
  FRONTEND_ENABLED="${current_frontend_enabled}"
  FRONTEND_IMAGE="${current_frontend_image}"
  FRONTEND_COMMIT="${current_frontend_commit}"
  FRONTEND_BRANCH="${current_frontend_branch}"
  BACKEND_ENABLED="${current_backend_enabled}"
  BACKEND_IMAGE="${current_backend_image}"
  BACKEND_COMMIT="${current_backend_commit}"
  BACKEND_BRANCH="${current_backend_branch}"
  DEPLOY_BRANCH=manual-rollback
  write_env_from_values "${current_env}.tmp"
  mv "${current_env}.tmp" "${current_env}"

  cp "${saved_env}" "${previous_env}"
  if [ -f "${saved_manifest}" ]; then cp "${saved_manifest}" "${previous_manifest}"; fi
  if ! docker compose --env-file "${current_env}" -f "${compose_file}" up -d "${component}" || \
     ! bash "${health_check_script}" application "${component}"; then
    cp "${saved_env}" "${current_env}"
    if [ -f "${saved_manifest}" ]; then cp "${saved_manifest}" "${current_manifest}"; fi
    docker compose --env-file "${current_env}" -f "${compose_file}" up -d "${component}"
    bash "${health_check_script}" application "${component}"
    echo "Requested rollback failed; original ${component} was restored" >&2
    return 1
  fi
  record_manual_release "${component}" "${saved_manifest}"
  echo "Manual ${component} rollback completed: ${selector}"
}

manual_release_rollback() {
  local selector="$1"
  local source_manifest
  source_manifest="$(resolve_release "${selector}")"
  local saved_env="${deploy_dir}/.rollback-current.env.$$"
  local target_env="${deploy_dir}/.rollback-target.env.$$"
  local saved_manifest="${deploy_dir}/.rollback-current.manifest.$$"
  temporary_files+=("${saved_env}" "${target_env}" "${saved_manifest}")
  test -r "${current_env}"
  cp "${current_env}" "${saved_env}"
  mapfile -t saved_services < <(enabled_services_from_env "${saved_env}")
  if [ -f "${current_manifest}" ]; then cp "${current_manifest}" "${saved_manifest}"; fi
  python3 "${release_manifest_script}" export-env "${source_manifest}" --output "${target_env}"
  cp "${target_env}" "${current_env}"
  mapfile -t target_services < <(enabled_services_from_env "${current_env}")
  if [ "${#target_services[@]}" -eq 0 ]; then
    echo "The target release has no application services" >&2
    return 1
  fi
  for service in "${saved_services[@]}"; do
    if ! contains_service "${service}" "${target_services[@]}"; then
      docker compose --env-file "${saved_env}" -f "${compose_file}" rm -sf "${service}" || true
    fi
  done
  cp "${saved_env}" "${previous_env}"
  if [ -f "${saved_manifest}" ]; then cp "${saved_manifest}" "${previous_manifest}"; fi
  if ! docker compose --env-file "${current_env}" -f "${compose_file}" up -d "${target_services[@]}" || \
     ! bash "${health_check_script}" application "${target_services[@]}"; then
    cp "${saved_env}" "${current_env}"
    if [ -f "${saved_manifest}" ]; then cp "${saved_manifest}" "${current_manifest}"; fi
    docker compose --env-file "${current_env}" -f "${compose_file}" up -d "${saved_services[@]}"
    bash "${health_check_script}" application "${saved_services[@]}"
    echo "Requested release rollback failed; original release was restored" >&2
    return 1
  fi
  record_manual_release "frontend,backend" "${source_manifest}"
  echo "Full release rollback completed: ${selector}"
}

case "${action}" in
  automatic)
    automatic_rollback "$@"
    ;;
  frontend|backend)
    if [ "$#" -ne 1 ]; then
      echo "usage: rollback.sh ${action} <release-id|manifest-path|immutable-image>" >&2
      exit 1
    fi
    manual_component_rollback "${action}" "$1"
    ;;
  release)
    if [ "$#" -ne 1 ]; then
      echo "usage: rollback.sh release <release-id|manifest-path>" >&2
      exit 1
    fi
    manual_release_rollback "$1"
    ;;
  *)
    echo "usage: rollback.sh [automatic [frontend|backend]...]|frontend <target>|backend <target>|release <target>" >&2
    exit 1
    ;;
esac
