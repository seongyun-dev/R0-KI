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
