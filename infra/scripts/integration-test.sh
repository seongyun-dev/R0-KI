#!/usr/bin/env bash
set -euo pipefail

repository_root="${CI_PROJECT_DIR:-$(pwd)}"
compose_file="${repository_root}/infra/compose/compose.integration.yaml"
project="${INTEGRATION_PROJECT:-aiot-integration-${CI_PIPELINE_ID:-local}-${CI_JOB_ID:-$$}}"
port="${INTEGRATION_PORT:-19080}"
base_url="http://127.0.0.1:${port}"
http_attempts="${INTEGRATION_HTTP_ATTEMPTS:-60}"
compose=(docker compose -p "${project}" -f "${compose_file}")

: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
docker image inspect "${FRONTEND_IMAGE}" >/dev/null
docker image inspect "${BACKEND_IMAGE}" >/dev/null

if [[ "${FRONTEND_IMAGE}" == aiot-frontend:front-* ]]; then
  docker run --rm --entrypoint sh "${FRONTEND_IMAGE}" -ec \
    '! grep -R -F "http://localhost:8080" /usr/share/nginx/html >/dev/null'
fi

show_failure_logs() {
  "${compose[@]}" ps || true
  "${compose[@]}" logs --no-color --tail 200 || true
}

cleanup() {
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}

trap show_failure_logs ERR
trap cleanup EXIT

wait_for_http() {
  local name="$1"
  local url="$2"
  local expected="${3:-}"
  local response_file
  response_file="$(mktemp "/tmp/aiot-integration-${name}.XXXXXX")"
  for _ in $(seq 1 "${http_attempts}"); do
    if curl --fail --silent --show-error --max-time 5 "${url}" >"${response_file}" 2>/dev/null; then
      if [ -z "${expected}" ] || grep -q "${expected}" "${response_file}"; then
        rm -f "${response_file}"
        return 0
      fi
    fi
    sleep 2
  done
  echo "${name} did not become ready: ${url}" >&2
  cat "${response_file}" >&2 2>/dev/null || true
  rm -f "${response_file}"
  return 1
}

export INTEGRATION_PROJECT="${project}"
export INTEGRATION_PORT="${port}"
"${compose[@]}" config --quiet
"${compose[@]}" up -d

wait_for_http gateway "${base_url}/integration-health" '^ok$'
wait_for_http frontend "${base_url}/"
wait_for_http openapi "${base_url}/v3/api-docs" '"openapi"'
wait_for_http swagger "${base_url}/swagger-ui.html"

"${compose[@]}" exec -T mysql sh -ec '
  mysql -uaiot_integration -pintegration-only-password aiot \
    -e "SELECT COUNT(*) AS migration_count FROM flyway_schema_history" \
    | grep -Eq "[1-9][0-9]*"
'

"${compose[@]}" exec -T mosquitto sh -ec '
  result=/tmp/integration-mqtt-result
  trap '\''rm -f "${result}"'\'' EXIT
  mosquitto_sub -h 127.0.0.1 -p 1883 -t integration/roundtrip -C 1 -W 5 >"${result}" &
  subscriber=$!
  sleep 1
  mosquitto_pub -h 127.0.0.1 -p 1883 -t integration/roundtrip -m ok
  wait "${subscriber}"
  grep -qx ok "${result}"
'

username="ci_${CI_PIPELINE_ID:-local}_${CI_JOB_ID:-$$}"
openapi_file="$(mktemp /tmp/aiot-openapi.XXXXXX)"
signup_file="$(mktemp /tmp/aiot-signup.XXXXXX)"
signin_file="$(mktemp /tmp/aiot-signin.XXXXXX)"
robots_file="$(mktemp /tmp/aiot-robots.XXXXXX)"
trap 'rm -f "${openapi_file}" "${signup_file}" "${signin_file}" "${robots_file}"; cleanup' EXIT
curl --fail --silent --show-error "${base_url}/v3/api-docs" >"${openapi_file}"

if python3 -c 'import json,sys; sys.exit(0 if "/api/auth/signup" in json.load(open(sys.argv[1], encoding="utf-8"))["paths"] else 1)' "${openapi_file}"; then
  curl --fail --silent --show-error \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${username}\",\"password\":\"integration-password-1!\",\"name\":\"CI User\",\"phoneNumber\":\"010-0000-0000\",\"apartment\":{\"name\":\"CI Apartment\",\"postalCode\":\"00000\",\"address\":\"Integration Test\"}}" \
    "${base_url}/api/auth/signup" >"${signup_file}"
  grep -q '"success":true' "${signup_file}"

  curl --fail --silent --show-error \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${username}\",\"password\":\"integration-password-1!\"}" \
    "${base_url}/api/auth/signin" >"${signin_file}"
  token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["data"]["accessToken"])' "${signin_file}")"
  test -n "${token}"

  curl --fail --silent --show-error \
    -H "Authorization: Bearer ${token}" \
    "${base_url}/api/robots?page=0&size=10" >"${robots_file}"
  grep -q '"success":true' "${robots_file}"
  echo "Auth, JWT and Robot API integration checks passed"
else
  protected_status="$(curl --silent --show-error -o "${robots_file}" -w '%{http_code}' \
    "${base_url}/api/robots?page=0&size=10")"
  test "${protected_status}" = 401
  echo "PLANNED: Auth fixture test skipped because the stable Backend has no signup contract yet"
fi

"${compose[@]}" ps
echo "Required integration checks passed for ${FRONTEND_IMAGE} + ${BACKEND_IMAGE}"
