# SDD: Patrol Start, Runtime, Stop Diagnostics

- Issue: E103-300
- 기준 브랜치: `feat/E103-300-map-patrol-diagnostics`
- Robot 코드 기준: `c763e519882a9bb37c0ad8e6dce82a75c79d6b93`
- 운영 Backend 기준: `daf1080ddf36d44ca2de2e0ff0adc15f187e5a4c`
- 운영 Frontend 기준: `28ccb068172578f2c1df4015bcd1bef7e8e00efd`
- 작성일: 2026-08-05
- 상태: 분석 및 설계. 구현·배포 승인 전.

## 0. 근거, 판정 표기 및 비범위

### 0.1 권위 자료

1. `robot/roki/docs/COMMUNICATION_CONTRACT.md`
2. `robot/roki/PROJECT_GUIDE.md`
3. `robot/README.md`
4. `robot/docs/integrated-runtime-operations.md`
5. `robot/docs/friday-navigation-and-e2e-field-validation-2026-08-05.md`
6. `robot/docs/goal-mode-integration-handoff-2026-08-02.md`
7. `robot/docs/waypoint-navigation-handoff.md`
8. `docs/handoff/2026-08-05-iot-navigation-runtime.md`
9. 현재 Robot 코드와 운영 Backend/Frontend Git 객체
10. EC2 Backend 최근 24시간 로그와 MySQL read-only 조회

판정 표기는 다음과 같다.

- `DOCUMENT_CONFIRMED`: 문서에서만 확인했다.
- `CODE_CONFIRMED`: 코드에서 확인했다.
- `BOTH_CONFIRMED`: 문서와 코드가 일치한다.
- `DOCUMENT_CODE_MISMATCH`: 문서와 현재 코드가 다르다.
- `RUNTIME_VERIFICATION_REQUIRED`: Jetson/ROS/ESP32 실기기에서 확인해야 한다.

`COMMUNICATION_CONTRACT.md`는 ESP32와 Jetson 사이의 protocol version 1 JSON Lines 계약만
정의하며 Jetson과 Backend 사이 MQTT/REST는 범위 밖이라고 명시한다. 따라서 본 문서에서
Serial의 `HELLO`, `ACK`, `ERROR`, `CONTROL`, `STOP`, `STATUS`, `ENCODER_ZERO`와 단일
Serial owner 원칙은 해당 문서를 그대로 따른다. MQTT topic, payload, ACK 및 Patrol 상태는
Backend/Robot 코드와 별도 운영 문서를 근거로 한다. 기존 topic, schema version, ACK status,
Robot enum 또는 Serial 계약을 이 설계가 임의로 바꾸지 않는다.

이번 문서의 비범위는 Mapping 재분석, 실제 MQTT 명령 발행, 모터 구동, 서비스 재시작,
EC2/DB 변경, 배포 및 구현이다.

## 1. 목적

이 설계는 순찰 시작, 실행, 사용자 정지, 정상 완주의 각 단계를 분리해 다음을 달성한다.

- 명령 수락과 실제 주행 준비, 정상 완주를 서로 다른 완료점으로 취급한다.
- L0~L12 중 최초 실패 계층과 원인을 잃지 않는다.
- 장애 또는 STOP에서 motion authorization을 먼저 제거하고 안전 정지를 검증한다.
- 같은 `commandId` 재전달이 새 mission을 만들지 않게 한다.
- 사용자에게는 해결 가능한 문구를, 운영자에게는 상관 ID와 원인을 제공한다.
- cleanup이 끝나지 않은 상태에서 재시작하지 않는다.

## 2. 사용자 시나리오

### 2.1 정상 시작

관리자가 대기 로봇을 선택하고 시작을 확인한다. Frontend는 한 번만 API를 호출하고
`patrolId`를 저장한다. Backend와 Robot의 readiness를 모두 통과한 뒤 Robot은 navigation
mission과 첫 Nav2 goal을 만들고 상태/ACK를 발행한다. Frontend는 HTTP 202가 아니라 Robot
status `PATROLLING`을 시작 확인점으로 사용한다.

### 2.2 시작 readiness 실패

Backend가 확인할 수 있는 robot freshness, sensor, map, route 문제는 MQTT 발행 전에
거절한다. Robot만 확인할 수 있는 Serial, odometry, localization, local map hash, Nav2,
AI 문제는 motion 전에 `REJECTED` 또는 시작 도중 rollback이 필요한 경우 `FAILED`로 닫는다.

### 2.3 장애물 정지

LiDAR가 obstacle `STOP`을 만들면 기존 status payload의 obstacle 객체를 사용한다. 새 MQTT
topic이나 새 Robot 내부 state enum을 도입하지 않는다. Nav2 goal을 취소하고 motion을
정지한 뒤 mission을 paused로 유지한다. 안정적인 CLEAR hold와 필수 readiness 재확인 후
같은 waypoint sequence를 새 goal로 발행한다.

### 2.4 순찰 중 Nav2 실패

goal reject/abort, bridge thread 종료, `cmd_vel` timeout은 motion zero, goal invalidate,
component cleanup, Robot `ERROR`로 fail-close 한다. 현재는 이 비동기 실패를 기존 START ACK의
후속 `FAILED`로 Backend에 전달하지 않으므로 결과 전달 보강이 필요하다.

### 2.5 사용자 종료

Frontend가 `POST /api/patrols/{patrolId}/stop`을 호출한다. Backend는 별도 commandId로
`STOP_REQUESTED`를 먼저 커밋하고 STOP을 발행한다. Robot은 queued motion과 Nav2 goal을
제거하고 ESP32 STOP, AI disable, component cleanup을 수행한다. 성공 ACK 뒤 Backend는
`STOPPED`로 확정한다.

### 2.6 정상 완주

Robot은 마지막 `DESTINATION` acceptance radius 진입을 로컬 pose로 감지해 Backend보다 먼저
정지한다. Backend도 pose를 같은 destination으로 판정해 completion용 STOP을 발행한다.
이 STOP의 성공 ACK가 와야 Backend가 `COMPLETED`로 확정한다.

### 2.7 STOP 실패

STOP의 publish/TTL/delivery/cleanup/ACK 중 하나라도 확정되지 않으면 성공으로 표시하지 않는다.
현재 구현은 ESP32 STOP ACK가 아니라 Serial write 성공을 Robot STOP 성공으로 간주하므로
`STOP_UNCONFIRMED` 안전 갭이 있다. firmware watchdog은 fallback이지 성공 증거가 아니다.

### 2.8 네트워크 또는 ACK timeout

현재 Backend에는 START/STOP ACK timeout scheduler가 없다. 설계상 deadline을 넘긴 attempt는
terminal timeout으로 기록하고, START는 `FAILED`, STOP은 `STOP_REQUESTED`와 unsafe/unknown
상태를 유지한 채 실제 정지 확인 전 재시작을 금지해야 한다.

## 3. 상태와 단계

### 3.1 상태 의미

| 상태 | 소유자 | 정확한 의미 | 판정 |
|---|---|---|---|
| `REQUESTED` | Mapping 전용 | Patrol DB에는 없는 상태 | `CODE_CONFIRMED` |
| `IN_PROGRESS` | Backend Patrol | START publish 전에 생성되는 낙관적 진행 상태. Robot 주행 확인 아님 | `CODE_CONFIRMED` |
| `PATROLLING` | Robot/Backend robot status | Robot mission start와 active patrol 확인 뒤 telemetry로 보고하는 실행 상태 | `CODE_CONFIRMED` |
| `STOP_REQUESTED` | Backend Patrol | STOP용 commandId가 저장됐으나 성공 ACK 전 | `CODE_CONFIRMED` |
| `STOPPED` | Backend Patrol | 사용자 STOP의 성공 ACK 처리 완료 | `CODE_CONFIRMED` |
| `COMPLETED` | Backend Patrol | destination pose가 completion STOP을 만들고 성공 ACK를 받은 정상 완주 | `CODE_CONFIRMED` |
| `FAILED` | Backend Patrol | START reject/fail, publish 보상 또는 별도 장애 처리 결과 | `CODE_CONFIRMED` |
| `CANCELLED` | Patrol에는 없음 | Mapping 전용 상태 | `CODE_CONFIRMED` |
| `ERROR` | Robot status | runtime/cleanup/safety 실패 후 새 readiness 검증이 필요한 fail-closed 상태 | `CODE_CONFIRMED` |
| `OBSTACLE_STOP` | Backend robot status | status payload의 obstacle `STOP`을 Backend가 우선 변환한 표시 상태 | `CODE_CONFIRMED` |

Robot의 in-memory `RobotStatusState.state`는 장애물 때문에 새 enum으로 바뀌지 않고 기존
`PATROLLING`을 유지할 수 있다. Backend `RobotTelemetryService`가 obstacle 객체를 보고
`OBSTACLE_STOP`으로 해석한다. 이는 기존 계약을 유지하는 의도된 계층 차이다.

### 3.2 START 단계

```text
Frontend pending
  -> Backend Patrol IN_PROGRESS + START commandId
  -> Robot prepare/readiness
  -> local mission start
  -> first Nav2 goal send_goal_async
  -> Robot PATROLLING
  -> START ACK SUCCEEDED
```

분석 기준 코드에서는 `send_goal_async()` 직후 Robot start 함수가 반환해 START ACK가 첫 goal
accept를 보장하지 않았다. 승인 후 Robot 변경에서는 `RosNav2Bridge.start_patrol()`이 첫 goal
accept event를 최대 5초 기다리며 reject·timeout·동시 STOP이면 fail-close 한다. Runtime Adapter는
이 비동기 경계 뒤 TTL을 다시 검사하므로 START ACK `SUCCEEDED`는 첫 goal accept 이후에만 가능하다.
실제 Nav2 timing은 Jetson 실기기에서 추가 검증한다. `IMPLEMENTED_THIS_CHANGE`

### 3.3 PATROLLING 단계

현재 waypoint pose update, Nav2 result, SCAN dwell, obstacle pause/resume, AI event delivery,
runtime safety watchdog를 수행한다. Nav2 goal 성공은 pose 기반 `WaypointMission` 진행과 별도
callback이며, 최종 완료는 destination pose event가 결정한다.

### 3.4 STOP 단계

```text
Backend STOP_REQUESTED + 새 commandId
  -> MQTT STOP_PATROL
  -> Robot motion authorization/queue 제거
  -> Nav2 goal invalidate/cancel + zero motion
  -> ESP32 STOP write
  -> AI disable + mission/component cleanup
  -> Robot IDLE 또는 ERROR
  -> STOP ACK
  -> Backend STOPPED 또는 COMPLETED
```

### 3.5 FAILED 단계

최초 오류와 cleanup 오류를 분리한다. 최초 오류가 `originalFault`, cleanup 실패가
`cleanupResult`를 채운다. cleanup 실패가 최초 오류를 덮어쓰면 안 된다.

## 4. 알고리즘 규칙

1. Backend와 Robot readiness가 모두 성공하기 전 motor command를 허용하지 않는다.
2. `commandId`는 attempt별 UUID이며 같은 ID와 같은 fingerprint는 저장된 ACK를 replay한다.
3. 같은 ID와 다른 fingerprint는 `REJECTED`하고 새 mission을 만들지 않는다.
4. schema v1과 `issuedAt < expiresAt`, 최대 TTL, future clock skew를 검사한다.
5. Mapping active, Patrol active 또는 cleanup pending이면 START를 거절한다.
6. STOP은 queued/active motion보다 높은 우선순위를 갖고 motion authorization부터 제거한다.
7. 최초 실패 원인은 후속 cleanup 실패로 덮어쓰지 않는다.
8. cleanup과 safe-state 확인이 끝나기 전 새 START를 허용하지 않는다.
9. 사용자 STOP은 `STOPPED`, destination 완주는 `COMPLETED`로 분리한다.
10. START ACK `SUCCEEDED`는 전체 순찰 성공이 아니다.
11. STOP ACK `SUCCEEDED`는 ESP32 STOP confirmation을 포함할 때만 최종 성공으로 정의한다.
12. 장애물 pause는 종료가 아니며 CLEAR 후 같은 sequence를 재전송한다.

## 5. 인터페이스와 계약

### 5.1 Frontend REST와 상태

- START: `POST /api/patrols`, 관리자 JWT, body `{"robotId": number}`, HTTP 202
- STOP: `POST /api/patrols/{patrolId}/stop`, 관리자 JWT, HTTP 202
- detail: `GET /api/patrols/{patrolId}`
- Robot status: `/api/robots/location/events` SSE
- 완료 알림: general SSE의 `patrol-completed`

Frontend `Dashboard.startPatrol()`은 중복 클릭과 pending start를 차단하고 16초 동안 Robot
status를 기다린다. Patrol 전용 command-result SSE는 현재 없다.

### 5.2 Backend

- `PatrolController`: 인증된 START/STOP REST 경계
- `PatrolCommandStateService`: row lock, readiness, 상태와 commandId의 선커밋
- `PatrolCommandService`: MQTT publish 및 publish 실패 보상
- `PatrolCommandAckService`: START/STOP ACK 상태 전이
- `RobotTelemetryService`: pose/status 저장, obstacle 해석, destination 자동 완료

### 5.3 MQTT

```text
command: hanbakwi/v1/robots/{robotKey}/command
ACK:     hanbakwi/v1/robots/{robotKey}/command/ack
pose:    hanbakwi/v1/robots/{robotKey}/pose
status:  hanbakwi/v1/robots/{robotKey}/status
QoS:     1
schema:  1
START/STOP TTL: 10 seconds
```

ACK 필드는 `schemaVersion`, `commandId`, `command`, `status`, `receivedAt`, 선택적
`reason`이다. status는 `SUCCEEDED`, `REJECTED`, `FAILED`만 사용한다.

### 5.4 ESP32 Serial

`COMMUNICATION_CONTRACT.md`의 protocol version 1을 변경하지 않는다. 운영 Serial owner는
`robot/scripts/run.sh -> roki-iot/run_integrated.py -> RobotRuntime` 단 하나다. 별도 legacy
reader, AI process 또는 진단 script가 동시에 `/dev/roki_esp32`를 열어서는 안 된다.

## 6. 구조와 책임

| 컴포넌트 | 책임 | 하지 않는 일 |
|---|---|---|
| Frontend | 사용자 intent, 중복 클릭 방지, 상태/오류 표시 | HTTP 202를 물리 성공으로 확정하지 않음 |
| Backend | 권한/소속/readiness, Patrol 상태, MQTT 상관관계, 완료 판정 | Robot-local ROS readiness를 추측하지 않음 |
| Mosquitto | QoS 1 command/ACK/telemetry 전달 | application 상태 전이를 결정하지 않음 |
| Command Handler | schema/TTL/idempotency, START/STOP orchestration, ACK | Serial을 직접 중복 소유하지 않음 |
| Patrol Runtime Adapter | lifecycle, pause/resume/fail-close, component cleanup | Backend DB를 직접 수정하지 않음 |
| Mission/Navigation Service | waypoint 순서와 destination pose 판정 | MQTT/Serial 소유하지 않음 |
| Nav2 Bridge | action goal, cmd_vel 변환, goal cancel/health | Patrol DB 상태를 결정하지 않음 |
| Motion Controller/RobotRuntime | motion authorization, queue, single Serial write | UI/Backend 결과 표현을 담당하지 않음 |
| Safety Controller | odometry/hardware freshness와 fault latch | obstacle product 상태를 새 topic으로 만들지 않음 |
| Serial Runtime | ESP32 handshake/status/odometry/STOP 전달 | 다른 프로세스와 port 공유하지 않음 |
| ESP32 | watchdog와 실제 motor/steering 제어 | Backend 명령을 직접 구독하지 않음 |

## 7. 안전 제약사항

- readiness 이전 구동 금지
- Mapping과 Patrol 동시 실행 금지
- active map 또는 waypoint가 없으면 시작 금지
- localization/Nav2가 준비되지 않으면 시작 금지
- obstacle/safety fault에서 motion authorization 해제와 STOP 우선
- STOP 미확인을 성공으로 처리 금지
- cleanup 실패를 숨기거나 최초 오류로 덮어쓰기 금지
- 중복 commandId로 새 mission/thread 생성 금지
- Robot destination 정지는 Backend STOP보다 먼저 수행
- firmware watchdog 의존은 degraded safe state이며 정상 성공이 아님

## 8. 오류 모델

신규 구조화 진단 모델은 기존 MQTT v1 필드를 깨지 않는 additive 설계로 한다.

| 필드 | 의미 |
|---|---|
| `operation` | `START_PATROL`, `PATROL_RUNTIME`, `STOP_PATROL`, `COMPLETE_PATROL` |
| `operationId` | `patrolId` |
| `commandId` | 해당 command attempt ID |
| `layer` | L0~L12 |
| `stage` | 실패가 발생한 구체 단계 |
| `errorCode` | 안정적인 제품/운영 코드 |
| `originalFault` | Robot/Backend의 원래 reason 또는 exception category |
| `lastSuccessfulStage` | 마지막 성공 단계 |
| `cleanupResult` | `NOT_REQUIRED`, `SUCCEEDED`, `PARTIAL`, `FAILED`, `UNKNOWN` |
| `safeState` | `IDLE_CONFIRMED`, `STOPPED_UNCONFIRMED`, `ERROR_STOPPED`, `UNKNOWN` |
| `retryable` | 현재 상태에서 재시도 가능한지 |
| `recommendedAction` | 사용자/운영자의 최소 조치 |

현재 실제 reason은 `ACTUAL`, 코드에 없는 계층 코드는 `PROPOSED`로 표시한다.

## 9. 계층별 실패와 복구

| 계층 | 대표 errorCode | 현재 근거 | 확인 위치 | 자동 처리와 복구 |
|---|---|---|---|---|
| L0 | `PATROL.L0.REQUEST_NOT_SENT`, `FRONTEND_TIMEOUT` | `PROPOSED` | Browser network, `Dashboard.tsx` | pending guard; 연결 회복 후 detail 재조회 |
| L1 | `ROBOT_NOT_FOUND`, `ROBOT_NOT_IDLE`, `ROBOT_OFFLINE`, `SENSOR_STATUS_NOT_READY`, `ACTIVE_PATROL_EXISTS`, `MAPPING_ACTIVE` | Backend 일부는 `ROBOT_001/003`, `PATROL_002`; 세분 코드는 `PROPOSED` | `PatrolCommandStateService` | MQTT 전 차단; Robot/status/map을 정상화 후 재시도 |
| L2 | `MQTT_PUBLISH_FAILED`, `ACK_TIMEOUT`, `STALE_IN_PROGRESS` | publish 보상은 구현, timeout은 `PROPOSED` | `PatrolCommandService`, Backend log/DB | START publish 실패는 FAILED 보상; watchdog 필요 |
| L3 | `ROBOT_NOT_CONNECTED`, `BROKER_DELIVERY_FAILED` | `PROPOSED` | Mosquitto/Backend/Robot 연결 로그 | 연결·인증·clientId 복구, 명령 자동 재발행 금지 |
| L4 | `INVALID_COMMAND`, `COMMAND_EXPIRED`, `DUPLICATE_PAYLOAD_MISMATCH` | validation/replay 구현, 제품 코드는 `PROPOSED` | `command_handler.py` | reject; 동일 payload만 cached ACK replay |
| L5 | `RUNTIME_NOT_READY`, `PATROL_ALREADY_ACTIVE`, `RUNTIME_LIFECYCLE_CHANGED`, `CLEANUP_PENDING` | 앞의 세 reason은 코드, cleanup code는 `PROPOSED` | Command Handler, Runtime Adapter | fail-close/rollback; cleanup 완료 후 새 ID |
| L6 | `SERIAL_NOT_READY`, `HARDWARE_STATUS_STALE`, `MOTOR_DISCONNECTED`, `ESP32_COMMAND_TIMEOUT` | freshness/STOP write 일부 구현 | RobotRuntime/SafetyController | queue 삭제+STOP+watchdog; 실물 정지 전 재시도 금지 |
| L7 | `LIDAR_NOT_READY`, `SCAN_TIMEOUT`, `ODOM_TIMEOUT`, `TF_UNAVAILABLE`, `LOCALIZATION_NOT_READY/LOST` | 일부 실제 reason, 나머지 `PROPOSED` | state store, ROS topics/TF | START 차단 또는 runtime fail-close; freshness 회복/재localize |
| L8 | `ACTIVE_MAP_MISSING`, `MAP_FILE_INVALID`, `MAP_VERSION_MISMATCH`, `MAP_HASH_MISMATCH`, `PATROL_ROUTE_NOT_CONFIGURED`, `NAVIGATION_ROUTE_UNSAFE`, `NAV2_NOT_READY`, `NAV2_ACTION_SERVER_NOT_READY` | 마지막 세 운영/코드 실제, 계층 코드는 `PROPOSED` | Backend navigation API, provider, Nav2 bridge | motor 전 reject; map/route/Nav2 정상화 |
| L9 | `ROUTE_BUILD_FAILED`, `AI_ENABLE_FAILED`, `START_SERIAL_FAILED`, `FIRST_GOAL_REJECTED/ABORTED` | Robot reason은 부분 구현, 계층 코드는 `PROPOSED` | provider, AI controller, Runtime, Nav2 callbacks | AI disable, STOP, cleanup, ERROR |
| L10 | `GOAL_TIMEOUT`, `GOAL_ABORTED`, `ROUTE_BLOCKED`, `OBSTACLE_STOPPED`, `SAFETY_FAULT`, `RUNTIME_CRASHED` | Nav2/obstacle/safety 일부 구현 | Nav2 bridge, command tick, RobotRuntime | obstacle만 pause/resume; 나머지는 fail-close |
| L11 | `STOP_COMMAND_FAILED`, `NAV2_CANCEL_FAILED`, `ESP32_STOP_TIMEOUT`, `STOP_UNCONFIRMED`, `CLEANUP_FAILED` | cleanup best effort 구현, confirmation 미구현 | STOP API/ACK, Adapter, Runtime | 모든 cleanup을 시도; unsafe/unknown이면 재시작 금지 |
| L12 | `DB_UPDATE_FAILED`, `SSE_DELIVERY_FAILED`, `FRONTEND_STATE_MISMATCH` | 일부 logging만 존재 | ACK handler, SSE, Frontend timeout | DB와 Robot truth 재조정, correlation 조회 필요 |

### 9.1 필수 오류별 운영 절차

| errorCode (`PROPOSED`) | 실제 기존 reason | 조건 / 확인 | 자동 cleanup | 해결·재시도·safeState | 사용자 / 운영자 문구 |
|---|---|---|---|---|---|
| `PATROL.L8.PATROL_ROUTE_NOT_CONFIGURED` | `PATROL_ROUTE_NOT_CONFIGURED` | route/provider 없음; Robot service와 ACK log | prepared state 취소 | route 설치·조회 성공 후 새 ID; `IDLE_CONFIRMED` | “순찰 경로가 준비되지 않았습니다.” / route source와 waypoint 수 확인 |
| `PATROL.L8.NAVIGATION_ROUTE_UNSAFE` | `NAVIGATION_ROUTE_UNSAFE` | bounds/occupancy/clearance/곡률 실패 | motion 전 reject | route 수정·검증 후 재시도 | “안전한 순찰 경로를 다시 설정해 주세요.” / 최초 unsafe segment 기록 |
| `PATROL.L8.NAV2_ACTION_SERVER_NOT_READY` | 동일 | `server_is_ready()==false` | motion 전 reject | Nav2 lifecycle/action server 정상 후 재시도 | “이동 시스템 준비 중입니다.” / action server·lifecycle 확인 |
| `PATROL.L1.ROBOT_NOT_IDLE` | reason 누락 가능 | Backend/Robot state가 IDLE 아님 | MQTT 전 또는 Robot reject | active operation과 cleanup 확인 후 재시도 | “로봇이 대기 상태가 아닙니다.” / robot state와 active patrol 확인 |
| `PATROL.L1.ROBOT_OFFLINE` | Backend `ROBOT_NOT_READY`로 합쳐짐 | `lastConnectedAt` 15초 초과 | MQTT 전 차단 | fresh status 확인 후 재시도 | “로봇 연결을 확인해 주세요.” / lastConnectedAt age |
| `PATROL.L8.ACTIVE_MAP_MISSING` | `NAVIGATION_CONFIG_NOT_READY` 등으로 합쳐짐 | Backend map 또는 local map 없음 | motion 전 reject | 동일 map bundle 설치 후 재시도 | “활성 지도가 없습니다.” / map path·mapId 확인 |
| `PATROL.L8.MAP_VERSION_MISMATCH` | `NAVIGATION_MAP_MISMATCH` 계열 | Backend/local version 불일치 | motion 전 reject | 승인된 동일 version 배치 | “지도 버전이 맞지 않습니다.” / 양쪽 mapId/version 기록 |
| `PATROL.L8.WAYPOINTS_EMPTY` | Backend `MAP_006` 또는 Robot `PATROL_ROUTE_NOT_CONFIGURED`로 합쳐짐 | route 레코드는 있으나 현재 version의 유효 waypoint가 0개 | motion 전 reject | waypoint≥1, 마지막 DESTINATION 저장 | “순찰 지점을 등록해 주세요.” / raw·valid waypoint count/version |
| `PATROL.L7.LOCALIZATION_NOT_READY` | `MAP_POSE_NOT_READY` | map pose 없음/AMCL 미준비 | motion 전 reject | AMCL pose와 TF 안정 후 재시도 | “로봇 위치를 확인하는 중입니다.” / pose timestamp와 covariance |
| `PATROL.L7.LIDAR_NOT_READY` | `LIDAR_NOT_READY` | status lidar != NORMAL | motion 전 reject | `/scan` freshness 회복 후 재시도 | “거리 센서를 확인해 주세요.” / status와 `/scan` Hz |
| `PATROL.L7.ODOM_TIMEOUT` | `ODOMETRY_NOT_READY` 또는 runtime fault | calibrated distance 없음/stale | START 차단 또는 fail-close | fresh `/odom` 후 새 ID | “위치 센서를 확인해 주세요.” / last odometry age |
| `PATROL.L7.TF_UNAVAILABLE` | 별도 구조화 reason 미확인 | map→odom 또는 odom→base_link 단절 | 기대상 motion 전 reject | TF 연속성 회복 전 금지; `UNKNOWN` | “로봇 위치 연결을 확인해 주세요.” / 누락 frame과 age |
| `PATROL.L6.ESP32_COMMAND_TIMEOUT` | Serial/runtime reason 계열 | CONTROL/STOP 응답 또는 watchdog 문제 | mission invalidate+STOP | 물리 정지·handshake 후 재시도 | “구동 장치 응답이 없습니다.” / sequence, ACK age |
| `PATROL.L9.FIRST_GOAL_REJECTED` | `NAV2_GOAL_REJECTED` | 첫 async goal reject | zero motion+goal invalidate | route/Nav2 원인 해결 후 새 START | “첫 이동 지점을 시작하지 못했습니다.” / sequence=1, goal response |
| `PATROL.L10.GOAL_ABORTED` | `NAV2_GOAL_STATUS_{status}` | accepted goal result != SUCCEEDED | zero motion+cleanup+ERROR | localization/path 회복 및 safe stop 후 | “순찰 이동이 중단되었습니다.” / sequence/status |
| `PATROL.L10.OBSTACLE_STOPPED` | obstacle `STOP` | LiDAR obstacle status | pause, zero motion, goal cancel | stable CLEAR+AI/LiDAR ready 후 같은 sequence resume | “장애물로 잠시 정지했습니다.” / direction·reason·clear hold |
| `PATROL.L11.STOP_UNCONFIRMED` | “STOP delivery is unconfirmed” | Serial write 실패 또는 ESP32 ACK 미확인 | watchdog fallback | 물리 정지 확인 전 재시작 금지; `STOPPED_UNCONFIRMED` | “안전 정지를 확인 중입니다.” / serial connected, STOP sequence/ACK |
| `PATROL.L2.ACK_TIMEOUT` | 현재 scheduler 없음 | START/STOP deadline 이후 ACK 없음 | 미구현 | Robot/물리 상태 대조 후 새 ID; 자동 START 재발행 금지 | “로봇 응답을 확인하지 못했습니다.” / publishAt, deadline, telemetry |
| `PATROL.L12.SSE_DELIVERY_FAILED` | emitter/connection 오류 | DB는 변경됐으나 UI 전달 실패 | 연결 제거/timeout | detail API로 reconciliation | “상태를 새로고침해 주세요.” / DB status와 SSE subscriber |
| `PATROL.L4.INVALID_COMMAND` | validation text가 ACK에 빠질 수 있음 | schema/ID/TTL 오류 | reject | payload 수정 후 새 ID | “명령 형식이 올바르지 않습니다.” / validation reason 필수화 |
| `PATROL.UNKNOWN.UNSPECIFIED_FAILURE` | 실제 `reason=null` | 원인 필드 미전달로 계층 판정 불가 | 안전 상태도 증거 없이는 `UNKNOWN` | 상·하위 로그와 Jetson correlation 전 자동 재시도 금지 | “원인을 확인할 수 없어 진단이 필요합니다.” / 원본 ACK·계층별 correlation |

`reason=null`은 독립 원인이 아니라 관측성 결함이다. 분석 기준 최초 유실 지점은 Robot의 여러
`_record_and_publish_command(..., status)` 호출이 reason 인자를 넘기지 않는 곳이었다. 승인 후
변경에서는 Robot의 모든 비성공 ACK에 reason을 강제하고, 알 수 없는 경우
`UNSPECIFIED_FAILURE`를 기록한다. 다만 Backend DB, SSE/API, Frontend의 영구 보존은 후속
Backend/Frontend Story가 필요하다. `ROBOT_IMPLEMENTED_THIS_CHANGE`

## 10. START_PATROL readiness

프로세스 존재와 값 freshness를 구분한다.

| Readiness | Backend | Robot | 실제 검사 위치 | 누락 | 실패 reason |
|---|---|---|---|---|---|
| Robot 존재/소속 | 예 | 해당 없음 | repository row lock | 없음 | `ROBOT_001` |
| Robot IDLE | 예 | `IDLE` 또는 recovery용 `ERROR` | StateService / Handler | ERROR recovery 조건 구조화 부족 | `ROBOT_003`, reason 누락 |
| connection fresh | 15초 | Serial runtime running | StateService / Adapter | Robot hardware timestamp를 별도 노출하지 않음 | `ROBOT_003`, `SERIAL_RUNTIME_NOT_RUNNING` |
| camera/lidar/motor NORMAL | 예 | lidar+Safety snapshot | StateService / Handler/Adapter | camera/motor 세부 reason 통합 | `ROBOT_003`, `LIDAR_NOT_READY` |
| active map/metadata | 예 | local bundle/provider 검증 | NavigationWaypointService/provider | 파일 readability 결과 구조화 필요 | `MAP_006`, navigation reason |
| mapId/version/hash | version 간접 | 강검증 | provider/map metadata | Backend는 hash를 직접 gate하지 않음 | mismatch 계열 |
| waypoint와 route 규칙 | 예 | 예 | NavigationWaypointService/route provider | 없음 | `MAP_006`, unsafe/config reason |
| active Patrol 중복 | 예 | 예 | repository/handler/service | cleanup-pending durable flag 없음 | `PATROL_002`, `PATROL_ALREADY_ACTIVE` |
| Mapping inactive | Backend 직접 미확인 | 예 | Handler | Backend shared operation gate 부족 | `MAPPING_ACTIVE` |
| Serial connected/owner | 간접 freshness | runtime running | RobotRuntime/Adapter | owner count 진단 없음 | `SERIAL_RUNTIME_NOT_RUNNING` |
| HardwareStatus fresh | 15초 status 간접 | SafetyController | state/safety snapshot | 항목별 age 전달 없음 | safety fault |
| `/scan` fresh | lidar status 간접 | ROS lidar bridge 간접 | bridge/state | frequency/age 구조화 부족 | `LIDAR_NOT_READY`/stale |
| `/odom` fresh | 아니오 | calibrated distances | Adapter/Safety | reason 명칭 불일치 | `ODOMETRY_NOT_READY` |
| TF/localization pose | 아니오 | pose 존재 | Adapter | map→odom, odom→base_link 개별 freshness 없음 | `MAP_POSE_NOT_READY` |
| map_server/AMCL lifecycle | 아니오 | 상위 gate 미확인 | ROS launch/Nav2 | 명시적 lifecycle gate 부족 | `PROPOSED` |
| NavigateToPose server | 아니오 | 예 | `RosNav2Bridge.is_ready` | 없음 | `NAV2_ACTION_SERVER_NOT_READY` |
| obstacle/safety allowed | 아니오 | Safety snapshot | Adapter | obstacle latch 별도 START reason 불명 | safety fault |
| cleanup pending 없음 | 아니오 | active/lease로 일부 | Adapter | durable state 없음 | `PROPOSED` |
| AI enable 가능 | 아니오 | readiness 후 enable | Handler | enable 성공과 applied 상태의 상관 기록 부족 | AI reason |
| ESP32 START 가능 | 간접 | Serial send/active confirmation | Runtime/Handler | ESP32 START ACK 의미와 timeout 명시 부족 | exception text |

## 11. STOP_PATROL과 안전 종료

### 11.1 현재 확인

- STOP은 START와 다른 UUID를 사용한다. `CODE_CONFIRMED`
- Backend Patrol row의 `command_id`는 STOP ID로 덮어써 START ID를 잃는다. `CODE_CONFIRMED`
- Robot ACK cache key는 commandId이므로 START와 STOP ACK가 구분된다. `CODE_CONFIRMED`
- STOP TTL은 10초다. `BOTH_CONFIRMED`
- RobotRuntime은 pending motion을 제거하고 mission generation을 무효화한다. `CODE_CONFIRMED`
- Nav2 bridge는 timer/goal을 invalidate하고 zero motion을 보낸 뒤 cancel을 best effort로 한다.
  `CODE_CONFIRMED`
- 모든 patrol component cleanup을 순서대로 시도한다. `CODE_CONFIRMED`
- Handler는 STOP 시 AI disable 후 `IDLE` 또는 `ERROR`를 발행한다. `CODE_CONFIRMED`
- Backend는 성공 ACK 뒤 사용자 STOP을 `STOPPED`로 바꾼다. `CODE_CONFIRMED`
- Nav2 cancel 완료 응답을 기다리지 않는다. `CODE_CONFIRMED`
- ESP32 STOP ACK를 기다리지 않고 Serial write 성공을 정지 확인으로 사용한다.
  `DOCUMENT_CODE_MISMATCH`: 운영 합격 문서는 STOP ACK/실제 정지를 요구한다.
- obstacle 상태를 명시적으로 CLEAR로 초기화하는 STOP 로직은 확인되지 않았다.
  `RUNTIME_VERIFICATION_REQUIRED`

### 11.2 정상 STOP 완료 조건

최종 설계의 STOP 성공은 다음 모두를 만족해야 한다.

1. Nav2 active/pending goal 없음
2. queued motion 및 motion authorization 없음
3. ESP32 STOP sequence ACK 또는 동등한 정지 telemetry 확인
4. Patrol Runtime IDLE
5. AI disabled/applied 상태 확인
6. Robot state IDLE 또는 명시적 안전 ERROR
7. Backend `STOPPED` 또는 completion 목적이면 `COMPLETED`
8. Frontend detail/status reconciliation 완료

현재 코드는 1, 2, 4, 5를 best effort로 수행하고 6~7을 상태/ACK로 연결하지만 3을 보장하지
않는다. 따라서 STOP ACK `SUCCEEDED`가 실제 motor stop 완료와 동일하다고 단정할 수 없다.

## 12. 정상 완주 COMPLETED

현재 완주 경로는 존재하지만 Robot 단독으로 Backend `COMPLETED`를 만들지는 않는다.

```text
Robot WaypointMission.update_pose
  -> final DESTINATION_REACHED
  -> local RobotRuntime STOP
  -> Nav2 cleanup, local IDLE/ERROR, AI disable, final telemetry
  -> Backend RobotTelemetryService.updatePose
  -> PatrolCommandService.autoCompleteIfArrived
  -> Patrol STOP_REQUESTED + completionRequested=true + STOP commandId
  -> MQTT STOP_PATROL
  -> Robot STOP 재확인 + ACK SUCCEEDED
  -> Backend PatrolCommandAckService.completeRequested
  -> COMPLETED + AI summary request + completion SSE
```

즉 완주 결과는 별도 MQTT completion ACK가 아니라 pose→Backend destination 판정→STOP ACK
경로다. Robot이 local destination에서 이미 IDLE로 바뀐 뒤에도 Backend의 STOP은 안전 재확인
명령이다. 이 경로는 코드상 가능하지만 실제 Jetson E2E 검증은 필요하다.

Patrol 36은 Frontend/사용자 STOP이 `requestStop()`을 호출해 `completionRequested=false`였기
때문에 성공 ACK 뒤 `STOPPED`가 됐다. destination 자동 완료가 아니므로 `COMPLETED`가 아니다.

위험한 경계는 Robot local destination stop 후 최종 pose가 Backend에 도달하지 않거나 Backend
route 판정이 실패하는 경우다. Robot은 IDLE인데 Patrol DB는 `IN_PROGRESS`로 남을 수 있다.

## 13. 장애물 정지

실제 경로는 기존 계약대로 다음과 같다.

```text
Jetson /roki/obstacle_stop
  -> ROS/LiDAR bridge와 shared RobotStateStore obstacle STOP
  -> CommandHandler.tick
  -> RuntimeAdapter.pause_patrol
  -> Nav2 goal invalidate/cancel + zero motion
  -> RobotRuntime STOP -> ESP32
  -> 기존 status payload obstacle {status: STOP, direction, reasonMessage}
  -> Backend RobotTelemetryService -> RobotStatus.OBSTACLE_STOP
```

- mission은 종료가 아니라 paused다.
- obstacle CLEAR, LiDAR normal, AI readiness/applied 상태가 hold 시간 동안 안정돼야 resume한다.
- resume은 현재 sequence를 다시 Nav2 goal로 발행한다.
- 사용자 STOP이 오면 paused 여부와 관계없이 STOP/cleanup 경로가 실행된다.
- clear 후 pose/TF/Nav2 전체 readiness를 다시 검사하는 구조는 충분하지 않다. 현재는 AI와
  LiDAR 상태를 재확인하고 Nav2 `resume_patrol()`을 호출하므로 localization/TF 재검사가
  `PROPOSED` 보강 항목이다.

## 14. 오류 전달과 정보 유실

| 정보 | Robot ACK | Backend log | DB | SSE/API | Frontend |
|---|---|---|---|---|---|
| commandId | 예 | 예 | 최신 하나 | 아니오 | 아니오 |
| ACK status | 예 | 예 | Patrol status로 축약 | 간접 detail | 일반 상태 |
| reason | 선택적 | ACK에 있으면 예 | 아니오 | 아니오 | 아니오 |
| errorCode | 아니오 | 일부 Backend code | 아니오 | REST validation만 일부 | API message만 일부 |
| failedStage | 아니오 | 로그 문맥만 | 아니오 | 아니오 | 아니오 |
| cleanupResult | 아니오 | 일부 text | 아니오 | 아니오 | 아니오 |
| safeState | 아니오 | telemetry 추론 | Robot status만 | Robot SSE | 축약 표시 |
| retryable | 아니오 | 아니오 | 아니오 | 아니오 | 아니오 |

reason의 최초 유실은 Robot ACK 생성 시 reason을 생략하는 호출이다. reason이 있더라도
`PatrolCommandAckService` 로그 이후 DB에 저장하지 않는 지점에서 영구 유실된다. START의
`REJECTED`와 `FAILED`는 모두 Patrol `FAILED`로 합쳐진다. Frontend는 16초 timeout 뒤 detail의
`FAILED`만 보고 “장비 상태를 확인”하라는 일반 문구를 표시한다.

## 15. 운영 Patrol attempts

EC2 host `ip-172-26-0-175`, Backend 최근 24시간 로그와 MySQL Patrol 30~36을 2026-08-05에
read-only로 교차 확인했다. 시간은 KST다. commandId는 운영 상관 ID이며 secret이 아니다.

| patrolId | attempt | command | commandId | publish | ACK | reason | DB final | 다음 START까지 |
|---|---:|---|---|---|---|---|---|---:|
| 30 | 1 | START | `309afc31-6f73-422f-8477-21e107e2d236` | 17:23:44.056 | 17:23:44.132 REJECTED | `null` | FAILED | 3m48s |
| 31 | 1 | START | `dc870b88-637b-4378-a528-63ecd1046e1b` | 17:27:32.326 | 17:27:32.400 REJECTED | `PATROL_ROUTE_NOT_CONFIGURED` | FAILED | 2h33m28s |
| 32 | 1 | START | `e3bd9396-66c8-40c4-a906-140254167266` | 20:01:00.220 | 20:01:00.490 REJECTED | `NAVIGATION_ROUTE_UNSAFE` | FAILED | 2m22s |
| 33 | 1 | START | `82d0ce94-8344-4de3-a362-916bd529b1b4` | 20:03:22.353 | 20:03:22.592 REJECTED | `NAVIGATION_ROUTE_UNSAFE` | FAILED | 1h07m20s |
| 34 | 1 | START | `db233064-25be-423b-aaf7-caaa1cf16536` | 21:10:42.145 | 21:10:42.522 REJECTED | `NAVIGATION_ROUTE_UNSAFE` | FAILED | 25m11s |
| 35 | 1 | START | `64cef744-7fd4-4fdf-afa9-b40069e13454` | 21:35:53.681 | 21:35:53.925 REJECTED | `NAV2_ACTION_SERVER_NOT_READY` | FAILED | 5m56s |
| 36 | 1 | START | `578b0aa6-2606-4a97-a571-893a7c0e3bd7` | 21:41:49.687 | 21:41:50.008 SUCCEEDED | null | STOPPED | 해당 없음 |
| 36 | 2 | STOP | `b184439e-dd45-4685-b840-fbef4a602cd0` | 21:42:22.198 | 21:42:22.351 SUCCEEDED | null | STOPPED | 해당 없음 |

DB Patrol 36에는 STOP commandId만 남아 START commandId를 영구 복원할 수 없다. 다른 row도
attempt history, ACK time, reason, layer 또는 cleanup 결과를 저장하지 않는다.

## 16. 변경 범위

### 16.1 반드시 필요한 변경

1. `patrol_command_attempts` 또는 동등한 append-only attempt 저장
2. START/STOP ACK deadline watchdog와 stale state reconciliation
3. Robot의 모든 reject/fail 경로에서 reason 필수화 — `IMPLEMENTED_THIS_CHANGE`
4. 최초 failure와 cleanup 결과를 분리해 저장
5. Patrol command-result SSE/API와 Frontend 상세 표시
6. ESP32 STOP write와 STOP confirmed를 분리하고 confirmation 전 성공 ACK 금지
7. first Nav2 goal accept 전 START `SUCCEEDED`를 보내지 않도록 완료점 재정의 — `IMPLEMENTED_THIS_CHANGE`
8. runtime failure/destination 후 Backend DB stale 상태 reconciliation
9. structured readiness snapshot과 각 freshness timestamp

### 16.2 선택적 변경

- read-only 진단 endpoint/CLI
- 운영자 화면의 attempt timeline
- Jetson local durable attempt journal과 Backend 동기화
- Frontend support correlation ID 복사 기능

### 16.3 변경하지 않는 계약

- 기존 MQTT topic과 schema version 1
- ACK status `SUCCEEDED/REJECTED/FAILED`
- 기존 Robot status enum
- obstacle status 객체와 기존 status topic
- ESP32 Serial protocol version 1
- 단일 Serial owner
- Robot/AI/Backend 책임 분리

### 16.4 후보 파일

Backend:

- `PatrolCommandService`, `PatrolCommandStateService`, `PatrolCommandAckService`
- `RobotTelemetryService`, Patrol response/SSE service
- 신규 attempt entity/repository와 Flyway migration

Frontend:

- `frontend/src/api/contracts.ts`, `frontend/src/api/services.ts`
- `frontend/src/pages/Dashboard.tsx`
- 신규 Patrol command-result hook/store

Robot:

- `robot/roki-iot/backend_mqtt/command_handler.py`
- `robot/roki-iot/integration/runtime_state_backend_adapter.py`
- `robot/roki/navigation/ros_nav2_bridge.py`
- `robot/roki/runtime/robot_runtime.py`

### 16.5 읽기 전용 운영 진단 CLI

`robot/tools/diagnose_operations.py`는 EC2 Backend 로그를 파일 또는 표준 입력으로 읽어
`START_MAPPING`, `START_PATROL`, `STOP_PATROL`의 발행과 ACK를 commandId로 연결한다.

```bash
python robot/tools/diagnose_operations.py --file backend.log
ssh aiot-ec2 "sudo docker logs --since 24h aiot-backend 2>&1" |
  python robot/tools/diagnose_operations.py --stdin
python robot/tools/diagnose_operations.py --file backend.log --command-id <UUID>
python robot/tools/diagnose_operations.py --file backend.log --patrol-id 36
python robot/tools/diagnose_operations.py --file backend.log --operation patrol --json
```

이 도구는 Python 표준 라이브러리로 로그 문자열만 분석한다. DB, MQTT, Robot, EC2 상태를
조회하거나 변경하지 않고 REST, ROS, Serial, Docker 명령도 실행하지 않는다. 파이프 예시의
SSH/Docker 로그 조회는 사용자가 별도로 실행하는 읽기 전용 입력 공급 단계이며 CLI 자체 기능이
아니다. Backend 로그에 없는 Jetson ROS/Nav2/TF 및 ESP32 wheel stop 상태는 확정할 수 없다.
과거 ACK의 reason이 `null`이거나 없으면 `UNKNOWN`으로 표시하고 동일 commandId의 Jetson 로그
확인을 안내한다. 정상 완주 `COMPLETED` 여부도 Backend command/ACK 로그만으로 단정하지 않는다.

## 17. 검증 기준

### 17.1 단위·Mock

- Backend readiness 각 조건과 row-lock 중복 START
- MQTT schema/TTL/future skew/fingerprint/ACK replay
- START publish 실패 보상과 ACK timeout
- active map, version/hash, waypoint, route unsafe
- first goal reject/abort 전에 START 성공이 확정되지 않는지
- STOP 우선순위, queued motion 제거, 모든 cleanup 계속 실행
- ESP32 STOP unconfirmed이면 ACK가 성공하지 않는지
- obstacle pause 후 같은 sequence 재개
- destination의 local STOP→completion STOP→COMPLETED
- reason, failedStage, cleanupResult가 DB/SSE/Frontend까지 보존되는지

### 17.2 EC2

- 동일 patrolId의 START/STOP attempts가 DB와 로그에서 일치
- timeout scheduler가 stale `IN_PROGRESS/STOP_REQUESTED`를 닫는지
- SSE 단절 뒤 detail API reconciliation
- secret을 제외한 correlation log

### 17.3 Jetson/Nav2/ESP32

- Serial owner 정확히 1개
- `/scan`, `/odom`, map→odom→base_link freshness
- map_server/AMCL/Nav2 lifecycle active
- 첫 NavigateToPose goal accepted 뒤 ACK 순서
- goal reject/abort와 `cmd_vel` timeout fail-close
- ESP32 STOP sequence ACK와 실제 wheel stop
- obstacle STOP/CLEAR hold/resume
- 최종 DESTINATION local STOP, Backend completion STOP, `COMPLETED`
- STOP 실패 뒤 재시작 차단

이 절은 `RUNTIME_VERIFICATION_REQUIRED`이며 사용자 승인과 현장 안전 절차 없이는 실행하지
않는다.

## 18. 롤백

- 코드: 각 component branch/image를 독립적으로 이전 검증 commit으로 되돌린다.
- DB: additive nullable 컬럼/attempt table을 우선하며 구버전 애플리케이션이 무시할 수 있게
  한다. 운영 데이터 삭제를 rollback 조건으로 삼지 않는다.
- Backend/Frontend: `/srv/aiot/deploy/current.env`의 이전 검증 이미지로 component별 rollback.
- Jetson: signed manifest와 `/opt/aiot/iot/previous`를 사용하고 활성 파일 직접 수정 금지.
- 계약 fallback: 신규 진단 필드가 없으면 기존 ACK v1을 계속 처리하되 진단 정보는 UNKNOWN으로
  표시한다. unsafe 상태를 성공으로 추정하지 않는다.

## 19. 미확정 항목

다음은 Jetson 실기기에서만 확정할 수 있다.

- 실제 설치된 IoT commit/package와 현재 Git 코드 일치 여부
- ROS node/lifecycle와 `/scan`, `/odom`, TF 실제 freshness
- local active map ID/version/hash와 Backend 일치
- AMCL pose 품질과 localization loss 동작
- Nav2 첫 goal accept/abort 실제 timing
- Serial STOP write 이후 ESP32 ACK와 실제 motor stop 시간
- firmware watchdog stop 시간
- obstacle CLEAR 뒤 localization/Nav2 재개 안전성
- destination 최종 pose 전달과 Backend `COMPLETED` E2E
- cleanup 실패 또는 process crash 뒤 재시작 interlock

## 20. 구현 우선순위와 Jira 분리

1. **E103-300A — STOP confirmation 및 safe-state gate**: 안전 최우선, Robot/ESP32 연계
2. **E103-300B — Patrol attempt/history 및 ACK timeout**: Backend/DB
3. **E103-300C — first goal acceptance와 runtime result 계약**: Robot/Nav2
4. **E103-300D — Patrol result SSE/API와 오류 표시**: Backend/Frontend
5. **E103-300E — structured readiness/diagnostic snapshot**: Robot/운영
6. **E103-300F — Jetson physical acceptance**: 현장 검증 Story

현재 단계에서 즉시 가능한 범위는 위 변경의 상세 설계·테스트 fixture 작성까지다. 실제
코드, migration, MQTT payload 확장, 배포 또는 실기기 검증은 별도 승인 후 진행한다.
