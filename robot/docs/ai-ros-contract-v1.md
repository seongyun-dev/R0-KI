# AI–Robot ROS 2 contract v1

Robot owns mission state, driving, pose, MQTT, backend authentication, and REST
delivery. AI owns cameras, inference, tracking, OCR, and evidence creation.
Both processes run on the same Jetson with `ROS_LOCALHOST_ONLY=1`.

All three topics use `std_msgs/msg/String` containing UTF-8 JSON. Unknown JSON
fields may be ignored. A missing or unsupported `schemaVersion` is rejected.

## `/ai/control` — Robot to AI

QoS: reliable, transient-local, keep-last 1.

```json
{
  "schemaVersion": 1,
  "command": "ENABLE",
  "patrolId": 15,
  "requestedAt": "2026-07-31T05:20:00Z",
  "reason": "PATROL_STARTED"
}
```

`command` is `ENABLE` or `DISABLE`. AI must remain loaded while disabled but
must not emit new detection events. The transient-local message restores the
latest state if AI restarts.

## `/ai/status` — AI to Robot

QoS: reliable, volatile, keep-last 5. Publish immediately at startup and every
2 seconds.

```json
{
  "schemaVersion": 1,
  "state": "READY",
  "ready": true,
  "cameraReady": true,
  "engineReady": true,
  "inferenceReady": true,
  "modelVersion": "vehicle-v1",
  "heartbeatAt": "2026-07-31T05:20:02Z",
  "errorCode": null,
  "message": null
}
```

`state` is one of `STARTING`, `READY`, `DEGRADED`, `ERROR`, or `STOPPED`.
Robot allows patrol start only when the most recently received status is no
older than `AIOT_AI_STATUS_TIMEOUT_SEC` and all four readiness booleans are
true. Otherwise Robot stays in limited mode: driving remains stopped and
`START_PATROL` must be rejected, while health, OTA, stop, and diagnostic
operations remain available.

The AI service should also atomically write `/run/aiot/ai-ready.json` after the
venv, TensorRT engine, camera, and one warm-up inference all succeed. That file
is for systemd/operations readiness; Robot's live gate uses the heartbeat.

## `/ai/detections` — AI to Robot

QoS: reliable, volatile, keep-last 100.

```json
{
  "schemaVersion": 1,
  "eventId": "01J4AIOTEVENT00000000000001",
  "patrolId": 15,
  "eventType": "ILLEGAL_PARKING",
  "cameraId": "front",
  "trackId": "track-42",
  "confidence": 0.93,
  "observedAt": "2026-07-31T05:20:03Z",
  "evidencePath": "/var/lib/aiot/evidence/01J4AIOTEVENT00000000000001.jpg",
  "bbox": {"x": 120, "y": 80, "width": 300, "height": 180},
  "attributes": {"plateText": "12가3456"}
}
```

AI writes evidence beneath `/var/lib/aiot/evidence` and sends only the path.
Robot validates the message and atomically spools it under
`/var/lib/aiot/outbox`. The future mission/backend adapter enriches it with
Robot-owned pose and identity, posts the backend REST DTO, and removes the file
only after a successful response.

## AI service launch order

The AI venv can import `rclpy` only after ROS is sourced:

```bash
#!/usr/bin/env bash
set -euo pipefail
set +u
source /opt/ros/humble/setup.bash
set -u
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
exec /home/e103/yolo-pipeline/venv/bin/python -m your_ai_entrypoint
```

If a future venv changes Python ABI or disables system site packages, keep the
topic contract unchanged and move only the ROS publish/subscribe adapter into a
small system-Python bridge process.
