#!/usr/bin/env bash
set -euo pipefail

repository_root="${CI_PROJECT_DIR:-$(pwd)}"
source_dir="${repository_root}/infra/scripts"
deploy_dir="${DEPLOY_DIR:-/srv/aiot/deploy}"

runtime_scripts=(
  backup.sh
  deploy.sh
  deploy-infrastructure.sh
  health-check.sh
  initialize-secrets.sh
  install-nginx.sh
  monitor-health.sh
  release-manifest.py
  rollback.sh
  sync-certificates.sh
  sync-runtime.sh
)

test -d "${source_dir}"
test -d "${deploy_dir}"
test -w "${deploy_dir}"

exec 9>"${deploy_dir}/runtime-sync.lock"
flock -w 30 9

temporary_files=()
cleanup() {
  local temporary_file
  for temporary_file in "${temporary_files[@]:-}"; do
    rm -f "${temporary_file}"
  done
}
trap cleanup EXIT

for script_name in "${runtime_scripts[@]}"; do
  source_file="${source_dir}/${script_name}"
  target_file="${deploy_dir}/${script_name}"
  temporary_file="${deploy_dir}/.${script_name}.new.${CI_JOB_ID:-$$}"

  test -r "${source_file}"
  install -m 0750 "${source_file}" "${temporary_file}"
  temporary_files+=("${temporary_file}")
  mv -f "${temporary_file}" "${target_file}"
done

echo "Runtime scripts synchronized to ${deploy_dir}"
