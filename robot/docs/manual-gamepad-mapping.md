# 게임패드 수동 주행 기반 지도 제작

기준일: 2026-08-04
범위: Frontend 지도 생성 요청 → Backend MQTT → Jetson 수동 주행 → SLAM 지도 저장 → Backend 업로드

## 1. 구현된 흐름

```text
Frontend 지도 생성 시작
  -> Backend가 mapping session 생성
  -> MQTT START_MAPPING
     { mappingSessionId, commandId, issuedAt, expiresAt }
  -> Jetson이 맵핑 전용 readiness 확인
     ESP32 runtime + odometry + hardware safety + LiDAR + SLAM Toolbox
     + 게임패드 + Robot service token + 지도 저장 경로
  -> ACK SUCCEEDED
  -> LB(deadman)를 누른 동안 게임패드로 저속 수동 주행
  -> Back + Start를 2초간 눌러 지도 제작 종료
  -> 즉시 STOP 및 수동 제어 해제
  -> nav2_map_server map_saver_cli
     map.yaml + map.pgm + map.png + 선택적 pose graph 저장
  -> POST /api/map/mapping-sessions/{mappingSessionId}/map
     mapImage(PNG), commandId, resolution, originX/Y/Yaw
  -> Backend mappingStatus=COMPLETED
  -> 응답의 mapId/version과 로컬 YAML·PGM 묶음을 SHA-256으로 결합
  -> /var/lib/aiot/maps/active/ 아래 불변 버전 디렉터리에 원자적으로 설치
  -> current-map.env를 새 지도와 patrol 모드로 원자적 교체
  -> root path unit이 Robot 정지 → ROS Nav2 재시작 → Robot 재시작
  -> Frontend의 기존 SSE/조회 흐름으로 완료 표시
```

Frontend와 Backend 계약은 바꾸지 않는다. IoT가 기존 `START_MAPPING`과 multipart
업로드 계약을 구현한다. 연결 실패, HTTP 408/425/429와 5xx만 2초부터 최대 30초
간격으로 재시도한다. 인증·권한·요청 형식 같은 영구 오류는 즉시 FAILED ACK로 끝내며
무한 재시도하지 않는다.

지도 원본은 `/var/lib/aiot/maps/mapping-<session>-*/`에 남는다. Backend에는 화면 표시와
구역 편집에 필요한 PNG 및 좌표 메타데이터를 보내며, Nav2용 YAML·PGM·pose graph는
Jetson 로컬에 보존한다.

## 2. 조작 기본값

| 입력 | 동작 |
|---|---|
| LB | deadman. 누르고 있는 동안에만 주행·조향 입력 허용 |
| 왼쪽 스틱 상/하 | 전진/후진, PWM 45 |
| 왼쪽 스틱 좌/우 | 서보 60~100도 범위 조향 |
| B | 즉시 STOP |
| Back + Start 2초 | STOP 후 지도 저장·업로드 |
| 수신기 분리/입력 오류 | 즉시 STOP, 재연결 대기 |

범용 2.4 GHz 게임패드는 제품마다 Linux axis/button 번호가 다를 수 있다. 기본값은
`config/robot.env.example`에 있으며, 최초 현장 확인 후 아래 값만 수정한다.

```text
ROKI_MAPPING_GAMEPAD_DEVICE=/dev/input/js0
ROKI_MAPPING_GAMEPAD_STEERING_AXIS=0
ROKI_MAPPING_GAMEPAD_THROTTLE_AXIS=1
ROKI_MAPPING_GAMEPAD_DEADMAN_BUTTON=4
ROKI_MAPPING_GAMEPAD_STOP_BUTTON=1
ROKI_MAPPING_GAMEPAD_FINISH_BUTTON_A=6
ROKI_MAPPING_GAMEPAD_FINISH_BUTTON_B=7
ROKI_MAPPING_GAMEPAD_INPUT_LEASE_SEC=0
```

Linux joystick은 값이 바뀔 때만 새 이벤트를 보내므로 이벤트가 없다는 사실만으로
수신기 단절을 판정할 수 없다. 기본값 `0`에서는 열린 장치의 LB와 스틱 상태를 주기적으로
짧은 pulse로 변환한다. LB 해제, B, 수신기 분리, 맵핑 종료는 즉시 STOP하며 프로세스가
멈추면 ESP32 watchdog이 남은 명령을 종료한다. 주기 이벤트를 보장하는 별도 수신기에만
양수 lease를 선택적으로 설정한다.

장치 권한을 위해 release 설치 과정은 운영 사용자 `e103`을 Linux `input` 그룹에
추가한다. 그룹 변경이 처음 적용된 뒤에는 서비스 재시작 또는 재로그인이 필요하다.
최초 번호 확인은 모터·시리얼에 접근하지 않는 아래 probe로 수행한다.

```bash
cd /opt/aiot/iot/current
PYTHONPATH=robot/roki-iot python3 robot/roki-iot/tools/gamepad_probe.py \
  --device /dev/input/js0
```

## 3. 맵핑 모드의 최소 조건과 안전 경계

맵핑에는 AI, 카메라, 순찰 route, Nav2 localization, 라인 센서를 요구하지 않는다.
`route.local.yaml`이 없어도 Robot runtime은 기동되고 `START_MAPPING`을 받을 수 있다.
이때 `START_PATROL`은 `PATROL_ROUTE_NOT_CONFIGURED`로 거절된다.

LiDAR 장애물 판정은 맵핑 주행을 자동 정지시키지 않는다. 벽과 물체에 접근해 지도를
그리는 작업 자체가 필요하기 때문이다. 대신 아래 안전장치는 그대로 유지한다.

- LB deadman 해제, B, 종료 조합, 게임패드 분리 시 STOP
- 0.2초 motion pulse를 유효한 deadman 상태에서만 갱신
- 스틱을 고정해도 LB가 눌린 동안 짧은 pulse만 반복 갱신
- ESP32 watchdog 및 유일한 시리얼 소유자
- 모터/encoder/odometry/hardware safety 오류 시 fail-closed
- LiDAR와 실제 SLAM Toolbox service가 준비되지 않으면 시작 거절
- 순찰과 맵핑의 동시 실행 금지

라인트레이싱을 사용하지 않으므로 line sensor 오류는 전체 runtime의 motion gate에서
제외한다. 모터·시리얼·배터리·odometry 안전 검사는 제외하지 않는다.

## 4. 현장 적용 전에 설정할 것

맵핑 시 `aiot-ros.service`는 SLAM Toolbox를 실행해야 한다.

```text
# /opt/aiot/secrets/ros.env
AIOT_ROS_MODE=mapping
```

LiDAR 위치 값과 alias도 기존 ROS preflight를 통과해야 한다. 실제 토큰은 Git에 넣지
않고 기존 `SET_TOKEN` 흐름 또는 `/var/lib/aiot/secrets/robot-service-token`을 사용한다.
게임패드 수신기는 Jetson에 직접 연결한다. EC2나 별도 runner를 경유하지 않는다.

완전히 새 지도를 다시 만들 때는 이전 SLAM graph를 이어 쓰지 않도록 맵핑 시작 전에
`aiot-ros.service`의 SLAM Toolbox를 새로 기동해야 한다. 지도 업로드가 Backend에서
완료된 이후의 patrol 전환만 `aiot-map-activate.path`가 root 권한으로 수행한다. Robot
프로세스 자체에는 systemd 권한을 주지 않는다.

## 5. 실물 승인 후 검증 순서

1. 모터 전원 없이 USB 수신기를 연결하고 `/dev/input/js0` 존재와 `e103` 읽기 권한을 확인한다.
2. axis/button 번호를 확인해 `robot.env` 기본값과 다르면 수정한다.
3. `AIOT_ROS_MODE=mapping`으로 LiDAR·RF2O·SLAM Toolbox를 시작하고 `/scan`, odom,
   `map -> odom -> base_link -> laser_frame` TF를 확인한다.
4. 바퀴를 띄운 상태에서 Frontend 지도 생성을 한 번 시작한다. ACK와 deadman/STOP,
   전후진 방향, 60/80/100도 조향을 확인한다. 스틱 고정 중 pulse가 갱신되고 LB 해제와
   수신기 분리 시 즉시 STOP하는지도 확인한다.
5. PWM 45로 빈 공간을 천천히 한 바퀴 수동 주행한다. 출발점으로 돌아와 loop closure와
   지도 겹침을 확인한다.
6. Back + Start 2초로 종료하고 로컬 map 파일, Backend 완료 응답, Frontend 지도 표시를
   같은 `mappingSessionId`로 확인한다.
7. `/var/lib/aiot/config/current-map.env`의 mapId/version/hash와
   `/var/lib/aiot/maps/active/`의 YAML·PGM, ROS/Robot 재기동 성공을 확인한다.
8. 지도 좌표와 실제 공간이 맞는지 확인한 뒤 Frontend에서 구역과 waypoint/route를
   확정한다. initial pose 실측값은 자동 생성하지 않는다.

## 6. 아직 자동화하지 않은 경계

- Backend에는 PNG만 업로드하므로 Jetson의 Nav2 원본 파일을 삭제하면 복구할 수 없다.
- Robot 프로세스가 지도 저장 뒤 종료되면 재기동 후 자동 업로드 재개는 아직 없다.
- 새 맵핑 시작을 위해 patrol에서 mapping으로 바꾸는 작업과 initial pose 실측은 운영자가
  현장에서 수행한다. 업로드 완료 뒤 mapping에서 patrol로 돌아오는 작업만 자동화했다.
- 현재 Frontend 좌표 변환이 회전된 map origin을 처리하지 않으므로 `originYaw != 0`인
  지도는 업로드하지 않고 오류로 남긴다.
- 게임패드 실제 axis/button 번호와 조향 방향은 수신기가 있을 때 최종 확정한다.

위 항목은 최초 현장 지도 1회 제작을 막지 않는다. 다중 재맵핑과 장애 복구까지 운영화할
때에는 pending-upload manifest와 SLAM session reset을 후속으로 추가한다.
