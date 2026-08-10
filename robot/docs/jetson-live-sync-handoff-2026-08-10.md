# Jetson 현장 런타임 동기화 인수인계 (2026-08-10)

## 기준과 목적

- 확인 장비: `e103-desktop` (`192.168.30.86`, DHCP로 변경 가능)
- 회수 기준: `/opt/aiot/iot/current/robot`
- 현재 링크: `/opt/aiot/iot/releases/manual-vehicle-zone-20260810-024041`
- 현재 `VERSION`: `manual-0cd8db3`
- 기준 Git 브랜치: `iot/chore/jetson-direct-sync-20260810`
- 기준 선행 브랜치: `iot/chore/jetson-direct-sync-20260809` (`57720cf`)

현장 링크 안의 `manifest.json`은 과거 `iot-v0.1.10`/`87f07c6b`를 가리키지만,
이후 파일이 Jetson에서 직접 여러 번 수정되었다. 따라서 manifest나 VERSION이 아니라
실제 `current/robot` 파일을 원본으로 삼아 회수했다.

이 브랜치는 GitLab에서 후속 개발과 리뷰가 가능하도록 현장 코드를 보존하는 목적이다.
Jetson의 활성 링크, 서비스, ESP32, 모터에는 적용하지 않았다.

## 회수한 동작

1. 순찰
   - `NavigateThroughPoses`와 연속 구간의 접선 yaw를 사용하는 고정 경로 순찰
   - `PatrolGridBased`/`patrol_goal_checker` 전용 BT
   - 첫 웨이포인트를 기준으로 `/initialpose` 재위치 추정 후 실제 `/pose` 확인
   - 포즈그래프 적재 중 같은 경로이면 불필요한 재적재 방지
2. 매핑
   - SLAM reset 이후 새 scan/map/transform의 신선도 판정
   - 매핑 종료 시 현재 map pose를 다음 localization 인계값으로 보존
   - 맵 저장 준비 확인의 짧은 DDS 재탐색과 제한 시간 처리
3. ESP32/하드웨어
   - pyserial의 1바이트 `readline()` 병목을 피하는 벌크 RX 버퍼
   - 최초 실제 hardware status 전에는 기본 `DISCONNECTED` MQTT status를 발행하지 않음
   - LiDAR scan 상태, 전방 거리와 차량 거리 샘플을 분리해 관리
4. AI/이벤트
   - bbox, 카메라, track context 유지
   - 차량 탐지 위치를 LiDAR 거리와 로봇 pose로 계산하고 구역 포함 여부 확인
   - 응급 탐지 시 순찰을 `AI_EMERGENCY`로 일시정지
   - Backend의 `RESUME_PATROL` 명령이 같은 patrolId의 응급 정지만 해제
5. 영상
   - AI MJPEG `8090`
   - 매핑 MJPEG `8091`
   - EC2 역방향 터널을 각각 별도 systemd 서비스로 관리

## 현장 측정값과 운영 기본값

아래 값은 비밀값이 아니며 `ros.env.example`/`robot.env.example`에 반영했다.
실제 `ros.env`가 `robot.env`보다 나중에 로드되므로 중복 키는 반드시 같은 값이어야 한다.

| 항목 | 값 |
| --- | --- |
| wheelbase | `0.124 m` |
| 최대 앞바퀴 조향각 | `8.6 deg` |
| LiDAR 위치 | `(0.0, 0.0, 0.337 m)` |
| LiDAR yaw | `-1.57079632679 rad` |
| raw scan의 로봇 전방 중심 | `+90 deg` |
| Nav2 목표 속도 | `0.075 m/s` |
| cmd_vel 변환 최대 속도 | `0.094 m/s` |
| 최대 구동 PWM | `51` |
| 순찰 action | `/navigate_through_poses` |
| 순찰 BT | `nav2_fixed_path_through_poses.xml` |
| 카메라 입력 | `640x480`, `MJPG`, `30 FPS`, 단일 카메라 |
| AI MJPEG | `8090`, 관제 최대 `5 FPS` |
| 매핑 MJPEG | `8091` |

지도 ID/version/hash, route, initial pose는 현장 상태이므로 Git에 넣지 않는다.
활성 값은 `/var/lib/aiot/config/current-map.env`와 `/var/lib/aiot/maps`에 남는다.

## systemd 상태

회수 시점 상태:

| Unit | active | enabled |
| --- | --- | --- |
| `aiot-robot.service` | yes | yes |
| `aiot-ros.service` | yes | yes |
| `aiot-ai.service` | yes | yes |
| `aiot-mjpeg-tunnel.service` | yes | yes |
| `aiot-mapping-mjpeg-tunnel.service` | yes | yes |
| `aiot-update.service` | no | no |
| `aiot-update.timer` | no | no |

현장 drop-in도 저장소에 재현 가능한 파일로 추가했다.

- Robot/ROS: `Restart=always`, 5초 후 복구, 60초 안 6회 start limit
- Robot: `AIOT_EMERGENCY_STOP_ENABLED=true`
- Robot/ROS: `20-current-map.conf`로 활성 지도 환경을 마지막에 로드
- updater: 현장에서는 `99-ota-disabled.conf`가 `/opt/aiot/OTA-UPDATES-ENABLED`
  marker가 없으면 실행을 막는다. 저장소의 `aiot-ota-disabled.conf`는 선택 설치 파일이며
  일반 installer가 자동 설치하지 않는다.
- journald: persistent, 총 `400M`, 파일당 `50M`, 최대 `2week`

`aiot-ai.service` 현장 본체는 60초/3회 start limit과 5초 restart를 사용하지만 저장소
본체에는 카메라 후결합을 위한 무제한 재시도 개선이 이미 있다. 이 더 나은 저장소 설정은
현장 구버전으로 되돌리지 않았다.

## Git/OTA에 넣지 않은 것

- `/opt/aiot/secrets/*.env`, MQTT/Backend/SSH 인증정보
- `/home/e103/yolo-pipeline`, `.pt`, `.onnx`, TensorRT `.engine`
- `/var/lib/aiot/maps`, active map, posegraph, route, command cache, outbox, evidence
- `.venv`, `__pycache__`, 로그
- Jetson에 남아 있던 `*.bak*` 현장 백업 파일

AI 저장소와 모델은 IoT OTA의 소유 범위가 아니다. 이 패키지는 `robot/`만 포함한다.

## 검증

Jetson의 실행 venv를 사용하되 별도 `/tmp/aiot-gitlab-sync-test.*`에 브랜치 코드를
풀어 전체 테스트를 실행했다. 실제 serial/MQTT/모터는 열지 않는 mock/unit test이다.

- 상위 Robot/AI 계약: 128개 통과
- RO-KI 하드웨어/주행: 189개 통과
- IoT 통합/MQTT/SLAM: 195개 통과
- 합계: 512개 통과

현장 벌크 RX 변경 때문에 낡아 있던 FakeSerial 테스트와, 최초 hardware status 게이트의
legacy store 경로를 브랜치에서 보완한 후 검증했다.

## 후속 작업 절차

1. 이 브랜치의 MR을 `iot/master`에 병합한다.
2. 병합 커밋에서 정식 `iot-vX.Y.Z` 태그를 만든다.
3. `iot_package`가 만든 archive와 manifest/checksum을 검토한다.
4. 현재 Jetson 직접 수정본이 기준인 동안 `iot_publish`와 stable manifest 갱신은 실행하지 않는다.
5. 나중에 배포할 때는 먼저 Jetson live tree와 태그 tree를 다시 비교하고 별도 승인을 받는다.

정식 CI는 태그 커밋이 `iot/master`에 포함되지 않으면 패키징을 거절한다. 따라서 이
브랜치만 태그해 규칙을 우회하지 않는다. 브랜치 단계에서는 동일 스크립트로 OTA 후보
archive와 manifest/checksum을 만들 수 있다.
