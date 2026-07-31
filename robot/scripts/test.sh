#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"

python3 -m unittest discover -s "${robot_root}/tests" -v
find "${robot_root}/src" "${robot_root}/tests" -type f -name '*.py' -print0 | \
  xargs -0 -r python3 -m py_compile
