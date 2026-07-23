#!/usr/bin/env bash
set -euo pipefail

target_branch="${1:-}"
commit_sha="${2:-}"
component_mode="${3:-auto}"
repository_root="${CI_PROJECT_DIR:-$(pwd)}"
deploy_dir="${DEPLOY_DIR:-/srv/aiot/deploy}"
compose_source="${repository_root}/infra/compose/compose.application.yaml"
frontend_dockerfile="${repository_root}/infra/docker/frontend.Dockerfile"
compose_target="${COMPOSE_TARGET:-/srv/aiot/compose/compose.application.yaml}"
current_env="${deploy_dir}/current.env"
previous_env="${deploy_dir}/previous.env"
previous_compose="${deploy_dir}/previous-compose.yaml"
current_manifest="${deploy_dir}/release-manifest.json"
previous_manifest="${deploy_dir}/previous-release-manifest.json"
release_history_dir="${deploy_dir}/releases"
health_check_script="${repository_root}/infra/scripts/health-check.sh"
rollback_script="${repository_root}/infra/scripts/rollback.sh"
release_manifest_script="${repository_root}/infra/scripts/release-manifest.py"
deploy_result_file="${DEPLOY_RESULT_FILE:-}"

write_deploy_result() {
  if [ -n "${deploy_result_file}" ]; then
    printf '%s\n' "$1" >"${deploy_result_file}"
  fi
}

rollback_after_failure() {
  if ROLLBACK_FROM_DEPLOY=true HEALTH_CHECK_SCRIPT="${health_check_script}" \
    bash "${rollback_script}" automatic "${deploy_services[@]}"; then
    write_deploy_result rolled_back
  else
    write_deploy_result rollback_failed
  fi
}

if [ -z "${target_branch}" ] || [ -z "${commit_sha}" ]; then
  echo "usage: deploy.sh <branch> <commit-sha> [auto|all|frontend|backend|frontend,backend]" >&2
  exit 1
fi

test -r "${compose_source}"
test -x "${health_check_script}" || test -r "${health_check_script}"
test -x "${rollback_script}" || test -r "${rollback_script}"
test -r "${release_manifest_script}"
install -d -m 2770 "${deploy_dir}"
install -d -m 2770 "${release_history_dir}"

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
current_frontend_branch=
current_backend_branch=
database_schema=
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
  current_frontend_branch="${FRONTEND_BRANCH:-${DEPLOY_BRANCH:-}}"
  current_backend_branch="${BACKEND_BRANCH:-${DEPLOY_BRANCH:-}}"
  database_schema="${DATABASE_SCHEMA:-}"
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
next_frontend_branch="${current_frontend_branch}"
next_backend_branch="${current_backend_branch}"

for service in "${deploy_services[@]}"; do
  case "${service}" in
    frontend)
      next_frontend_enabled=true
      next_frontend_image="aiot-frontend:front-${short_sha}"
      next_frontend_commit="${commit_sha}"
      next_frontend_branch="${target_branch}"
      if ! docker image inspect "${next_frontend_image}" >/dev/null 2>&1; then
        test -r "${frontend_dockerfile}"
        docker build --pull \
          -f "${frontend_dockerfile}" \
          --build-arg VITE_API_BASE_URL= \
          --build-arg VITE_USE_MOCKS=false \
          -t "${next_frontend_image}" \
          "${repository_root}/frontend"
      fi
      ;;
    backend)
      test -r /srv/aiot/secrets/backend.env
      next_backend_enabled=true
      next_backend_image="aiot-backend:back-${short_sha}"
      next_backend_commit="${commit_sha}"
      next_backend_branch="${target_branch}"
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
if [ -f "${current_manifest}" ]; then
  cp "${current_manifest}" "${previous_manifest}"
else
  rm -f "${previous_manifest}"
fi

install -m 0640 "${compose_source}" "${compose_target}"
umask 0027
cat >"${current_env}.tmp" <<EOF
DEPLOY_BRANCH=${target_branch}
DEPLOY_COMMIT=${commit_sha}
FRONTEND_ENABLED=${next_frontend_enabled}
FRONTEND_IMAGE=${next_frontend_image}
FRONTEND_COMMIT=${next_frontend_commit}
FRONTEND_BRANCH=${next_frontend_branch}
BACKEND_ENABLED=${next_backend_enabled}
BACKEND_IMAGE=${next_backend_image}
BACKEND_COMMIT=${next_backend_commit}
BACKEND_BRANCH=${next_backend_branch}
DATABASE_SCHEMA=${database_schema}
BACKEND_HEALTH_URL=${backend_health_url}
FRONTEND_HEALTH_URL=${frontend_health_url}
EOF
mv "${current_env}.tmp" "${current_env}"

if ! docker compose --env-file "${current_env}" -f "${compose_target}" up -d "${deploy_services[@]}"; then
  rollback_after_failure
  exit 1
fi

if ! bash "${health_check_script}" application "${deploy_services[@]}"; then
  rollback_after_failure
  exit 1
fi

integration_status="${INTEGRATION_STATUS:-}"
if [ -z "${integration_status}" ]; then
  case "${target_branch}" in
    front/master|back/master) integration_status=passed ;;
    develop) integration_status=legacy ;;
    *) integration_status=provisional ;;
  esac
fi

components_csv="$(IFS=,; echo "${deploy_services[*]}")"
if ! release_id="$(python3 "${release_manifest_script}" write \
  --env "${current_env}" \
  --output "${current_manifest}" \
  --history-dir "${release_history_dir}" \
  --previous "${previous_manifest}" \
  --infra-commit "${CI_COMMIT_SHA:-${commit_sha}}" \
  --pipeline-id "${CI_PIPELINE_ID:-local}" \
  --job-id "${CI_JOB_ID:-$$}" \
  --components "${components_csv}" \
  --integration-status "${integration_status}")"; then
  echo "Release manifest update failed; restoring the previous component version" >&2
  rollback_after_failure
  exit 1
fi

printf '%s|%s|%s|release=%s|frontend=%s|backend=%s\n' \
  "$(date --iso-8601=seconds)" \
  "${target_branch}" \
  "${commit_sha}" \
  "${release_id}" \
  "${next_frontend_image}" \
  "${next_backend_image}" \
  >>"${deploy_dir}/history.log"
write_deploy_result succeeded
echo "Deployment ${commit_sha} completed: ${deploy_services[*]}"
