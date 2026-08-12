# Jetson SLAM Toolbox reset backport

`slam-toolbox-2.6.10-reset-backport.patch` preserves the directly tested Jetson
changes that add `/slam_toolbox/reset` to upstream `slam_toolbox` 2.6.10.

- Upstream base: `8293d21fe5c816d0405e0cc1f3eb46c70659c267`
- Jetson workspace: `/home/e103/slam-toolbox-2610-reset-backport-ws`
- Runtime overlay: `/home/e103/slam-toolbox-2610-reset-backport-ws/install/setup.bash`

The patch includes the new `srv/Reset.srv`. Apply it only to the upstream base
above, build it as a separate colcon overlay, and source the overlay after
`/opt/ros/humble/setup.bash`. It is preserved for source control and must not be
used as an OTA payload for the directly modified Jetson.

# RO-KI explore_lite frontier recovery

`m-explore-ros2-326cf8a-roki-frontier-recovery.patch` is an OTA-managed patch
for upstream `m-explore-ros2` commit
`326cf8a0b487c34246bb8f3326afbcd69576dc60`.

During installation, `scripts/build-explore-overlay.sh` copies the preserved
Jetson source workspace, validates the exact base revision, applies the patch
only to the release-local copy, and builds `ros-overlay/install`. It never
modifies `/home/e103/explore_ws`. The explorer supervisor and smoke test both
require that release-local overlay, which keeps activation and rollback atomic.

The patch changes mapping only: it chooses a robot-connected FREE approach
cell, points the goal from that approach cell toward the last FREE cell at the
frontier boundary, prechecks it with `MappingGridBased`, retries transient
failures with a bounded cooldown, and distinguishes `exploration_stalled` from
true completion. Start-point return remains disabled in
`config/ros/explore.params.yaml`.
