# Hanbakwi Robot runtime

Friday field-test checklist:
[`docs/friday-field-test-runbook-2026-08-04.md`](docs/friday-field-test-runbook-2026-08-04.md)

Backend ordered waypoint, 게임패드/encoder, 고정 지도, 차량 좌표와 중복 이벤트의
최종 실물 기록은
[`docs/friday-navigation-and-e2e-field-validation-2026-08-05.md`](docs/friday-navigation-and-e2e-field-validation-2026-08-05.md)를 따른다.

`robot/`은 Jetson에서 실행되는 IoT 운영 소스다. 운영 진입점은
`robot/scripts/run.sh`이며, 이 스크립트는 `roki-iot/run_integrated.py` 하나만
실행한다. 해당 프로세스만 ESP32 시리얼 포트를 소유한다.

## 현재 구성

- `roki/`: operating-json 시리얼, 안전 제어, odometry, waypoint/Nav2 연동
- `roki-iot/`: 백엔드 MQTT 명령·ACK·pose·status와 통합 composition root
- `src/aiot_robot/`: AI ROS 계약, readiness, 이벤트 outbox/REST 전달, OTA 잠금
- `config/ros/`: YDLIDAR, RF2O, SLAM Toolbox, Ackermann Nav2 운영 설정
- `hardware/`: 승인 후에만 실행하는 실물 진단·제한 주행 도구
- `scripts/`: 설치, 운영 실행, 비이동 smoke, 전체 테스트

운영 흐름은 `START_PATROL`에서 Backend navigation config/map version 검증 →
AI ENABLE → ESP32 시작 → waypoint 이동 →
pose/status 및 AI 이벤트 전달 → 로컬 DESTINATION 즉시 STOP → 백엔드
`STOP_PATROL` 재확인·ACK → IDLE이다. LiDAR 장애물, 오래된 LiDAR/AI 상태,
ESP32 안전 오류는 fail-closed로 정지시킨다.

위치 소스는 `map -> base_link` ROS TF를 우선한다. Nav2에 필요한 실측값이나
패키지가 없으면 `encoder_limited` 모드만 허용하며, 이 모드는 짧고 직선인 현장
검증 경로만 받는다. 기본 보정은 65 mm 바퀴, LEFT 329 / RIGHT 328 ticks/rev,
조향 60/80/100도, PWM 45다.

## 비이동 검증

다음 명령은 시리얼, MQTT, ROS 노드 및 모터를 열지 않는다.

```bash
./robot/scripts/test.sh
ROKI_ROUTE_FILE=robot/roki/maps/dummy_rectangle/route.short-straight.yaml \
  ./robot/scripts/smoke-test.sh pre-activate
```

운영 설정 예시는 `config/robot.env.example`에 있다. 실제 `.env`, MQTT 비밀번호,
서비스 토큰과 현장 `route.local.yaml`은 Git에 넣지 않는다.

자동 주행이 완성되기 전 프론트 START·STOP과 AI를 그대로 검증하는 임시 수동 시연은
[`docs/manual-patrol-ai-demo.md`](docs/manual-patrol-ai-demo.md)를 따른다. 수동 모드는
foreground에서 `--manual-keyboard`를 명시할 때만 활성화되며 운영 기본값을 바꾸지 않는다.

Frontend의 기존 지도 생성 버튼부터 게임패드 수동 주행, SLAM 저장, Backend 지도
업로드까지의 맵핑 흐름은
[`docs/manual-gamepad-mapping.md`](docs/manual-gamepad-mapping.md)를 따른다. 맵핑은
순찰 route·AI·카메라 없이 시작할 수 있지만 LiDAR, odometry, hardware safety,
SLAM Toolbox와 deadman 입력은 반드시 준비돼야 한다.

배포·진단·복구와 현장 검증 순서는
[`docs/integrated-runtime-operations.md`](docs/integrated-runtime-operations.md)를
따른다. 아직 실측하지 않은 값과 현장 합격 기준은
[`docs/field-calibration-and-live-gates.md`](docs/field-calibration-and-live-gates.md),
Robot-AI 메시지는
[`docs/ai-ros-contract-v1.md`](docs/ai-ros-contract-v1.md), ESP32 시리얼은
[`roki/docs/COMMUNICATION_CONTRACT.md`](roki/docs/COMMUNICATION_CONTRACT.md)가
기준이다. 2026-08-02 Goal 인수인계의 구현 결과는
[`docs/goal-mode-integration-handoff-2026-08-02.md`](docs/goal-mode-integration-handoff-2026-08-02.md)

2026-08-04 실제 지도 스냅샷, 단일 BRIO 설정, 차량 LiDAR 좌표와 Backend
불법주차 계약 대조 결과는
[`docs/mapping-parking-integration-status-2026-08-04.md`](docs/mapping-parking-integration-status-2026-08-04.md)에 정리했다.
맨 위 완료 갱신을 우선해서 읽는다.
