#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
wrapper="${repository_root}/infra/scripts/deploy-with-notification.sh"
test_root="$(mktemp -d /tmp/aiot-deploy-notify-test.XXXXXX)"

cleanup() {
  case "${test_root}" in
    /tmp/aiot-deploy-notify-test.*) rm -rf -- "${test_root}" ;;
    *) echo "Refusing to remove unexpected test path: ${test_root}" >&2 ;;
  esac
}
trap cleanup EXIT

fake_project="${test_root}/project"
fake_scripts="${fake_project}/infra/scripts"
notify_log="${test_root}/notify.log"
deploy_log="${test_root}/deploy.log"
mkdir -p "${fake_scripts}"

cat >"${fake_scripts}/sync-runtime.sh" <<'EOF'
#!/usr/bin/env bash
exit "${FAKE_SYNC_EXIT:-0}"
EOF

cat >"${fake_scripts}/deploy.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${FAKE_DEPLOY_LOG}"
if [ -n "${DEPLOY_RESULT_FILE:-}" ] && [ -n "${FAKE_DEPLOY_RESULT:-}" ]; then
  printf '%s\n' "${FAKE_DEPLOY_RESULT}" >"${DEPLOY_RESULT_FILE}"
fi
exit "${FAKE_DEPLOY_EXIT:-0}"
EOF

cat >"${fake_scripts}/notify-mattermost.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${FAKE_NOTIFY_LOG}"
EOF
chmod +x "${fake_scripts}"/*.sh

run_wrapper() {
  CI_PROJECT_DIR="${fake_project}" \
  FAKE_NOTIFY_LOG="${notify_log}" \
  FAKE_DEPLOY_LOG="${deploy_log}" \
  bash "${wrapper}" front/master aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa frontend
}

: >"${notify_log}"
: >"${deploy_log}"
FAKE_SYNC_EXIT=0 FAKE_DEPLOY_EXIT=0 FAKE_DEPLOY_RESULT=succeeded run_wrapper
grep -q '^success frontend ' "${notify_log}"

: >"${notify_log}"
if FAKE_SYNC_EXIT=0 FAKE_DEPLOY_EXIT=1 FAKE_DEPLOY_RESULT=rolled_back run_wrapper; then
  echo "Rolled-back deployment unexpectedly succeeded" >&2
  exit 1
fi
grep -q '^rolled_back frontend ' "${notify_log}"

: >"${notify_log}"
if FAKE_SYNC_EXIT=0 FAKE_DEPLOY_EXIT=1 FAKE_DEPLOY_RESULT=rollback_failed run_wrapper; then
  echo "Failed rollback unexpectedly succeeded" >&2
  exit 1
fi
grep -q '^rollback_failed frontend ' "${notify_log}"

: >"${notify_log}"
: >"${deploy_log}"
if FAKE_SYNC_EXIT=1 FAKE_DEPLOY_EXIT=0 FAKE_DEPLOY_RESULT=succeeded run_wrapper; then
  echo "Runtime synchronization failure unexpectedly succeeded" >&2
  exit 1
fi
grep -q '^failed frontend ' "${notify_log}"
test ! -s "${deploy_log}"

echo "Deployment notification wrapper tests passed"
