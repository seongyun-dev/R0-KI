# RO-KI 라인트레이싱 현장 통합 계획

> **Project**: S15P11E103 한바퀴
> **Version**: 0.1
> **Date**: 2026-08-02
> **Status**: Active
> **Baseline**: `iot/dev` `1fcb455`

## 1. 결정

순찰의 1차 주행 방식은 수동 SLAM 지도와 Nav2 waypoint가 아니라 검은 테이프 기반
5채널 라인트레이싱으로 변경한다. LiDAR는 전방 장애물 정지, 엔코더는 이동거리와
진행률, 체크포인트 간 상대 이동량에 사용한다. 지도·Nav2는 시연 필수 범위에서 빼고
후속 고도화로 유지한다.

```text
백엔드 START_PATROL
→ Jetson MQTT
→ ESP32 STOP/HELLO/ENCODER_ZERO
→ 라인 센서 원시값
→ Jetson LineFollower가 speed/steering 계산
→ 기존 RobotRuntime 한 곳만 Serial 소유
→ ESP32 모터·서보 제어
→ 엔코더 진행률 + LiDAR 장애물 정지
→ 목적지 마커 또는 체크포인트 조건
→ STOP + ACK + IDLE
```

## 2. 2026-08-02 Jetson 점검 결과

- Jetson: Ubuntu 22.04, L4T R36.4.7, ROS 2 Humble, Python 3.10.12.
- ESP32: CP2102 `/dev/ttyUSB0`, by-id 경로 정상, 점유 프로세스 없음.
- Jetson 실기 운영 펌웨어: 프로토콜 1, 버전 3.0.0, watchdog 400ms.
- GitLab 하드웨어 시험본 2.2.0과 실기본 3.0.0은 같은 프로토콜 1 범위에서
  검사 도구가 모두 허용한다.
- 라인 센서 GPIO: 16, 17, 18, 19, 23. 5개 raw 값은 100ms마다 발행됨.
- 라인 센서의 물리적 좌우 순서, 검은색 극성, 잡음은 아직 미확정.
- `CLP`, `NEAR`는 현재 펌웨어와 주행 계약에서 사용하지 않음.
- 엔코더: 좌 34/35, 우 36/39. 바퀴 1회전 tick과 전진 부호 미확정.
- 과거 실기 로그상 전진 시 좌측 음수·우측 양수일 가능성이 있어 반드시 재측정 필요.
- 조향 중앙 80도, 펌웨어 허용 범위 60~100도.
- LiDAR와 카메라는 점검 당시 미연결.
- YDLIDAR X4 Pro 드라이버와 설정, RF2O, `slam_toolbox` 설정은 존재함.
- 설치된 Nav2는 일부 패키지만 있으며 전체 Navigation2 실행 환경은 아님.
- `roki_ros2_ws`의 `roki_bridge` 노드 파일은 비어 있어 실제 통합 코드로 볼 수 없음.
- LiDAR 설정도 `/dev/ttyUSB0`를 사용하므로 두 USB 장치 연결 후 고정 별칭이 필수.
- `aiot-robot`, `roki-iot` 등의 systemd 자동 실행 서비스는 아직 없음.
- Jetson의 `roki`, `roki-iot`, `robot-hw-test`는 Git 저장소가 아닌 실기본임.
- GitLab 공통 파일은 실기본과 일치하지만 Jetson에만 있는 예전 보조 코드가 다수 존재함.
- 최신 `robot/roki`에는 단일 Serial 소유자인 `RobotRuntime`, 운영 JSON protocol,
  `MissionController`, `MotionController`, 안전 정지 골격이 이미 있음.
- `RobotRuntime`은 5채널 `lineValues`를 수신·기록하지만 라인 오차를 조향각으로
  바꾸는 LineFollower는 아직 없음.
- `MotionController`에는 좌우 encoder 전진 부호 정규화 설정이 없고 tick/회전 및
  직진 보정값도 `null`이므로, 현재 상태로 거리 계산을 확정하면 안 됨.
- `robot/roki-iot`의 예전 SerialReader와 `RobotRuntime`이 동시에 포트를 열면 안 되며,
  통합 실행은 기존 runtime adapter를 통해 한 프로세스만 Serial을 소유해야 함.

## 3. 현재 ESP32 펌웨어 주의사항

2026-08-02 최초 실기 확인 시 ESP32에는 운영 펌웨어가 아니라
`S1:1 S2:1 S3:1 S4:1 S5:1` 형식으로 출력하는 라인센서 확인용 펌웨어가
올라가 있다. 따라서 현재 상태에서는 라인센서 극성·채널 확인은 가능하지만,
MQTT 경유 제어, JSON handshake, 엔코더 텔레메트리는 사용할 수 없다.

- 현재 4MB 플래시는 운영 펌웨어 복구 전에 별도 백업한다.
- Jetson 홈의 라인센서 전용 펌웨어 소스는 찾지 못했으므로 플래시 백업을 보존한다.
- 백업 파일 `esp32-full-20260802-line-debug-before-operating.bin`의 SHA-256은
  `b986aec0baea87253b6bf8bfb1404e687ab0d14491846969ede01964db5fbdfa`다.
- `field_calibration.py line-session`은 두 출력 형식을 자동 판별한다.
- 백업 후 운영 펌웨어 3.0.0을 복구하고 라인·엔코더 측정을 진행한다.
- 라인센서 GPIO와 극성은 측정 결과를 운영 펌웨어에 반영한다.
- 라인센서 전용 펌웨어 상태에서 엔코더 명령은 실패 처리하며 구동하지 않는다.

## 4. 현장에서 한 번만 수행할 시험

### A. 무동작 시험 — Battery B 분리

1. `jetson_field_audit.sh`로 ESP32, LiDAR, 카메라 USB 속성을 기록한다.
2. 라인 센서를 바닥, 각 물리 센서 한 개, 중앙선, 넓은 도착 마커에 놓고 raw 값을 기록한다.
3. 좌우 바퀴를 각각 전진 방향으로 정확히 10회 손으로 돌린다.
4. 좌우 encoder 부호, tick/회전, 반대편 채널 간섭을 기록한다.
5. 멀티미터 실측 배터리 전압과 ESP32 `batteryVoltage`를 비교한다.
6. 로봇 기준 LiDAR와 카메라 장착 위치 `x/y/z/yaw`를 줄자로 측정한다.

### B. 바퀴 공중 시험 — Battery B 연결

1. ESP32 운영 preflight와 PCA9685 0x60을 확인한다.
2. 좌·우 전진 명령에서 두 encoder가 정규화 후 모두 양수가 되는지 확인한다.
3. PWM 45, 51, 60에서 1초간 회전량과 무부하 속도를 기록한다.
4. 조향 80, 75, 70, 85, 90의 실제 방향과 기계 간섭 여부를 기록한다.
5. watchdog 입력 중단 후 400ms 부근에서 모터와 서보 출력이 꺼지는지 확인한다.

### C. 바닥 저속 시험 — 통제된 직선과 곡선

1. PWM 45, 51, 60으로 각각 1m 직진하고 실제 거리·시간·좌우 tick을 기록한다.
2. 같은 시험을 3회 반복해 tick/m 중앙값과 좌우 오차를 구한다.
3. 조향 70, 75, 85, 90에서 짧은 원호를 주행해 유효 회전 방향과 반경을 기록한다.
4. 라인트레이싱은 중앙선 직진부터 시작하고, 완만한 좌·우 곡선으로 확장한다.
5. 선을 잃으면 탐색하지 않고 즉시 정지하는 것을 첫 안전 정책으로 한다.
6. 넓은 횡방향 테이프가 일반 선과 구분되면 목적지 마커 후보로 사용한다.

### D. LiDAR·카메라 시험

1. ESP32와 LiDAR를 동시에 연결하고 각각의 VID/PID/serial/path를 기록한다.
2. udev 별칭 `/dev/roki_esp32`, `/dev/roki_lidar`를 만든다.
3. X4 Pro `/scan` 주기, angle 0의 실제 정면, 최소·최대 유효거리를 기록한다.
4. 전방 중앙·좌·우에 장애물을 놓고 0.6m STOP, 0.8m CLEAR 후보를 검증한다.
5. 작은 물체와 한 점 노이즈에서 오정지가 없는지 확인한다.
6. Logitech 카메라의 by-id, 실제 `/dev/video*`, 720p MJPG FPS를 기록한다.
7. LiDAR 정면과 카메라 영상 중앙의 yaw 오프셋을 측정한다.

### E. 전원·통합 시험

1. 정지·직진·조향 중 배터리 전압 강하를 각각 기록한다.
2. Jetson, ESP32, LiDAR, 카메라 동시 연결 시 USB 재연결과 포트 변화를 확인한다.
3. MQTT START/STOP에서 단일 Serial 소유권과 STOP ACK를 확인한다.
4. 전원 재인가 시 모터가 정지 상태로 시작하는지 확인한다.
5. Wi-Fi 재연결 후 Jetson SSH와 MQTT가 복구되는지 확인한다.

## 5. 측정 결과로 확정할 설정

```yaml
line_following:
  channel_order: null
  black_value: null
  weights: [-2, -1, 0, 1, 2]
  lost_line_policy: STOP
  destination_pattern: null
  kp: null
  kd: null

odometry:
  left_tick_sign: null
  right_tick_sign: null
  encoder_ticks_per_revolution: null
  ticks_per_meter: null

drive:
  minimum_moving_pwm: null
  pwm_speed_table: null
  steering_center_deg: 80
  steering_left_limit_deg: null
  steering_right_limit_deg: null

lidar:
  device_alias: /dev/roki_lidar
  front_angle_offset_deg: null
  stop_distance_m: null
  clear_distance_m: null
```

실제 값은 로봇별 로컬 설정으로 저장하고 비밀값과 함께 Git에 커밋하지 않는다.
검토된 예시와 스키마만 GitLab에 반영한다.

## 6. 현장 시험 후 노트북에서 가능한 작업

- 라인 오차 계산과 PD 조향 알고리즘 구현·단위 테스트
- 속도별 조향 제한과 곡선 감속 구현
- encoder 부호 정규화, 거리·속도·진행률 계산
- 목적지 마커 또는 체크포인트 카운트 상태기계 구현
- LiDAR 장애물 STOP을 RobotRuntime 안전 우선순위에 연결
- MQTT START/STOP/ACK와 라인트레이싱 mission 통합
- 수집 로그 replay 기반 회귀 테스트
- udev 규칙, 실행 스크립트, systemd/OTA 서비스 작성
- 카메라·AI 이벤트와 순찰 상태 연결

## 7. 첫 두 명령

도구가 Jetson의 `~/robot-hw-test`에 배치된 뒤 사용자가 직접 실행한다.

```bash
cd ~/robot-hw-test
./.venv/bin/python field_calibration.py line-session
```

```bash
./.venv/bin/python field_calibration.py encoder-manual \
  --side left --revolutions 10

./.venv/bin/python field_calibration.py encoder-manual \
  --side right --revolutions 10
```

두 시험 모두 Battery B를 분리하고 바퀴를 바닥에서 띄운다. 모터·서보 명령은 보내지 않는다.

## 8. 완료 게이트

- 라인 5채널의 물리 순서와 black/floor 극성이 재현 가능하게 확정됨.
- 정상 테이프와 넓은 목적지 마커 패턴이 구분 가능한지 결론이 남음.
- 좌우 encoder 전진 부호와 tick/회전이 각 3회 측정에서 허용 편차 내에 있음.
- ESP32와 LiDAR가 동시에 연결돼도 서로 잘못 선택되지 않음.
- LiDAR 정면과 장애물 STOP/CLEAR 거리가 실물에서 검증됨.
- 카메라 장치 경로와 AI 입력 조건이 고정됨.
- 배터리 전압 보정과 저전압 기준을 결정할 자료가 남음.
- 모든 raw 로그를 노트북으로 가져와 하드웨어 없이 replay할 수 있음.
