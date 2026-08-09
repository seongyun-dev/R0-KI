# RO-KI waypoint 현장 시연 인수인계

> **2026-08-03 상태:** 이 문서의 소프트웨어 통합 TODO는 완료됐다. 현재 운영
> 절차와 남은 실물 검증은 `integrated-runtime-operations.md`, 최신 Robot-AI
> 계약은 `ai-ros-contract-v1.md`를 따른다. 이 문서는 0.60 m 직선 시험과 실측
> 근거를 보존하는 기록이다.

> 소프트웨어·백엔드·AI·OTA를 이어서 완성하는 작업자는 먼저
> [`goal-mode-integration-handoff-2026-08-02.md`](goal-mode-integration-handoff-2026-08-02.md)를
> 읽는다. 이 문서는 실측 및 현장 waypoint 증거로 유지한다.

기준일: 2026-08-02
대상: IoT/Robot 개발자, Jetson 배포 담당자

## 1. 확정된 결정

- 라인트레이싱은 주행 제어에서 제외한다. 센서가 중앙선 `11011`을 읽은 뒤 차체가
  조향되기 전에 `11111`로 이탈하여 현재 장착 구조로는 안정적인 폐루프 주행이
  불가능했다. 센서와 관련 도구는 원시 진단용으로만 보존한다.
- 지도는 사람이 로봇을 수동 주행해 SLAM으로 만든다.
- 순찰은 저장된 지도와 Jetson 로컬 `route.local.yaml`의 waypoint 순서로 수행한다.
- 차체는 자동차형 전륜 조향이므로 제자리 회전 명령은 허용하지 않는다.
- 첫 통합 시연은 실제 지도 없이도 검증 가능한 0.60 m 직선 경로로 제한한다.

## 2. 실물 보정값과 현장 확인 결과

| 항목 | 확정값/결과 |
|---|---|
| 휠 지름 | 65 mm |
| 왼쪽 encoder | 평균 329 ticks/rev (3회: 327, 325, 335) |
| 오른쪽 encoder | 평균 328 ticks/rev (3회: 320, 335, 329) |
| 런타임 공통값 | 329 ticks/rev |
| 조향 | 60° 왼쪽, 80° 정면, 100° 오른쪽 |
| 저속 시험 PWM | 45 |
| ESP32 안정 경로 | `/dev/roki_esp32` |
| LiDAR 안정 경로 | `/dev/roki_lidar` |

ESP32와 LiDAR의 CP2102가 모두 factory serial `0001`을 보고하므로
`/dev/serial/by-id/...0001`은 사용할 수 없다. Jetson의 물리 USB path를 기준으로 만든
udev 별칭을 사용한다.

## 3. 완료된 구현

### 현장 도구

- ESP32 포트 탐색을 `/dev/roki_esp32` 우선 방식으로 통일했다.
- 운영 펌웨어 preflight와 모터·서보 시험 도구를 현재 JSON protocol에 맞췄다.
- 라인센서 수동 측정, replay, 제한된 line-follow 시험 도구를 추가했다.
- encoder 거리 기반 waypoint 현장 시험 도구를 추가했다.
- Jetson의 ESP32/LiDAR udev 별칭과 카메라 2대 식별 절차를 문서화했다.

### waypoint 내비게이션

- 지도 메타데이터와 route YAML loader/validator를 구현했다.
- `PASS`, `SCAN`, `DESTINATION` waypoint 상태기계를 구현했다.
- 자동차형 차체용 `cmd_vel -> speed/steering` 변환 계층을 구현했다.
- encoder 누적 거리로 직선 경로 pose를 계산하고 waypoint 진행을 판정한다.
- `DESTINATION_REACHED` 직후 다음 CONTROL 전송 전에 STOP을 재검사하도록 런타임을
  수정했다.
- 실제 route 파일이 없으면 고정 직진 fallback으로 출발하지 않고 fail-closed한다.

### MQTT 통합

- 기존 MQTT `START_PATROL`이 waypoint mission과 ESP32 주행을 시작하도록 연결했다.
- 목적지 도달 시 즉시 물리 정지하고 Robot 상태를 IDLE로 변경한다.
- 이후 백엔드 `STOP_PATROL`을 받으면 STOP을 재확인하고 기존 ACK 계약을 유지한다.
- 별도 진단 도구 `tools/waypoint_mqtt_demo.py`를 추가했다.
  - 기본값은 MQTT를 발행하지 않는 dry-run이다.
  - START 실발행에는 `--send --confirm STRAIGHT_ROUTE_CLEAR`가 모두 필요하다.
  - ACK는 commandId가 일치하는 응답만 받고 timeout/REJECTED/FAILED를 구분한다.

## 4. 완료된 실물 시험

다음 dummy map 경로를 실제 로봇에서 encoder-only pose로 주행했다.

```text
start                0.000 m
CHECKPOINT_20CM       0.166 m
SCAN_POINT_40CM       0.361 m
DESTINATION_60CM      0.564 m
STOP                  DESTINATION_REACHED
```

물리 결과는 정상이며 목적지에서 정지했다. 이 시험은 직접 실행한 현장 도구 기준이고,
MQTT를 통해 동일 경로를 출발하는 최종 시험은 아직 수행하지 않았다.

## 5. 코드 검증 결과

- Robot core 단위 테스트: 76개 통과
- roki-iot waypoint/MQTT/state 통합 테스트: 13개 통과
- MQTT payload 전용 테스트: 3개 통과
- Jetson 격리 스테이징 테스트와 Python compile 통과
- 실제 MQTT 발행 없이 실제 로봇 키의 command/ack topic 생성 확인

## 6. 아직 활성 Jetson에 설치하지 않은 이유

다른 작업자가 만들었던 pose/status 송신과 ROS TF/LiDAR health 연결은 이후
`goal-mode-integration-handoff-2026-08-02.md` 작성 시 waypoint 코드와 선별 병합해
GitLab 브랜치에 보존했다. 다만 Jetson 활성 경로에는 아직 설치하지 않았다.

현재 병합 후보는 다음 격리 경로에만 존재한다.

```text
/home/e103/waypoint-status-merge-stage-20260802-205644
```

이 스테이징은 이제 병합 출처 기록일 뿐이다. 활성 경로에 직접 설치하지 않고 GitLab의
검증된 병합 commit과 정식 OTA 절차를 사용한다.

## 7. 남은 필수 작업

> 2026-08-03 갱신: Gate A의 소프트웨어 항목은 모두 완료됐다. 아래 내용은 당시
> TODO의 근거를 보존한다. 현재 남은 작업은 Gate B 이후의 실물 검증뿐이다.

### Gate A — 상태 송신 병합본을 production entrypoint로 승격

1. pose/status store, ROS TF/LiDAR bridge와 waypoint 소스 병합은 GitLab에 보존됐다.
2. OTA의 `robot/scripts/run.sh`가 아직 정지 전용 entrypoint를 실행하므로 통합
   `run_integrated.py`를 production composition에 연결한다.
3. pose 좌표계가 다음 route와 같은 `map` frame인지 소프트웨어 fixture로 확인한다.

   ```text
   start       (1.0, 2.5)
   checkpoint  (1.2, 2.5)
   scan        (1.4, 2.5)
   destination (1.6, 2.5)
   ```

4. 비이동 통합 테스트를 다시 실행한 뒤 정식 OTA 릴리스로만 Jetson에 설치한다.

### Gate B — MQTT 직선 물리 시험

1. `/dev/roki_esp32` 점유가 없을 때 병합본을 설치한다.
2. `PATROL_DRIVE_SPEED_PWM=45`로 런타임을 실행한다.
3. MQTT START를 한 번 발행한다.
4. START ACK, 세 waypoint, 목적지 물리 정지, 최종 pose와 IDLE을 확인한다.
5. 백엔드 STOP을 발행해 STOP ACK `SUCCEEDED`를 확인한다.

정확한 명령과 안전 확인 순서는
[`waypoint-mqtt-field-runbook.md`](waypoint-mqtt-field-runbook.md)에 기록했다.

### Gate C — 실제 지도 주행

1. 수동 주행 SLAM 결과(`map.yaml`, image, pose graph)를 인계받는다.
2. localization과 `map -> odom -> base_link -> laser_frame` TF를 검증한다.
3. 자동차형 차체가 통과 가능한 waypoint를 `route.local.yaml`에 기록한다.
4. 한 waypoint부터 시작해 다중 waypoint와 DESTINATION까지 확대한다.

### Gate D — 시연 기능 완성

- LiDAR 전방 장애물 정지 및 제거 후 남은 경로 재개
- `SCAN_POINT`와 실제 AI 차량 탐지 연결
- 탐지 차량의 방향, LiDAR 거리와 robot pose를 이용한 map 좌표 계산
- 증거 이미지와 차량 확인 REST 전송
- 프론트 START → 백엔드 MQTT → 물리 순찰 → 목적지 종료 전체 검증

## 8. 배포 및 보안 주의사항

- 실제 `.env`, MQTT 비밀번호, Robot token은 커밋하지 않는다.
- `route.local.yaml`은 현장 지도 전용이므로 Git에서 제외한다.
- 움직임 도구는 명시적인 확인 문자열 없이는 실행하지 않는다.
- 상태 송신 코드와 waypoint 코드를 모두 포함한 병합본이 확정되기 전 OTA 대상으로
  승격하지 않는다.
- 기능 브랜치 push만으로 Jetson이 자동 갱신되지는 않는다. `iot/master` 기반 release
  tag와 OTA publish 절차가 별도로 필요하다.
