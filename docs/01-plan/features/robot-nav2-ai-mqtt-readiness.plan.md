# Robot Nav2, AI, MQTT Readiness - Plan Document

> Version: 1.1.0 | Date: 2026-08-03 | Status: Software scope complete
> Level: Enterprise | Owner: IoT

---

## 1. Overview

### 1.1 Purpose

Prepare every software, configuration, deployment, and non-actuating verification
step that can be completed before wheelbase, road-wheel angle, final map, and live
driving measurements are available. The result must be ready for a controlled
field session without requiring ad-hoc source changes on the Jetson.

### 1.2 Confirmed Device Baseline

- Two USB cameras have stable, unique `by-id` identities.
- Camera A and Camera B both sustain `640x480 MJPG 30 FPS` concurrently.
- The deployed AI pipeline currently defaults to sources `0` and `1`; source `1`
  is not a capture node and must be replaced by stable aliases.
- `yolo26_b2_416_fp16.engine` deserializes on TensorRT 10.3 with batch size 2.
- `plate_rec_fp16.engine` also deserializes successfully.
- YDLIDAR and RF2O workspaces are built on the Jetson; RF2O has previously
  emitted odometry.
- Full Navigation2 and `nav2_bringup` are not installed.
- MQTT TLS on port 8883 is reachable from the Jetson and certificate verification
  succeeds.

## 2. Goals

### 2.1 Primary Goals

- [x] Add stable left/right camera configuration without modifying the AI model.
- [x] Enforce the verified dual-camera capture format before AI startup.
- [x] Add versioned mapping and patrol ROS bringup configuration for YDLIDAR,
      RF2O, SLAM Toolbox, AMCL, and Nav2.
- [x] Add systemd readiness and service ordering without starting actuators.
- [x] Add safe MQTT TLS/auth/token verification that never prints credentials.
- [x] Preserve the single ESP32 serial owner and the integrated Robot runtime.
- [x] Document all deferred physical measurements and their acceptance gates.
- [x] Run all software-only tests, then push the IoT feature branch.

### 2.2 Non-Goals

- Installing packages or changing active services on the Jetson without a
  separately reviewed deployment step.
- Driving motors, steering the servo, occupying the ESP32 serial port, or making
  the robot move.
- Producing the final occupancy map or route coordinates.
- Guessing wheelbase, maximum road-wheel angle, LiDAR transform, or AMCL initial
  pose.
- Automatic exploration, complex dynamic obstacle avoidance, camera-LiDAR 3D
  fusion, or encoder/RF2O EKF fusion.

## 3. Selected Architecture

RF2O is the primary Nav2 odometry source because it is already built and has
produced odometry on the device. Encoder odometry remains the safety and telemetry
source in the integrated Robot runtime. If the field RF2O gate fails, a later
encoder-to-ROS odometry publisher will be added inside the existing single serial
owner; no second serial reader is permitted.

The patrol stack uses a fixed map and reviewed local waypoint file. Nav2 provides
map localization and path tracking. The Robot runtime remains the authority for
MQTT commands, AI readiness, LiDAR stop/resume interlocks, ESP32 control, final
STOP, pose/status publication, and backend event delivery.

## 4. Immediate Implementation Scope

### 4.1 Camera and AI

- Introduce `AIOT_AI_CAMERA_LEFT_DEVICE` and
  `AIOT_AI_CAMERA_RIGHT_DEVICE`, retaining front/rear compatibility.
- Install stable camera udev aliases for the two verified devices.
- Configure `640x480`, MJPG, 30 FPS, and a shallow capture buffer.
- Require both cameras and both TensorRT engines during preflight.
- Keep the existing AI repository and model files unchanged.

### 4.2 ROS and Nav2

- Provide `mapping` and `patrol` launch entrypoints.
- Source configurable YDLIDAR and RF2O workspaces.
- Add versioned YDLIDAR, RF2O, SLAM Toolbox, AMCL, costmap, planner, and
  controller parameters.
- Use Smac Hybrid-A and Regulated Pure Pursuit with rotate-to-heading disabled.
- Add readiness checks for `/scan`, `/odom`, TF, map, and Nav2 action server.
- Keep dynamic rerouting out of scope; the Robot LiDAR interlock performs the
  mandatory physical stop.

### 4.3 MQTT and Operations

- Verify TLS certificate and optional MQTT authentication without logging secret
  values.
- Observe real Robot status/ACK/token state using bounded timeouts.
- Document staged transport, contract, wheels-up, and live-patrol gates.
- Extend systemd installation and static CI validation.

## 5. Deferred Field Gates

- Wheelbase in metres.
- Actual left and right road-wheel angles for servo commands 60 and 100.
- LiDAR translation and yaw relative to `base_link`.
- RF2O stability and drift while stationary and moving.
- Final occupancy map, start pose, waypoint coordinates, and waypoint yaw.
- AMCL localization accuracy and recovery.
- LiDAR stop distance and clear hysteresis.
- Wheels-up and floor-driving tests at PWM 45.
- Real retained service token, backend START/STOP, event upload, reboot, and OTA
  rollback.

The runtime must remain fail-closed in `encoder_limited` mode until the steering
measurements are populated.

## 6. Success Criteria

- [x] All 183 Robot/Roki/Roki-IoT tests pass.
- [x] New camera, ROS config, systemd, and MQTT verification tests pass without
      serial access or actuator commands.
- [x] Both real cameras pass non-recording preflight via stable aliases.
- [x] Both TensorRT engines deserialize on the current Jetson runtime.
- [x] Nav2 configuration fails clearly when measurements are absent.
- [x] MQTT TLS verification passes and never outputs usernames, passwords, or
      service tokens.
- [x] The deployment package contains the new configuration and excludes secrets,
      field maps, local routes, and model binaries.
- [x] The feature branch is pushed only after the local and Jetson non-actuating
      checks pass.

Broker authentication and retained-token/command observation remain deferred
because the Jetson does not yet contain `/opt/aiot/secrets/robot.env` or a service
token file. The probe is implemented and ready for that field gate.

## 7. Schedule

| Phase | Estimate | Status |
|---|---:|---|
| Plan and device audit | 1 hour | Complete |
| Software/config implementation | 3-5 hours | Complete |
| Local test and package validation | 1-2 hours | Complete |
| Jetson non-actuating validation | 1 hour | Complete |
| Field measurements and mapping | 2-4 hours | Deferred |
| Live Nav2/MQTT patrol | 2-4 hours | Deferred |

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| RF2O scan timing is unstable | Nav2 cannot localize | Gate RF2O first; fall back to an encoder ROS publisher in the single runtime |
| Camera numbering changes | AI startup failure or wrong view | Use unique udev aliases and reject non-capture nodes in preflight |
| Ackermann robot receives an in-place turn | Unsafe steering command | Disable rotate-to-heading and retain the cmd_vel fail-closed adapter |
| Missing measurements are guessed | Unsafe curved driving | Keep values blank and Nav2 unavailable until measured |
| MQTT test leaks credentials | Credential exposure | Read root-only env files and redact all command output |
| Jetson AI working tree is overwritten | Loss of teammate work | Use execution adapters and environment values; never edit the AI checkout |

## 9. References

- `robot/docs/integrated-runtime-operations.md`
- `robot/docs/goal-mode-integration-handoff-2026-08-02.md`
- `robot/docs/ai-ros-contract-v1.md`
- `infra/jetson/README.md`
- `infra/HANDOFF.md`
