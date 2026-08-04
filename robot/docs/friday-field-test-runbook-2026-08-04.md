# Friday field-test scope

This runbook covers only the changes required for the first manual mapping and
patrol integration test. Reboot recovery, automatic mapping-to-patrol mode
switching, general camera/LiDAR calibration and SSE reconnection remain
deferred.

## Changes required before the test

Deploy both field-test branches before using the Frontend mapping flow:

- IoT: `iot/feat/manual-mapping-gamepad`
- Backend: `back/fix/field-mapping-test`

The IoT branch allows an OTA smoke check without a route when manual mapping
is enabled. The Backend branch reuses a failed mapping session with a new
command ID, and no longer requires the unused line sensor to be `NORMAL`
before patrol.

## Gamepad safety behaviour

`ROKI_MAPPING_GAMEPAD_INPUT_LEASE_SEC` defaults to `0.25`. If no new Linux
joystick event arrives before that lease expires, Robot sends STOP and
disarms the gamepad. The operator must return both axes to neutral, release
the deadman button, and press it again before motion resumes.

Some inexpensive wireless receivers do not emit repeated events while a stick
is held steady. With such a receiver, a held direction intentionally becomes a
short pulse instead of continuous motion. Re-centre and command another pulse.
Do not increase the lease for the field test.

After a reconnect, Linux `JS_EVENT_INIT` values never arm motion. This prevents
a held deadman/stick state from being restored as a live drive command.

## Test order

1. Keep the motor power path disabled and connect the gamepad receiver.
2. Run the gamepad probe and record the actual axis/button numbers.
3. Confirm that releasing deadman, removing the receiver, and leaving input
   silent each produce STOP before enabling free-floor motion.
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

## Vehicle-location MVP constraint

For this test, place the robot at a known stationary scan point, centre one
vehicle in the BRIO image, and keep the LiDAR front sector clear of walls,
posts and other vehicles. The current implementation combines Robot map pose,
BRIO detection and the nearest samples in the configured front LiDAR sector.
It does not associate a detection bounding box with a LiDAR cluster.

This constraint is suitable only for the controlled Friday demonstration. A
moving multi-vehicle scenario requires camera/LiDAR calibration, timestamp
synchronisation and object association and is not part of this patch.
