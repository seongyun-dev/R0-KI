#!/usr/bin/env bash
set -euo pipefail

target_branch="${1:-}"
commit_sha="${2:-}"
component="${3:-}"
repository_root="${CI_PROJECT_DIR:-$(pwd)}"
sync_script="${repository_root}/infra/scripts/sync-runtime.sh"
deploy_script="${repository_root}/infra/scripts/deploy.sh"
notify_script="${repository_root}/infra/scripts/notify-mattermost.sh"

if [ -z "${target_branch}" ] || [ -z "${commit_sha}" ]; then
  echo "usage: deploy-with-notification.sh <branch> <commit-sha> <frontend|backend|all>" >&2
  exit 1
fi
case "${component}" in
  frontend|backend|all) ;;
  *) echo "Unknown deployment component: ${component}" >&2; exit 1 ;;
esac

started_epoch="$(date +%s)"
result_file="$(mktemp /tmp/aiot-deploy-result.XXXXXX)"
cleanup() {
  rm -f -- "${result_file}"
}
trap cleanup EXIT

notify() {
  bash "${notify_script}" "$1" "${component}" "${started_epoch}" || \
    echo "Mattermost notifier returned an error; deployment result is unchanged" >&2
}

if bash "${sync_script}"; then
  :
else
  deploy_rc=$?
  notify failed
  exit "${deploy_rc}"
fi

component_mode="${component}"
if [ "${component}" = all ]; then component_mode=all; fi

if DEPLOY_RESULT_FILE="${result_file}" INTEGRATION_STATUS="${INTEGRATION_STATUS:-passed}" \
  bash "${deploy_script}" "${target_branch}" "${commit_sha}" "${component_mode}"; then
  notify success
  exit 0
else
  deploy_rc=$?
fi

deploy_result="$(tr -d '\r\n' <"${result_file}")"
case "${deploy_result}" in
  rolled_back) notify rolled_back ;;
  rollback_failed) notify rollback_failed ;;
  *) notify failed ;;
esac
exit "${deploy_rc}"
