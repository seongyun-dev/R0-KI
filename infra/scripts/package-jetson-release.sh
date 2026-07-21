#!/usr/bin/env bash
set -euo pipefail

release="${1:-}"
output_dir="${2:-build/jetson}"
repository_root="${CI_PROJECT_DIR:-$(pwd)}"
source_commit="${CI_COMMIT_SHA:-}"
robot_commit="${ROBOT_COMMIT:-${source_commit}}"
ai_commit="${AI_COMMIT:-${source_commit}}"
model_version="${MODEL_VERSION:-unversioned}"
artifact_url="${JETSON_ARTIFACT_URL:-}"
published_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ ! "${release}" =~ ^jetson-v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "release must match jetson-vX.Y.Z" >&2
  exit 1
fi
if [[ ! "${robot_commit}" =~ ^[0-9a-f]{40}$ ]] || \
   [[ ! "${ai_commit}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ROBOT_COMMIT and AI_COMMIT must be 40-character lowercase commit SHAs" >&2
  exit 1
fi
if [[ ! "${artifact_url}" =~ ^https:// ]]; then
  echo "JETSON_ARTIFACT_URL must be an HTTPS URL" >&2
  exit 1
fi

has_component_files() {
  local directory="$1"
  find "${directory}" -type f ! -name '.gitignore' -print -quit 2>/dev/null | grep -q .
}

if ! has_component_files "${repository_root}/robot"; then
  echo "robot code is required for a Jetson release" >&2
  exit 1
fi
if ! has_component_files "${repository_root}/ai"; then
  echo "AI code is required for a Jetson release" >&2
  exit 1
fi

install -d -m 0750 "${output_dir}"
work_dir="$(mktemp -d /tmp/aiot-jetson-package.XXXXXX)"
stage_dir="${work_dir}/stage"

cleanup() {
  if [[ "${work_dir}" == /tmp/aiot-jetson-package.* ]] && [ -d "${work_dir}" ]; then
    find "${work_dir}" -depth -delete
  fi
}
trap cleanup EXIT

install -d -m 0750 \
  "${stage_dir}/robot" \
  "${stage_dir}/ai" \
  "${stage_dir}/models" \
  "${stage_dir}/requirements" \
  "${stage_dir}/scripts"

cp -a "${repository_root}/robot/." "${stage_dir}/robot/"
cp -a "${repository_root}/ai/." "${stage_dir}/ai/"
if [ -d "${repository_root}/models" ]; then
  cp -a "${repository_root}/models/." "${stage_dir}/models/"
fi
install -m 0755 "${repository_root}/infra/jetson/release/install.sh" \
  "${stage_dir}/scripts/install.sh"
install -m 0755 "${repository_root}/infra/jetson/release/smoke-test.sh" \
  "${stage_dir}/scripts/smoke-test.sh"
printf '%s\n' "${release}" >"${stage_dir}/VERSION"

(
  cd "${stage_dir}"
  find robot ai models -type f \
    \( -name 'requirements*.txt' -o -name 'pyproject.toml' -o \
       -name 'package.xml' -o -name 'CMakeLists.txt' \) \
    -print | LC_ALL=C sort >requirements/component-files.txt
  find robot ai models requirements scripts -type f -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum >CHECKSUMS.sha256
)

payload_sha256="$(sha256sum "${stage_dir}/CHECKSUMS.sha256" | awk '{print $1}')"
python3 - "${stage_dir}/manifest.json" "${release}" "${robot_commit}" \
  "${ai_commit}" "${model_version}" "${payload_sha256}" "${published_at}" <<'PY'
import json
import sys

path, release, robot_commit, ai_commit, model_version, payload_sha256, created_at = sys.argv[1:]
manifest = {
    "schema_version": 1,
    "release": release,
    "robot_commit": robot_commit,
    "ai_commit": ai_commit,
    "model_version": model_version,
    "jetpack": "6.2",
    "architecture": "aarch64",
    "payload_checksums_sha256": payload_sha256,
    "created_at": created_at,
}
with open(path, "w", encoding="utf-8") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY

archive_name="aiot-${release}.tar.gz"
archive_path="${output_dir}/${archive_name}"
manifest_path="${archive_path}.manifest.json"
tar -C "${stage_dir}" -czf "${archive_path}" .

artifact_sha256="$(sha256sum "${archive_path}" | awk '{print $1}')"
artifact_size_bytes="$(stat -c '%s' "${archive_path}")"
python3 - "${manifest_path}" "${release}" "${robot_commit}" "${ai_commit}" \
  "${model_version}" "${artifact_url}" "${artifact_size_bytes}" \
  "${artifact_sha256}" "${published_at}" <<'PY'
import json
import sys

(
    path,
    release,
    robot_commit,
    ai_commit,
    model_version,
    artifact_url,
    artifact_size_bytes,
    artifact_sha256,
    published_at,
) = sys.argv[1:]
manifest = {
    "schema_version": 1,
    "release": release,
    "robot_commit": robot_commit,
    "ai_commit": ai_commit,
    "model_version": model_version,
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
printf 'Jetson release packaged: %s\nManifest: %s\n' "${archive_path}" "${manifest_path}"
