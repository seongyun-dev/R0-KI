#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_COMMAND:-python3}"

export PYTHONPATH="${robot_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
"${python_bin}" -m unittest discover -s "${robot_root}/tests" -v

(
  cd "${robot_root}/roki"
  PYTHONPATH= "${python_bin}" -m unittest discover -s tests -v
)
(
  cd "${robot_root}/roki-iot"
  PYTHONPATH="${robot_root}/roki:${robot_root}/src" \
    "${python_bin}" -m unittest discover -s . -p 'test_*.py' -v
)
find "${robot_root}/src" "${robot_root}/tests" -type f -name '*.py' -print0 | \
  xargs -0 -r "${python_bin}" -m py_compile
find "${robot_root}/roki" "${robot_root}/roki-iot" -type f -name '*.py' -print0 | \
  xargs -0 -r "${python_bin}" -m py_compile
