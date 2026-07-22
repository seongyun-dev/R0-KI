#!/usr/bin/env bash
set -euo pipefail

release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for component in robot ai; do
  install_script="${release_root}/${component}/scripts/install.sh"
  if [ -x "${install_script}" ]; then
    "${install_script}"
  fi
done

test -x "${release_root}/robot/scripts/run.sh"
echo "Jetson release dependencies installed"
