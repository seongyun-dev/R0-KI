#!/usr/bin/env bash
set -euo pipefail

robot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="${AIOT_EXPLORE_SOURCE_DIR:-/home/e103/explore_ws/src/m-explore-ros2}"
base_setup="${AIOT_EXPLORE_BASE_SETUP_FILE:-/home/e103/explore_ws/install/setup.bash}"
base_commit="326cf8a0b487c34246bb8f3326afbcd69576dc60"
patch_file="${robot_root}/patches/m-explore-ros2-326cf8a-roki-frontier-recovery.patch"
workspace="${robot_root}/.build/explore-overlay"
overlay="${robot_root}/ros-overlay"

case "${workspace}" in
  "${robot_root}"/.build/*) ;;
  *) echo "Refusing unsafe explore build path: ${workspace}" >&2; exit 1 ;;
esac
case "${overlay}" in
  "${robot_root}"/ros-overlay) ;;
  *) echo "Refusing unsafe explore overlay path: ${overlay}" >&2; exit 1 ;;
esac

test -d "${source_root}/.git"
test -r "${base_setup}"
test -s "${patch_file}"
test "$(git -C "${source_root}" rev-parse HEAD)" = "${base_commit}"

rm -rf "${workspace}" "${overlay}"
mkdir -p "${workspace}/src" "${overlay}"
cp -a --no-preserve=ownership "${source_root}" \
  "${workspace}/src/m-explore-ros2"

# Patch only the release-local copy. The directly tested Jetson workspace is
# never modified, so an OTA rollback also rolls back this explorer binary.
git -C "${workspace}/src/m-explore-ros2" reset --hard "${base_commit}"
git -C "${workspace}/src/m-explore-ros2" clean -fdx
git -C "${workspace}/src/m-explore-ros2" apply --check "${patch_file}"
git -C "${workspace}/src/m-explore-ros2" apply "${patch_file}"

set +u
# shellcheck disable=SC1090
source "${base_setup}"
set -u

colcon --log-base "${workspace}/log" build \
  --merge-install \
  --base-paths "${workspace}/src/m-explore-ros2/explore" \
  --build-base "${workspace}/build" \
  --install-base "${overlay}/install" \
  --packages-select explore_lite \
  --cmake-args -DBUILD_TESTING=OFF

test -r "${overlay}/install/setup.bash"
test -x "${overlay}/install/lib/explore_lite/explore"
echo "RO-KI explore overlay built from ${base_commit}"
