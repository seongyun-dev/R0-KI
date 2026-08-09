# 수동 매핑·단일 BRIO·불법주차 연계 현황 (2026-08-04)

## 이번 결정

- 재부팅 후 자동 복구와 mapping/patrol 자동 모드 전환은 이번 작업에서 미룬다.
- 지도는 게임패드로 로봇을 수동 조종하며 SLAM Toolbox로 만든다.
- 카메라는 Logitech Brio 100 한 대만 사용한다.
- 차량 거리는 엔코더가 아니라 정면 LiDAR 구간에서 얻는다. 엔코더/SLAM pose는 로봇의 지도상 위치를 제공한다.
- 불법주차 여부는 로봇이 중복 판단하지 않고 기존 Backend 차량 판별 API에 차량의 지도 좌표와 번호판을 보낸다.

## 실제 환경에서 확인한 상태

확인 기준은 `origin/iot/dev` `df57119`, `origin/back/dev` `1f46c78`,
`origin/front/dev` `7f9a758`, `origin/ai/dev` `8ec3d7a`이다.

- Jetson의 `aiot-ros.service`는 mapping 모드로 실행 중이다.
- `/scan`은 약 11.6 Hz이며 `/map`은 실제 발행 중이다.
- 현재 지도 메타데이터는 224 x 234 px, 0.05 m/px, origin `[-5.42, -6.05, 0]`이다.
- 2026-08-04 현장 스냅샷은 벽 윤곽이 여러 방향으로 퍼져 실제 순찰 지도에 사용할 수 없었다.
- 해당 스냅샷은 Backend에 업로드하지 않았다. Jetson의
  `/home/e103/aiot-map-check-20260804-211835`에 원본 PGM/YAML만 보존했다.
- 당시 RF2O `/odom`은 거의 정지한 선속도와 달리 약 `0.046 rad/s`의 각속도를 보고했다.
  로봇을 움직이지 않은 상태에서도 같은 값이면 LiDAR odometry 회전 드리프트를 먼저 해결해야 한다.
- 실제 AI 서비스는 아직 두 카메라를 열고 있다. 이 문서와 같은 브랜치의 단일 BRIO 코드는 아직 Jetson 서비스에 배포하지 않았다.

## 지도 생성부터 Frontend 구역 저장까지

현재 코드의 정상 흐름은 다음과 같다.

1. Frontend가 `POST /api/map/mapping-sessions`로 세션을 시작한다.
2. Backend가 MQTT `START_MAPPING`에 `mappingSessionId`, `commandId`를 넣어 보낸다.
3. Jetson은 게임패드 deadman 입력이 있을 때만 ESP32에 짧은 주행 pulse를 보낸다.
4. 종료 조합을 누르면 먼저 정지한 뒤 `map_saver_cli`로 PGM/YAML을 저장한다.
5. IoT가 PGM을 PNG로 변환하고 resolution/origin과 함께
   `POST /api/map/mapping-sessions/{mappingSessionId}/map`으로 업로드한다.
6. Frontend는 완성된 PNG를 표시하고 14 x 7 격자에서 드래그한 사각형을 실제 `map` meter 좌표로 변환한다.
7. Frontend가 `POST /api/map/{mapId}/zones`로 `PARKING`, `START`, `DESTINATION` 등을 저장한다.

현장에서는 Nav2 `map_saver_cli`의 내부 기본 대기 2초가 짧아 첫 저장이 실패했고,
`save_map_timeout=20`에서는 성공했다. 따라서 IoT exporter가 전체 제한 시간의 80%를
Nav2 내부 `save_map_timeout`으로 명시하도록 수정했다.

## 불법주차 관련 기존 구현

### Backend

`POST /api/robot/vehicle-checks`가 이미 구현되어 있다. 요청에는 `tempId`, `x`, `y`,
`licensePlate`, `occurredAt`이 필요하다.

Backend 판정 우선순위는 다음과 같다.

1. 번호판이 입주 차량 DB에 없으면 `UNREGISTERED_VEHICLE`
2. 등록 차량이지만 좌표가 어떤 `PARKING` 사각형에도 없으면 `ILLEGAL_PARKING`
3. 등록 차량이고 주차구역 안이면 이벤트 없음

따라서 “주차구역 밖의 모든 차 = ILLEGAL_PARKING”은 현재 Backend 의미와 다르다.
미등록 차량은 위치와 관계없이 `UNREGISTERED_VEHICLE`이 먼저 생성된다.

### Frontend

- 구역 편집과 `PARKING` 저장이 이미 실제 API에 연결되어 있다.
- 이벤트 목록과 상세는 `ILLEGAL_PARKING`, `UNREGISTERED_VEHICLE`을 표시한다.
- 화면 좌표와 ROS map 좌표 변환은 resolution, origin, width, height를 사용하며 Y축을 뒤집는다.

### AI / IoT

- Jetson AI에는 차량 번호판 탐지, OCR, 증거 이미지 저장과 `vehicle-checks` 큐가 있다.
- 기존 Jetson AI 소스는 이벤트 좌표를 `(10, 20)`으로 고정한다.
- IoT ROS adapter는 AI의 직접 REST 전송을 가로채며 Robot이 가진 최신 map pose를 붙인다.
- 이번 변경부터 차량은 최신 BRIO 정면 LiDAR 거리 없이 전송하지 않는다.
- 유효 거리가 있으면 `vehicle = robot pose + range * heading`으로 map 좌표를 계산한 뒤
  기존 Backend API로 보낸다.

첫 MVP는 BRIO가 차를 정면에 두고 번호판 OCR을 성공시키는 상황을 전제로 한다. bbox 각도와
LiDAR ray를 정밀하게 매칭하는 기능은 후속이다.

## 단일 BRIO 설정

목표 설정은 다음과 같다. 실제 비밀값은 포함하지 않는다.

```dotenv
AIOT_AI_SINGLE_CAMERA=true
AIOT_AI_REQUIRE_DUAL_CAMERAS=false
AIOT_AI_CAMERA_DEVICE=/dev/roki_camera_right
AIOT_AI_CAMERA_LEFT_DEVICE=
AIOT_AI_CAMERA_RIGHT_DEVICE=
```

`/dev/roki_camera_right`는 현재 Jetson에서 Logitech Brio 100의 serial 기반 별칭이다.
USB 포트 번호가 바뀌어도 같은 장치 별칭을 사용한다. TensorRT engine은 batch 2이므로 기존
AI detector의 `track_frame`이 두 번째 slot을 검은 프레임으로 채우며, 실제 V4L2 장치는 한 개만 연다.

## Backend에 남은 계약

불법주차 판정만을 위해 Robot이 zone 목록을 내려받을 필요는 없다. Backend가 이미 같은 DB의
`PARKING` 영역으로 판정한다.

반면 Frontend에서 정한 waypoint/순찰 경로를 Robot이 주행하려면 Robot service token으로 읽는
별도 navigation config API가 필요하다. 현재 `GET /api/map/{mapId}/zones`는 관리자 JWT와
`CustomUserDetails`를 전제로 하므로 Robot token으로 호출할 수 없다. 또한 현재 Frontend onboarding은
사각형 zone만 저장하고 waypoint 순서/행동은 저장하지 않는다.

지도 재생성 시 처리도 보강해야 한다. Backend는 같은 `PatrolMap` 행의 이미지와 메타데이터만
갱신하고 기존 checkpoint를 삭제하지 않는다. Frontend의 zone 저장도 기존 목록을 교체하지 않고
새 행을 추가한다. 이미 zone이 있는 단지에서 새 지도를 업로드하면 이전 좌표의 zone이 남으므로,
새 map version 완료 시 checkpoint 초기화 또는 `PUT zones` 교체 계약이 필요하다.

권장 후속 계약은 map version, map metadata, ordered waypoints와 zone을 한 번에 반환하는
`GET /api/robot/navigation-config`이다. 이 API가 확정되기 전까지 순찰 route는 Jetson 로컬 파일을 사용한다.

## 실물 검증 체크리스트

- [ ] 게임패드 USB 수신기를 연결하고 `/dev/input/js0` 및 `e103`의 input 그룹 권한 확인
- [ ] 축/버튼 번호 확인. 모터 전원 없이 probe부터 실행
- [ ] 로봇 정지 상태에서 RF2O angular velocity가 0 근처인지 확인
- [ ] 빈 공간을 천천히 한 바퀴 돌고 출발점으로 복귀해 loop closure 확인
- [ ] 저장된 PNG가 실제 벽 윤곽과 일치하는지 확인한 뒤에만 Backend 업로드
- [ ] 단일 BRIO 배포 후 실제로 V4L2 장치 하나만 열리는지 확인
- [ ] BRIO 정면에 차량을 두고 LiDAR 정면 거리와 줄자 거리를 비교
- [ ] 카메라 중심과 LiDAR 정면 오차를 `AIOT_VEHICLE_CAMERA_YAW_DEG`로 보정
- [ ] 등록 차량을 PARKING 안/밖에 각각 배치해 정상/`ILLEGAL_PARKING` 확인
- [ ] 미등록 번호판은 위치와 관계없이 `UNREGISTERED_VEHICLE`이 되는 현재 정책 확인
- [ ] 생성 event의 증거 이미지와 map 좌표가 Frontend 상세에 맞게 표시되는지 확인

## 보안 주의

Jetson의 AI 작업트리 `config.py`에 service token fallback이 평문으로 들어간 수정 상태가 발견됐다.
값은 이 문서에 기록하지 않는다. 관리형 token 파일이 이미 있으므로 AI 담당 변경을 보존한 채 별도
합의 후 fallback을 제거하고 해당 token을 교체해야 한다.
