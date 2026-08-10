#!/usr/bin/env bash
set -euo pipefail

release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

test ! -e "${release_root}/ai"
test -x "${release_root}/robot/scripts/install.sh"
"${release_root}/robot/scripts/install.sh"
test -x "${release_root}/robot/scripts/run.sh"
echo "Jetson IoT release dependencies installed; AI baseline was not modified"
