#!/usr/bin/env bash
set -euo pipefail

phase="${1:-pre-activate}"
release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "${phase}" in
  pre-activate|post-activate) ;;
  *) echo "usage: smoke-test.sh [pre-activate|post-activate]" >&2; exit 2 ;;
esac

test -s "${release_root}/VERSION"
test -x "${release_root}/robot/scripts/run.sh"
test ! -e "${release_root}/ai"

"${release_root}/robot/scripts/smoke-test.sh" "${phase}"

find "${release_root}/robot" -type f -name '*.py' -print0 | \
  xargs -0 -r python3 -m py_compile
if find "${release_root}" -type f \
  \( -name '*.engine' -o -name '*.onnx' -o -name '*.pt' \) -print -quit | grep -q .; then
  echo "IoT release unexpectedly contains an AI model or engine" >&2
  exit 1
fi

if [ "${phase}" = post-activate ]; then
  set +e
  timeout --signal=TERM --kill-after=5s 5s \
    "${release_root}/robot/scripts/run.sh"
  runtime_status=$?
  set -e
  if [ "${runtime_status}" -ne 124 ] && [ "${runtime_status}" -ne 143 ]; then
    echo "Robot runtime exited during the stationary startup probe: ${runtime_status}" >&2
    exit 1
  fi
fi
echo "Jetson IoT ${phase} smoke passed; no actuator command was sent"
