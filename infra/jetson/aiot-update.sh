#!/usr/bin/env bash
set -euo pipefail
umask 0027

aiot_root="${AIOT_ROOT:-/opt/aiot}"
iot_root="${AIOT_IOT_ROOT:-${aiot_root}/iot}"
config_file="${AIOT_PACKAGE_ENV:-${aiot_root}/secrets/package-read.env}"
lock_file="${iot_root}/state/update.lock"
current_link="${iot_root}/current"
previous_link="${iot_root}/previous"
patrol_lock_file="${AIOT_PATROL_DEPLOY_LOCK_FILE:-/var/lib/aiot/state/patrol-deploy.lock}"

log() {
  printf 'aiot-update component=iot release=%s phase=%s result=%s\n' \
    "${release:-unknown}" "$1" "$2"
}

keep_current() {
  local phase="$1"
  shift
  log "${phase}" "${*:-keep-current}"
  exit 0
}

install -d -m 0750 \
  "${iot_root}/releases" \
  "${iot_root}/.staging" \
  "${iot_root}/state" \
  "${aiot_root}/secrets"

exec 9>"${lock_file}"
flock -n 9 || keep_current lock busy

if [ ! -r "${config_file}" ]; then
  keep_current config missing
fi
# shellcheck disable=SC1090
source "${config_file}"

stable_manifest_url="${STABLE_MANIFEST_URL:-}"
package_registry_user="${PACKAGE_REGISTRY_USER:-}"
package_registry_token="${PACKAGE_REGISTRY_TOKEN:-}"
device_jetpack="${JETPACK_VERSION:-}"
device_architecture="${AIOT_DEVICE_ARCH_OVERRIDE:-$(uname -m)}"
ai_contract_version="${AI_CONTRACT_VERSION:-}"
allowed_artifact_host="${ALLOWED_ARTIFACT_HOST:-}"
allowed_artifact_path_prefix="${ALLOWED_ARTIFACT_PATH_PREFIX:-}"

if [[ ! "${stable_manifest_url}" =~ ^https:// ]]; then
  keep_current config invalid-manifest-url
fi
if [ -z "${device_jetpack}" ]; then
  keep_current compatibility jetpack-unknown
fi
if [[ ! "${ai_contract_version}" =~ ^[0-9]+$ ]]; then
  keep_current compatibility ai-contract-unknown
fi
if [ -z "${allowed_artifact_host}" ] || \
   [[ "${allowed_artifact_path_prefix}" != /* ]]; then
  keep_current config invalid-artifact-allowlist
fi

work_dir="$(mktemp -d "${iot_root}/.staging/update.XXXXXX")"
cleanup() {
  if [[ "${work_dir}" == "${iot_root}/.staging/"* ]] && [ -d "${work_dir}" ]; then
    find "${work_dir}" -depth -delete
  fi
}
trap cleanup EXIT

manifest_path="${work_dir}/manifest.json"
if ! curl --fail --silent --show-error --location \
  --connect-timeout 10 --max-time 30 --retry 2 \
  "${stable_manifest_url}" --output "${manifest_path}"; then
  keep_current manifest unavailable
fi

values_path="${work_dir}/manifest.values"
if ! python3 - "${manifest_path}" "${allowed_artifact_host}" \
  "${allowed_artifact_path_prefix}" >"${values_path}" <<'PY'
import json
import re
import sys
from urllib.parse import urlparse

path, allowed_host, allowed_path_prefix = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    data = json.load(stream)

required = {
    "schema_version",
    "component",
    "release",
    "iot_commit",
    "required_ai_contract_version",
    "jetpack",
    "architecture",
    "artifact_url",
    "artifact_size_bytes",
    "sha256",
    "published_at",
}
if set(data) != required:
    raise ValueError("manifest field set does not match IoT schema v1")
if data["schema_version"] != 1 or data["component"] != "iot":
    raise ValueError("unsupported manifest schema or component")
if not re.fullmatch(r"iot-v\d+\.\d+\.\d+", data["release"]):
    raise ValueError("invalid release")
if not re.fullmatch(r"[0-9a-f]{40}", data["iot_commit"]):
    raise ValueError("invalid iot_commit")
if (
    isinstance(data["required_ai_contract_version"], bool)
    or not isinstance(data["required_ai_contract_version"], int)
    or data["required_ai_contract_version"] < 1
):
    raise ValueError("invalid required_ai_contract_version")
if not re.fullmatch(r"[0-9a-f]{64}", data["sha256"]):
    raise ValueError("invalid sha256")
artifact = urlparse(data["artifact_url"])
if artifact.scheme != "https":
    raise ValueError("artifact URL must use HTTPS")
if artifact.hostname != allowed_host:
    raise ValueError("artifact host is not allowlisted")
if not artifact.path.startswith(allowed_path_prefix):
    raise ValueError("artifact path is not allowlisted")
if "/packages/generic/aiot-iot/" not in artifact.path:
    raise ValueError("artifact is not an aiot-iot package")
if not isinstance(data["artifact_size_bytes"], int) or data["artifact_size_bytes"] < 1:
    raise ValueError("invalid artifact size")
for key in (
    "release",
    "iot_commit",
    "jetpack",
    "architecture",
    "artifact_url",
    "sha256",
):
    value = str(data[key])
    if "\n" in value or "\r" in value:
        raise ValueError(f"invalid newline in {key}")
    print(value)
print(data["artifact_size_bytes"])
print(data["required_ai_contract_version"])
PY
then
  keep_current manifest invalid
fi

mapfile -t manifest_values <"${values_path}"
if [ "${#manifest_values[@]}" -ne 8 ]; then
  keep_current manifest invalid-values
fi
release="${manifest_values[0]}"
iot_commit="${manifest_values[1]}"
required_jetpack="${manifest_values[2]}"
required_architecture="${manifest_values[3]}"
artifact_url="${manifest_values[4]}"
artifact_sha256="${manifest_values[5]}"
artifact_size_bytes="${manifest_values[6]}"
required_ai_contract="${manifest_values[7]}"

installed_version=""
if [ -r "${iot_root}/state/VERSION" ]; then
  installed_version="$(tr -d '\r\n' <"${iot_root}/state/VERSION")"
fi
if [ "${installed_version}" = "${release}" ]; then
  log compare already-current
  exit 0
fi
if [ "${device_architecture}" != "${required_architecture}" ]; then
  keep_current compatibility architecture-mismatch
fi
if [ "${device_jetpack}" != "${required_jetpack}" ]; then
  keep_current compatibility jetpack-mismatch
fi
if [ "${ai_contract_version}" != "${required_ai_contract}" ]; then
  keep_current compatibility ai-contract-mismatch
fi

available_bytes="$(df -PB1 "${iot_root}" | awk 'NR == 2 {print $4}')"
required_bytes=$((artifact_size_bytes * 3))
if [ "${available_bytes}" -lt "${required_bytes}" ]; then
  keep_current storage insufficient
fi

artifact_path="${work_dir}/release.tar.gz"
curl_auth=()
if [ -n "${package_registry_user}" ] && [ -n "${package_registry_token}" ]; then
  curl_auth=(--user "${package_registry_user}:${package_registry_token}")
fi
if ! curl --fail --silent --show-error --location \
  --connect-timeout 10 --max-time 1800 --retry 3 \
  "${curl_auth[@]}" "${artifact_url}" --output "${artifact_path}"; then
  keep_current download failed
fi
printf '%s  %s\n' "${artifact_sha256}" "${artifact_path}" | \
  sha256sum --check --status || keep_current checksum mismatch

extract_dir="${work_dir}/payload"
install -d -m 0750 "${extract_dir}"
if ! python3 - "${artifact_path}" <<'PY'
import pathlib
import sys
import tarfile

allowed_roots = {"robot", "scripts", "VERSION", "manifest.json", "CHECKSUMS.sha256"}
with tarfile.open(sys.argv[1], "r:gz") as archive:
    for member in archive.getmembers():
        path = pathlib.PurePosixPath(member.name)
        normalized = pathlib.PurePosixPath(*[part for part in path.parts if part != "."])
        if (
            path.is_absolute()
            or ".." in path.parts
            or member.isdev()
            or not normalized.parts
            or normalized.parts[0] not in allowed_roots
        ):
            raise ValueError(f"unsafe or unexpected archive member: {member.name}")
        if member.issym() or member.islnk():
            target = pathlib.PurePosixPath(member.linkname)
            if target.is_absolute() or ".." in target.parts:
                raise ValueError(f"unsafe archive link: {member.name}")
PY
then
  keep_current extract unsafe-archive
fi
tar --no-same-owner --no-same-permissions -xzf "${artifact_path}" -C "${extract_dir}"

test "$(tr -d '\r\n' <"${extract_dir}/VERSION")" = "${release}" || \
  keep_current extract version-mismatch
test -x "${extract_dir}/scripts/install.sh" || \
  keep_current extract missing-installer
test -x "${extract_dir}/scripts/smoke-test.sh" || \
  keep_current extract missing-smoke
test -x "${extract_dir}/robot/scripts/run.sh" || \
  keep_current extract missing-runtime
test ! -e "${extract_dir}/ai" || keep_current extract contains-ai
if ! python3 - "${extract_dir}/manifest.json" "${release}" "${iot_commit}" \
  "${required_ai_contract}" <<'PY'
import json
import sys

path, release, iot_commit, contract_version = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    manifest = json.load(stream)
expected = {
    "schema_version": 1,
    "component": "iot",
    "release": release,
    "iot_commit": iot_commit,
    "required_ai_contract_version": int(contract_version),
    "jetpack": "6.2",
    "architecture": "aarch64",
}
for key, value in expected.items():
    if manifest.get(key) != value:
        raise ValueError(f"payload manifest mismatch: {key}")
PY
then
  keep_current extract payload-manifest-mismatch
fi
if find "${extract_dir}" -type f \
  \( -name '*.engine' -o -name '*.onnx' -o -name '*.pt' \) -print -quit | grep -q .; then
  keep_current extract contains-model
fi
(
  cd "${extract_dir}"
  sha256sum --check --strict CHECKSUMS.sha256
) >/dev/null || keep_current checksum payload-mismatch

exec 8>>"${patrol_lock_file}"
if ! flock -n 8; then
  keep_current activate patrol-active
fi

release_dir="${iot_root}/releases/${release}"
if [ -e "${release_dir}" ]; then
  quarantine="${iot_root}/.staging/stale-${release}-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "${release_dir}" "${quarantine}"
  log activate stale-release-quarantined
fi
mv "${extract_dir}" "${release_dir}"

find "${release_dir}" -type d -exec chmod 0750 {} +
find "${release_dir}" -type f -exec chmod 0640 {} +
find "${release_dir}/scripts" "${release_dir}/robot/scripts" \
  -type f -name '*.sh' -exec chmod 0750 {} +

if ! "${release_dir}/scripts/install.sh"; then
  keep_current install failed
fi
if getent group aiot >/dev/null 2>&1; then
  chown -R root:aiot "${release_dir}"
fi
if ! "${release_dir}/scripts/smoke-test.sh" pre-activate; then
  keep_current smoke pre-activate-failed
fi

old_current=""
if [ -L "${current_link}" ]; then
  old_current="$(readlink -f "${current_link}")"
fi
ai_was_active=false
robot_was_active=false
if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
  systemctl is-active --quiet aiot-ai.service && ai_was_active=true
  systemctl is-active --quiet aiot-robot.service && robot_was_active=true
fi
if [ -n "${old_current}" ]; then
  previous_next="${iot_root}/.previous.next.$$"
  ln -s "${old_current}" "${previous_next}"
  mv -Tf "${previous_next}" "${previous_link}"
fi

current_next="${iot_root}/.current.next.$$"
ln -s "${release_dir}" "${current_next}"
mv -Tf "${current_next}" "${current_link}"

if ! "${current_link}/scripts/smoke-test.sh" post-activate; then
  if [ -n "${old_current}" ]; then
    rollback_next="${iot_root}/.current.rollback.$$"
    ln -s "${old_current}" "${rollback_next}"
    mv -Tf "${rollback_next}" "${current_link}"
  else
    unlink "${current_link}"
  fi
  keep_current smoke post-activate-rollback
fi

restart_failed=false
if [ "${ai_was_active}" = true ]; then
  systemctl restart aiot-ai.service || restart_failed=true
  systemctl is-active --quiet aiot-ai.service || restart_failed=true
fi
if [ "${restart_failed}" = false ] && [ "${robot_was_active}" = true ]; then
  systemctl restart aiot-robot.service || restart_failed=true
  systemctl is-active --quiet aiot-robot.service || restart_failed=true
fi
if [ "${restart_failed}" = true ]; then
  if [ -n "${old_current}" ]; then
    rollback_next="${iot_root}/.current.service-rollback.$$"
    ln -s "${old_current}" "${rollback_next}"
    mv -Tf "${rollback_next}" "${current_link}"
    [ "${ai_was_active}" = true ] && systemctl restart aiot-ai.service || true
    [ "${robot_was_active}" = true ] && systemctl restart aiot-robot.service || true
  else
    unlink "${current_link}"
  fi
  keep_current activate service-start-failed-rollback
fi

version_tmp="${iot_root}/state/VERSION.tmp.$$"
printf '%s\n' "${release}" >"${version_tmp}"
mv -f "${version_tmp}" "${iot_root}/state/VERSION"
log complete activated
