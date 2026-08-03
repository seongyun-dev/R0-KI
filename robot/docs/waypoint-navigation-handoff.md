# Waypoint 주행 전환 인계

## 확정 결정

- 지도 생성: 사람이 수동 주행하며 SLAM 수행
- 순찰: 저장된 `map`에서 Jetson 로컬 waypoint 순서대로 주행
- 구동: Nav2의 `cmd_vel`을 자동차형 차체의 속도·서보 각도로 변환해 ESP32에 전달
- 라인센서: 주행 제어에서 제외하고 상태 진단값만 보존
- 장애물: LiDAR 전방 감지 시 정지, 안전 상태가 지속되면 남은 waypoint 재개
- 종료: `DESTINATION` 허용 반경 진입 후 정지 및 백엔드 완료 흐름 실행

확정된 실측값은 휠 지름 `65 mm`, 바퀴 `329 ticks/rev`, 서보
`60도=왼쪽, 80도=정면, 100도=오른쪽`이다.

## 2026-08-02 남은 작업 재계획

| 순서 | 작업 | 현재 상태 | ESP32 필요 | 오늘 완료 기준 |
|---|---|---|---|---|
| 1 | 수동 SLAM 지도 생성·저장 | 다른 작업자 진행 중 | 사용 중 | `map.yaml`, 이미지, pose graph 확보 |
| 2 | 지도·route 파일 검증기 | 구현·단위 테스트 완료 | 불필요 | 잘못된 경로·좌표·누락 파일을 실행 전에 거부 |
| 3 | waypoint loader와 mission 상태기계 | 구현·단위 테스트 완료 | 불필요 | `PASS/SCAN/DESTINATION` 순서 및 완료 단위 테스트 |
| 4 | `cmd_vel -> speed/steering` 자동차형 변환기 | 순수 변환·fake transport 완료 | 불필요 | 정지·직진·곡선·제자리회전 거부 검증 완료 |
| 5 | ROS 2 TF·odometry·Nav2 설정/launch | 저장소 기준 미구현 | 불필요 | launch/config 생성 및 정적 검증 |
| 6 | MQTT START/STOP과 waypoint mission 연결 | fake runtime 통합 완료 | 불필요 | START, STOP, DESTINATION 정지·IDLE 검증 완료 |
| 7 | 저장 지도 재로딩·localization | 지도 완료 후 | ESP32 불필요 | 정지 로봇 pose가 지도에서 안정적으로 유지 |
| 8 | waypoint 1개 실주행 | 대기 | 필요 | 저속으로 1개 목표 도착 후 정지 |
| 9 | 다중 waypoint와 목적지 종료 | 대기 | 필요 | 2~3개 경유 후 DESTINATION 정지·완료 |
| 10 | LiDAR 장애물 정지·재개 | obstacle guard 골격 존재 | 최종 검증 필요 | 장애물 정지 후 같은 mission 재개 |
| 11 | pose/status MQTT와 프론트 표시 | 계약·publisher 골격 존재 | 최종 검증 필요 | 실제 pose 및 완료 상태 표시 |

### ESP32를 다른 작업자가 사용하는 동안 바로 구현 가능한 묶음

다음은 노트북에서 Serial, Jetson 장치, 실제 ROS topic 없이 개발·테스트할 수 있다.

1. `route.yaml` 스키마, loader, 좌표·순서·action validation
2. waypoint 진행 상태기계와 `DESTINATION` 완료 이벤트
3. Ackermann형 `cmd_vel` 변환 수학과 속도·조향 clamp
4. `linear.x=0`, `angular.z!=0`인 제자리 회전 명령을 STOP으로 바꾸는 안전 규칙
5. ESP32 대신 메모리 fake transport를 사용하는 변환 계층 테스트
6. URDF/TF, Nav2 map server·AMCL·controller·waypoint follower 설정 파일
7. MQTT `START_PATROL/STOP_PATROL`을 fake mission에 연결하는 통합 테스트
8. 새 파일을 OTA/systemd 배포 대상에 포함하는 smoke test

지도 파일이 도착하면 ESP32 없이도 다음 단계까지 진행할 수 있다.

1. `map.yaml`과 이미지의 resolution/origin/크기 검증
2. map server로 지도 로드
3. RViz에서 waypoint 좌표 선택 및 `route.local.yaml` 작성
4. Nav2가 만드는 `/cmd_vel`을 ESP32로 보내지 않고 로그로만 관찰
5. localization과 TF 검증

실제 ESP32가 필요한 시점은 `/cmd_vel` 변환 결과를 처음 모터·서보에 전달하는
**8번 waypoint 1개 실주행부터**다.

## 구현된 비하드웨어 코드

- `navigation/route.py`: route schema와 최종 DESTINATION 검증
- `navigation/map_metadata.py`: map YAML/이미지 및 waypoint 지도 범위 검증
- `navigation/waypoint_mission.py`: pose 기반 경유·SCAN·종료 상태기계
- `navigation/service.py`: patrolId와 mission event를 묶는 thread-safe facade
- `navigation/cmd_vel_adapter.py`: 자동차형 변환, 제한, 제자리 회전 거부
- `roki-iot` 통합: START 시 waypoint 시작, DESTINATION 즉시 정지·IDLE
- 실제 route 파일이 없으면 운영 진입점 시작 거부(고정 직진 fallback 제거)

아직 남은 비하드웨어 작업은 ROS 2 `/cmd_vel`·localization pose를 위 facade에
연결하는 노드와 Nav2 launch/config다. 지도 파일이 도착하는 즉시 map 검증과
`route.local.yaml` 생성으로 이어간다.

더미 직사각형 맵과 중앙 직선 route의 비하드웨어 완료 흐름은
[`dummy-map-waypoint-plan.md`](dummy-map-waypoint-plan.md)에 기록한다.

## 지금 Serial 없이 준비할 항목

줄자와 메모만으로 다음 값을 실제 로봇에서 측정한다. 단위는 모두 mm다.

| 값 | 측정 기준 |
|---|---|
| wheelbase | 후륜축 중심부터 전륜 조향축 중심까지 |
| rear_track | 좌·우 후륜 타이어 접지 중심 간 거리 |
| front_track | 좌·우 전륜 타이어 접지 중심 간 거리 |
| body_length / body_width | 돌출 부품을 포함한 실제 최대 외곽 |
| lidar_x | 후륜축 중앙 기준 LiDAR 중심의 전후 거리, 전방이 + |
| lidar_y | 후륜축 중앙 기준 LiDAR 중심의 좌우 거리, 왼쪽이 + |
| lidar_z | 바닥부터 LiDAR 스캔 평면까지 높이 |
| lidar_yaw | 로봇 정면과 LiDAR 0도 방향의 차이 |
| camera_x/y/z | 동일 기준의 카메라 렌즈 중심 위치 |

최소 회전반경은 바닥에 테이프나 분필로 전륜 최대 조향 상태의 원을 표시한 뒤,
후륜축 중앙 궤적의 반지름을 측정한다. Serial을 사용하는 사람이 작업 중이면 이
시험은 하지 않고 치수만 측정한다.

## 수동 매핑 작업자에게 받을 산출물

작업 종료 시 아래를 한 폴더로 받는다.

```text
map.yaml
map.pgm 또는 map.png
slam pose graph/serialized map
사용한 ROS launch 및 parameter 파일
rosbag 경로(있으면)
시작 pose: x, y, yaw
ROS topic 목록과 TF tree 캡처
```

반드시 함께 기록할 값은 `map.yaml`의 `resolution`, `origin`, 지도 생성 시각과
LiDAR 장치명이다. 지도 이미지만 받으면 localization에 사용할 수 없다.

## 지도 수령 후 작업 순서

1. 저장 지도 재로딩과 `map -> odom -> base_link -> laser_frame` TF 확인
2. AMCL 또는 slam_toolbox localization에서 정지 pose 확인
3. RViz에서 회전이 완만한 waypoint 1개 등록
4. `cmd_vel -> speed/steering` 변환 계층을 속도 제한 상태로 연결
5. waypoint 1개 성공 후 2~3개와 `DESTINATION`을 연결
6. LiDAR 장애물 STOP, MQTT pose/status, 순찰 종료를 순서대로 결합

자동차형 차체이므로 가까운 위치에 큰 yaw 차이를 주거나 제자리 회전이 필요한
waypoint를 만들지 않는다. 실제 경로는 `route.example.yaml`을 복사한
`route.local.yaml`에 저장한다.
