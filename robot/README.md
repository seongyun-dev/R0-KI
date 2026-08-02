# Hanbakwi Robot runtime

This directory is the Jetson-side Robot runtime contract for the `iot/*`
branches. It deliberately starts without commanding motors or steering.

The initial runtime provides:

- a real `robot/scripts/run.sh` entrypoint for `aiot-robot.service`;
- ROS 2 subscriptions for AI status and detections;
- a latched AI `ENABLE` / `DISABLE` control publisher;
- an AI readiness gate that rejects patrol start while AI is missing, stale, or
  degraded;
- a durable local detection outbox for later backend REST delivery;
- an HTTPS Robot backend client matching the current `/api/robot/events`,
  `/events/batch`, `/vehicle-checks`, and evidence upload endpoints;
- install, test, and OTA smoke-test entrypoints.

The mission/drive owner can compose `AiRosBridge` into the real Robot process.
Until that integration happens, the standalone entrypoint remains stationary,
publishes `DISABLE`, monitors AI, and safely spools any received detections.

## Why no separate ROS bridge process is required

On the target Jetson, the AI venv uses Python 3.10 and
`include-system-site-packages = true`. `rclpy` is available inside that venv
after ROS 2 is sourced:

```bash
source /opt/ros/humble/setup.bash
/home/e103/yolo-pipeline/venv/bin/python -c \
  'import rclpy; rclpy.init(); n=rclpy.create_node("probe"); n.destroy_node(); rclpy.shutdown()'
```

Therefore the AI service should source ROS before starting its existing venv.
A separate bridge is only a fallback if the Python/ROS ABI changes later.

## Local Jetson execution

This is a no-movement runtime:

```bash
cd robot
./scripts/install.sh
AIOT_EVENT_OUTBOX_DIR="$HOME/.local/state/aiot/outbox" ./scripts/run.sh
```

Run the checks with:

```bash
./scripts/test.sh
./scripts/smoke-test.sh pre-activate
```

The assembled Jetson must expose the ESP32 as `/dev/roki_esp32`. The ESP32 and
LiDAR CP2102 adapters both report serial `0001`, so `/dev/serial/by-id/...0001`
is ambiguous and is intentionally not used by the Robot runtime.

The production environment template is in
`config/robot.env.example`. The ROS JSON contract and integration points are in
`docs/ai-ros-contract-v1.md`.

The physical robot integration order, calibration responsibilities, same-day
gates, and demo acceptance criteria are documented in
`docs/robot-demo-integration-plan.md`.

## ESP32, drive, and MQTT implementation snapshot

The assembled robot's verified hardware implementation is preserved separately
from the no-movement OTA entrypoint:

- `roki/`: ESP32 JSON protocol, odometry, safety, mission, and motion runtime;
- `roki-iot/`: the existing MQTT publisher composed with `roki/`;
- `hardware/`: ESP32 firmware 2.2.0 and bounded bench/drive tests.

These directories mirror the live Jetson paths `/home/e103/roki`,
`/home/e103/roki-iot`, and selected files from `/home/e103/robot-hw-test`.
They are not yet the process started by `scripts/run.sh`.

The live-source snapshot also preserves the legacy `roki/ai`, `roki/camera`,
`roki/mqtt`, manual diagnostic scripts, and `roki-iot/esp32_serial` modules.
They are source backup and integration reference only. They were syntax-checked
during import, but production OTA must not invoke them until the mission owner reviews their
hardware side effects and folds the required pieces into the stationary
`scripts/run.sh` entrypoint.

Read [the ESP32/MQTT runtime handoff](docs/esp32-mqtt-runtime-handoff.md)
before changing the production entrypoint, systemd service, or OTA activation
flow. It records the pin map, wire protocol, verified commands, safety
invariants, test evidence, and remaining integration work.

## Mission integration

The patrol pipeline must do three things:

1. Before accepting `START_PATROL`, call `bridge.gate.decision()` and reject the
   command unless `allowed` is true.
2. After a patrol is accepted, call
   `bridge.set_detection_enabled(True, patrol_id, "PATROL_STARTED")`.
3. On patrol stop, emergency stop, or shutdown, call
   `bridge.set_detection_enabled(False, patrol_id, reason)`.

The backend adapter should consume durable outbox files only after it can add
the current `robotId`, `patrolId`, and robot pose required by the REST DTO.
Successful REST delivery may then delete the corresponding outbox file.

`RobotBackendClient` already implements the authenticated HTTP transport. The
mission owner supplies the event DTO at the point where pose and patrol timing
are known; secrets stay in `/opt/aiot/secrets/robot.env`.
