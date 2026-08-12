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

The patch changes mapping only. Each frontier cluster gets up to three
separated, robot-connected FREE viewpoints. `MappingGridBased` checks them in
sequence, the first feasible viewpoint keeps the established robot-to-target yaw,
and only exhaustion of all viewpoints consumes one retry for the cluster. The
exact `ComputePathToPose` result is sent to Nav2's `FollowPath` action instead
of asking `NavigateToPose` to create a different path and replan it while the
robot is moving. A short UNKNOWN fringe at the robot or frontier is allowed,
but a known-to-known shortcut containing more than 0.30 m of UNKNOWN space is
not crossed in one motion. The controller follows the known-space prefix,
stops 0.10 m before the bridge, and lets the next LiDAR update re-evaluate it.
This preserves exploration progress without permanently excluding a frontier.
Failures cool down for five seconds and an exhausted cluster can be
reactivated once only after local FREE-space growth proves that the map has
changed. It also distinguishes `exploration_stalled` from true completion and
waits for the previous Nav2 action to become terminal before replacing it. A
five-second cancel deadline fails closed instead of allowing a stale path to
remain live, and late callbacks from an older mapping generation are ignored.
Start-point return remains disabled in `config/ros/explore.params.yaml`.
