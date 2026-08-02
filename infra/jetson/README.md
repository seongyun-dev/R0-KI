# Jetson AI service and Robot Pull OTA

This directory implements two deliberately separate lifecycles:

```text
/home/e103/yolo-pipeline        fixed AI baseline, aiot-ai.service
/opt/aiot/iot/releases/*        Robot-only iot-v* Pull OTA
```

IoT OTA never packages or modifies the AI venv, `*.pt`, `*.onnx`, `*.engine`,
AI logs, or evidence. AI and Robot communicate only through the versioned ROS 2
JSON contract in `robot/docs/ai-ros-contract-v1.md`.

## Boot order and failure policy

```text
network-online.target
  ├─ aiot-ai.service
  │    ├─ source /opt/ros/humble/setup.bash
  │    ├─ exec existing Python 3.10 AI venv
  │    └─ wait for /ai/status READY -> /run/aiot/ai-ready.json
  └─ aiot-update.service
       └─ check approved Robot manifest and activate when valid

aiot-robot.service
  ├─ Requires/After aiot-update.service
  └─ Wants/After aiot-ai.service
```

AI failure does not terminate Robot. Robot's live gate uses the two-second
`/ai/status` heartbeat, not the operations readiness file, and stays in LIMITED
mode when AI is missing, stale, or degraded.

The `aiot` system user writes ROS 2 logs below `/var/lib/aiot/ros`, not below
the read-only `/opt/aiot` release root. Python bytecode generation is disabled
for immutable Robot releases.

## AI runtime requirements

The existing entrypoint is:

```text
/home/e103/yolo-pipeline/venv/bin/python -m yolo_pipeline.main
```

The AI process must implement:

- `/ai/control`: reliable, transient-local, keep-last 1;
- `/ai/status`: reliable, volatile, keep-last 5, immediate and every 2 seconds;
- `/ai/detections`: reliable, volatile, keep-last 100;
- `ROS_LOCALHOST_ONLY=1`;
- evidence beneath `/var/lib/aiot/evidence`;
- a READY status only after engine load, camera open, and one warm-up inference.

`aiot-ai-wait-ready` observes the first valid READY heartbeat and atomically
writes `/run/aiot/ai-ready.json`. If no READY heartbeat arrives within the
configured timeout, systemd treats AI startup as failed and applies the bounded
restart policy.

AI configuration defaults are in `ai.env.example`. Do not put Backend, MQTT, or
Robot service credentials in AI configuration; Robot owns all external
delivery.

## Robot release contract

A protected `iot-vX.Y.Z` tag must point to a commit contained in `iot/master`.
The CI archive contains:

```text
aiot-iot-vX.Y.Z.tar.gz
  robot/
  scripts/install.sh
  scripts/smoke-test.sh
  VERSION
  manifest.json
  CHECKSUMS.sha256
```

`iot_publish` is a protected manual job. It uploads the immutable archive to
the `aiot-iot` Generic Package Registry and atomically replaces:

```text
/srv/aiot/releases/jetson/iot/stable/manifest.json
```

Public URL:

```text
https://i15e103.p.ssafy.io/jetson/releases/iot/stable/manifest.json
```

The manifest records the Robot commit, required AI contract version, JetPack,
architecture, archive size, and SHA-256. It does not record secrets or AI model
files.

## One-time installation

Copy the reviewed infra files to the Jetson through an authenticated channel,
then install without enabling:

```bash
sudo bash infra/jetson/install.sh
sudo install -m 0600 -o root -g root \
  infra/jetson/ai.env.example /opt/aiot/secrets/ai.env
sudo install -m 0600 -o root -g root \
  infra/jetson/package-read.env.example /opt/aiot/secrets/package-read.env
```

Fill the read-only GitLab Deploy Token only in `package-read.env`. Review AI
paths and optional camera/engine checks in `ai.env`.

The installer also creates stable serial aliases for this assembled Jetson USB
topology:

```text
/dev/roki_esp32  -> ESP32 CP2102 on physical USB path 2.4
/dev/roki_lidar  -> LiDAR CP2102 on physical USB path 2.2
```

Both adapters report the same factory serial number `0001`, so their
`/dev/serial/by-id` name must not be used. Keep the labelled devices in the
recorded USB sockets and verify both aliases after any cable-layout change.

Two USB cameras require the same treatment. A single UVC camera can create
multiple `/dev/video*` nodes, and their numbers are not stable. After both
cameras are physically connected, record `ID_PATH`, `ID_V4L_CAPABILITIES`, and
the video4linux `index` using `robot/hardware/jetson_field_audit.sh`; then add
udev aliases `/dev/roki_camera_front` and `/dev/roki_camera_rear` for the two
capture nodes. Configure those aliases in `ai.env`, never numeric video nodes.
`aiot-ai-run` forwards them to the current pipeline as `--source-a` and
`--source-b`.

Manual validation:

```bash
sudo systemctl start aiot-ai.service
sudo systemctl status aiot-ai.service --no-pager
sudo journalctl -u aiot-ai.service -n 100 --no-pager
sudo test -s /run/aiot/ai-ready.json

sudo systemctl start aiot-update.service
sudo systemctl status aiot-update.service --no-pager
readlink -f /opt/aiot/iot/current

sudo systemctl start aiot-robot.service
sudo systemctl status aiot-robot.service --no-pager
sudo journalctl -u aiot-robot.service -n 100 --no-pager
```

Only after normal, limited-mode, shutdown, and reboot tests pass:

```bash
sudo bash infra/jetson/install.sh --enable
sudo reboot
```

The installer never overwrites existing secret files or AI runtime files.

## Update and rollback behavior

At boot, `aiot-update`:

1. downloads the public stable manifest;
2. verifies exact schema, `component=iot`, AI contract, JetPack, architecture,
   and artifact host/path allowlist;
3. downloads the private archive with a read-only Deploy Token;
4. verifies archive size and SHA-256;
5. rejects unsafe paths, AI/model files, and payload checksum mismatches;
6. runs dependency install and a no-actuator pre-activation smoke;
7. atomically switches `/opt/aiot/iot/current`;
8. runs post-activation smoke and a five-second stationary runtime probe;
9. restores the previous symlink when post-activation validation fails.

Network, manifest, compatibility, download, or checksum failure keeps the
current release. A first installation with no valid current release remains
stopped instead of reporting a usable Robot runtime.

OTA is boot-time only. Before a manual update, stop patrol, confirm the
actuators are stopped, stop `aiot-robot.service`, then use
`sudo systemctl restart aiot-update.service`.

## Remaining application-owned integration

Infra does not reimplement Robot or AI features.

- AI must publish the ROS contract from `yolo_pipeline.main`.
- The drive/mission owner must call `AiRosBridge.gate.decision()` before
  `START_PATROL` and `set_detection_enabled()` on start/stop.
- The mission adapter must enrich detection outbox entries with Robot pose and
  deliver the Backend REST DTO.

These application hooks do not change the systemd or OTA contract.
