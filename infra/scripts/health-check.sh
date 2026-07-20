#!/usr/bin/env bash
set -euo pipefail

runtime_env="${RUNTIME_ENV:-/srv/aiot/secrets/runtime.env}"
current_env="${CURRENT_ENV:-/srv/aiot/deploy/current.env}"
mode="${1:-infrastructure}"
shift || true
requested_components=("$@")
http_attempts="${HEALTH_HTTP_ATTEMPTS:-30}"
retry_delay="${HEALTH_RETRY_DELAY_SECONDS:-5}"

if [[ ! "${http_attempts}" =~ ^[1-9][0-9]*$ ]] || \
   [[ ! "${retry_delay}" =~ ^[1-9][0-9]*$ ]]; then
  echo "health retry settings must be positive integers" >&2
  exit 1
fi

if [ "${mode}" != infrastructure ] && [ "${mode}" != application ]; then
  echo "usage: health-check.sh [infrastructure|application] [frontend] [backend]" >&2
  exit 1
fi

test -r "${runtime_env}"
# shellcheck disable=SC1090
source "${runtime_env}"

if [ -f "${current_env}" ]; then
  # shellcheck disable=SC1090
  source "${current_env}"
fi

wait_for_container_health() {
  local container_name="$1"
  local expected_status="$2"
  local attempts="${3:-30}"
  local status

  for _ in $(seq 1 "${attempts}"); do
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "${container_name}" 2>/dev/null || true)
    if [ "${status}" = "${expected_status}" ]; then
      return 0
    fi
    sleep "${retry_delay}"
  done

  echo "${container_name} did not reach ${expected_status}" >&2
  docker logs --tail 100 "${container_name}" >&2 2>/dev/null || true
  return 1
}

wait_for_http() {
  local service_name="$1"
  local url="$2"

  for _ in $(seq 1 "${http_attempts}"); do
    if curl --fail --silent --show-error --max-time 10 "${url}" >/dev/null; then
      return 0
    fi
    sleep "${retry_delay}"
  done

  echo "${service_name} readiness check failed: ${url}" >&2
  return 1
}

mqtt_round_trip() {
  local topic="infra/health/$(hostname)/$$"

  docker exec \
    -e MQTT_USERNAME="${MQTT_BACKEND_USERNAME}" \
    -e MQTT_PASSWORD="${MQTT_BACKEND_PASSWORD}" \
    -e MQTT_TOPIC="${topic}" \
    aiot-mosquitto sh -ec '
      result_file="/tmp/aiot-mqtt-health.$$"
      trap '\''rm -f "${result_file}"'\'' EXIT
      mosquitto_sub -h 127.0.0.1 -p 1883 \
        -u "${MQTT_USERNAME}" -P "${MQTT_PASSWORD}" \
        -t "${MQTT_TOPIC}" -C 1 -W 5 >"${result_file}" &
      subscriber_pid=$!
      sleep 1
      mosquitto_pub -h 127.0.0.1 -p 1883 \
        -u "${MQTT_USERNAME}" -P "${MQTT_PASSWORD}" \
        -t "${MQTT_TOPIC}" -m ok
      wait "${subscriber_pid}"
      grep -qx ok "${result_file}"
    '
}

add_component() {
  local candidate="$1"
  local existing

  case "${candidate}" in
    frontend|backend) ;;
    *)
      echo "unknown application component: ${candidate}" >&2
      exit 1
      ;;
  esac

  for existing in "${components[@]:-}"; do
    if [ "${existing}" = "${candidate}" ]; then
      return
    fi
  done
  components+=("${candidate}")
}

wait_for_container_health aiot-mysql healthy 36
wait_for_container_health aiot-mosquitto running 12

for _ in $(seq 1 6); do
  if mqtt_round_trip; then
    mqtt_ready=true
    break
  fi
  sleep "${retry_delay}"
done
if [ "${mqtt_ready:-false}" != true ]; then
  echo "MQTT authenticated publish/subscribe check failed" >&2
  exit 1
fi

if [ -r /srv/aiot/certs/mqtt/fullchain.pem ]; then
  openssl x509 -checkend 1209600 -noout -in /srv/aiot/certs/mqtt/fullchain.pem >/dev/null || {
    echo "MQTT certificate expires in less than 14 days" >&2
    exit 1
  }
fi

if [ "${mode}" = application ]; then
  components=()
  if [ "${#requested_components[@]}" -gt 0 ]; then
    for component in "${requested_components[@]}"; do
      add_component "${component}"
    done
  else
    if [ "${FRONTEND_ENABLED:-false}" = true ]; then
      add_component frontend
    fi
    if [ "${BACKEND_ENABLED:-false}" = true ]; then
      add_component backend
    fi
  fi

  if [ "${#components[@]}" -eq 0 ]; then
    echo "No application components are enabled; infrastructure checks passed"
    exit 0
  fi

  for component in "${components[@]}"; do
    case "${component}" in
      frontend)
        wait_for_container_health aiot-frontend running 12
        wait_for_http frontend "${FRONTEND_HEALTH_URL:-http://127.0.0.1:3000/}"
        ;;
      backend)
        wait_for_container_health aiot-backend running 12
        wait_for_http backend "${BACKEND_HEALTH_URL:-http://127.0.0.1:8080/swagger-ui.html}"
        ;;
    esac
  done

  echo "application health checks passed: ${components[*]}"
  exit 0
fi

echo "infrastructure health checks passed"
