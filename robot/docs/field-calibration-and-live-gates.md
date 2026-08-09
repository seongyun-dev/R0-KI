# Robot 현장 실측·지도·실주행 게이트

기준일: 2026-08-03
목적: 소프트웨어 준비 이후 현장에서만 확정할 수 있는 값을 추측 없이 채우고,
무구동 확인에서 전체 순찰까지 안전하게 확대한다.

## 1. 현재 확정된 값

| 항목 | 값 |
|---|---|
| 바퀴 지름 | 65 mm |
| 왼쪽 encoder | 329 ticks/rev |
| 오른쪽 encoder | 328 ticks/rev |
| 서보 명령 | 왼쪽 60 / 중앙 80 / 오른쪽 100 |
| 최대 운영 PWM | 45 |
| Camera A | Web Camera, `/dev/roki_camera_left` |
| Camera B | Logitech Brio 100, `/dev/roki_camera_right` |
| 카메라 형식 | 640x480, MJPG, 30 FPS, batch 2 |
| YOLO 입력 | 2x3x416x416 FP16 |

## 2. 반드시 실측할 값

다음 값은 `/opt/aiot/secrets/ros.env`에 기록한다. Git이나 Mattermost에는 값을
복사하지 않는다.

### 휠베이스와 조향각

- `ROKI_WHEELBASE_M`: 앞·뒤 차축 중심 사이 거리
- `ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG`: 서보 명령 60과 100에서 바퀴가 실제로
  꺾인 각도의 절댓값 중 더 작은 값

바퀴 각도는 서보 혼 각도가 아니라 바닥을 향한 실제 road-wheel 각도다. 좌우 값이
크게 다르면 작은 값을 사용하고, 기구 정렬을 먼저 수정한다. Nav2 최소 회전 반경은
`wheelbase / tan(maximum road-wheel angle)`으로 자동 계산된다.

### Robot 외곽과 LiDAR TF

- `ROKI_ROBOT_RADIUS_M`: 차량 중심에서 범퍼·바퀴·카메라 지지대까지의 최대 수평
  거리보다 여유 있게 잡은 원형 안전 반경
- `ROKI_LIDAR_X_M`, `ROKI_LIDAR_Y_M`, `ROKI_LIDAR_Z_M`: `base_link` 중심에서
  LiDAR 스캔 중심까지의 변위
- `ROKI_LIDAR_YAW_RAD`: Robot 정면 대비 LiDAR 0도 방향

값을 채우기 전에는 `ros-preflight.sh`가 patrol 모드를 실패시킨다. 빈 값을 0으로
대체하지 않는다.

## 3. 장치 게이트

```bash
readlink -f /dev/roki_camera_left
readlink -f /dev/roki_camera_right
readlink -f /dev/roki_esp32
readlink -f /dev/roki_lidar
```

카메라는 고유 serial 기반이므로 USB 포트를 바꿔도 별칭이 유지된다. 두 CP2102
직렬 장치는 serial이 모두 `0001`이므로 USB topology 기반이다. ESP32와 LiDAR
케이블·포트를 라벨링하고 바꾸지 않는다.

## 4. RF2O 합격 기준

LiDAR만 연결하고 모터 전원은 분리한 상태에서 검증한다.

```bash
sudo systemctl start aiot-ros.service
ros2 topic hz /scan
ros2 topic hz /odom
ros2 run tf2_ros tf2_echo odom base_link
```

- `/scan`과 `/odom`이 5분간 끊기지 않는다.
- TF가 `odom -> base_link -> laser_frame`으로 연결된다.
- 정지 2분 동안 translation drift 0.05 m, yaw drift 2도 이내를 목표로 한다.
- 손으로 천천히 이동했다가 되돌렸을 때 방향과 좌표 부호가 맞는다.

RF2O가 이 게이트를 통과하지 못하면 별도 시리얼 프로세스를 만들지 않는다. 기존
RobotRuntime encoder callback에서 `/odom`과 `odom -> base_link`를 발행하는
fallback을 구현한다.

## 5. 지도 제작

1. `AIOT_ROS_MODE=mapping`으로 설정한다.
2. 주변의 움직이는 사람과 임시 장애물을 최소화한다.
3. 고정 시작점을 바닥에 표시하고 Robot 방향도 표시한다.
4. PWM 45 이하로 외곽부터 천천히 수동 주행한다.
5. 같은 벽을 두 번 지날 때 겹침과 loop closure를 확인한다.
6. 원점으로 돌아와 map을 저장한다.

```bash
ros2 run nav2_map_server map_saver_cli \
  -f /var/lib/aiot/config/patrol-map
```

생성된 YAML과 이미지의 소유권을 `aiot:aiot`, mode를 0660으로 맞춘다. map과 실제
`route.local.yaml`은 OTA archive나 Git에 넣지 않는다.

## 6. Nav2 단계별 게이트

1. 모터 전원 없음: map, `/scan`, `/odom`, TF, AMCL, action server만 확인
2. 바퀴 들림: 한 개 goal의 `/cmd_vel`과 60~100 조향 범위를 확인
3. 직선 0.7 m: STOP과 방향 확인
4. 완만한 단일 회전: 계산한 최소 회전 반경 확인
5. 짧은 세 waypoint: CHECKPOINT, SCAN, DESTINATION 확인
6. 전체 route: 장애물 정지·1초 clear·재개와 최종 STOP 확인

Ackermann Robot은 제자리 회전할 수 없다. `linear.x=0`인데 `angular.z!=0`인 명령은
기존 adapter가 정지로 변환해야 하며 이를 우회해서는 안 된다.

## 7. MQTT·백엔드 게이트

비밀값을 화면에 출력하지 않고 root-only env를 현재 셸에만 로드한다.

```bash
sudo bash -c '
  set -a
  source /opt/aiot/secrets/robot.env
  set +a
  exec /opt/aiot/iot/current/robot/scripts/mqtt-e2e-check.sh
'
```

실제 명령을 30초간 관찰할 때도 payload나 token 값은 출력되지 않는다.

```bash
sudo bash -c '
  set -a
  source /opt/aiot/secrets/robot.env
  set +a
  exec /opt/aiot/iot/current/robot/scripts/mqtt-e2e-check.sh \
    --observe-seconds 30
'
```

순서는 TLS 인증 → IDLE status/pose → retained SET_TOKEN metadata → 만료·중복 명령
→ wheels-up START/STOP → 실제 한 바퀴다. 합격 기준은 token file mode 0600, 같은
commandId의 동일 ACK, DESTINATION 물리 STOP, STOP ACK `SUCCEEDED`, 최종 IDLE이다.

## 8. 최종 완료 증거

- 저장한 map과 검토된 route 파일
- `/scan`, `/odom`, TF, AMCL 및 Nav2 lifecycle 상태
- 좌우 카메라 첫 inference와 AI READY
- 한 patrolId의 START, pose/status, AI 이벤트, DESTINATION, STOP ACK, IDLE
- 카메라·LiDAR·MQTT 장애 복구
- 재부팅 자동 시작
- 순찰 중 OTA 보류와 실패 릴리스 rollback

## 9. 2026-08-03 비구동 준비 결과

- Jetson에 전체 Navigation2와 `nav2_bringup`을 설치했다.
- `/dev/roki_camera_left -> /dev/video0`,
  `/dev/roki_camera_right -> /dev/video2` 별칭을 적용했다.
- 두 카메라, ROS 2, TensorRT 10.3, batch-2 YOLO engine과 번호판 engine의
  preflight가 통과했다. AI 모델 저장소는 수정하지 않았다.
- Robot/Roki/Roki-IoT unittest 183건, Jetson readiness, OTA activation·rollback,
  manifest 검증이 Linux 임시 릴리스에서 통과했다.
- `aiot-ai`, `aiot-ros`, `aiot-robot` unit은 설치했지만 모두 disabled/inactive다.
  `ros.env`도 생성하지 않아 부팅이나 수동 오조작으로 ROS가 시작되지 않는다.
- MQTT 8883 TLS 인증서 검증은 통과했다. Jetson의 root-only `robot.env`와 service
  token 파일이 아직 없으므로 broker 로그인, retained `SET_TOKEN`, START/STOP E2E는
  현장 게이트로 남겼다.
