#!/usr/bin/env bash
set -euo pipefail

release="${1:-}"
output_dir="${2:-build/iot}"
repository_root="${CI_PROJECT_DIR:-$(pwd)}"
robot_source="${ROBOT_SOURCE_DIR:-${repository_root}/robot}"
source_commit="${CI_COMMIT_SHA:-}"
iot_commit="${IOT_COMMIT:-${source_commit}}"
required_ai_contract_version="${REQUIRED_AI_CONTRACT_VERSION:-1}"
artifact_url="${IOT_ARTIFACT_URL:-}"
published_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ ! "${release}" =~ ^iot-v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "release must match iot-vX.Y.Z" >&2
  exit 1
fi
if [[ ! "${iot_commit}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "IOT_COMMIT must be a 40-character lowercase commit SHA" >&2
  exit 1
fi
if [[ ! "${required_ai_contract_version}" =~ ^[1-9][0-9]*$ ]]; then
  echo "REQUIRED_AI_CONTRACT_VERSION must be a positive integer" >&2
  exit 1
fi
if [[ ! "${artifact_url}" =~ ^https:// ]]; then
  echo "IOT_ARTIFACT_URL must be an HTTPS URL" >&2
  exit 1
fi
if [ ! -x "${robot_source}/scripts/run.sh" ] || \
   [ ! -x "${robot_source}/scripts/install.sh" ] || \
   [ ! -x "${robot_source}/scripts/test.sh" ] || \
   [ ! -x "${robot_source}/scripts/smoke-test.sh" ]; then
  echo "robot/scripts run, install, test, and smoke-test contracts are required" >&2
  exit 1
fi
if [ ! -s "${robot_source}/docs/ai-ros-contract-v1.md" ]; then
  echo "robot/docs/ai-ros-contract-v1.md is required" >&2
  exit 1
fi

install -d -m 0750 "${output_dir}"
work_dir="$(mktemp -d /tmp/aiot-iot-package.XXXXXX)"
stage_dir="${work_dir}/stage"

cleanup() {
  if [[ "${work_dir}" == /tmp/aiot-iot-package.* ]] && [ -d "${work_dir}" ]; then
    find "${work_dir}" -depth -delete
  fi
}
trap cleanup EXIT

install -d -m 0750 "${stage_dir}/robot" "${stage_dir}/scripts"
tar -C "${robot_source}" \
  --exclude='./.venv' \
  --exclude='./.env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -cf - . | tar -C "${stage_dir}/robot" -xf -
install -m 0755 "${repository_root}/infra/jetson/release/install.sh" \
  "${stage_dir}/scripts/install.sh"
install -m 0755 "${repository_root}/infra/jetson/release/smoke-test.sh" \
  "${stage_dir}/scripts/smoke-test.sh"
printf '%s\n' "${release}" >"${stage_dir}/VERSION"

python3 - "${stage_dir}/manifest.json" "${release}" "${iot_commit}" \
  "${required_ai_contract_version}" "${published_at}" <<'PY'
import json
import sys

path, release, iot_commit, contract_version, created_at = sys.argv[1:]
manifest = {
    "schema_version": 1,
    "component": "iot",
    "release": release,
    "iot_commit": iot_commit,
    "required_ai_contract_version": int(contract_version),
    "jetpack": "6.2",
    "architecture": "aarch64",
    "created_at": created_at,
}
with open(path, "w", encoding="utf-8") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY

if find "${stage_dir}" -type f \
  \( -name '*.engine' -o -name '*.onnx' -o -name '*.pt' \) -print -quit | grep -q .; then
  echo "IoT release must not contain AI models or TensorRT engines" >&2
  exit 1
fi
if [ -e "${stage_dir}/ai" ]; then
  echo "IoT release must not contain ai/" >&2
  exit 1
fi

(
  cd "${stage_dir}"
  find robot scripts -type f -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum >CHECKSUMS.sha256
  sha256sum VERSION manifest.json >>CHECKSUMS.sha256
)

archive_name="aiot-${release}.tar.gz"
archive_path="${output_dir}/${archive_name}"
manifest_path="${archive_path}.manifest.json"
tar -C "${stage_dir}" -czf "${archive_path}" .

artifact_sha256="$(sha256sum "${archive_path}" | awk '{print $1}')"
artifact_size_bytes="$(stat -c '%s' "${archive_path}")"
python3 - "${manifest_path}" "${release}" "${iot_commit}" \
  "${required_ai_contract_version}" "${artifact_url}" "${artifact_size_bytes}" \
  "${artifact_sha256}" "${published_at}" <<'PY'
import json
import sys

(
    path,
    release,
    iot_commit,
    contract_version,
    artifact_url,
    artifact_size_bytes,
    artifact_sha256,
    published_at,
) = sys.argv[1:]
manifest = {
    "schema_version": 1,
    "component": "iot",
    "release": release,
    "iot_commit": iot_commit,
    "required_ai_contract_version": int(contract_version),
    "jetpack": "6.2",
    "architecture": "aarch64",
    "artifact_url": artifact_url,
    "artifact_size_bytes": int(artifact_size_bytes),
    "sha256": artifact_sha256,
    "published_at": published_at,
}
with open(path, "w", encoding="utf-8") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY

python3 "${repository_root}/infra/scripts/validate-jetson-manifest.py" \
  "${manifest_path}" "${repository_root}/infra/jetson/manifest.schema.json"
printf 'Jetson IoT release packaged: %s\nManifest: %s\n' \
  "${archive_path}" "${manifest_path}"
