#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
rollback_script="${repository_root}/infra/scripts/rollback.sh"
manifest_script="${repository_root}/infra/scripts/release-manifest.py"
test_root="$(mktemp -d /tmp/aiot-rollback-test.XXXXXX)"

cleanup() {
  case "${test_root}" in
    /tmp/aiot-rollback-test.*) rm -rf -- "${test_root}" ;;
    *) echo "Refusing to remove unexpected test path: ${test_root}" >&2 ;;
  esac
}
trap cleanup EXIT

deploy_dir="${test_root}/deploy"
fake_bin="${test_root}/bin"
compose_file="${test_root}/compose.application.yaml"
health_script="${test_root}/health-check.sh"
docker_log="${test_root}/docker.log"
mkdir -p "${deploy_dir}/releases" "${fake_bin}"

cat >"${fake_bin}/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${DOCKER_LOG}"
EOF
chmod +x "${fake_bin}/docker"

cat >"${health_script}" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${HEALTH_LOG}"
EOF
chmod +x "${health_script}"

cat >"${compose_file}" <<'EOF'
name: rollback-test
services:
  frontend: {image: "${FRONTEND_IMAGE}"}
  backend: {image: "${BACKEND_IMAGE}"}
EOF
cp "${compose_file}" "${deploy_dir}/previous-compose.yaml"

write_env() {
  local output="$1"
  local frontend_image="$2"
  local frontend_commit="$3"
  cat >"${output}" <<EOF
DEPLOY_BRANCH=front/master
DEPLOY_COMMIT=aaaaaaaa
FRONTEND_ENABLED=true
FRONTEND_IMAGE=${frontend_image}
FRONTEND_COMMIT=${frontend_commit}
FRONTEND_BRANCH=front/master
BACKEND_ENABLED=true
BACKEND_IMAGE=aiot-backend:back-3333333
BACKEND_COMMIT=3333333
BACKEND_BRANCH=back/master
DATABASE_SCHEMA=1
BACKEND_HEALTH_URL=http://127.0.0.1:8080/swagger-ui.html
FRONTEND_HEALTH_URL=http://127.0.0.1:3000/
EOF
}

write_env "${deploy_dir}/current.env" aiot-frontend:front-2222222 2222222
write_env "${deploy_dir}/previous.env" aiot-frontend:front-1111111 1111111
: >"${docker_log}"
: >"${test_root}/health.log"

PATH="${fake_bin}:${PATH}" \
DOCKER_LOG="${docker_log}" \
HEALTH_LOG="${test_root}/health.log" \
ROLLBACK_FROM_DEPLOY=true \
DEPLOY_DIR="${deploy_dir}" \
COMPOSE_TARGET="${compose_file}" \
HEALTH_CHECK_SCRIPT="${health_script}" \
RELEASE_MANIFEST_SCRIPT="${manifest_script}" \
bash "${rollback_script}" automatic frontend

grep -q '^FRONTEND_IMAGE=aiot-frontend:front-1111111$' "${deploy_dir}/current.env"
grep -q 'up -d frontend' "${docker_log}"
! grep -q 'up -d backend' "${docker_log}"

# Build historical and current manifests, then verify a selective manual rollback.
write_env "${test_root}/old.env" aiot-frontend:front-1111111 1111111
write_env "${deploy_dir}/current.env" aiot-frontend:front-2222222 2222222
python3 "${manifest_script}" write \
  --env "${test_root}/old.env" \
  --output "${test_root}/old-current.json" \
  --history-dir "${deploy_dir}/releases" \
  --release-id release-old \
  --infra-commit aaaaaaaa \
  --components frontend \
  --integration-status passed >/dev/null
python3 "${manifest_script}" write \
  --env "${deploy_dir}/current.env" \
  --output "${deploy_dir}/release-manifest.json" \
  --history-dir "${deploy_dir}/releases" \
  --release-id release-new \
  --infra-commit aaaaaaaa \
  --components frontend \
  --integration-status passed >/dev/null

: >"${docker_log}"
PATH="${fake_bin}:${PATH}" \
DOCKER_LOG="${docker_log}" \
HEALTH_LOG="${test_root}/health.log" \
DEPLOY_DIR="${deploy_dir}" \
COMPOSE_TARGET="${compose_file}" \
HEALTH_CHECK_SCRIPT="${health_script}" \
RELEASE_MANIFEST_SCRIPT="${manifest_script}" \
bash "${rollback_script}" frontend release-old

grep -q '^FRONTEND_IMAGE=aiot-frontend:front-1111111$' "${deploy_dir}/current.env"
grep -q '^BACKEND_IMAGE=aiot-backend:back-3333333$' "${deploy_dir}/current.env"
grep -q 'up -d frontend' "${docker_log}"
! grep -q 'up -d backend' "${docker_log}"
python3 "${manifest_script}" validate "${deploy_dir}/release-manifest.json" >/dev/null

echo "rollback tests passed"
