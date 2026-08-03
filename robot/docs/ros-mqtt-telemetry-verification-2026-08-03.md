# ROS → MQTT telemetry 현장 검증 (2026-08-03)

## 검증 결과

- Jetson: `e103@192.168.0.13`
- 운영 로봇 키: `ROKI-01`
- ESP32 시리얼을 열지 않는 `run_integrated.py --pose-only`로 검증했다.
- `map -> base_link`의 실제 TF를 사용했으며 시작 좌표를 임의 고정하지 않았다.
- MQTT 구독에서 다음 실제 pose를 연속 수신했다.

```text
x=0.005,  y=-0.068, heading=91.0
x=0.000,  y=-0.071, heading=90.0
x=-0.009, y=-0.058, heading=90.6
```

- payload의 `robotKey=ROKI-01`, `schemaVersion=1`을 확인했다.
- status는 `state=IDLE`, `camera=NORMAL`, `lidar=NORMAL`로 갱신됐다.
- MQTT 발행 직후 운영 백엔드 `GET /api/robots/16/location`에서도
  `x=0.003`, `y=-0.061`, `heading=90.1`, 갱신 시각 `20:10:35`를 확인했다.
  따라서 MQTT consumer와 프론트 위치 조회 데이터까지 반영되는 경로가 확인됐다.
- 비구동 검증 종료 후 Robot 서비스를 정지했기 때문에 백엔드의 최종 로봇 상태는
  `ERROR`다. 좌표 반영 실패가 아니라 ESP32 telemetry가 없는 의도된 결과다.
- 검증 중 START/CONTROL 및 모터 명령은 전송하지 않았다.

## 확인된 원인과 반영 사항

1. `aiot-robot.service`가 `aiot`, ROS/AI 서비스가 `e103` 계정으로 실행되면
   `ROS_LOCALHOST_ONLY=1`의 Fast DDS 그래프가 계정별로 분리되어 Robot 프로세스가
   `map -> base_link`, `/scan`, `/ai/status`를 받지 못했다.
2. 세 프로세스를 같은 `e103` 계정에서 실행한 비구동 검증에서는 pose와 AI/LiDAR
   상태가 모두 MQTT까지 전달됐다. Robot 서비스 계정을 `e103`으로 통일한다.
3. RF2O 실행 노드명이 YAML 최상위 키와 달라 파라미터가 적용되지 않았다.
   실행 시 노드명을 `rf2o_laser_odometry`로 명시한다.
4. YDLIDAR X4-Pro는 현장 검증값인 고정 해상도, DTR 비활성, 10 Hz,
   0.1~12 m 범위를 사용한다. 해당 값으로 `/scan` 약 11.8 Hz를 확인했다.
5. 배터리 ADC 미세 변동마다 status가 연속 발행되던 문제를 막기 위해 status는
   설정 주기(현재 5초) 또는 명시적 최종 telemetry 요청 때만 발행한다.

## 다음 배포/실측 게이트

- 이 변경을 다른 작업자의 수동 주행 변경과 병합한 뒤 CI를 통과시킨다.
- 새 OTA 릴리스 배포 후 `aiot-robot.service`를 시작하기 전에 ESP32 프로토콜
  호환 여부를 확인한다.
- 현재 Jetson의 `aiot-robot.service`는 다른 작업자의 시리얼 사용을 위해
  `inactive`로 두었고 `/dev/roki_esp32`는 점유되지 않았다.
- 서비스 시작 후 pose 1초, status 5초 주기와 `camera/lidar=NORMAL`을 다시 확인한다.
