#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
updater="${repository_root}/infra/jetson/aiot-update.sh"
test_root="$(mktemp -d /tmp/aiot-jetson-updater-test.XXXXXX)"

cleanup() {
  case "${test_root}" in
    /tmp/aiot-jetson-updater-test.*) find "${test_root}" -depth -delete ;;
  esac
}
trap cleanup EXIT

mkdir -p "${test_root}/bin" "${test_root}/device/secrets" "${test_root}/source"

cat >"${test_root}/bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
url=""
output=""
previous=""
for argument in "$@"; do
  if [ "${previous}" = "--output" ]; then
    output="${argument}"
  fi
  case "${argument}" in
    https://*) url="${argument}" ;;
  esac
  previous="${argument}"
done
test -n "${url}" && test -n "${output}"
case "${url}" in
  */stable/manifest.json) cp "${TEST_PUBLIC_MANIFEST}" "${output}" ;;
  */packages/generic/aiot-iot/*) cp "${TEST_ARTIFACT}" "${output}" ;;
  *) exit 22 ;;
esac
SH
chmod 0755 "${test_root}/bin/curl"

cat >"${test_root}/bin/systemctl" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "is-active" ]; then
  exit 3
fi
exit 0
SH
chmod 0755 "${test_root}/bin/systemctl"

cat >"${test_root}/bin/getent" <<'SH'
#!/usr/bin/env bash
exit 2
SH
chmod 0755 "${test_root}/bin/getent"

cat >"${test_root}/device/secrets/package-read.env" <<'ENV'
STABLE_MANIFEST_URL=https://release.test/jetson/iot/stable/manifest.json
JETPACK_VERSION=6.2
AI_CONTRACT_VERSION=1
ALLOWED_ARTIFACT_HOST=release.test
ALLOWED_ARTIFACT_PATH_PREFIX=/packages/generic/aiot-iot/
ENV

create_release() {
  local release="$1"
  local fail_post="$2"
  local payload="${test_root}/source/${release}"
  local archive="${test_root}/source/aiot-${release}.tar.gz"
  local public_manifest="${archive}.manifest.json"

  mkdir -p "${payload}/robot/scripts" "${payload}/scripts"
  printf '%s\n' "${release}" >"${payload}/VERSION"
  cat >"${payload}/manifest.json" <<JSON
{"schema_version":1,"component":"iot","release":"${release}","iot_commit":"1111111111111111111111111111111111111111","required_ai_contract_version":1,"jetpack":"6.2","architecture":"aarch64","created_at":"2026-08-03T00:00:00Z"}
JSON
  cat >"${payload}/robot/scripts/run.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  cat >"${payload}/scripts/install.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  cat >"${payload}/scripts/smoke-test.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "${1:-}" = "post-activate" ] && [ -e "${root}/scripts/fail-post" ]; then
  exit 1
fi
SH
  if [ "${fail_post}" = true ]; then
    printf 'fail\n' >"${payload}/scripts/fail-post"
  fi
  chmod 0755 "${payload}/robot/scripts/run.sh" \
    "${payload}/scripts/install.sh" "${payload}/scripts/smoke-test.sh"
  (
    cd "${payload}"
    find robot scripts -type f -print0 | LC_ALL=C sort -z | \
      xargs -0 sha256sum >CHECKSUMS.sha256
    sha256sum VERSION manifest.json >>CHECKSUMS.sha256
    tar -czf "${archive}" robot scripts VERSION manifest.json CHECKSUMS.sha256
  )
  python3 - "${public_manifest}" "${archive}" "${release}" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path, archive_path, release = sys.argv[1:]
artifact = pathlib.Path(archive_path)
data = {
    "schema_version": 1,
    "component": "iot",
    "release": release,
    "iot_commit": "1" * 40,
    "required_ai_contract_version": 1,
    "jetpack": "6.2",
    "architecture": "aarch64",
    "artifact_url": (
        f"https://release.test/packages/generic/aiot-iot/{release}/"
        f"aiot-{release}.tar.gz"
    ),
    "artifact_size_bytes": artifact.stat().st_size,
    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    "published_at": "2026-08-03T00:00:00Z",
}
pathlib.Path(manifest_path).write_text(json.dumps(data), encoding="utf-8")
PY
  TEST_ARTIFACT="${archive}"
  TEST_PUBLIC_MANIFEST="${public_manifest}"
  export TEST_ARTIFACT TEST_PUBLIC_MANIFEST
}

run_updater() {
  PATH="${test_root}/bin:${PATH}" \
    AIOT_ROOT="${test_root}/device" \
    AIOT_DEVICE_ARCH_OVERRIDE=aarch64 \
    AIOT_PATROL_DEPLOY_LOCK_FILE="${test_root}/device/iot/state/patrol-deploy.lock" \
    bash "${updater}"
}

create_release iot-v0.0.1 false
first_output="$(run_updater)"
grep -q 'phase=complete result=activated' <<<"${first_output}"
test "$(readlink -f "${test_root}/device/iot/current")" = \
  "${test_root}/device/iot/releases/iot-v0.0.1"
test "$(cat "${test_root}/device/iot/state/VERSION")" = "iot-v0.0.1"

create_release iot-v0.0.2 true
failed_output="$(run_updater)"
grep -q 'phase=smoke result=post-activate-rollback' <<<"${failed_output}"
test "$(readlink -f "${test_root}/device/iot/current")" = \
  "${test_root}/device/iot/releases/iot-v0.0.1"
test "$(cat "${test_root}/device/iot/state/VERSION")" = "iot-v0.0.1"

create_release iot-v0.0.3 false
exec 7>>"${test_root}/device/iot/state/patrol-deploy.lock"
flock -n 7
locked_output="$(run_updater)"
flock -u 7
grep -q 'phase=activate result=patrol-active' <<<"${locked_output}"
test "$(readlink -f "${test_root}/device/iot/current")" = \
  "${test_root}/device/iot/releases/iot-v0.0.1"

echo "Jetson updater activation, rollback, and patrol interlock tests passed"
