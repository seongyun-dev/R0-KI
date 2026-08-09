# 프론트 순찰 시작 + 수동 주행 + AI 시연

이 문서는 자동 주행이 완성되기 전, 프론트와 백엔드의 실제 순찰 흐름을 유지하면서
SSH 키보드로만 주행을 보조하는 **임시 시연 모드**를 설명한다. 기본 systemd 실행은
기존 웨이포인트/Nav2 모드이며, `--manual-keyboard`를 명시한 경우에만 수동 모드가 된다.

## 보장되는 실행 순서

1. 프론트가 순찰 시작 API를 호출한다.
2. 백엔드가 `ROKI-01`의 `START_PATROL` MQTT 명령을 보낸다.
3. Jetson이 AI readiness, LiDAR, ESP32, OTA interlock을 확인한다.
4. AI에 현재 `patrolId`로 `ENABLE`을 전송한다.
5. 수동 controller를 활성화하되 속도는 0, 조향은 80도로 시작한다.
6. `START_PATROL SUCCEEDED` ACK와 `PATROLLING` 상태를 발행한다.
7. 그때부터 SSH 터미널의 W/A/S/D 입력만 짧은 제어 pulse로 반영한다.
8. 프론트 STOP은 모터 STOP을 먼저 요청하고 AI를 DISABLE한 뒤 STOP ACK와 IDLE을
   발행한다.

AI service는 부팅 때 카메라와 TensorRT engine을 미리 열고 warm-up한다. 실제 반복
추론과 MJPEG 프레임 발행은 4번의 AI ENABLE 이후에만 진행된다. 따라서 순찰 시작
지연은 줄이면서 관제 화면과 객체 인식을 순찰 기간에만 동작시키는 구조다.

## 안전 제약

- 시리얼 소유 프로세스는 통합 런타임 하나뿐이다.
- MQTT START 전에는 모든 주행 키를 무시한다.
- W 전진은 LiDAR가 `NORMAL`이고 전방 장애물 상태가 `STOP`이 아닐 때만 허용한다.
- W/S는 기본 0.2초 pulse이며, 키를 계속 누르지 않아도 자동 STOP한다.
- A/D는 현장 확인 범위인 70~90도 안에서 2도씩 조향하며, 모터 속도 0으로 servo만
  pulse한다.
- Space와 Q는 즉시 로컬 정지다. 정식 순찰 종료와 AI DISABLE은 프론트 STOP으로 한다.
- 키보드 thread는 Serial을 직접 열거나 쓰지 않는다. 요청은 RobotRuntime mailbox를
  거쳐 Serial 소유 thread에서만 전송된다.
- 백그라운드 systemd에는 TTY가 없으므로 수동 옵션을 사용할 수 없고 즉시 실패한다.

## 시연 시작 전

현재 다른 수동 프로그램이 `/dev/roki_esp32`를 점유하면 먼저 그 프로그램의 터미널에서
정상 종료한다. 임의로 PID를 kill하지 않는다. 바퀴를 띄운 상태에서 방향을 한 번 확인한
후 바닥 시연으로 전환한다.

```bash
systemctl is-active aiot-ai.service aiot-ros.service
systemctl is-active aiot-robot.service
fuser -v /dev/roki_esp32
```

`aiot-ai`와 `aiot-ros`는 active, `aiot-robot`은 inactive, `fuser`는 출력 없음이어야
한다. 그다음 SSH의 foreground TTY에서 실행한다.

```bash
sudo /opt/aiot/iot/current/robot/scripts/run-manual-demo.sh
```

스크립트는 다음을 자동 검증한 뒤 실행한다.

- `/opt/aiot/secrets/robot.env` 존재
- 실제 `ROBOT_KEY` 존재
- AI/ROS service active
- 운영 Robot service inactive
- ESP32 Serial 미점유
- foreground TTY 존재

## 시연 조작

1. 위 명령을 실행한 터미널은 그대로 둔다.
2. 프론트에서 순찰 시작을 누른다.
3. 터미널에서 `START_PATROL succeeded`와 `PATROLLING`을 확인한다.
4. 관제 영상이 나타나고 AI 상태가 정상인지 확인한다.
5. W=전진, S=후진, A=좌, D=우, Space/Q=즉시 정지를 사용한다.
6. 프론트에서 순찰 중지를 누른다.
7. `STOP_PATROL completed`, AI DISABLE, IDLE을 확인한다.

프론트 START가 실패하면 W/S를 눌러도 움직이지 않는다. LiDAR가 끊겼거나 전방 장애물이
있으면 전진은 `FORWARD_BLOCKED` 또는 `SAFETY_STOP`으로 정지한다.

## 자동 주행 복귀

수동 터미널에서 Ctrl+C로 통합 런타임을 종료한 뒤 기본 서비스를 시작한다. systemd에는
수동 플래그가 없으므로 자동 웨이포인트/Nav2 실행으로 복귀한다.

```bash
sudo systemctl start aiot-robot.service
sudo systemctl status aiot-robot.service --no-pager
```

환경 파일이나 systemd unit을 수동 모드로 변경하지 않는다. 시연 뒤 제거할 것은
`--manual-keyboard`를 사용한 foreground 실행뿐이다.

## 2026-08-03 비구동 검증 결과

- 카메라 2대: READY
- YOLO TensorRT engine: READY
- OCR TensorRT engine: READY
- AI ENABLE 뒤 상태: `detectionEnabled=true`
- AI ENABLE 4초 뒤 MJPEG: `ready=true`, 34 frames
- 검증 종료 뒤 AI DISABLE: `detectionEnabled=false`
- ESP32/모터 명령: 전송하지 않음
