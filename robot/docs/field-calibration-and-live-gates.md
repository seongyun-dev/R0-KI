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
| 서보 명령 | 왼쪽 40 / 중앙 80 / 오른쪽 120 (2026-08-06 재교정, 조향각 ±20°) |
| 서보 방향 | 낮은 각도 = 왼쪽 (2026-08-07 실물 확인) |
| 최대 운영 PWM | 45 |
| PWM 45 실주행 속도 | **0.094 m/s** (외삽) |
| PWM 50 실주행 속도 | **0.114 m/s** (실측) |
| 구동 ticks/m | **1470** (실측) / 1611 (지름·ticks/rev 이론값, 9% 일치) |
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

## 10. 2026-08-07 구동 속도 실측과 PWM 스팬 문제

### 측정 방법
`aiot-robot`을 정지시켜 시리얼을 비우고, 운영 펌웨어 프로토콜로 직접
`{"type":"control","speed":-50,"steering":80}`을 150 ms 주기로 2.02초 전송.
펌웨어가 알려주는 `commandTimeoutMs`는 400이므로 그보다 빠르게 갱신해야
`stopActuators()`가 서보·모터를 끊지 않는다. `hello` 선행 없이는
`protocolSessionActive`가 false여서 모든 control이 `INVALID_COMMAND`로 래치된다.

### 서로 독립적인 네 측정이 일치
| 측정 | 값 | 줄자 대비 |
|---|---|---|
| 줄자 | 0.230 m | 기준 |
| TF `map→base_link` | 0.236 m | +2.6% |
| LiDAR 정면 섹터 중앙값 | 0.216 m | −6.1% |
| 인코더 | 338 ticks → 1470 ticks/m | 이론값 1611의 91% |

위치추정 스케일은 정확하다. 라이다 기준값을 쓸 때는 **yaw 변화가 작은 구간에서만**
유효하다. yaw가 8.2° 변한 주행에서 같은 방법을 쓰면 1.65배까지 틀린다.

### 발견된 문제: PWM 스팬 0
`robot.env`가 `ROKI_MAXIMUM_DRIVE_PWM=45`, `PATROL_DRIVE_SPEED_PWM=45`이므로
`cmd_vel_adapter`의

    pwm_span = maximum_drive_pwm - minimum_drive_pwm   # 45 - 45 = 0
    pwm = minimum_drive_pwm + round(speed_ratio * pwm_span)

는 **어떤 요구 속도에도 항상 PWM 45**를 낸다. Nav2의 속도 제어가 섀시에
전달되지 않는다. RegulatedPurePursuit이 곡률이 커질 때 감속해서 코너를 도는
동작이 물리적으로 불가능하므로, 컨트롤러는 감속 대신 조향만 계속 키운다.
`ROKI_MAXIMUM_LINEAR_SPEED_MPS=0.07`도 실측 0.094 m/s보다 34% 낮아,
Nav2는 자기가 아는 최고속도보다 빠른 로봇을 제어하게 된다.

### PWM 하한 실측 (2026-08-07)
매 단계를 **정지 상태에서 출발**시켜 1초간 주행. Nav2에 필요한 것은 정속 유지가
아니라 출발 토크이므로 반드시 정지에서 시작한다.

| PWM | 속도 | 좌/우 ticks | 좌우 편차 | 판정 |
|---|---|---|---|---|
| 44 | 0.074 m/s | +116 / +119 | 2.6% | 주행 |
| 42 | 0.059 m/s | +89 / +98 | 10% | 주행 |
| 40 | 0.039 m/s | +57 / +66 | 16% | 주행 |
| 38 | 0.024 m/s | +28 / +48 | **58%** | 주행 |
| 36 | 0 | +0 / +0 | - | **stall** |
| 34, 32, 30 | 0 | +0 / +0 | - | **stall** |

36 이하는 인코더와 LiDAR 정면 거리(3초 주행) **두 계측기가 독립적으로** 무동작을
확인했다 (이동량 9 mm 이하, 노이즈 수준). 인코더 미검출이 아니라 실제 stall이다.

핵심은 **PWM이 내려갈수록 두 후륜 모터의 편차가 급격히 커진다**는 점이다. 38에서
58%면 조향을 중앙에 두어도 크게 휘므로, 컨트롤러가 감속할 때마다 경로를 벗어난다.
따라서 실사용 하한은 stall 하한(38)이 아니라 **편차가 10% 이내인 41**로 잡는다.

### 적용된 값
    PATROL_DRIVE_SPEED_PWM=41            # minimum_drive_pwm, 0.05 m/s
    ROKI_MAXIMUM_DRIVE_PWM=45            # 최고속도 유지 (0.094 m/s)
    ROKI_MAXIMUM_LINEAR_SPEED_MPS=0.094  # PWM 45의 실측값
    ROKI_NAV2_DESIRED_LINEAR_SPEED_MPS=0.075   # 대역 중간, 감속 여유 확보

이제 speed_ratio가 PWM 41~45의 4칸에 펼쳐지므로 RegulatedPurePursuit의 곡률 감속이
실제로 섀시에 전달된다. mapping 모드는 `regulated_linear_scaling_min_speed=0.05`
(PWM 41)로 감속 하한을 실측 하한에 맞춘다.

### 후속 확인 필요
- 저PWM 좌우 편차가 모터 특성인지 인코더 스케일 차이인지 미확정. PWM 44에서 2.6%,
  38에서 58%로 벌어지는 양상은 모터 정지마찰 차이 쪽을 시사한다.
- `ros2 node list`에 `/rf2o_laser_odometry`가 2회 등록된다. 고아 프로세스를 전부
  정리한 뒤 재시작해도 재현되므로 구조적 문제다. `/odom` 퍼블리셔는 1개이고 TF도
  정상이라 현재 블로커는 아니다.
- `hw_test.py`는 `roki_safe_test` 펌웨어 핸드셰이크를 요구하므로 운영 펌웨어
  (`roki_operating`)에서는 어떤 프로브도 실행되지 않는다. 하드웨어 진단 경로가 없다.

## 11. 2026-08-07 LiDAR 좌우 반사 (근본 원인)

### 증상
자율 매핑에서 로봇이 매번 오른쪽으로 끝까지 꺾고 멈췄다. Nav2 파라미터
(lookahead, 감속 하한, REEDS_SHEPP + 후진, PWM 스팬)를 모두 바로잡은 뒤에도 동일했다.

### 원인
YDLidar가 방위를 자기 0점 기준으로 **반사**해 보고하고 있었다
(`ydlidar.yaml`의 `inverted: false`). TF는 회전이므로 반사를 되돌릴 수 없다.

로봇을 구석에 몰아넣은 상태에서 확인했다. 스캔은 근접 벽을 좌측 0.32 m,
우측 여유 0.75 m로 보고했으나 **실제 근접 벽은 우측**이었다.

두 관측으로 변환식을 특정했다.
- 후진 실측: 보고 방위 −90°가 물리적 정면 → `B(−90) = 0`
- 구석 확인: 보고 방위 0°가 물리적 우측 → `B(0) = −90`
- 두 점을 지나는 선형 변환 → **`B(θ) = −θ − 90`**. 코드는 `B = θ + 90`을 썼다.
  부호와 오프셋이 모두 반대다.

### 수정
| 항목 | 이전 | 이후 |
|---|---|---|
| `ydlidar.yaml` `inverted` | false | **true** |
| `ROKI_LIDAR_YAW_RAD` | +1.57079632679 | **−1.57079632679** |
| `AIOT_LIDAR_FORWARD_CENTER_ANGLE_DEG` | −90 | **90** |
| `AIOT_VEHICLE_LIDAR_CENTER_ANGLE_DEG` | −90 | **90** |

반사를 드라이버에서 되돌리면 `B(θ) = θ − 90`이 되므로 TF yaw가 −pi/2여야 하고,
인터락 중심각(원시 스캔 방위 기준)은 +90이 된다.

### 검증
| 방향 | 수정 전 | 수정 후 |
|---|---|---|
| 좌측 최소 | 0.316 m | 0.752 m |
| 우측 최소 | 0.749 m | **0.318 m** (실제와 일치) |

### 이것이 설명하는 것
- Nav2가 좌회전을 명령하면 로봇이 우회전 → 오차 증가 → 조향 증대 → 락까지 꺾임.
  컨트롤러 튜닝으로는 원리적으로 교정 불가.
- 후진(REEDS_SHEPP)도 거울 세계에서 계획되어 무의미.
- 지도가 직사각형으로 나오지 않던 현상.
- 장애물 인터락이 반대쪽 섹터를 감시.
- rf2o가 거울 세계 안에서 자기일관적이어서 정상으로 보였다. 줄자 대비 2.6%로
  정확했던 것도 이 때문이며, 반사는 오도메트리 검증으로는 걸러지지 않는다.

### 왜 늦게 발견됐는가
후진 실측은 **전/후 축만** 검증한다. `inverted`는 좌우를 뒤집으므로 그 테스트를
통과한다. 정면 개방 확인도 ±90° 양쪽이 모두 열려 있으면 구분되지 않는다.
좌우를 운영자에게 직접 확인한 것이 결정적이었다.

### 후속 필수 작업
- **기존 지도 전부 무효.** `patrol_maps` map_id=1(단지 2, version 13)은 거울상이며
  재작성이 필요하다. 그 지도 위 웨이포인트도 거울 좌표라 무효.
- 지도 재작성 전에는 순찰 검증을 신뢰할 수 없다.
