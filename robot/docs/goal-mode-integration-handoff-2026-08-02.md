# RO-KI 완성 작업 인수인계서 — Goal 모드 실행본

기준 시각: 2026-08-02 23:00 KST

대상: 다음 Codex Goal 작업자

범위: 실측·배선·물리 주행을 제외한 Robot 소프트웨어, 백엔드/MQTT, AI, systemd, OTA 통합

이 문서는 이전 대화를 다시 읽지 않고도 작업을 시작할 수 있도록 작성한 단일 기준서다.
과거의 현장 기록은 증거로 남기되, 서로 충돌하는 설명이 있으면 이 문서의 결정과 현재
코드를 먼저 따른다.

## 0. 다음 작업자가 가장 먼저 할 일

아래 순서로 현재 상태를 다시 감사한다. 이 단계에서는 ESP32 포트를 열거나 서비스를
시작하지 않는다.

```powershell
cd C:\workspace\iot\.codex_tmp\iot-dev-20260802
git fetch origin --prune
git status --short --branch
git log -1 --oneline
git log --all --date=iso --pretty=format:'%h %ad %d %s' -n 30
```

현재 문서 작성 브랜치의 기준은 다음과 같다.

```text
branch: iot/feat/waypoint-mqtt-field-demo
base commit before this handoff: 27f5c4b
remote: origin/iot/feat/waypoint-mqtt-field-demo
```

반드시 `origin/iot/dev`, 상태 송신 담당자의 새 브랜치/MR, `origin/back/dev`,
`origin/back/fix_revise_api_url`, `origin/front/dev`가 문서 작성 후 갱신됐는지 다시 확인한다.
다른 작업자의 변경이 올라왔다면 먼저 병합하고 이 문서의 상태 표를 갱신한다.

이 IoT 브랜치의 working tree에는 backend/frontend 전체 소스가 없다. `git diff
origin/back/dev -- backend`에 대량의 `D`가 보이는 것은 로컬 파일을 실수로 지운 것이 아니라
역할 브랜치 구조 때문이다. 백엔드와 프론트를 검사하거나 수정할 때는 현재 IoT worktree에
두 브랜치를 섞지 말고 별도 worktree를 만든다.

```powershell
git worktree add --detach C:\workspace\iot\.codex_tmp\back-dev-audit origin/back/dev
git worktree add --detach C:\workspace\iot\.codex_tmp\front-dev-audit origin/front/dev
```

백엔드 변경이 필요하면 audit worktree에서 `origin/back/dev` 기반의 별도 `back/*` feature
branch를 만들고 그 브랜치/MR로 제출한다. IoT commit에 backend 소스를 통째로 복사하지 않는다.

Jetson은 감사 당시 다음 주소로 접속됐다.

```text
host: e103@192.168.0.10
hostname: e103-desktop
```

IP는 DHCP로 바뀔 수 있다. 비밀번호·토큰은 Git에 적지 않는다. 사용자가 별도로 제공한
자격 증명이 더 이상 맞지 않으면 추측하지 말고 사용자에게 다시 확인한다.

## 1. Goal에 그대로 넣을 목표

```text
실측, 배선 변경, 실제 모터 구동 없이 RO-KI의 production Robot 런타임을 완성한다.
GitLab의 최신 IoT/상태 송신 변경을 먼저 재감사하고, START_PATROL MQTT 수신부터
AI readiness 확인, ESP32 명령, waypoint 진행, pose/status 발행, AI 탐지 이벤트의
Robot outbox 및 백엔드 REST 전달, DESTINATION 자동 종료, STOP_PATROL ACK까지를
하나의 OTA 배포 가능한 서비스 구성으로 통합한다. 실제 장비 대신 fake serial,
recorded telemetry, fake AI detections, 로컬 MQTT와 백엔드 fixture로 E2E를 검증한다.
Jetson의 활성 서비스·/home 소스·비밀 파일은 덮어쓰지 않는다. 모든 변경은 테스트,
운영 환경 템플릿, 배포/롤백 절차, 남은 물리 검증 게이트와 함께 GitLab에 남긴다.
```

### Goal의 완료 조건

다음이 모두 충족돼야 완료다.

1. `aiot-robot.service`가 정지 전용 `aiot_robot.main`이 아니라 실제 통합 런타임을 실행한다.
2. 같은 프로세스가 ESP32 Serial을 단독 소유하고 MQTT START/STOP, waypoint, pose/status,
   ROS AI bridge를 조율한다.
3. `START_PATROL`은 유효한 명령, 준비된 ESP32, fresh AI READY 상태를 모두 확인한 뒤에만
   `SUCCEEDED` ACK를 보낸다.
4. 목적지에서는 백엔드 STOP을 기다리지 않고 Robot이 먼저 STOP을 보낸다. 최종 pose가
   백엔드 DESTINATION 사각형 안에 들어가면 백엔드가 순찰을 완료하고 `STOP_PATROL`을
   발행하며 Robot은 정지를 재확인하고 ACK한다.
5. AI는 고정 좌표와 직접 REST를 사용하지 않는다. 탐지·OCR·증거만 만들고 ROS 계약으로
   Robot에 넘기며, Robot이 당시 pose와 patrolId를 붙여 REST/outbox를 관리한다.
6. 기능 브랜치의 비이동 테스트, 계약 테스트, 로컬 MQTT/백엔드 E2E가 통과한다.
7. 실제 움직임이 필요한 검증은 실행하지 않고 명확한 현장 게이트로 남긴다.
8. OTA 패키지에 모델, `.env`, 토큰, 현장 `route.local.yaml`이 포함되지 않는다.

## 2. 최종 시연에서 요구하는 흐름

```text
프론트 순찰 시작 버튼
  -> POST /api/patrols (202)
  -> backend: Patrol IN_PROGRESS 저장
  -> MQTT START_PATROL (QoS 1, TTL 10초)
  -> Jetson: 명령 schema/robotKey/commandId/expiresAt 검증
  -> Jetson: AI READY heartbeat + ESP32 준비 상태 확인
  -> ESP32: STOP -> HELLO -> ENCODER_ZERO -> fresh odometry/status
  -> Robot: AI ENABLE, waypoint mission 시작, START ACK SUCCEEDED
  -> 저속 주행 + map frame pose/status MQTT
  -> AI: 카메라/추론/Tracker/OCR, evidence 저장, detection ROS 발행
  -> Robot: detection에 patrolId/pose를 결합하고 REST/outbox 처리
  -> Robot: 로컬 DESTINATION waypoint 도달 즉시 ESP32 STOP
  -> Robot: DESTINATION 안의 최종 pose와 IDLE 상태 발행
  -> backend: pose가 DESTINATION 사각형 안인지 판정
  -> backend: Patrol COMPLETED, STOP_PATROL MQTT
  -> Jetson: STOP 재전송, AI DISABLE, STOP ACK SUCCEEDED, IDLE 유지
  -> 프론트: 완료된 순찰 상세/이벤트 조회
```

Robot의 선제 정지와 백엔드의 STOP은 중복이 아니라 안전을 위한 이중 확인이다.

## 3. 권위 소스와 절대 덮어쓰면 안 되는 것

| 영역 | 권위 소스 | 현재 상태 | 규칙 |
|---|---|---|---|
| Robot/IoT | 이 GitLab 브랜치의 `robot/` | waypoint/MQTT와 동료의 pose/status 작업까지 보존됨 | 모든 최종 코드는 Git에서 수정 |
| 백엔드 계약 | `origin/back/dev` | START/STOP, DESTINATION, REST 존재 | Swagger 설명보다 실제 DTO/서비스 우선 |
| 백엔드 파일 URL 수정 | `origin/back/fix_revise_api_url` | `back/dev`와 4파일 차이 | 최신 병합 여부를 다시 확인 |
| 프론트 | `origin/front/dev` | 시작 버튼이 `POST /api/patrols` 호출 | 완료 표시 신뢰성은 별도 개선 |
| AI 모델 | `origin/ai/dev:ai/Yolo/best.pt`와 Jetson engine | 모델 변경 없음 전제 | IoT OTA에 모델을 포함하지 않음 |
| AI 실행 소스 | `/home/e103/yolo-pipeline` | Git repo가 아닌 수동 배치본 | 원본 백업 없이 수정/덮어쓰기 금지 |
| Jetson 수동 Robot 소스 | `/home/e103/roki`, `/home/e103/roki-iot` | Git repo가 아니며 Git보다 일부 최신 | 참고·비교만 하고 바로 활성화하지 않음 |
| OTA 활성본 | `/opt/aiot/iot/current` | `iot-v0.1.1` | 릴리스 외 직접 편집 금지 |
| 병합 출처 | `/home/e103/waypoint-status-merge-stage-20260802-205644` | 이 handoff commit에 선별 보존됨 | 출처 증거일 뿐, 앞으로는 Git이 권위 소스 |

병합 출처에는 `.env`, token 파일, venv, `__pycache__`, 현장 route가 섞여 있었다. 사용자와
동료 작업자의 위임을 확인한 뒤 소스·설정·테스트만 파일별로 선별 병합했다. 앞으로는 해당
Jetson 디렉터리를 다시 복사하지 말고 이 Git commit을 기준으로 수정한다.

## 4. 확정된 실물 상수 — 다시 추정하지 말 것

이 값은 이미 현장에서 측정 또는 검증됐다. Goal 작업 중에는 상수와 fixture로 사용한다.

| 항목 | 값 |
|---|---|
| 휠 지름 | 65 mm |
| 왼 encoder 평균 | 329 ticks/rev (327, 325, 335) |
| 오른 encoder 평균 | 328 ticks/rev (320, 335, 329) |
| 런타임 공통값 | 329 ticks/rev |
| 조향 기준 | 60° 왼쪽, 80° 정면, 100° 오른쪽 |
| 검증된 저속 PWM | 45 |
| ESP32 운영 장치 | `/dev/roki_esp32` |
| LiDAR 운영 장치 | `/dev/roki_lidar` |
| 첫 직선 route 시작 | map `(1.0, 2.5, yaw 0°)` |
| 첫 직선 DESTINATION | map `(1.6, 2.5, yaw 0°)` |

라인트레이싱은 주행 방식에서 폐기됐다. 센서 코드는 진단 자산일 뿐 production mission에
다시 연결하지 않는다. 지도는 수동 주행 SLAM으로 만들고, 순찰은 map-frame waypoint를
사용한다. 실제 지도가 오기 전에는 checked-in dummy map을 사용한다.

## 5. 2026-08-02 Jetson 감사 결과

### 서비스와 장치

```text
aiot-update.service: enabled, active(exited)
aiot-robot.service:  disabled, inactive
aiot-ai.service:     disabled, inactive
active OTA symlink: /opt/aiot/iot/releases/iot-v0.1.1
/dev/roki_esp32:    /dev/ttyUSB0
/dev/roki_lidar:    없음
/dev/video*:        없음
ESP32 serial owner: 없음
```

따라서 전원만 넣는다고 Robot/AI가 자동 실행되는 상태가 아니다. OTA updater도 부팅 당시
`i15e103.p.ssafy.io` DNS 해석 실패를 로그에 남겼다. 서비스 활성화는 통합본이 fail-closed로
검증된 뒤 마지막 단계에서만 한다.

### Python과 ROS

- Jetson: L4T R36.4.7, Python 3.10.12.
- `/opt/ros/humble/setup.bash`를 source하면 system Python과
  `/home/e103/yolo-pipeline/venv/bin/python` 모두 `rclpy`를 import한다.
- 현재 환경에서는 Python ABI 때문에 별도 ROS bridge 프로세스를 만들 필요가 없다.
- 향후 AI venv ABI가 바뀔 때만 system-Python bridge를 fallback으로 고려한다.

### 현재 production 시작점의 문제

`robot/scripts/run.sh`는 다음만 실행한다.

```text
python -m aiot_robot.main
```

`robot/src/aiot_robot/main.py`는 AI 상태와 detection을 받는 정지 전용 ROS node다. 시작 시
`DISABLE`을 발행하고 모터 명령을 만들지 않는다. 반면 실제 주행/MQTT/waypoint 구현은
`robot/roki/`, `robot/roki-iot/`에 따로 있다. OTA 서비스가 이 코드를 실행하지 않으므로
현재 릴리스는 실제 순찰을 시작할 수 없다.

### 이 handoff와 함께 Git에 보존한 동료 작업

다음 코드는 Jetson 격리 staging과 기존 waypoint 브랜치를 파일별로 병합한 뒤 비이동
테스트를 통과했다.

- `roki/localization/`: encoder odom, map pose 모델·arbitrator, ROS TF bridge.
- `roki/sensors/ros_lidar_health_bridge.py`: scan health와 obstacle 갱신.
- `roki/safety/obstacle_guard.py`: 전방 sector 정지/해제 hysteresis.
- 공용 `RobotStateStore`: pose/status/obstacle를 Robot과 MQTT가 공유.
- `roki-iot/run_integrated.py`: Serial runtime, ROS pose/LiDAR, waypoint, MQTT 단일 조립 후보.
- `hardwareStatus`: 배터리 SoC와 미보정 pack voltage를 분리해 보존.
- udev alias의 실제 장치 경로를 해석하는 serial device finder.
- 동료 작업 테스트와 waypoint/status 병합 회귀 테스트.

stable `/dev/roki_esp32`, camera alias, PWM 45, line-follow 폐기, waypoint route 등 이 브랜치의
더 최신 현장 결정을 유지했고 staging의 `/dev/ttyUSB0`, numeric camera, PWM 51 같은 과거
기본값은 가져오지 않았다. 이 보존은 Git 소스에만 했으며 Jetson 활성 경로와 service는
변경하지 않았다.

### 현재 AI 시작점의 문제

`aiot-ai.service`는 기본적으로 다음을 실행한다.

```text
/home/e103/yolo-pipeline/venv/bin/python -m yolo_pipeline.main
```

읽기 전용 시험 결과:

```text
ModuleNotFoundError: No module named 'config'
```

현재 `main.py`가 `import config`, `from detector import ...` 같은 스크립트 기준 절대 import를
사용하기 때문이다. `python yolo_pipeline/main.py --help`만 성공한다.

현재 `aiot-ai-preflight`는 `find_spec()`까지만 검사해 실제 module body를 import하지 않으므로
이 오류를 잡지 못한다. Goal에서는 실제 entrypoint import 또는 `--help` smoke까지 검사해
preflight의 false positive를 제거한다.

더 중요한 기능 차이는 다음과 같다.

- `/ai/control`, `/ai/status`, `/ai/detections`를 구현하지 않았다.
- 시작하자마자 두 카메라와 TensorRT를 실행한다.
- 위치를 `CURRENT_X=10.0`, `CURRENT_Y=20.0`으로 고정한다.
- AI가 Robot을 거치지 않고 backend REST를 직접 호출한다.
- 증거가 `/var/lib/aiot/evidence`가 아닌 AI 폴더 아래에 생성된다.
- `/run/aiot/ai-ready.json`을 만들지 않아 systemd ready gate를 통과할 수 없다.

즉, entrypoint 문자열만 고치는 것으로는 AI 통합이 완료되지 않는다.

## 6. 백엔드 실제 계약

### MQTT 토픽

```text
command:     hanbakwi/v1/robots/{robotKey}/command
command ACK: hanbakwi/v1/robots/{robotKey}/command/ack
pose:        hanbakwi/v1/robots/{robotKey}/pose
status:      hanbakwi/v1/robots/{robotKey}/status
QoS:         1
```

`START_PATROL`과 `STOP_PATROL`의 TTL은 백엔드 코드상 10초다.

```json
{
  "schemaVersion": 1,
  "commandId": "uuid",
  "command": "START_PATROL",
  "patrolId": 23,
  "issuedAt": "2026-08-02T23:00:00+09:00",
  "expiresAt": "2026-08-02T23:00:10+09:00"
}
```

STOP에는 `patrolId`가 없다. ACK는 다음과 같다.

```json
{
  "schemaVersion": 1,
  "commandId": "요청과 같은 uuid",
  "command": "START_PATROL",
  "status": "SUCCEEDED",
  "receivedAt": "2026-08-02T23:00:02+09:00"
}
```

ACK status는 `SUCCEEDED`, `REJECTED`, `FAILED` 중 하나다. START의 실패 ACK는 순찰을
`FAILED`로 바꾸지만, STOP 실패 ACK는 경고만 남기고 이미 `COMPLETED`인 순찰을 되돌리지
않는다.

### pose와 status

```json
{
  "schemaVersion": 1,
  "robotKey": "registered-serial-number",
  "x": 1.600,
  "y": 2.500,
  "heading": 0.0,
  "timestamp": "2026-08-02T23:00:05+09:00"
}
```

```json
{
  "schemaVersion": 1,
  "robotKey": "registered-serial-number",
  "battery": 82.5,
  "state": "PATROLLING",
  "motor": "NORMAL",
  "camera": "NORMAL",
  "lidar": "NORMAL",
  "lineSensor": "DISCONNECTED",
  "obstacle": {
    "status": "CLEAR",
    "direction": null,
    "reasonMessage": null
  },
  "timestamp": "2026-08-02T23:00:05+09:00"
}
```

Robot state는 `IDLE`, `PATROLLING`, `CHARGING`, `ERROR`, `OFFLINE`, `DELETED`,
`OBSTACLE_STOP`; sensor state는 `NORMAL`, `NEEDS_INSPECTION`, `ERROR`, `DISCONNECTED`다.
라인센서를 주행에서 쓰지 않으므로 `lineSensor=DISCONNECTED`가 정상적인 현재 정책이다.

pose는 1초마다 프론트 마커와 도착 판정에 쓰인다. status 수신 시점의 최신 pose가 약 5초
간격의 영구 순찰 경로로 저장된다. 첫 번째 `DESTINATION` checkpoint의 사각형에 pose가
포함되면 백엔드가 순찰을 완료한다.

### 백엔드 REST

- `POST /api/patrols`, 관리자 JWT, body `{"robotId": <id>}`, HTTP 202.
- `POST /api/robot/events`, Robot service token, 응급 단건.
- `POST /api/robot/events/batch`, Robot service token, 일반 이벤트 일괄.
- `POST /api/robot/vehicle-checks`, Robot service token, 차량/OCR 일괄.
- `POST /api/events/{eventId}/evidence`, Robot service token, multipart 증거.
- `POST /api/map/{mapId}/zones`, 관리자 JWT, checkpoint 사각형 일괄 등록.

이벤트 타입은 `ILLEGAL_PARKING`, `UNREGISTERED_VEHICLE`, `TRASH_DETECTED`,
`RECYCLING_AREA_FULL`, `EMERGENCY`; risk는 `LOW`, `NORMAL`, `EMERGENCY`다.

`RobotBackendClient`는 이미 위 REST transport를 구현하지만 outbox 소비 worker와 pose/patrol
결합 로직은 없다. 운영 secret에는 실제 service token을 `AIOT_BACKEND_ACCESS_TOKEN`으로
주입한다. 값을 소스나 로그에 출력하지 않는다.

### dummy backend fixture

실제 지도 없이 소프트웨어 E2E를 할 때 dummy map과 같은 frame을 사용한다.

```json
{
  "zones": [
    {
      "name": "DUMMY_DESTINATION_60CM",
      "type": "DESTINATION",
      "startX": 1.55,
      "startY": 2.45,
      "endX": 1.65,
      "endY": 2.55
    }
  ]
}
```

지도 업로드 API는 `START_MAPPING` 세션과 ACK를 요구하지만 현재 Robot handler는
`START_MAPPING`을 무시한다. Goal의 비이동 E2E에서는 다음 중 하나를 택한다.

1. backend integration test/Testcontainers가 map, robot, DESTINATION을 fixture로 저장한다.
2. 로컬 개발 DB 전용 seed를 별도 테스트 프로파일에 둔다.

운영 DB에 임의 SQL을 넣거나 실제 mapping session을 위조하지 않는다. 실제 지도 등록은
추후 수동 SLAM 산출물로 수행한다.

### 확인된 백엔드 신뢰성 결함

최소 시연은 가능하지만 production 완료 전에 다음을 처리하거나 issue로 명시해야 한다.

1. `MqttPublisher`가 publish 실패를 로그만 남긴다. 따라서 REST는 202를 반환하고 Patrol은
   `IN_PROGRESS`인데 START가 전송되지 않을 수 있다. 실패를 호출부에 전파하거나 command
   outbox/retry를 구현해야 한다.
2. START/STOP ACK timeout scheduler가 없다. 기한 내 ACK가 없을 때 상태와 재시도 정책을
   구현해야 한다.
3. pose/status handler가 topic의 robotKey와 payload의 robotKey 일치를 확인하지 않는다.
   ACK처럼 둘을 대조해야 한다.
4. START가 Robot의 online/IDLE/health를 검사하지 않는다. 적어도 최신 status 시각과 상태를
   확인하는 정책이 필요하다.

위 네 항목을 백엔드 담당 브랜치에 직접 넣기 전에 최신 `back/dev`와 담당자 작업 여부를
확인한다. Goal의 Robot 작업을 막지는 않으므로 mock contract를 먼저 완성할 수 있다.

## 7. 프론트 실제 상태

`origin/front/dev`의 Robot detail 화면에는 순찰 시작 버튼이 있고 다음을 호출한다.

```text
patrolsApi.start({ robotId }) -> POST /api/patrols
```

그러나 HTTP 202 직후 로컬 `patrolStarted=true`로 바꿔 MQTT START ACK보다 먼저 성공처럼
보인다. 또한 API service에 백엔드에 없는 과거 `/api/patrols/{id}/end`, `/path` 메서드가
남아 있다.

물리 시작과 DB 완료 기록만 보여주는 최소 시연에는 프론트 수정이 필수는 아니다. 최종
완성에서는 robot status/SSE 또는 patrol detail polling으로 ACK 실패·COMPLETED를 표시하고
낡은 메서드를 제거한다.

## 8. 목표 런타임의 책임 분리

### Robot process — 유일한 오케스트레이터

- MQTT command 구독과 ACK 발행.
- ESP32 Serial의 유일한 소유자.
- handshake, safety, mission, waypoint, 즉시 STOP.
- localization pose 선택과 MQTT pose/status.
- AI readiness gate와 ENABLE/DISABLE.
- detection에 현재 patrolId와 map pose 결합.
- REST 전송과 durable outbox retry.
- 종료 시 AI DISABLE, ESP32 STOP, MQTT disconnect 순서 보장.

### AI process — 추론 전용

- TensorRT engine, 두 카메라, BOT-SORT, OCR.
- `/ai/control` 수신 전에는 detection을 만들지 않음.
- `/ai/status` 시작 즉시 및 2초 주기 heartbeat.
- `/ai/detections`로 정규화한 event와 evidence path 발행.
- 증거는 `/var/lib/aiot/evidence` 아래 원자적으로 저장.
- backend token, MQTT credential, robot pose를 소유하지 않음.

### backend

- Robot 등록과 service token 발급.
- 순찰 레코드와 START/STOP command lifecycle.
- pose 기반 DESTINATION 판정.
- event/evidence 저장과 프론트 조회.

현재 `roki-iot/pipeline/patrol_pipeline.py`가 AI를 subprocess로 직접 시작하는 구조와
`aiot-ai.service`를 동시에 쓰면 AI가 중복 실행된다. production에서는 별도 AI service를
유지하고 `PIPELINE_ENABLED=false`로 둔 채 ROS control만 사용한다. legacy subprocess runner는
진단 호환용으로만 남기거나 제거한다.

## 9. AI ROS 계약과 구현 결정

계약 원문은 `robot/docs/ai-ros-contract-v1.md`다.

```text
/ai/control     Robot -> AI, reliable + transient-local, ENABLE/DISABLE
/ai/status      AI -> Robot, reliable + volatile, 2초 heartbeat
/ai/detections  AI -> Robot, reliable + volatile
```

권장 구현은 IoT OTA에 포함되는 `aiot_robot.ai_runtime` 같은 adapter entrypoint를 만드는
것이다. 이 entrypoint는 AI venv로 실행하되 Jetson의 모델/engine과 기존 detector 모듈을
라이브러리로 사용한다.

1. `infra/jetson/aiot-ai-run.sh`가 OTA의 `robot/src`와 기존
   `yolo_pipeline` 디렉터리를 `PYTHONPATH`에 추가한다.
2. `AIOT_AI_ENTRYPOINT=aiot_robot.ai_runtime`을 사용한다.
3. adapter가 기존 `DualCamTensorRTBotSortDetector`, `EventManager`, `PlateCollector`를 재사용해
   loop를 소유한다.
4. 기존 `RestEventClient`를 호출하지 않고 detection ROS만 발행한다.
5. 현재 Robot의 `/ai/control`을 구독해 DISABLE 상태에서는 engine을 유지하되 event 생성을
   중단한다.
6. engine load, 두 camera open, warm-up inference가 성공한 뒤에만 READY와 ready file을
   만든다.

기존 `main.py`를 subprocess로 실행하고 JSONL 로그를 tail하는 방식은 직접 REST 중복,
정적 좌표, 불완전한 lifecycle 때문에 최종안으로 쓰지 않는다.

카메라 장치명은 `/dev/video0` 같은 번호가 아니라 `/dev/roki_camera_front`,
`/dev/roki_camera_rear`를 사용한다. 현재는 장치가 분리되어 있으므로 Goal 테스트에서는
recorded video 또는 fake frame source를 주입한다.

## 10. production entrypoint 통합 순서

### WP0 — 최신 변경 재감사와 보존

산출물:

- 최신 상태 송신 담당 브랜치/MR 식별.
- GitLab과 Jetson staging의 파일별 diff 목록.
- 소유자 변경은 Git 브랜치에서 병합하고 staging 전체 복사를 하지 않았다는 기록.

이 handoff commit에서 ROS TF pose, encoder fallback, LiDAR health, obstacle guard와
waypoint를 합친 후보를 이미 Git에 선별 보존했다. 다음 작업자는 새 원격 branch/MR이 생긴
경우에만 추가 diff를 확인한다. Jetson staging 자체는 더 이상 배포 입력으로 사용하지 않는다.

### WP1 — 하나의 Robot composition root

`robot/scripts/run.sh`가 실행할 production 진입점을 하나로 만든다. 새 entrypoint는 다음을
한 프로세스에서 생성해야 한다.

- `RobotRuntime`과 Serial bridge.
- waypoint navigation과 map pose source/arbitrator.
- shared `RobotStateStore`.
- MQTT client, publisher, command handler.
- ROS `AiRosBridge`와 executor thread.
- detection outbox delivery worker.

중복 `state` package와 `sys.path` 조작은 현재 `run_integrated.py`의 취약점이다. 당장 패키지
이름 전체를 바꾸기 어렵다면 composition root에서 import 경로를 명시적으로 고정하고 이를
검증하는 test를 둔다. 장기적으로 `roki`, `roki_iot`, `aiot_robot`을 installable package로
정리한다.

운영 route는 OTA release 안이 아니라 다음 persistent 경로를 권장한다.

```text
/var/lib/aiot/config/route.local.yaml
```

파일이 없거나 map/frame/좌표가 잘못되면 주행하지 않고 START ACK를 `REJECTED` 또는
`FAILED`로 보낸다. 고정 직진 fallback은 금지한다.

### WP2 — START/STOP lifecycle

START 처리 순서:

1. schemaVersion, commandId, command, patrolId, expiresAt 검증.
2. 중복 commandId는 이전 ACK를 재발행하고 mission을 중복 시작하지 않음.
3. AI heartbeat가 fresh READY인지 확인.
4. route/localization/serial/hardware가 준비됐는지 확인.
5. encoder baseline 이후에만 motion target 설정.
6. AI ENABLE과 mission start가 모두 성공한 후 START ACK `SUCCEEDED`.
7. 어느 단계든 실패하면 STOP + AI DISABLE + 실패 ACK.

STOP 처리 순서:

1. commandId 검증과 idempotency 확인.
2. ESP32 STOP을 가장 먼저 전송.
3. mission/waypoint latch를 정지.
4. AI DISABLE.
5. 최종 pose/status를 한 번 flush.
6. STOP ACK `SUCCEEDED`; 부분 실패는 `FAILED`와 원인 로그.

### WP3 — localization과 waypoint

pose source 우선순위는 다음으로 고정한다.

1. fresh ROS `map -> base_link` TF/AMCL pose.
2. TF가 없을 때 명시적으로 허용한 encoder-only 직선 demo pose.
3. 둘 다 없으면 pose 미발행 및 START 거절.

encoder-only는 이미 검증한 0.60 m 직선 demo 전용이다. 실제 다중 waypoint에서는 encoder
진행률만으로 map x/y를 만들지 않는다. 수동 SLAM map, localization, TF가 필요하다.

`DESTINATION_REACHED` listener는 다음 CONTROL이 쓰이기 전에 STOP을 적용해야 하며 현재
Robot core test가 이 회귀를 검증한다.

### WP4 — AI adapter와 readiness

fake/recorded source로 다음을 먼저 통과시킨다.

- AI STARTING -> READY heartbeat.
- DISABLE 상태에서 detection 0건.
- ENABLE(patrolId) 후 detection과 evidence 생성.
- stale/error heartbeat에서 Robot START 거절.
- AI restart가 transient-local DISABLE/ENABLE을 복구.
- 종료 시 STOPPED heartbeat와 ready file 제거.

실제 두 카메라·성능은 물리 게이트로 미룬다.

### WP5 — outbox와 backend REST

outbox 상태를 최소 다음처럼 명시한다.

```text
PENDING_CONTEXT -> READY_TO_SEND -> SENT
                         |             ^
                         +-> RETRY ----+
```

- detection 수신 시 evidence path가 `/var/lib/aiot/evidence` 아래인지 검증.
- current patrolId와 nearest/fresh map pose를 snapshot으로 결합.
- 응급은 즉시 단건, 일반/차량은 순찰 종료 시 batch.
- 성공 응답과 eventId를 확인한 뒤에만 outbox JSON 제거.
- evidence 실패는 event를 재생성하지 않고 evidence만 retry.
- 재부팅 후 pending 파일을 다시 읽음.
- 로그에 bearer token을 절대 남기지 않음.

### WP6 — 로컬 backend/MQTT E2E

실제 ESP32 대신 fake serial transport를 사용한다. 테스트가 만들어야 할 순서는 다음과 같다.

```text
POST /api/patrols
-> capture START MQTT
-> Robot receives START
-> fake HELLO/ACK/ODOMETRY/HARDWARE_STATUS
-> START ACK
-> interpolated pose 1.2, 1.4, 1.6
-> AI fake detection + evidence
-> backend event/evidence API
-> backend sees DESTINATION and emits STOP
-> Robot STOP + STOP ACK + IDLE
-> Patrol COMPLETED and route/event persisted
```

테스트 broker와 backend를 localhost/container로 띄우며 AWS를 필수 조건으로 만들지 않는다.
인증이 필요한 frontend E2E는 기존 로그인 fixture를 사용한다.

backend test는 앞에서 만든 `back-dev-audit` 또는 그 기반 feature worktree에서 실행한다.
현재 IoT worktree만으로 compose를 실행하면 backend build context가 비어 실패하므로, 별도
worktree를 쓰거나 CI가 사용하는 통합 checkout 방식을 명시적으로 재현한다.

### WP7 — systemd와 OTA

- `aiot-ai.service`는 Robot보다 먼저 뜨되 READY 실패 시 계속 재시작 폭주하지 않게 한다.
- `aiot-robot.service`는 AI service가 process로 떴다는 이유만으로 motion을 허용하지 않고
  live heartbeat를 검사한다.
- 두 서비스 모두 성공적으로 fail-closed한 뒤에만 enable한다.
- `robot/scripts/smoke-test.sh pre-activate`는 serial을 열지 않고 import/config/권한만 검사한다.
- OTA activation 전 current release를 남기고 실패 시 symlink rollback을 검증한다.
- feature branch push는 CI workflow 대상이 아니다. MR 또는 `iot/dev`, release tag가 필요하다.
- 실제 Jetson 갱신은 `iot-vX.Y.Z` tag, artifact/manifest 게시, updater가 manifest를 가져오는
  단계가 있어야 한다. 단순 전원 인가가 최신 Git을 pull하는 구조는 아니다.

## 11. 환경 변수 기준

비밀값 없는 template만 Git에 둔다.

```text
SCHEMA_VERSION=1
ROBOT_KEY=<backend robot serial number>
MQTT_HOST=i15e103.p.ssafy.io
MQTT_PORT=8883
MQTT_USE_TLS=true
POSE_PUBLISH_INTERVAL_SECONDS=1
STATUS_PUBLISH_INTERVAL_SECONDS=5
PATROL_DRIVE_SPEED_PWM=45
PATROL_STEERING_DEGREES=80
ROKI_ROUTE_FILE=/var/lib/aiot/config/route.local.yaml
ROKI_ROUTE_START_X_M=1.0
ROKI_ROUTE_START_Y_M=2.5
ROKI_ROUTE_MAXIMUM_TRAVEL_M=0.70
PIPELINE_ENABLED=false
AIOT_BACKEND_BASE_URL=https://i15e103.p.ssafy.io
AIOT_BACKEND_ACCESS_TOKEN=<service token from secret file>
AIOT_EVENT_OUTBOX_DIR=/var/lib/aiot/outbox
AIOT_AI_EVIDENCE_DIR=/var/lib/aiot/evidence
AIOT_AI_ENTRYPOINT=aiot_robot.ai_runtime
AIOT_AI_CAMERA_FRONT_DEVICE=/dev/roki_camera_front
AIOT_AI_CAMERA_REAR_DEVICE=/dev/roki_camera_rear
```

Jetson의 수동 `/home/e103/roki-iot/.env`는 감사 당시 numeric camera source와 PWM 51을
포함하고 있어 template과 다르다. 이를 운영 기준으로 복사하지 않는다. 실제 token 파일은
존재하지만 내용을 읽거나 Git에 남기지 않는다.

## 12. 소프트웨어 전용 검증 명령

동료 작업 병합 후 현재 브랜치에서 다음이 통과했다.

```text
robot/tests: 29
robot/roki/tests: 112
robot/roki-iot tests: 15
total: 156
```

Windows에서는 bundled Python 또는 프로젝트 Python으로 다음과 같은 검증을 한다.

```powershell
$py = 'C:\Users\SSAFY\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'

$env:PYTHONPATH = (Resolve-Path 'robot\src').Path
& $py -m unittest discover -s robot\tests -v

$env:PYTHONPATH = (Resolve-Path 'robot\roki').Path
& $py -m unittest discover -s robot\roki\tests -v

$env:PYTHONPATH = (Resolve-Path 'robot\roki-iot').Path + ';' + (Resolve-Path 'robot\roki').Path
& $py -m unittest discover -s robot\roki-iot -p 'test_*.py' -v
```

다음 테스트를 새로 추가한다.

- production entrypoint가 legacy Serial reader를 만들지 않고 하나의 runtime만 생성.
- MQTT duplicate/expired command idempotency.
- AI missing/stale/error START rejection.
- START rollback과 STOP ordering.
- destination listener가 다음 CONTROL 전에 STOP.
- fake ROS AI detection -> durable outbox -> REST retry.
- backend command TTL 10초 계약.
- topic robotKey와 payload robotKey 불일치 거절.
- dummy backend fixture의 DESTINATION 자동 완료.
- OTA archive에 `.env`, token, model, engine, local route가 없음.

## 13. Goal 모드에서 금지되는 작업

다음은 사용자가 로봇 앞에서 명시적으로 허용하는 별도 현장 세션까지 하지 않는다.

- `/dev/roki_esp32` open, flash, CONTROL/START 명령.
- `aiot-robot.service`, `aiot-ai.service` 시작 또는 enable.
- Battery B 연결/분리 안내를 실행으로 간주하는 작업.
- 모터, 서보, LiDAR, 카메라 실물 시험.
- 활성 `/home/e103/roki*`, `/home/e103/yolo-pipeline`, `/opt/aiot/iot/current` 덮어쓰기.
- 실제 MQTT broker에 START/STOP command 발행.
- 운영 DB에 dummy map/checkpoint 삽입.
- secret/token/password 출력, 문서화, 커밋.

Jetson은 read-only source/service 감사와 CPU-only import/test에만 사용한다. `--help`처럼
명백히 장치를 열지 않는 명령도 코드 경로를 먼저 읽은 뒤 실행한다.

## 14. 물리 세션으로 남길 최종 게이트

Goal 작업이 끝난 뒤 사용자와 다음만 확인한다.

1. stable camera alias 두 개와 실제 front/rear 매핑.
2. LiDAR alias, scan topic, `map -> odom -> base_link -> laser_frame` TF.
3. 실제 SLAM map과 `route.local.yaml` waypoint의 통과 가능성.
4. 45 PWM, 80° 정면으로 한 waypoint 저속 시험.
5. 장애물 STOP/제거 후 재개.
6. 실제 AI warm-up, 두 카메라 FPS, evidence 품질.
7. 프론트 START부터 DESTINATION/STOP ACK/완료 화면까지 단 한 번의 E2E.

현장 시험은 반드시 바퀴 들기/비상 전원 차단/코스 확인 등 기존 runbook을 따른다. 이
문서는 물리 실행 명령을 제공하지 않는다.

## 15. 해결된 판단과 아직 외부 입력이 필요한 것

### 이 문서에서 결정해 해소한 것

- 주행 방식: line following이 아니라 map waypoint.
- 첫 소프트웨어/직선 demo pose: encoder-only, 실제 다중 route는 SLAM localization.
- ROS bridge: 현재 AI venv 안에서 가능, 별도 process 불필요.
- AI lifecycle: Robot가 ROS control, AI systemd는 별도 process, legacy subprocess 비활성.
- REST ownership: Robot 단독, AI 직접 REST 금지.
- deploy ownership: `robot/`만 IoT OTA, model/engine은 Jetson AI baseline 유지.
- destination: Robot 선제 정지 + backend pose 판정 + STOP 재확인.
- actual source: GitLab 우선, Jetson staging은 참고 후보.
- dummy map: software E2E 가능, production map으로 간주하지 않음.

### Goal이 재감사해야 하지만 사용자 답을 바로 요구하지 않는 것

- 상태 송신 담당자의 최신 Git 브랜치/MR 도착 여부.
- `back/fix_revise_api_url`의 `back/dev` 병합 여부.
- CI/CD 세션이 추가한 새 systemd/OTA 변경.
- Jetson DHCP 주소와 DNS 복구 여부.

### 물리 직전에만 사용자 확인이 필요한 것

- 실제 map/route 파일 최종본.
- 카메라 두 대의 물리 front/rear 대응.
- 로봇 주변 안전 확보와 Battery B 연결 허가.

이 세 가지가 없어도 Goal의 소프트웨어 구현과 fake E2E는 끝낼 수 있다.

## 16. 다음 인수인계에 반드시 남길 산출물

Goal 작업자는 종료 전에 다음을 GitLab에 남긴다.

1. 최종 commit SHA와 대상 브랜치/MR.
2. production process tree와 실제 entrypoint.
3. 수정한 MQTT/ROS/REST 계약과 호환성 여부.
4. 모든 비이동 테스트 명령, 통과 수, 로그 요약.
5. local broker/backend E2E의 commandId와 상태 전이 로그(비밀 제외).
6. OTA 패키지 manifest와 secret/model 제외 검사 결과.
7. Jetson에 적용하지 않은 변경과 그 이유.
8. 남은 물리 게이트만 분리한 짧은 현장 runbook.

## 17. 관련 문서

- `robot/docs/field-demo-handoff-2026-08-02.md`: 현장 측정과 waypoint 구현 증거.
- `robot/docs/waypoint-mqtt-field-runbook.md`: 향후 물리 MQTT 직선 시험 절차.
- `robot/docs/waypoint-navigation-handoff.md`: 내비게이션 모듈 구조.
- `robot/docs/esp32-mqtt-runtime-handoff.md`: ESP32 protocol과 MQTT 보존본.
- `robot/docs/ai-ros-contract-v1.md`: Robot-AI ROS JSON 계약.
- `robot/docs/robot-demo-integration-plan.md`: 이전 통합 계획.

다음 작업자는 위 문서를 전부 처음부터 재해석하기보다 이 문서의 작업 순서에 따라 필요한
근거 섹션만 참조한다.
