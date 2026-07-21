#!/usr/bin/env bash
set -euo pipefail

target_branch="${1:-}"
commit_sha="${2:-}"
component_mode="${3:-auto}"
repository_root="${CI_PROJECT_DIR:-$(pwd)}"
deploy_dir="${DEPLOY_DIR:-/srv/aiot/deploy}"
compose_source="${repository_root}/infra/compose/compose.application.yaml"
compose_target="${COMPOSE_TARGET:-/srv/aiot/compose/compose.application.yaml}"
current_env="${deploy_dir}/current.env"
previous_env="${deploy_dir}/previous.env"
previous_compose="${deploy_dir}/previous-compose.yaml"
health_check_script="${repository_root}/infra/scripts/health-check.sh"
rollback_script="${repository_root}/infra/scripts/rollback.sh"

if [ -z "${target_branch}" ] || [ -z "${commit_sha}" ]; then
  echo "usage: deploy.sh <branch> <commit-sha> [auto|all|frontend|backend|frontend,backend]" >&2
  exit 1
fi

test -r "${compose_source}"
test -x "${health_check_script}" || test -r "${health_check_script}"
test -x "${rollback_script}" || test -r "${rollback_script}"
install -d -m 2770 "${deploy_dir}"

exec 9>"${deploy_dir}/deploy.lock"
flock -n 9 || { echo "Another deployment is running" >&2; exit 1; }

frontend_available=false
backend_available=false
if [ -f "${repository_root}/frontend/Dockerfile" ] && [ -f "${repository_root}/frontend/package.json" ]; then
  frontend_available=true
fi
if [ -f "${repository_root}/backend/Dockerfile" ] && \
   { [ -f "${repository_root}/backend/build.gradle" ] || \
     [ -f "${repository_root}/backend/build.gradle.kts" ] || \
     [ -f "${repository_root}/backend/pom.xml" ]; }; then
  backend_available=true
fi

current_frontend_enabled=false
current_backend_enabled=false
current_frontend_image=aiot-frontend:pending
current_backend_image=aiot-backend:pending
current_frontend_commit=
current_backend_commit=
frontend_health_url=http://127.0.0.1:3000/
backend_health_url=http://127.0.0.1:8080/swagger-ui.html

if [ -f "${current_env}" ]; then
  # shellcheck disable=SC1090
  source "${current_env}"
  current_frontend_enabled="${FRONTEND_ENABLED:-false}"
  current_backend_enabled="${BACKEND_ENABLED:-false}"
  current_frontend_image="${FRONTEND_IMAGE:-${current_frontend_image}}"
  current_backend_image="${BACKEND_IMAGE:-${current_backend_image}}"
  current_frontend_commit="${FRONTEND_COMMIT:-}"
  current_backend_commit="${BACKEND_COMMIT:-}"
  frontend_health_url="${FRONTEND_HEALTH_URL:-${frontend_health_url}}"
  backend_health_url="${BACKEND_HEALTH_URL:-${backend_health_url}}"
fi

deploy_services=()

has_service() {
  local candidate="$1"
  local existing
  for existing in "${deploy_services[@]:-}"; do
    if [ "${existing}" = "${candidate}" ]; then
      return 0
    fi
  done
  return 1
}

add_service() {
  local candidate="$1"
  local available=false

  case "${candidate}" in
    frontend) available="${frontend_available}" ;;
    backend) available="${backend_available}" ;;
    *) echo "Unknown deployment component: ${candidate}" >&2; exit 1 ;;
  esac

  if [ "${available}" != true ]; then
    if [ "${component_mode}" = auto ]; then
      echo "Skipping unavailable ${candidate} component"
      return
    fi
    echo "${candidate} was requested but its code contract is incomplete" >&2
    exit 1
  fi

  if ! has_service "${candidate}"; then
    deploy_services+=("${candidate}")
  fi
}

path_changed() {
  local path="$1"
  local before_sha="${CI_COMMIT_BEFORE_SHA:-}"

  if [ -z "${before_sha}" ] || [[ "${before_sha}" =~ ^0+$ ]] || \
     ! git -C "${repository_root}" cat-file -e "${before_sha}^{commit}" 2>/dev/null; then
    return 0
  fi
  ! git -C "${repository_root}" diff --quiet "${before_sha}" "${commit_sha}" -- "${path}"
}

case "${component_mode}" in
  auto)
    if path_changed frontend; then
      add_service frontend
    fi
    if path_changed backend; then
      add_service backend
    fi
    if path_changed infra/compose/compose.application.yaml || \
       path_changed infra/scripts/deploy.sh || \
       path_changed infra/scripts/health-check.sh || \
       path_changed infra/scripts/rollback.sh; then
      if [ "${current_frontend_enabled}" = true ]; then add_service frontend; fi
      if [ "${current_backend_enabled}" = true ]; then add_service backend; fi
    fi
    ;;
  all)
    add_service frontend
    add_service backend
    ;;
  frontend|backend)
    add_service "${component_mode}"
    ;;
  frontend,backend|backend,frontend)
    add_service frontend
    add_service backend
    ;;
  *)
    echo "Invalid component mode: ${component_mode}" >&2
    exit 1
    ;;
esac

if [ "${#deploy_services[@]}" -eq 0 ]; then
  echo "No deployable application component changed; infrastructure-only pipeline completed"
  exit 0
fi

short_sha="${commit_sha:0:12}"
next_frontend_enabled="${current_frontend_enabled}"
next_backend_enabled="${current_backend_enabled}"
next_frontend_image="${current_frontend_image}"
next_backend_image="${current_backend_image}"
next_frontend_commit="${current_frontend_commit}"
next_backend_commit="${current_backend_commit}"

for service in "${deploy_services[@]}"; do
  case "${service}" in
    frontend)
      next_frontend_enabled=true
      next_frontend_image="aiot-frontend:${short_sha}"
      next_frontend_commit="${commit_sha}"
      if ! docker image inspect "${next_frontend_image}" >/dev/null 2>&1; then
        docker build --pull -t "${next_frontend_image}" "${repository_root}/frontend"
      fi
      ;;
    backend)
      test -r /srv/aiot/secrets/backend.env
      next_backend_enabled=true
      next_backend_image="aiot-backend:${short_sha}"
      next_backend_commit="${commit_sha}"
      if ! docker image inspect "${next_backend_image}" >/dev/null 2>&1; then
        docker build --pull -t "${next_backend_image}" "${repository_root}/backend"
      fi
      ;;
  esac
done

if [ -f "${current_env}" ]; then
  cp "${current_env}" "${previous_env}"
else
  rm -f "${previous_env}"
fi
if [ -f "${compose_target}" ]; then
  cp "${compose_target}" "${previous_compose}"
else
  cp "${compose_source}" "${previous_compose}"
fi

install -m 0640 "${compose_source}" "${compose_target}"
umask 0027
cat >"${current_env}.tmp" <<EOF
DEPLOY_BRANCH=${target_branch}
DEPLOY_COMMIT=${commit_sha}
FRONTEND_ENABLED=${next_frontend_enabled}
FRONTEND_IMAGE=${next_frontend_image}
FRONTEND_COMMIT=${next_frontend_commit}
BACKEND_ENABLED=${next_backend_enabled}
BACKEND_IMAGE=${next_backend_image}
BACKEND_COMMIT=${next_backend_commit}
BACKEND_HEALTH_URL=${backend_health_url}
FRONTEND_HEALTH_URL=${frontend_health_url}
EOF
mv "${current_env}.tmp" "${current_env}"

if ! docker compose --env-file "${current_env}" -f "${compose_target}" up -d "${deploy_services[@]}"; then
  HEALTH_CHECK_SCRIPT="${health_check_script}" bash "${rollback_script}"
  exit 1
fi

if ! bash "${health_check_script}" application "${deploy_services[@]}"; then
  HEALTH_CHECK_SCRIPT="${health_check_script}" bash "${rollback_script}"
  exit 1
fi

printf '%s|%s|%s|frontend=%s|backend=%s\n' \
  "$(date --iso-8601=seconds)" \
  "${target_branch}" \
  "${commit_sha}" \
  "${next_frontend_image}" \
  "${next_backend_image}" \
  >>"${deploy_dir}/history.log"
echo "Deployment ${commit_sha} completed: ${deploy_services[*]}"
