#!/usr/bin/env bash
set -euo pipefail

target_branch="${1:-}"
commit_sha="${2:-}"
repository_root="${CI_PROJECT_DIR:-$(pwd)}"
deploy_dir=/srv/aiot/deploy
compose_source="${repository_root}/infra/compose/compose.application.yaml"
compose_target=/srv/aiot/compose/compose.application.yaml
current_env="${deploy_dir}/current.env"
previous_env="${deploy_dir}/previous.env"
previous_compose="${deploy_dir}/previous-compose.yaml"

if [ -z "${target_branch}" ] || [ -z "${commit_sha}" ]; then
  echo "usage: deploy.sh <branch> <commit-sha>" >&2
  exit 1
fi

if [ ! -f "${repository_root}/frontend/Dockerfile" ] || [ ! -f "${repository_root}/backend/Dockerfile" ]; then
  echo "Application Dockerfiles are not present yet; infrastructure-only pipeline completed."
  exit 0
fi

test -r /srv/aiot/secrets/backend.env

exec 9>"${deploy_dir}/deploy.lock"
flock -n 9 || { echo "Another deployment is running" >&2; exit 1; }

short_sha="${commit_sha:0:12}"
frontend_image="aiot-frontend:${short_sha}"
backend_image="aiot-backend:${short_sha}"

docker build --pull -t "${frontend_image}" "${repository_root}/frontend"
docker build --pull -t "${backend_image}" "${repository_root}/backend"

if [ -f "${current_env}" ]; then
  cp "${current_env}" "${previous_env}"
else
  rm -f "${previous_env}"
fi
cp "${compose_target}" "${previous_compose}"

install -m 0640 "${compose_source}" "${compose_target}"
umask 0027
cat >"${current_env}.tmp" <<EOF
DEPLOY_BRANCH=${target_branch}
DEPLOY_COMMIT=${commit_sha}
FRONTEND_IMAGE=${frontend_image}
BACKEND_IMAGE=${backend_image}
BACKEND_HEALTH_URL=http://127.0.0.1:8080/swagger-ui.html
FRONTEND_HEALTH_URL=http://127.0.0.1:3000/
EOF
mv "${current_env}.tmp" "${current_env}"

if ! docker compose --env-file "${current_env}" -f "${compose_target}" up -d; then
  /srv/aiot/deploy/rollback.sh
  exit 1
fi

if ! /srv/aiot/deploy/health-check.sh application; then
  /srv/aiot/deploy/rollback.sh
  exit 1
fi

printf '%s|%s|%s\n' "$(date --iso-8601=seconds)" "${target_branch}" "${commit_sha}" \
  >>"${deploy_dir}/history.log"
echo "Deployment ${commit_sha} completed"
