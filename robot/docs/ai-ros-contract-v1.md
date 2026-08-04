# Robot-AI ROS 2 contract v1

Robot은 순찰 상태, 주행, pose, MQTT, 백엔드 인증과 REST 전달을 소유한다. AI는
카메라, 추론, 추적, OCR과 증거 이미지 생성을 소유한다. 두 프로세스는 같은
Jetson에서 `ROS_LOCALHOST_ONLY=1`로 실행한다.

세 토픽은 모두 UTF-8 JSON을 담은 `std_msgs/msg/String`이다. 알 수 없는 필드는
무시할 수 있지만 `schemaVersion != 1`인 메시지는 거절한다.

## `/ai/control`: Robot → AI

QoS는 reliable, transient-local, keep-last 1이다.

```json
{
  "schemaVersion": 1,
  "command": "ENABLE",
  "patrolId": 15,
  "requestedAt": "2026-08-03T05:20:00Z",
  "reason": "PATROL_STARTED"
}
```

`command`는 `ENABLE` 또는 `DISABLE`이다. AI는 DISABLE 중에도 모델을 메모리에
유지하되 새 detection을 발행하지 않는다. AI가 재시작하면 transient-local 메시지로
마지막 제어 상태를 복구한다.

## `/ai/status`: AI → Robot

QoS는 reliable, volatile, keep-last 5이며 시작 즉시와 이후 2초마다 발행한다.

```json
{
  "schemaVersion": 1,
  "state": "READY",
  "ready": true,
  "cameraReady": true,
  "engineReady": true,
  "inferenceReady": true,
  "detectionEnabled": true,
  "patrolId": 15,
  "modelVersion": "vehicle-v1",
  "heartbeatAt": "2026-08-03T05:20:02Z",
  "errorCode": null,
  "message": null
}
```

Robot treats `ENABLE` as applied only after a newer status reports both
`detectionEnabled=true` and the same `patrolId`. A missing or mismatched
application status fails START closed after `AIOT_AI_CONTROL_APPLY_TIMEOUT_SEC`.

`state`는 `STARTING`, `READY`, `DEGRADED`, `ERROR`, `STOPPED` 중 하나다. Robot은
heartbeat가 `AIOT_AI_STATUS_TIMEOUT_SEC`보다 오래되지 않았고 네 readiness 값이
모두 true일 때만 START를 받는다. AI가 죽어도 Robot 프로세스는 MQTT STOP과 상태
발행을 계속 처리한다.

## `/ai/detections`: AI → Robot

QoS는 reliable, volatile, keep-last 100이다.

```json
{
  "schemaVersion": 1,
  "eventId": "01J4AIOTEVENT00000000000001",
  "patrolId": 15,
  "eventType": "VEHICLE_DETECTED",
  "cameraId": "front",
  "trackId": "track-42",
  "confidence": 0.93,
  "observedAt": "2026-08-03T05:20:03Z",
  "evidencePath": "/var/lib/aiot/evidence/01J4AIOTEVENT00000000000001.jpg",
  "bbox": {"x": 120, "y": 80, "width": 300, "height": 180},
  "attributes": {"plateText": "masked-example"}
}
```

AI는 증거를 `/var/lib/aiot/evidence` 아래에 복사하고 경로만 보낸다. Robot은 수신
시점의 map pose를 붙여 `/var/lib/aiot/outbox`에 원자적으로 저장한다. map pose가
아직 없으면 잘못된 좌표를 만들지 않고 해당 detection을 폐기한다. 차량은 AI가
불법 여부를 확정하지 않고 `VEHICLE_DETECTED`와 번호판을 전달한다. Robot이
`POST /api/robot/vehicle-checks`를 호출하고 백엔드가 주차 구역과 등록 여부를
판정한다. 그 외 이벤트는 현재 백엔드 enum인 `TRASH_DETECTED`,
`RECYCLING_AREA_FULL`, `EMERGENCY` 등을 사용한다.
지원하지 않는 eventType과 번호판이 비어 있는 차량은 잘못된 백엔드 이벤트로
재시도하지 않고 폐기한다.

백엔드가 eventId를 만든 뒤 evidence 업로드가 실패하면 outbox는 eventId를 보존해
다음 retry에서 이벤트를 중복 생성하지 않는다. 이전 patrol의 outbox가 남아 있으면,
백엔드가 event 요청에 patrolId를 받지 않는 현재 계약 때문에 다음 START를 거절한다.
전달 또는 차량 정상 판정이 끝난 증거는 기본적으로 로컬에서 지워 디스크 누적을 막는다.

## 실제 AI 실행 방식

`aiot-ai.service`는 모델 소스를 수정하지 않고 아래 어댑터를 AI venv로 실행한다.

```text
/opt/aiot/iot/current/robot/src/aiot_robot/ai_runtime.py
  └─ /home/e103/yolo-pipeline/yolo_pipeline/main.py
```

어댑터는 기존 pipeline의 `RestEventClient`만 ROS sink로 교체한다. 따라서 AI가
백엔드 REST를 직접 호출하지 않으며 Robot이 유일한 전달자다. engine 생성 완료,
카메라 두 대 open, 첫 inference 완료 뒤에만 READY를 낸다. `rclpy`는 반드시
`source /opt/ros/humble/setup.bash` 후 AI venv에서 import한다.
