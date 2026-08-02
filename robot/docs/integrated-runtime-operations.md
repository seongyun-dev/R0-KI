# Integrated Robot runtime 운영·현장 검증

기준일: 2026-08-03  
범위: Jetson Robot/AI 런타임, MQTT/REST, systemd, Pull OTA, 현장 검증

## 1. 운영 구조

```text
Frontend POST /api/patrols
  -> Backend MQTT START_PATROL (QoS 1, TTL 10s)
  -> aiot-robot.service / run_integrated.py
       -> AI READY + LiDAR + ESP32/odometry + OTA lock 확인
       -> /ai/control ENABLE
       -> 유일한 RobotRuntime -> /dev/roki_esp32
       -> route.local.yaml + map pose/Nav2 또는 encoder_limited
       -> MQTT pose 1s / status 5s+변경즉시 / command ACK
       -> AI detection + 현재 pose -> durable outbox -> Backend REST
       -> DESTINATION 즉시 물리 STOP + 최종 pose/status
  <- Backend가 목적지 pose 판정 후 MQTT STOP_PATROL
  -> STOP 재확인 + AI DISABLE + ACK + IDLE
```

`aiot-ai.service`는 기존 모델 pipeline을 `aiot_robot.ai_runtime`으로 감싼다. AI가
직접 REST를 호출하지 않고 Robot만 REST를 소유한다. `aiot-update.timer`는 5분마다
stable manifest를 확인하지만 순찰이 보유한 `patrol-deploy.lock`을 얻지 못하면
`phase=activate result=patrol-active`로 현재 버전을 유지한다.

부팅에서는 현재 검증본의 AI/Robot과 updater가 함께 시작될 수 있다. 새 릴리스가
있을 때 updater가 잠금을 얻고 AI→ROS→Robot을 재시작한다. 서비스가 updater 종료를
`After=`로 기다리지는 않으므로 updater 내부 재시작과 교착하지 않는다.

## 2. Git에서 검증하는 명령

다음 명령은 모터, 시리얼, MQTT를 사용하지 않는다.

```bash
./robot/scripts/test.sh

export ROKI_ROUTE_FILE="$PWD/robot/roki/maps/dummy_rectangle/route.short-straight.yaml"
export ROKI_NAVIGATION_MODE=encoder_limited
./robot/scripts/smoke-test.sh pre-activate
```

성공 기준은 모든 unittest `OK`, `serialAccessed: false`, 마지막 메시지
`no actuator command was sent`다.

## 3. 최초 Jetson 설치

이 절은 Git 변경을 검토·병합하고 현장 책임자가 허용한 뒤 실행한다. 설치 자체는
모터를 움직이지 않지만 systemd start는 카메라·ROS·시리얼을 점유한다.

```bash
sudo apt update
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup

sudo bash infra/jetson/install.sh
sudo install -m 0600 -o root -g root \
  infra/jetson/package-read.env.example /opt/aiot/secrets/package-read.env
sudo install -m 0600 -o root -g root \
  infra/jetson/ai.env.example /opt/aiot/secrets/ai.env
sudo install -m 0600 -o root -g root \
  infra/jetson/ros.env.example /opt/aiot/secrets/ros.env.example
sudo install -m 0600 -o root -g root \
  robot/config/robot.env.example /opt/aiot/secrets/robot.env
```

실측 후 `ros.env.example`을 `ros.env`로 복사한다. 네 env를 현장에서 수정하되 실제 토큰·비밀번호를 Git, shell history, Mattermost에
남기지 않는다. `package-read.env`에는 `read_package_registry` 전용 Deploy Token만
사용한다. Robot service token은 백엔드의 retained `SET_TOKEN`을 받아
`/var/lib/aiot/secrets/robot-service-token`에 mode 0600으로 저장된다.

2026-08-03 비구동 준비에서 `ros-humble-navigation2`와
`ros-humble-nav2-bringup` 설치를 완료했고, AMCL·planner·controller·BT navigator
패키지 경로를 확인했다. lifecycle node 기동과 실제 `/scan`, `/odom`, TF 검증은
실측값을 채운 뒤 수행한다.

## 4. 현장 설정

### route와 map

운영 route는 릴리스가 아니라 persistent 경로에 둔다.

```bash
sudo install -m 0660 -o aiot -g aiot \
  reviewed-route.yaml /var/lib/aiot/config/route.local.yaml
sudo -u aiot env \
  ROKI_ROUTE_FILE=/var/lib/aiot/config/route.local.yaml \
  ROKI_NAVIGATION_MODE=nav2 \
  /opt/aiot/iot/current/robot/scripts/run.sh --check
```

route의 `frame_id`, 좌표, yaw는 저장한 occupancy map의 `map` frame과 같아야 한다.
sequence는 1부터 연속이고 마지막 action은 `DESTINATION`이어야 한다. 주차·스캔
지점은 `SCAN`, 통과점은 `PASS`를 사용한다.

### 반드시 실측할 값

`/opt/aiot/secrets/robot.env`의 아래 빈 값은 곡선 Nav2 제어 전에 직접 측정한다.

```text
ROKI_WHEELBASE_M=<앞/뒤 차축 중심 거리 m>
ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG=<서보 60/100도일 때 실제 바퀴 최대 조향각>
ROKI_ROBOT_RADIUS_M=<차체와 장착물을 포함한 안전 반경 m>
```

측정하지 않으면 `auto`가 `encoder_limited`를 선택한다. 제한 모드는 직선·최대
0.70 m route만 받으므로 최종 순찰용 대체 수단이 아니다. 확인된 상수는 바퀴
65 mm, LEFT 329 / RIGHT 328 ticks/rev, 서보 60/80/100도, PWM 45다.

### 장치 이름

```bash
readlink -f /dev/roki_esp32
readlink -f /dev/roki_lidar
readlink -f /dev/roki_camera_left
readlink -f /dev/roki_camera_right
```

ESP32와 LiDAR CP2102는 serial `0001`이 같으므로 `/dev/serial/by-id/...0001`을
쓰지 않는다. USB 물리 포트를 바꾸면 udev 규칙을 다시 검증한다. 카메라도
`/dev/video0` 같은 번호 대신 캡처 노드의 stable alias를 사용한다.

## 5. 승인 후 단계별 시작

아래부터는 장치 점유와 실제 구동 가능성이 있다. 배터리·바퀴 들림·비상정지·주행
공간을 확인하고 사용자 승인 후 한 단계씩 실행한다.

```bash
sudo systemctl start aiot-update.service
sudo systemctl status aiot-update.service --no-pager
readlink -f /opt/aiot/iot/current

sudo systemctl start aiot-ai.service
sudo systemctl status aiot-ai.service --no-pager
sudo test -s /run/aiot/ai-ready.json

sudo systemctl start aiot-ros.service
sudo systemctl status aiot-ros.service --no-pager

sudo systemctl start aiot-robot.service
sudo systemctl status aiot-robot.service --no-pager
```

기대 결과는 updater `result=activated` 또는 `already-current`, AI READY 파일,
Robot `active (running)`이다. 먼저 프론트 START가 아닌 MQTT 모니터링으로
IDLE/status/pose 준비 상태를 확인한다.

```bash
sudo journalctl -u aiot-update.service -n 100 --no-pager
sudo journalctl -u aiot-ai.service -n 100 --no-pager
sudo journalctl -u aiot-ros.service -n 200 --no-pager
sudo journalctl -u aiot-robot.service -n 200 --no-pager
sudo systemctl list-timers aiot-update.timer --no-pager
```

## 6. 현장 검증 순서와 합격 기준

1. **전원 없음**: 장치 alias, env, route `--check`, systemd unit만 확인한다.
2. **바퀴를 띄움**: operating-json HELLO/ACK, encoder zero, 중앙 80도, PWM 45의
   방향과 STOP을 확인한다.
3. **AI 단독**: 두 카메라와 engine, 첫 inference 뒤 `/ai/status READY`를 확인한다.
4. **LiDAR 단독**: `/scan` heartbeat와 전방 임계거리 STOP, 장애물 제거 후 1초
   stable clear를 확인한다.
5. **짧은 직선**: `encoder_limited` fixture로 CHECKPOINT/SCAN/DESTINATION과 즉시
   STOP을 확인한다.
6. **Nav2**: localization/TF가 안정된 뒤 실제 route를 저속 PWM 45로 1회 수행한다.
7. **전체 흐름**: 프론트 START부터 백엔드 patrol 완료, 이벤트·증거, STOP ACK,
   최종 IDLE까지 한 patrolId로 확인한다.
8. **장애 복구**: AI 종료, LiDAR stale, MQTT 재연결, 전원 재부팅, 순찰 중 OTA
   보류를 각각 확인한다.

합격 조건은 시리얼 소유 프로세스 하나, 중복 START 무동작·동일 ACK, 만료 명령
REJECTED, DESTINATION에서 백엔드 STOP보다 먼저 물리 STOP, eventId 중복 없음,
최종 pose가 목적지 영역 안, STOP ACK `SUCCEEDED`, 상태 `IDLE`이다.

## 7. OTA와 rollback

`iot/master`에 포함된 commit에 protected `iot-vX.Y.Z` tag를 만들고, GitLab의
manual `iot_publish`를 승인한다. Jetson은 stable manifest와 private package를
검증한 뒤에만 `current`를 교체한다.

```bash
sudo systemctl start aiot-update.service
sudo journalctl -u aiot-update.service -n 100 --no-pager
readlink -f /opt/aiot/iot/current
readlink -f /opt/aiot/iot/previous
cat /opt/aiot/iot/state/VERSION
```

pre/post smoke나 서비스 재시작이 실패하면 `current`를 이전 symlink로 되돌리고
이전에 실행 중이던 AI/ROS/Robot만 다시 시작한다. 순찰 중이면 새 릴리스를 활성화하지
않는다. 수동 복구가 필요하면 먼저 실제 STOP을 확인한 후 다음처럼 previous를
가리키고 서비스를 AI → Robot 순서로 재시작한다.

```bash
sudo ln -sfn "$(readlink -f /opt/aiot/iot/previous)" /opt/aiot/iot/current
sudo systemctl restart aiot-ai.service
sudo systemctl restart aiot-ros.service
sudo systemctl restart aiot-robot.service
```

상세 실측법과 단계별 합격 기준은
[`field-calibration-and-live-gates.md`](field-calibration-and-live-gates.md)를 따른다.

## 8. 현재 남은 물리 게이트

- Nav2 lifecycle node 정상 기동과 `/scan`, `/odom`, TF 연결
- wheelbase와 실제 최대 바퀴 조향각 실측
- 최종 occupancy map, initial pose, map→odom→base_link TF
- 카메라 좌/우 물리 장착 방향 확인
- LiDAR 전방 임계거리·사각·clear hysteresis 현장 검증
- `/opt/aiot/secrets/robot.env` 생성 후 실제 MQTT 인증, retained token과
  end-to-end 순찰 1회
- 재부팅, 순찰 중 OTA 보류, 실패 릴리스 rollback 검증

이 항목은 소프트웨어 미구현이 아니라 장비·운영 승인 없이는 완료할 수 없는 검증
게이트다. 활성 Jetson의 `/home/e103/yolo-pipeline` 변경 파일과 현재 서비스는
릴리스 절차 밖에서 덮어쓰지 않는다.
