# Waypoint MQTT 현장 통합 체크리스트

기준일: 2026-08-02

## 현재 확인된 결과

- 65 mm 휠과 329 ticks/rev 기준으로 0.60 m 직선 경로를 실제 주행했다.
- `CHECKPOINT_20CM`, `SCAN_POINT_40CM`, `DESTINATION_60CM`을 순서대로 판정하고 목적지에서 정지했다.
- 로봇 코어 비이동 테스트 76개가 통과했다.
- MQTT 명령, waypoint, 상태 저장소 통합 테스트 13개가 통과했다.
- Jetson 격리 스테이징은 `/home/e103/waypoint-status-merge-stage-20260802-205644`이다.
- 활성 경로에는 아직 스테이징을 설치하지 않았다.

## 다른 작업자 완료 전 할 수 있는 작업

ESP32 Serial과 실제 MQTT 명령을 사용하지 않는다.

1. MQTT 명령 payload를 드라이런으로 확인한다.

   ```bash
   cd /home/e103/waypoint-status-merge-stage-20260802-205644/roki-iot
   python3 tools/waypoint_mqtt_demo.py start --patrol-id 23
   python3 tools/waypoint_mqtt_demo.py stop
   ```

   출력 끝에 `DRY_RUN_ONLY`가 있어야 한다.

2. 상태 송신 작업자가 사용하는 좌표계가 다음 경로와 일치하는지 확인한다.

   ```text
   frame: map
   start:       (1.0, 2.5)
   checkpoint:  (1.2, 2.5)
   scan point:  (1.4, 2.5)
   destination: (1.6, 2.5)
   ```

3. 상태 송신 작업이 끝나면 해당 작업자의 최신 `run_integrated.py`, 상태 저장소,
   pose publisher와 실행 환경을 먼저 스테이징에 반영한다. 현재 스테이징으로 활성
   파일을 바로 덮어쓰지 않는다.

## 상태 송신 작업 완료 후 병합 게이트

1. 작업자가 실행 중인 프로세스를 정상 종료한다. 강제 종료하지 않는다.
2. `/dev/roki_esp32` 점유가 없는지 확인한다.

   ```bash
   fuser -v /dev/roki_esp32
   ```

3. 상태 송신 최신본과 waypoint 스테이징을 다시 병합한 뒤 비이동 테스트를 실행한다.
4. 상태 pose가 위 `map` 좌표를 발행하는지 확인한다. 시작점을 `(0, 0)`으로 발행하면
   백엔드의 `DESTINATION (1.6, 2.5)` 판정과 맞지 않는다.
5. 병합본이 확정된 뒤에만 설치 스크립트를 실행한다.

   ```bash
   bash /home/e103/waypoint-status-merge-stage-20260802-205644/install_waypoint_status_merge.sh
   ```

   이 스크립트는 Serial 점유가 있으면 배포를 거부하고 기존 파일을 별도 경로에
   백업한다.

## 첫 MQTT 물리 시험

바퀴, 조향, 전방 코스와 비상 전원 차단 수단을 확인한 뒤 진행한다.

1. 병합 런타임을 저속 설정으로 실행한다.

   ```bash
   cd /home/e103/roki-iot
   PATROL_DRIVE_SPEED_PWM=45 \
   ROKI_ROUTE_FILE=/home/e103/roki/config/route.local.yaml \
   ROKI_ROUTE_START_X_M=1.0 \
   ROKI_ROUTE_START_Y_M=2.5 \
   ROKI_ROUTE_MAXIMUM_TRAVEL_M=0.70 \
   python3 run_integrated.py
   ```

2. 별도 터미널에서 실제 `patrolId`로 START를 한 번 보낸다.

   ```bash
   cd /home/e103/roki-iot
   python3 tools/waypoint_mqtt_demo.py start \
     --patrol-id 23 \
     --send \
     --confirm STRAIGHT_ROUTE_CLEAR
   ```

3. 다음 순서를 확인한다.

   ```text
   START ACK SUCCEEDED
   -> CHECKPOINT 도달
   -> SCAN_POINT ACTION_REQUIRED
   -> DESTINATION 도달
   -> 모터 즉시 정지
   -> 최종 pose/IDLE 발행
   ```

4. 백엔드 STOP 연동 전 진단이 필요할 때만 STOP을 한 번 보낸다.

   ```bash
   python3 tools/waypoint_mqtt_demo.py stop --send
   ```

5. `ACK timeout`, `REJECTED`, `FAILED` 중 하나라도 나오면 다음 물리 시험을 하지 않고
   런타임 로그, commandId, ACK payload를 함께 보관한다.

## 오늘의 완료 기준

- 최신 상태 송신 코드와 waypoint 코드가 하나의 런타임으로 실행된다.
- MQTT START 한 번으로 0.60 m 경로를 출발한다.
- 목적지에서 명령 없이도 물리 정지한다.
- 최종 pose가 `(1.6, 2.5)` 부근으로 발행된다.
- 백엔드 STOP을 수신하면 정지를 재확인하고 STOP ACK `SUCCEEDED`와 IDLE을 발행한다.
- 실행 로그에 START commandId, waypoint 이벤트, 목적지 정지, STOP commandId가 남는다.

AI 실제 객체 인식 연결과 LiDAR 장애물 정지·재개는 이 최소 직선 MQTT 시연을 통과한
뒤 별도 게이트로 검증한다.
