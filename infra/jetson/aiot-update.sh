#!/usr/bin/env bash
set -euo pipefail

aiot_root="${AIOT_ROOT:-/opt/aiot}"
config_file="${AIOT_PACKAGE_ENV:-${aiot_root}/secrets/package-read.env}"
lock_file="${aiot_root}/state/update.lock"
current_link="${aiot_root}/current"
previous_link="${aiot_root}/previous"

log() {
  printf 'aiot-update release=%s phase=%s result=%s\n' \
    "${release:-unknown}" "$1" "$2"
}

run_current() {
  local phase="$1"
  shift
  log "${phase}" "${*:-run-current}"
  exit 0
}

install -d -m 0750 \
  "${aiot_root}/releases" \
  "${aiot_root}/.staging" \
  "${aiot_root}/state" \
  "${aiot_root}/secrets"

exec 9>"${lock_file}"
flock -n 9 || run_current lock busy

if [ ! -r "${config_file}" ]; then
  run_current config missing
fi
# shellcheck disable=SC1090
source "${config_file}"

stable_manifest_url="${STABLE_MANIFEST_URL:-}"
package_registry_user="${PACKAGE_REGISTRY_USER:-}"
package_registry_token="${PACKAGE_REGISTRY_TOKEN:-}"
device_jetpack="${JETPACK_VERSION:-}"
device_architecture="${AIOT_DEVICE_ARCH_OVERRIDE:-$(uname -m)}"

if [[ ! "${stable_manifest_url}" =~ ^https:// ]]; then
  run_current config invalid-manifest-url
fi
if [ -z "${device_jetpack}" ]; then
  run_current compatibility jetpack-unknown
fi

work_dir="$(mktemp -d "${aiot_root}/.staging/update.XXXXXX")"
cleanup() {
  if [[ "${work_dir}" == "${aiot_root}/.staging/"* ]] && [ -d "${work_dir}" ]; then
    find "${work_dir}" -depth -delete
  fi
}
trap cleanup EXIT

manifest_path="${work_dir}/manifest.json"
if ! curl --fail --silent --show-error --location \
  --connect-timeout 10 --max-time 30 --retry 2 \
  "${stable_manifest_url}" --output "${manifest_path}"; then
  run_current manifest unavailable
fi

values_path="${work_dir}/manifest.values"
if ! python3 - "${manifest_path}" >"${values_path}" <<'PY'
import json
import re
import sys
from urllib.parse import urlparse

with open(sys.argv[1], encoding="utf-8") as stream:
    data = json.load(stream)

required = {
    "schema_version",
    "release",
    "robot_commit",
    "ai_commit",
    "model_version",
    "jetpack",
    "architecture",
    "artifact_url",
    "artifact_size_bytes",
    "sha256",
    "published_at",
}
if set(data) != required:
    raise ValueError("manifest field set does not match schema v1")
if data["schema_version"] != 1:
    raise ValueError("unsupported manifest schema")
if not re.fullmatch(r"jetson-v\d+\.\d+\.\d+", data["release"]):
    raise ValueError("invalid release")
if not re.fullmatch(r"[0-9a-f]{64}", data["sha256"]):
    raise ValueError("invalid sha256")
if urlparse(data["artifact_url"]).scheme != "https":
    raise ValueError("artifact URL must use HTTPS")
if not isinstance(data["artifact_size_bytes"], int) or data["artifact_size_bytes"] < 1:
    raise ValueError("invalid artifact size")
for key in ("release", "jetpack", "architecture", "artifact_url", "sha256"):
    value = str(data[key])
    if "\n" in value or "\r" in value:
        raise ValueError(f"invalid newline in {key}")
    print(value)
print(data["artifact_size_bytes"])
PY
then
  run_current manifest invalid
fi

mapfile -t manifest_values <"${values_path}"
if [ "${#manifest_values[@]}" -ne 6 ]; then
  run_current manifest invalid-values
fi
release="${manifest_values[0]}"
required_jetpack="${manifest_values[1]}"
required_architecture="${manifest_values[2]}"
artifact_url="${manifest_values[3]}"
artifact_sha256="${manifest_values[4]}"
artifact_size_bytes="${manifest_values[5]}"

installed_version=""
if [ -r "${aiot_root}/state/VERSION" ]; then
  installed_version="$(tr -d '\r\n' <"${aiot_root}/state/VERSION")"
fi
if [ "${installed_version}" = "${release}" ]; then
  log compare already-current
  exit 0
fi
if [ "${device_architecture}" != "${required_architecture}" ]; then
  run_current compatibility architecture-mismatch
fi
if [ "${device_jetpack}" != "${required_jetpack}" ]; then
  run_current compatibility jetpack-mismatch
fi

available_bytes="$(df -PB1 "${aiot_root}" | awk 'NR == 2 {print $4}')"
required_bytes=$((artifact_size_bytes * 3))
if [ "${available_bytes}" -lt "${required_bytes}" ]; then
  run_current storage insufficient
fi

artifact_path="${work_dir}/release.tar.gz"
curl_auth=()
if [ -n "${package_registry_user}" ] && [ -n "${package_registry_token}" ]; then
  curl_auth=(--user "${package_registry_user}:${package_registry_token}")
fi
if ! curl --fail --silent --show-error --location \
  --connect-timeout 10 --max-time 1800 --retry 3 \
  "${curl_auth[@]}" "${artifact_url}" --output "${artifact_path}"; then
  run_current download failed
fi
printf '%s  %s\n' "${artifact_sha256}" "${artifact_path}" | sha256sum --check --status || \
  run_current checksum mismatch

extract_dir="${work_dir}/payload"
install -d -m 0750 "${extract_dir}"
if ! python3 - "${artifact_path}" <<'PY'
import pathlib
import sys
import tarfile

with tarfile.open(sys.argv[1], "r:gz") as archive:
    for member in archive.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.isdev():
            raise ValueError(f"unsafe archive member: {member.name}")
        if member.issym() or member.islnk():
            target = pathlib.PurePosixPath(member.linkname)
            if target.is_absolute() or ".." in target.parts:
                raise ValueError(f"unsafe archive link: {member.name}")
PY
then
  run_current extract unsafe-archive
fi
tar --no-same-owner --no-same-permissions -xzf "${artifact_path}" -C "${extract_dir}"

test "$(tr -d '\r\n' <"${extract_dir}/VERSION")" = "${release}" || \
  run_current extract version-mismatch
test -x "${extract_dir}/scripts/install.sh" || run_current extract missing-installer
test -x "${extract_dir}/scripts/smoke-test.sh" || run_current extract missing-smoke

if ! "${extract_dir}/scripts/install.sh"; then
  run_current install failed
fi
if ! "${extract_dir}/scripts/smoke-test.sh" pre-activate; then
  run_current smoke pre-activate-failed
fi

release_dir="${aiot_root}/releases/${release}"
if [ -e "${release_dir}" ]; then
  run_current activate immutable-release-exists
fi
mv "${extract_dir}" "${release_dir}"

old_current=""
if [ -L "${current_link}" ]; then
  old_current="$(readlink -f "${current_link}")"
fi
if [ -n "${old_current}" ]; then
  previous_next="${aiot_root}/.previous.next.$$"
  ln -s "${old_current}" "${previous_next}"
  mv -Tf "${previous_next}" "${previous_link}"
fi

current_next="${aiot_root}/.current.next.$$"
ln -s "${release_dir}" "${current_next}"
mv -Tf "${current_next}" "${current_link}"

if ! "${current_link}/scripts/smoke-test.sh" post-activate; then
  if [ -n "${old_current}" ]; then
    rollback_next="${aiot_root}/.current.rollback.$$"
    ln -s "${old_current}" "${rollback_next}"
    mv -Tf "${rollback_next}" "${current_link}"
  else
    unlink "${current_link}"
  fi
  run_current smoke post-activate-rollback
fi

version_tmp="${aiot_root}/state/VERSION.tmp.$$"
printf '%s\n' "${release}" >"${version_tmp}"
mv -f "${version_tmp}" "${aiot_root}/state/VERSION"
log complete activated
