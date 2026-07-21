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

for component in robot ai; do
  smoke_script="${release_root}/${component}/scripts/smoke-test.sh"
  if [ -x "${smoke_script}" ]; then
    "${smoke_script}" "${phase}"
  fi
done

find "${release_root}/robot" "${release_root}/ai" -type f -name '*.py' -print0 | \
  xargs -0 -r python3 -m py_compile
echo "Jetson ${phase} smoke passed"
