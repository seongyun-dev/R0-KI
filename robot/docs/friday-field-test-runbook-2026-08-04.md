# Friday field-test scope

This runbook covers only the changes required for the first manual mapping and
patrol integration test. Reboot recovery, automatic mapping-to-patrol mode
switching and general camera/LiDAR calibration remain deferred. Frontend SSE
and MJPEG reconnect handling is part of the demo-readiness release.

## Changes required before the test

Deploy all three demo-readiness merge requests before using the Frontend
mapping flow:

- IoT: `iot/fix/demo-readiness-20260807` into `iot/master`
- Backend: `back/fix/demo-readiness-20260807` into `back/master`
- Frontend: `front/fix/demo-readiness-20260807` into `front/master`

The IoT branch allows an OTA smoke check without a route when manual mapping
is enabled. The Backend branch reuses a failed mapping session with a new
command ID, and no longer requires the unused line sensor to be `NORMAL`
before patrol.

## Single-camera release step

The signed IoT OTA archive contains `robot/`, including the one-camera
`ai_runtime.py`, but intentionally does not replace the Jetson AI baseline
wrappers or `/opt/aiot/secrets/ai.env`. Therefore the one-camera rollout is a
single coordinated deployment with the IoT tag, not a tag-only operation.

Before activating the tag:

1. Keep `aiot-robot.service` inactive and confirm no patrol or mapping is active.
2. Back up the current AI run wrapper, preflight wrapper and `ai.env` without
   printing their contents.
3. Install the reviewed `aiot-ai-run.sh` and `aiot-ai-preflight.sh` atomically.
4. Update only the non-secret camera keys in the existing `ai.env`: enable
   single-camera mode, disable the dual-camera requirement and select
   `/dev/roki_camera_right`. Preserve every credential and model path.
5. Run shell syntax and AI preflight checks, activate the IoT tag, then restart
   `aiot-ai.service` and verify one physical capture plus fresh MJPEG frames.
6. If any gate fails, restore all three backups and the previous IoT release
   before restarting AI.

Never copy the example environment file over the live file, and never print or
record live environment values.

## Gamepad safety behaviour

`ROKI_MAPPING_GAMEPAD_INPUT_LEASE_SEC` defaults to `1.0`. If no new Linux
joystick event arrives before that lease expires, Robot sends STOP and
disarms the gamepad. The operator must return both axes to neutral, release
the deadman button, and press it again before motion resumes.

Some inexpensive wireless receivers do not emit repeated events while a stick
is held steady. With such a receiver, a held direction intentionally becomes a
bounded pulse of at most about one second instead of continuous motion.
Re-centre and command another pulse. Do not increase the lease beyond `1.0`
for the field test.

After a reconnect, Linux `JS_EVENT_INIT` values never arm motion. This prevents
a held deadman/stick state from being restored as a live drive command.

## Test order

1. Keep the motor power path disabled and connect the gamepad receiver.
2. Run the gamepad probe and record the actual axis/button numbers.
3. Confirm that releasing deadman, removing the receiver, and leaving input
   silent for more than one second each produce STOP before enabling free-floor
   motion. Confirm that silent-input STOP requires neutral/deadman re-arming.
4. Start mapping from the Frontend. A waypoint route is not required.
5. Drive at PWM 45 using short pulses. Avoid fast steering and revisit the
   starting area so SLAM can close the map.
6. Finish mapping only after the map shape is visually acceptable.
7. If START_MAPPING is rejected or fails, correct the readiness issue and use
   the Frontend retry action. The Backend reissues START_MAPPING for the same
   mapping session with a new command ID.
8. If the browser SSE stream ends unexpectedly, reload the mapping page. SSE
   automatic reconnect is outside this field-test patch.
9. Do not reboot or restart the Robot service between START_MAPPING and map
   upload. Pending-job reboot recovery is intentionally deferred.

## Mapping-to-patrol gate

Map upload does not automatically switch the Jetson from mapping to patrol.
Before the demonstration, an operator must complete this one-time binding:

1. Accept the final map in the Backend and keep its `mapId` and `mapVersion`.
2. Define the real parking zones, ordered waypoints, destination and fixed dock
   pose against that exact map. Do not reuse `DESTINATION_60CM` coordinates.
3. Install the matching map YAML/image and `route.local.yaml` on the Jetson.
4. Atomically update Robot/ROS environment identity fields: map ID/version,
   map and route SHA-256, fixed dock pose and `AIOT_ROS_MODE=patrol`.
5. Run the Nav2 preflight. It must validate identity, bounds, free-space
   clearance, dock pose and route hashes before ROS/Robot restart.
6. With the wheels raised first, verify `map -> odom -> base_link`, AMCL pose,
   both encoder distances and immediate STOP. Then perform a supervised
   low-speed curved waypoint run in the actual demo space.

The ROS odometry source is RF2O LiDAR odometry corrected by AMCL against the
fixed map. Wheel encoders are still required for drive feedback, travelled
distance and safety readiness, but there is no encoder/LiDAR EKF fusion in this
release. A stationary RF2O drift or failed AMCL correction blocks the floor
test. The line sensor is not used by any mapping or patrol gate.

## Vehicle-location MVP constraint

For this test, place the robot at a known stationary scan point, centre one
vehicle in the BRIO image, and keep the LiDAR front sector clear of walls,
posts and other vehicles. The current implementation combines Robot map pose,
BRIO detection and the nearest samples in the configured front LiDAR sector.
It does not associate a detection bounding box with a LiDAR cluster.

This constraint is suitable only for the controlled Friday demonstration. A
moving multi-vehicle scenario requires camera/LiDAR calibration, timestamp
synchronisation and object association and is not part of this patch.
