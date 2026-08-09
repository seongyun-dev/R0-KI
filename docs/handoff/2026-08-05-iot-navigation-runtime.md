# IoT 원격 Navigation Config·탐지 필터 인수인계

## 작업 기준

- 작업 브랜치: `iot/feat/remote-navigation-config`
- 기준 브랜치/커밋: `origin/iot/dev` / `9751c63`
- 병합 대상: `iot/dev` 검증 후 `iot/master`
- 이 작업에서는 Jetson 서비스, ESP32, motor, serial, MQTT 운영 연결을 변경하지 않았다.

## 변경 내용

1. `START_PATROL` 때 Backend의 최신 navigation config를 조회한다.
2. 응답 계약과 map/version/waypoint를 검증한 뒤 기존 Route/Waypoint/Nav2 입력으로 변환한다.
3. 원격 설정이 없거나 안전하지 않으면 주행을 시작하지 않고 명확한 ACK reason과 status를 보낸다.
4. 기존 로컬 YAML route는 현장 디버그 fallback으로 보존하되 기본값에서는 자동 사용하지 않는다.
5. `SCAN` waypoint 문맥을 기존 AI detection 흐름에 연결한다.
6. Robot event delivery를 Backend event 생성의 단일 소유 경로로 정리했다.
7. 다른 작업 세션에서 추가한 `confidence < 0.5` 탐지 폐기 변경을 함께 포함했다.

## 주요 파일

- `robot/src/aiot_robot/navigation_config.py`: navigation config HTTP provider/검증/변환
- `robot/src/aiot_robot/backend_client.py`: Robot API 호출
- `robot/roki-iot/backend_mqtt/command_handler.py`: START_PATROL preflight와 fail-closed ACK
- `robot/roki-iot/integration/runtime_state_backend_adapter.py`: SCAN 문맥과 event 전달
- `robot/roki/navigation/route.py`: action/zone/acceptance radius 포함 route
- `robot/roki/navigation/ros_nav2_bridge.py`: 기존 Nav2 bridge 연결
- `robot/src/aiot_robot/event_delivery.py`: 단일 event owner 및 confidence filter
- `robot/config/robot.env.example`, `robot/roki-iot/.env.example`: 안전한 기본 설정 예시
- `robot/docs/integrated-runtime-operations.md`: 운영 절차
- `robot/docs/friday-navigation-and-e2e-field-validation-2026-08-05.md`: 실물 현장 검증표

## Backend 계약과 변환

- Endpoint: `GET /api/robot/navigation-config`
- 인증: Robot service bearer token. 값은 코드/문서/로그에 기록하지 않는다.
- 지원 schema: `schemaVersion=1`
- 고정된 `mapId`, `mapVersion`과 로컬 map metadata가 일치해야 한다.
- waypoint 순서, 마지막 DESTINATION 하나, action, zone 참조, acceptance radius 0.2~1.0m를 검사한다.
- Backend의 yaw 라디안을 기존 route의 `yaw_deg`로 변환한다.
- yaw가 없으면 인접 route geometry로 유도한다. 단일 waypoint에서 yaw가 없으면 localization heading이 있어야 하며, 없으면 시작하지 않는다.
- 로컬 occupancy/map hash/clearance 검증은 기존 navigation factory를 그대로 통과한다.

## 원격 설정과 로컬 fallback

- 기본 source: `AIOT_NAVIGATION_CONFIG_SOURCE=backend`
- 기본 fallback: `AIOT_NAVIGATION_LOCAL_FALLBACK_ENABLED=false`
- fallback을 명시적으로 켠 경우에도 일시적인 transport outage에서만 로컬 YAML을 사용한다.
- TLS, 인증, HTTP 오류, schema 불일치, map mismatch, 지도 안전성 실패에는 fallback하지 않는다.
- START deadline을 넘기거나 응답이 만료되면 동작을 시작하지 않는다.

## 0.5 미만 탐지 폐기

- 기본값: `AIOT_MIN_DETECTION_CONFIDENCE=0.5`
- `confidence < 0.5`인 detection은 pose 조회와 outbox 저장 전에 폐기한다.
- `confidence == 0.5`는 허용한다.
- 폐기 로그에는 event 식별자와 confidence/threshold만 남기며 이미지나 인증정보를 출력하지 않는다.
- 테스트에서 0.499 폐기와 0.5 보존을 확인했다.

## AI 이벤트 소유권

- AI inference는 detection을 runtime에 전달한다.
- Robot의 `DetectionRecorder`가 좌표/SCAN 문맥을 붙이고 Backend outbox 전송을 담당한다.
- AI가 같은 detection을 별도 HTTP 경로로 다시 전송하지 않는 구성을 기준으로 한다.
- 실제 현장에서는 한 detection에 eventId, 사진, DB row가 각각 정확히 하나인지 반드시 검증한다.

## 검증 결과

- 기본 Python에는 `pyserial`, `PyYAML`, `paho-mqtt`가 없어 import collection 5건이 실패했다. 코드 결함이 아니라 실행 환경 의존성 부족이다.
- 기존 프로젝트 venv `D:\codex\S15P11E103-handoff-venv\Scripts\python.exe`로 재실행했다.
- 테스트 결과: 88 + 159 + 102, 총 349 tests 통과.
- 전체 Python `py_compile` 통과.
- 실물 motor, battery, serial open, Jetson service restart는 수행하지 않았다.

## 현장 검증

`robot/docs/friday-navigation-and-e2e-field-validation-2026-08-05.md`를 사용한다. 다음을 기록하도록 되어 있다.

- 게임패드 장치/축/버튼, deadman, STOP, finish
- 무입력 lease, radio loss, 재연결 후 neutral+deadman 재무장
- PWM/조향/encoder 방향과 거리, E-stop/BTS EN
- BRIO 1대 alias와 입력, LiDAR/SLAM map 품질과 저장
- mapping 종료 후 명시적인 localization/Nav2 전환
- 차량 좌표 ground truth와 주차구역 경계 오차
- detection 재전송과 짧은 연속 탐지의 중복 event 여부
- Front START부터 DESTINATION/STOP/IDLE/재시작까지 전체 E2E

## 다음 작업자 확인 사항

- Back의 V15와 navigation config API가 먼저 배포된 dev 환경에서 fetch/검증을 확인한다.
- Jetson에 필요한 환경 변수의 존재만 확인하고 값은 공유하거나 commit하지 않는다.
- 로컬 map bundle의 mapId/version/hash와 Backend 최신 map을 맞춘 후 시작한다.
- 자동 mapping, 자동 서비스 재시작, 자동 재부팅 복구는 이번 구현 범위가 아니며 추가하지 않았다.
- 실제 장치 검증은 현장 문서의 중지 기준과 감독자 동반 조건을 따른다.
