# 금요일 고정 지도·waypoint·AI E2E 현장 검증서

기준일: 2026-08-05
범위: 로봇 1대, 지도 1개, 미리 만든 고정 지도, 감독자 동반 시연

이 문서는 실물에서만 확정할 수 있는 값과 시연 중단 기준을 기록하기 위한 것이다.
실제 모터·배터리·시리얼·서비스·Jetson 설정 변경은 사용자의 명시적 허용을 받은 뒤에만
수행한다. 비밀번호, MQTT credential, Robot service token, 환경변수의 비밀값은 화면이나
기록표에 복사하지 않는다.

## 0. 공통 사전 조건과 중단 기준

사전 조건:

- 감독자와 물리 STOP 담당자가 로봇 옆에 있다.
- 처음에는 바퀴를 띄우고 모터 전원 경로를 비활성화한다.
- 최종 지도 ID/version과 Jetson의 로컬 map YAML/image가 일치한다.
- `AIOT_NAVIGATION_CONFIG_SOURCE=backend`이며 로컬 fallback은 명시적으로 승인하지 않은 한 꺼져 있다.
- AI 이벤트의 Backend REST owner는 Robot 한 경로뿐이다. AI 프로세스는 ROS detection만 보낸다.
- 순찰 위치 추정은 LiDAR localization과 encoder odometry를 함께 사용한다.
- 라인센서는 주행·readiness·motion gate에 사용하지 않으며 상태 진단값만 남긴다.

즉시 중단:

- 물리 E-stop 또는 BTS7960 EN 차단을 1초 안에 수행할 수 없다.
- STOP 뒤 바퀴가 계속 돌거나, 수신기 분리 뒤 motion pulse가 다시 살아난다.
- 좌우 바퀴 방향·encoder 부호가 서로 다르거나 정지 상태 odometry가 계속 이동한다.
- 지도/route의 map ID, version, SHA-256 또는 TF가 일치하지 않는다.
- 같은 detection이 Backend event row 두 개 이상을 만든다.
- 차량 좌표 오차가 아래 합의 허용 오차를 넘거나 다른 물체의 LiDAR 거리를 사용한다.

공통 기록:

| 항목 | 기록값 |
|---|---|
| 시험 일시/담당/감독자 | |
| Robot key(비밀 아님) / Backend robotId | |
| IoT commit 또는 OTA version | |
| Backend/Frontend commit | |
| mapId / mapVersion / map bundle SHA-256 앞 12자리 | |
| route source (`backend`/승인된 `local`) | |
| 바닥·조명·차량 배치 | |
| 최종 판정 / 중단 사유 | |

## 1. 게임패드 식별과 안전 재무장

모터 전원을 끈 상태에서만 먼저 실행한다.

```bash
ls -l /dev/input/js*
id e103
getent group input
cd /opt/aiot/iot/current
PYTHONPATH=robot/roki-iot python3 robot/roki-iot/tools/gamepad_probe.py \
  --device /dev/input/js0
```

판정 기준:

- `e103`이 장치를 읽을 수 있고 `input` 그룹 적용 상태다.
- 각 입력을 하나씩 조작했을 때 한 axis/button 번호만 의도대로 바뀐다.
- 수신기 분리, 1초 무입력 lease, 재연결 직후 모두 STOP이다.
- 재연결 뒤 init event만으로 움직이지 않는다. 스틱 중립 + deadman 해제 후 다시 눌러야 재무장된다.

| 기능 | 기대 기본값 | 실측 axis/button | 눌림/방향 값 | 합격 |
|---|---:|---:|---:|---|
| 조향 | axis 0 | | | |
| 전후진 | axis 1 | | | |
| deadman(LB) | button 4 | | | |
| 즉시 STOP(B) | button 1 | | | |
| finish Back | button 6 | | | |
| finish Start | button 7 | | | |

| 안전 시나리오 | 실행 | 기대 결과 | 실제 STOP 지연 | 재무장 전 움직임 | 판정 |
|---|---|---|---:|---|---|
| deadman 해제 | 짧은 pulse 중 LB 해제 | 즉시 STOP | | 없어야 함 | |
| radio loss | 짧은 pulse 중 수신기 분리 | 즉시 STOP | | 없어야 함 | |
| 무입력 lease | stick 고정, 새 event 없음 | 1초 이내 STOP/disarm | | 없어야 함 | |
| 재연결 | stick/LB 상태를 유지한 채 연결 | init event 무시 | | 중립+재누름 전 0 | |
| finish | Back+Start 2초 | STOP 후 map 저장 | | 해당 없음 | |

실패 시: 모터 전원을 켜지 말고 실제 번호·권한만 기록한다. lease를 1초보다 늘려 우회하지 않는다.

## 2. 구동·encoder·물리 차단

승인 후 바퀴를 띄운 상태에서 PWM 45만 사용한다. 기준은 65 mm 바퀴,
LEFT 329 ticks/rev, RIGHT 328 ticks/rev, 조향 60/80/100도다.

| 시험 | 명령/조작 | 기대 | 실측 | 합격 |
|---|---|---|---|---|
| 물리 E-stop | 정지 상태에서 차단/복구 | 차단 중 구동 불가 | | |
| BTS EN | 좌/우 EN 차단 | 해당 모터 즉시 무토크 | | |
| 중앙 조향 | 80도 | 전륜 정면 | 실제 바퀴각 | |
| 좌/우 조향 | 60 / 100도 | 좌/우가 문서와 일치 | 방향/최대각 | |
| 전진 PWM | 45 | 좌우 모두 전진 | 방향/전류/소음 | |
| 후진 PWM | 45 | 좌우 모두 후진 | 방향/전류/소음 | |
| 1회전 encoder | 손으로 정확히 1회전 | L≈329, R≈328, 부호 일치 | L / R | |
| 직선 실측 | 감독자 승인 저속 pulse | 계산 거리와 줄자 거리 일치 | 계산 / 실측 / 오차 | |

거리 계산은 `ticks / ticks_per_rev × π × 0.065 m`로 기록한다. 한쪽 부호가 반대거나
STOP 후 tick이 빠르게 증가하면 바닥 주행을 중단한다.

## 3. 단일 BRIO·LiDAR·SLAM 지도

읽기 전용 확인:

```bash
readlink -f /dev/roki_camera_right
v4l2-ctl --device /dev/roki_camera_right --all
v4l2-ctl --device /dev/roki_camera_right --list-formats-ext
readlink -f /dev/roki_lidar
ros2 topic hz /scan
ros2 topic echo /odom --once
ros2 run tf2_ros tf2_echo map base_link
```

| 항목 | 기대 | 기록값 | 합격 |
|---|---|---|---|
| BRIO alias | 단일 실제 capture node | alias→device / format / FPS | |
| 카메라 수 | V4L2 실제 장치 1개만 open | 프로세스/FD 수 | |
| `/scan` | 끊김 없이 약 10 Hz 이상 | 평균/최저 Hz | |
| 정지 drift | 정지 60초 동안 pose 안정 | Δx / Δy / Δyaw | |
| loop closure | 천천히 순회 후 벽 윤곽 단일 정렬 | 겹침/이중벽 여부 | |
| 출발점 복귀 | 물리 출발점 재진입 | map pose 오차 x/y/yaw | |
| map save | YAML+PGM/PNG(+pose graph) 생성 | 경로/크기/SHA 앞 12자리 | |

지도에 다중 벽 윤곽이 생기거나 정지 drift가 누적되면 해당 map을 Backend에 올리지 않는다.
최종 저장물의 resolution, origin, width/height와 map ID/version을 함께 기록한다.

## 4. mapping 종료 후 localization/Nav2 전환

Backend가 업로드를 `COMPLETED`로 승인하면 Robot은 응답의 mapId/version과 정확한
YAML·PGM bundle hash를 묶어 `/var/lib/aiot/maps/active/`에 설치한다. 설치가 끝나기
전에는 기존 `current-map.env`를 건드리지 않는다. 이후 root path unit이 Robot을 먼저
정지하고 ROS를 patrol/Nav2로 재시작한 뒤 Robot을 다시 시작한다. 실패하면 pending
marker를 남겨 같은 승인 지도로 재시도하며 이전 선택 파일은 보존한다.

운영자는 다음 항목을 확인한다.

1. Front/Backend의 최종 mapId/version과 `current-map.env`가 일치하는지 확인한다.
2. Front에서 구역과 ordered waypoint를 저장한다. 마지막 지점은 유일한 `DESTINATION`이다.
3. 자동 생성할 수 없는 fixed initial pose 실측값을 `ros.env`에 맞춘다.
4. `--check`로 local map, route와 field parameter를 검증한다.
5. TF/AMCL/Nav2 lifecycle을 확인한다.
6. 바퀴를 띄운 채 START_PATROL config fetch와 즉시 STOP을 먼저 검증한다.

```bash
cd /opt/aiot/iot/current
./robot/scripts/run.sh --check
ros2 lifecycle nodes
ros2 topic echo /amcl_pose --once
ros2 run tf2_ros tf2_echo map base_link
```

| 게이트 | 기대 | 기록 | 판정 |
|---|---|---|---|
| local map identity | Backend mapId/version과 동일 | | |
| map bundle hash | 배포 기록과 동일 | | |
| TF | `map→odom→base_link→laser_frame` 연속 | | |
| AMCL 정지 pose | 출발점 허용 오차 안 | | |
| Nav2 lifecycle | 필요한 node active | | |
| navigation config | Backend source, ordered route 수신 | waypoint 수/reason | |

`NAVIGATION_CONFIG_UNAVAILABLE`, `NAVIGATION_MAP_MISMATCH`, `NAVIGATION_CONFIG_INVALID` 또는
`PATROL_ROUTE_NOT_CONFIGURED`이면 AI/모터가 켜지기 전에 START가 거절되어야 한다. 원인을 고치지
않고 local fallback을 켜지 않는다.

## 5. 차량 map 좌표 정확도

MVP 전제는 고정된 SCAN waypoint, 차량 한 대, BRIO 중앙, LiDAR 전방 sector에 다른 물체가
없는 상황이다. bbox와 LiDAR cluster의 일반 연관은 아직 없다.

시험 준비:

1. 바닥에 Robot 기준점과 차량 기준점을 테이프로 표시하고 map ground truth를 실측한다.
2. Robot pose `(x, y, heading)`를 고정한다.
3. 차량이 BRIO 중앙 허용 ROI 안에 오도록 두고 전방 sector의 벽·기둥을 치운다.
4. 줄자 거리, LiDAR front range, 계산 좌표, Backend 저장 좌표를 같은 detection ID로 기록한다.

계산 기준:

```text
theta = robot heading + camera yaw correction
vehicleX = robotX + lidarRange * cos(theta)
vehicleY = robotY + lidarRange * sin(theta)
```

시험 전 팀이 위치 허용 오차를 기록한다. 권장 시작 기준은 줄자 대비 LiDAR 거리 ±0.15 m,
계산 map 좌표 Euclidean error ±0.30 m이며, 실제 공간·센서 결과에 따라 더 엄격하게 확정한다.

| case | Robot pose | 차량 ground truth | BRIO 중앙/ROI | 줄자/LiDAR m | 계산 좌표 | Backend 좌표 | 오차 m | 판정 |
|---|---|---|---|---|---|---|---:|---|
| PARKING 중심 내부 | | | | | | | | |
| PARKING 경계 안쪽 | | | | | | | | |
| PARKING 경계 바깥쪽 | | | | | | | | |
| 다른 heading | | | | | | | | |

경계 case는 위치 오차보다 충분히 큰 여유를 두고 배치한다. 오차 band 안의 점으로 정책을
판정하지 않는다. 등록 차량이 구역 밖이면 `ILLEGAL_PARKING`, 미등록 번호판은 현재 정책상
위치보다 먼저 `UNREGISTERED_VEHICLE`로 판정되는 점을 별도 기록한다.

## 6. 중복 이벤트와 단일 owner

코드상 owner는 다음 한 경로다.

```text
AI pipeline -> ROS /ai/detections -> Robot durable outbox
-> Robot service token REST -> Backend event/evidence
```

AI의 기존 direct REST client가 실제 프로세스에서 교체됐는지 로그와 네트워크 요청 수로 확인한다.
비밀 token이나 Authorization header를 출력하지 않는다.

| 시나리오 | detection eventId | Robot outbox 파일 수 | Backend event row | evidence row/file | 기대 | 판정 |
|---|---|---:|---:|---:|---|---|
| detection 1회 | | | | | 각각 정확히 1 | |
| evidence upload 1회 실패 후 retry | | | | | event 재생성 없이 evidence만 재시도 | |
| 짧은 연속 동일 차량 | | | | | 합의 dedupe 결과 기록 | |
| Robot 재연결 | | | | | 완료 event 재생성 없음 | |

하나의 AI eventId에서 Backend event row가 둘 이상이면 즉시 중단한다. 연속 detection의 제품
정책 dedupe는 현장 결과를 보고 확정하되, AI direct 전송과 Robot 전송의 이중 경로는 허용하지 않는다.

## 7. 전체 시연 E2E

시연 rehearsal가 시작되면 같은 map version의 지도·구역·waypoint를 동결한다. 순찰 중에는
Backend가 설정 변경을 거절해야 하며, 순찰 종료 뒤 구역을 다시 저장하면 과거 순찰 화면의
좌표 기반 구역명이 현재 active 구역 기준으로 달라질 수 있으므로 발표용 기록을 만든 뒤에는
구역을 다시 편집하지 않는다.

| 순서 | 화면/명령 | 기대 결과 | 실패 시 중단 기준 | 실제 기록 |
|---:|---|---|---|---|
| 1 | Front 지도/route 확인 | map version과 waypoint 순서 표시 | stale map/route | |
| 2 | Front START | Backend patrol 생성, MQTT START | 중복 patrol/명령 만료 | patrolId / commandId |
| 3 | Robot config fetch | map identity 일치, ACK SUCCEEDED | config reason으로 REJECTED/FAILED | ACK/status |
| 4 | Nav2 주행 | pose/status 1초/5초 흐름, 순서대로 이동 | TF jump/STOP 불능 | pose 시각 |
| 5 | SCAN | SCAN dwell과 zone context, AI detection | 다른 zone/range 사용 | sequence/zoneId |
| 6 | AI event | Robot outbox→REST→evidence 1개 | 중복 row/사진 누락 | eventId |
| 7 | DESTINATION | Robot이 Backend STOP보다 먼저 물리 STOP | 허용 반경 밖 완료/계속 구동 | 최종 pose |
| 8 | Backend STOP | STOP_PATROL, ACK SUCCEEDED | ACK FAILED/모터 동작 | ACK 시각 |
| 9 | IDLE | AI DISABLE, Robot IDLE, stream stale 처리 | detection 지속/상태 불일치 | |
| 10 | 재시작 | 새 patrolId로 다시 START 가능 | 이전 상태/lock 잔존 | |

최종 합격은 한 patrolId에 대해 `START → ordered Nav2 → SCAN/AI event → DESTINATION local STOP
→ Backend STOP ACK → IDLE → 새 순찰`이 끊김 없이 한 번, 장애/STOP 시나리오가 한 번 성공한 경우다.

## 8. 현장 결과 인계

시험 종료 후 다음만 저장소 밖 안전한 팀 공간에 남긴다.

- 이 문서의 기록표(비밀값 제외)
- map/route identity와 SHA-256
- axis/button, wheel/encoder/steering 실측값
- TF와 pose 오차, 차량 좌표 오차 표
- patrolId/commandId/eventId 같은 비밀이 아닌 상관 ID
- 실패 시각과 secret을 제거한 관련 로그 구간
- 합격하지 못한 항목의 담당자, 재시험 조건, 가장 빠른 확인 방법
