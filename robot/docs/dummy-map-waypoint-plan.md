# 더미 맵 Waypoint 검증 계획

## 현재 ROS/SLAM 기준

2026-08-02 Jetson 파일을 Serial 접근 없이 읽어 확인한 기준이다.

- ROS 2 Humble
- slam_toolbox 설정: `/home/e103/slam_config/hanbakwi_slam.yaml`
- frame: `map -> odom -> base_link -> laser_frame`
- scan topic: `/scan`
- mapping resolution: `0.05 m/pixel`
- RF2O: `/scan`으로 `/odom_rf2o`와 `odom -> base_link`를 20 Hz 발행
- YDLIDAR frame: `laser_frame`
- 기존 LiDAR static TF는 임시값 `base_link -> laser_frame z=0.02`
- X4-Pro 원본 parameter의 `/dev/ttyUSB0`는 사용 금지하고 `/dev/roki_lidar` 사용
- `roki_bridge`의 `pose_node.py`, `robot_state_node.py`, launch 파일은 현재 비어 있음

설치 상태:

| ROS 패키지 | 상태 |
|---|---|
| slam_toolbox | 설치됨 |
| nav2_map_server | 설치됨 |
| nav2_amcl | 없음 |
| nav2_planner | 없음 |
| nav2_controller | 없음 |
| nav2_waypoint_follower | 없음 |
| nav2_bt_navigator | 없음 |

## 생성한 더미 자료

`robot/roki/maps/dummy_rectangle`에 다음을 생성했다.

- `map.pgm`: 8 m × 5 m 직사각형 벽, 0.05 m/pixel
- `map.yaml`: ROS map_server 형식
- `route.yaml`: 중앙 직선의 PASS, SCAN, DESTINATION 세 지점

생성기는 `scripts/generate_dummy_map.py`이며 크기와 해상도를 바꿔 재생성할 수 있다.

```bash
python3 scripts/generate_dummy_map.py \
  --output-dir maps/dummy_rectangle \
  --width-m 8 \
  --height-m 5 \
  --resolution-m 0.05 \
  --overwrite
```

## 현재 가능한 검증

ROS, ESP32, Serial 없이 아래 흐름은 통과했다.

```text
map/route 파일 검증
→ STARTED
→ CHECKPOINT WAYPOINT_REACHED
→ SCAN ACTION_REQUIRED
→ DESTINATION_REACHED
→ COMPLETED
```

재실행:

```bash
python3 scripts/dry_run_waypoint_route.py \
  --map maps/dummy_rectangle/map.yaml \
  --route maps/dummy_rectangle/route.yaml \
  --patrol-id 17
```

## 실제 주행 가능 조건

임의의 더미 맵은 로직과 화면 검증에만 쓴다. 실제 공간과 벽 크기가 일치하지 않으면
LiDAR localization이 성립하지 않으므로 실물 waypoint 주행 기준으로 사용할 수 없다.

실물 주행은 다음 중 하나가 필요하다.

1. 수동 SLAM으로 만든 실제 지도와 pose graph를 사용한다.
2. 실제 시험 공간이 단순 직사각형이면 치수가 맞는 더미 맵을 만들고 AMCL로 위치를 잡는다.
3. 지도 localization 없이 RF2O odom 원점을 임시 `map` 원점으로 사용해 짧은 직선 경로만 시험한다.

정식 경로는 1번이다. 2번은 벽 치수가 맞을 때만 가능하고, 3번은 누적 오차 때문에
당일 짧은 시험 이외에는 사용하지 않는다.

## 다음 구현 순서

1. 누락된 Nav2 구성요소 설치 여부 확정
2. map server + localization launch 작성
3. localization pose를 `WaypointNavigationService.update_pose()`에 연결
4. Nav2 `/cmd_vel`을 `CmdVelToEsp32Adapter`에 연결하되 첫 실행은 fake transport
5. `/cmd_vel` 로그와 waypoint 완료를 확인한 뒤에만 ESP32 실주행
