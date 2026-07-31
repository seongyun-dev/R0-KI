# 한바퀴 ESP32·주행·MQTT 런타임 handoff

> 기준일: 2026-07-31 (Asia/Seoul)
>
> 대상 장비: Jetson Orin Nano `e103@192.168.30.86`
>
> 저장소 기준 브랜치: `iot/feat/esp32-mqtt-runtime-handoff`
>
> 기준 상위 브랜치: `origin/iot/dev` (`c0d7c5b`)

이 문서는 실물 로봇에서 완료한 ESP32 운영 프로토콜, Jetson 주행
런타임, 기존 MQTT publisher 통합 작업을 다음 작업자가 그대로 이어가기
위한 기준 문서다. 비밀번호, MQTT 자격 증명, 서비스 토큰은 포함하지
않는다.

## 1. 가장 먼저 알아야 할 현재 상태

현재 `robot/`에는 서로 목적이 다른 두 계층이 함께 있다.

| 경로 | 역할 | 현재 상태 |
| --- | --- | --- |
| `robot/src/aiot_robot` | OTA용 AI/ROS·REST 골격 | 무구동 안전 골격. 기존 코드 유지 |
| `robot/roki` | ESP32 운영 프로토콜·주행·안전·엔코더 런타임 | Jetson 실물 검증 완료 |
| `robot/roki-iot` | MQTT publisher와 `robot/roki` 통합 | 실제 브로커 START/STOP 계약 검증 완료 |
| `robot/hardware` | ESP32 펌웨어와 직접 하드웨어 시험 도구 | 운영 펌웨어 2.2.0 플래시·preflight 완료 |

중요한 제한은 다음과 같다.

- 현재 OTA의 `robot/scripts/run.sh`는 여전히 무구동 AI/ROS 골격을
  실행한다.
- `robot/roki-iot/run_integrated.py`가 실물 주행과 MQTT를 담당하지만,
  아직 `aiot-robot.service`의 정식 진입점으로 교체되지 않았다.
- 따라서 이 브랜치를 패키징했다고 해서 부팅 직후 자동으로 모터가
  움직이지 않는다.
- 다음 작업자는 아래 P0 통합을 끝낸 뒤에만 systemd/OTA 진입점을
  변경해야 한다.

## 2. Jetson의 현재 배치와 저장소 대응

Jetson의 작업 디렉터리는 Git 저장소가 아니었다. 검증된 소스를 다음과
같이 저장소로 옮겼다.

| Jetson 실물 경로 | 저장소 경로 |
| --- | --- |
| `/home/e103/roki` | `robot/roki` |
| `/home/e103/roki-iot` | `robot/roki-iot` |
| `/home/e103/robot-hw-test`의 선별 소스 | `robot/hardware` |

Jetson의 변경 전 백업은 다음 경로에 있다.

```text
/home/e103/robot-integration-backup-20260731-162430
```
다음 항목은 의도적으로 Git에 넣지 않았다.

- `.venv`
- 실제 `.env`
- MQTT 계정·비밀번호
- `runtime/robot_service_token`
- ESP32 전체 플래시 백업
- Arduino toolchain·빌드 산출물
- 실험 로그와 과거 백업 파일

## 3. 검증된 하드웨어 기준

### 3.1 ESP32와 구동부

| 기능 | 핀/값 |
| --- | --- |
| LEFT BTS7960 RPWM | GPIO 25 |
| LEFT BTS7960 LPWM | GPIO 26 |
| RIGHT BTS7960 RPWM | GPIO 27 |
| RIGHT BTS7960 LPWM | GPIO 33 |
| LEFT encoder A/B | GPIO 34/35 |
| RIGHT encoder A/B | GPIO 36/39 |
| PCA9685 I2C SDA/SCL | GPIO 21/22 |
| PCA9685 servo channel | CH0 |
| 실측 조향 중앙 | 80도 |
| 허용 조향 범위 | 60~100도 |
| 기본 시연 속도 | PWM 51/255, 약 20% |

모터 극성과 펌웨어 방향 보정은 다음 실물 결과를 기준으로 한다.

```text
LEFT  : LPWM = 전진, RPWM = 후진
RIGHT : RPWM = 전진, LPWM = 후진
```

`writeSignedMotorPwm()`에서 좌우 모터의 물리 방향 차이를 보정한다. 배선을
바꾸거나 핀을 다시 배정하면 이 함수를 함께 검토해야 한다.

### 3.2 전원 경계

- Jetson 전원과 구동용 Battery B는 별도 경로다.
- 모터·서보가 실제로 움직이는 시험에서는 Battery B가 필요하다.
- 펌웨어 플래시 때는 반드시 Battery B를 물리적으로 분리한다.
- ESP32 USB 연결만으로는 모터와 서보 구동 전력이 공급되지 않는다.
- `operating_steering_drive_test.py`는 Battery B 전압을 감지하지 못하면
  이동 명령을 거절한다.

### 3.3 최종 확인 당시 실물 상태

- 좌·우 후륜은 개별 전진/후진이 확인됐다.
- PCA9685 CH0의 MG996R 조향 동작이 확인됐다.
- 조향 중앙값은 80도로 확인됐다.
- 펌웨어 2.2.0 플래시 이후 운영 프로토콜 preflight는 통과했다.
- 최종 MQTT START/STOP 계약 검증은 Battery B를 분리한 상태에서
  수행했으므로, 2.2.0과 MQTT를 결합한 실제 바닥 주행은 다음 작업자가
  안전구역에서 한 번 더 확인해야 한다.

## 4. ESP32 운영 JSON line 프로토콜

통신은 USB serial 115200 baud, UTF-8 JSON 한 줄당 한 메시지다.

### 4.1 Jetson에서 ESP32로 보내는 명령

```json
{"type":"stop","sequence":0}
{"type":"hello","protocol":1,"sequence":1}
{"type":"encoder_zero","sequence":2}
{"type":"status","sequence":3}
{"type":"control","speed":51,"steering":80,"sequence":4}
```

연결 직후 순서는 반드시 다음과 같다.

```text
STOP
→ HELLO
→ ENCODER_ZERO
→ STATUS
→ fresh odometry/hardwareStatus 수신
→ CONTROL 허용
```

### 4.2 ESP32에서 Jetson으로 보내는 메시지

```json
{
  "type": "hello",
  "firmware": "roki-operating",
  "version": "2.2.0",
  "protocol": 1,
  "sequence": 1,
  "commandTimeoutMs": 400,
  "telemetryIntervalMs": 100
}
```

```json
{
  "type": "odometry",
  "seq": 10,
  "uptimeMs": 12345,
  "leftTicks": 100,
  "rightTicks": 98
}
```

```json
{
  "type": "hardwareStatus",
  "battery": 82.5,
  "batteryVoltage": 12.1,
  "motor": "NORMAL",
  "lineSensor": "NORMAL",
  "lineValues": [1, 1, 0, 1, 1]
}
```

`battery`는 백엔드 계약에 맞춘 0~100 퍼센트이고,
`batteryVoltage`는 보정·진단용 실제 전압이다. 현재 퍼센트 환산은
3S LiPo 무부하 전압 기반 근삿값이므로 실물 부하 데이터를 수집해
보정해야 한다.

### 4.3 안전 동작

- ESP32 CONTROL watchdog은 400ms다.
- 주행 중 Jetson은 약 100ms마다 CONTROL heartbeat를 보내야 한다.
- heartbeat가 끊기면 ESP32가 모터와 서보 출력을 정지한다.
- STOP은 sequence 재시작 상황에서도 항상 수용한다.
- Jetson serial 런타임도 안전 오류와 종료 시 STOP을 보낸다.
- CP2102를 열면 ESP32가 재부팅될 수 있다. `SerialManager`는 2초를
  기다리고 부트/부분 데이터를 비운 뒤 handshake한다.
- Linux `exclusive=True`를 사용하므로 MQTT 런타임과 직접 시험 도구가
  같은 serial 포트를 동시에 열 수 없다.

## 5. 백엔드 MQTT 계약

현재 백엔드 `back/dev`와 대조한 토픽은 다음과 같다.

```text
command : hanbakwi/v1/robots/{robotKey}/command
ack     : hanbakwi/v1/robots/{robotKey}/command/ack
status  : hanbakwi/v1/robots/{robotKey}/status
pose    : hanbakwi/v1/robots/{robotKey}/pose
```

### 5.1 START_PATROL

```json
{
  "schemaVersion": 1,
  "commandId": "UUID",
  "command": "START_PATROL",
  "patrolId": 15,
  "issuedAt": "2026-07-31T16:00:00+09:00",
  "expiresAt": "2026-07-31T16:01:00+09:00"
}
```

현재 처리 결과:

```text
MQTT START_PATROL 수신
→ 선택적으로 AI pipeline 시작
→ Mission target = speed 51, steering 80
→ 상태 PATROLLING
→ command/ack SUCCEEDED
```

### 5.2 STOP_PATROL

```json
{
  "schemaVersion": 1,
  "commandId": "UUID",
  "command": "STOP_PATROL",
  "issuedAt": "2026-07-31T16:00:10+09:00",
  "expiresAt": "2026-07-31T16:01:10+09:00"
}
```

현재 처리 결과:

```text
Mission speed = 0
→ runtime이 STOP 전송
→ 선택적으로 AI pipeline 중지
→ 상태 IDLE
→ command/ack SUCCEEDED
```

ACK 형식:

```json
{
  "schemaVersion": 1,
  "commandId": "UUID",
  "command": "START_PATROL",
  "status": "SUCCEEDED",
  "receivedAt": "2026-07-31T16:00:00+09:00"
}
```

`status`는 `SUCCEEDED`, `REJECTED`, `FAILED` 중 하나다.

## 6. 현재 실행 방법

### 6.1 무구동 preflight

Battery B를 분리한 상태에서:

```bash
cd /home/e103/robot-hw-test
./.venv/bin/python operating_preflight.py
```

정상 결과:

```text
{"stopAck":true,"hello":true,"encoderAck":true,"statusAck":true,"odometry":true,"hardwareStatus":true}
OPERATING_PREFLIGHT_PASS_NO_MOVEMENT
```

### 6.2 서보 포함 제한 주행

로봇을 안전한 바닥에 놓고 이동 공간을 확보한 다음 Battery B를 연결한다.

```bash
cd /home/e103/robot-hw-test
./.venv/bin/python operating_steering_drive_test.py \
  --confirm DRIVE_AREA_CLEAR
```

기본 시험:

```text
PWM 51
80° → 85° → 80° → 75° → 80°
각 구간 600ms
총 powered time 3초
종료 시 STOP
```

범위를 키운 시험:

```bash
./.venv/bin/python operating_steering_drive_test.py \
  --confirm DRIVE_AREA_CLEAR \
  --speed 51 \
  --segment-ms 800 \
  --angles 80,90,80,70,80
```

### 6.3 MQTT 통합 런타임

```bash
cd /home/e103/roki-iot
/home/e103/roki/.venv/bin/python run_integrated.py
```

이 프로세스가 실행 중이면 `operating_preflight.py`, `hw_test.py`,
직접 주행 도구를 동시에 실행하면 안 된다. `Ctrl+C` 종료 시에도 STOP이
전송된다.

카메라 없이 하드웨어만 시험할 때 live `.env`는 다음이어야 한다.

```text
PIPELINE_ENABLED=false
PATROL_DRIVE_SPEED_PWM=51
PATROL_STEERING_DEGREES=80
```

AI 서비스와 결합한 후에만 `PIPELINE_ENABLED=true`로 전환한다.

## 7. 완료한 검증

2026-07-31에 다음 결과를 확인했다.

| 검증 | 결과 |
| --- | --- |
| ESP32 펌웨어 compile | 통과 |
| ESP32 펌웨어 2.2.0 flash | 통과 |
| 운영 프로토콜 preflight | 통과 |
| `robot/roki` unit test | 50개 통과 |
| `robot/roki-iot` unit test | 5개 통과 |
| 상시 runtime handshake | invalid 0, HELLO 1, encoder ACK 1 |
| 실제 TLS MQTT 연결/구독 | 통과 |
| MQTT START_PATROL ACK | SUCCEEDED |
| MQTT STOP_PATROL ACK | SUCCEEDED |
| MQTT 상태 변화 | IDLE → PATROLLING → IDLE |
| Battery B 미감지 이동 차단 | 통과 |
| 종료 후 serial 포트 반환 | 통과 |

테스트 중 실제 자격 증명이나 서비스 토큰은 출력·커밋하지 않는다.

## 8. 아직 완료되지 않은 기능

다음 항목은 검증 완료로 간주하면 안 된다.

1. **거리 기반 자동 종료**
   - 현재 START는 STOP 명령이 올 때까지 주행 목표를 유지한다.
   - 목표 거리 도달 판정과 자동 `STOP_PATROL` 전환은 미구현이다.
2. **pose x/y 발행**
   - 엔코더 누적 거리는 계산하지만 지도 좌표 x/y로 변환하지 않는다.
   - publisher는 가짜 좌표를 보내지 않고 실제 pose를 기다린다.
3. **START ACK의 물리 실행 확인**
   - 현재 SUCCEEDED는 Mission target을 런타임이 수용했다는 의미다.
   - ESP32의 첫 CONTROL ACK까지 기다리는 동기 확인은 미구현이다.
4. **라인센서 단선 진단**
   - `lineValues` 5채널은 발행하지만 물리적 단선 판별이 없어
     펌웨어는 현재 `lineSensor=NORMAL`로 보고한다.
5. **배터리 SOC 보정**
   - 전압→퍼센트 곡선은 근삿값이다.
6. **AI/ROS 골격과 주행 Mission의 단일 프로세스 통합**
   - AI readiness gate와 `run_integrated.py`의 START 처리 흐름은 아직
     결합되지 않았다.
7. **systemd/OTA 정식 활성화**
   - `aiot-robot.service`는 아직 새 MQTT·주행 런타임을 실행하지 않는다.

## 9. 다음 작업 순서

### P0: 실물 시연을 위한 필수 작업

1. `operating_steering_drive_test.py`로 2.2.0 결합 실물 주행을 확인한다.
2. 좌우 엔코더 증가 방향과 실제 전진 방향을 기록한다.
3. `run_integrated.py`를 켠 상태에서 백엔드 START/STOP으로 실물
   주행·정지를 확인한다.
4. START 직후 첫 CONTROL ACK 또는 첫 정상 odometry까지 기다린 후
   MQTT SUCCEEDED를 보내도록 ACK 의미를 강화한다.
5. 엔코더 평균 이동거리 목표를 Mission에 추가하고 도달 즉시 STOP한다.

### P1: 기존 `aiot_robot` 골격과 통합

1. MQTT START 수신 시 AI readiness gate를 확인한다.
2. 허용된 경우에만 AI `ENABLE`과 Mission START를 함께 실행한다.
3. STOP/비상정지/종료 시 Mission STOP을 먼저 실행하고 AI를
   `DISABLE`한다.
4. detection event에 실제 patrolId와 로봇 pose를 결합한다.
5. 중복된 상태 저장소와 프로세스 진입점을 하나로 정리한다.

### P2: 운영·OTA

1. 단일 production entrypoint와 smoke test를 만든다.
2. systemd unit에서 production entrypoint를 실행한다.
3. 서비스 시작 직후에는 무조건 STOP 상태를 유지한다.
4. OTA pre/post-activate smoke에서 serial handshake만 검증하고
   모터 명령은 보내지 않는다.
5. 장애 시 이전 release로 rollback되는지 실장비에서 확인한다.

## 10. 변경 시 지켜야 할 불변 조건

- START 전에 STOP/HELLO/ENCODER_ZERO가 성공해야 한다.
- ESP32 CONTROL heartbeat 간격은 400ms watchdog보다 충분히 짧아야 한다.
- STOP은 어떤 상태와 sequence에서도 전송 가능해야 한다.
- serial 포트 소유자는 한 프로세스뿐이어야 한다.
- 펌웨어 flash 중 Battery B는 분리해야 한다.
- `.env`, MQTT 비밀번호, 서비스 토큰은 Git에 넣지 않는다.
- OTA smoke test는 모터·서보를 움직이지 않는다.
- 가짜 x/y pose를 발행하지 않는다.
- root `robot/src/aiot_robot`가 아직 무구동 골격이라는 사실을 숨기지
  않는다.

## 11. 주요 파일

```text
robot/
├── docs/esp32-mqtt-runtime-handoff.md
├── hardware/
│   ├── firmware/roki_safe_test/roki_safe_test.ino
│   ├── flash_operating_firmware.sh
│   ├── operating_preflight.py
│   └── operating_steering_drive_test.py
├── roki/
│   ├── config/robot.yaml
│   ├── config/serial.yaml
│   ├── mission/mission_controller.py
│   ├── runtime/robot_runtime.py
│   ├── serial_comm/protocol.py
│   ├── serial_comm/serial_manager.py
│   └── scripts/run_runtime.py
└── roki-iot/
    ├── config/settings.py
    ├── integration/runtime_state_backend_adapter.py
    ├── mqtt/client.py
    ├── mqtt/command_handler.py
    ├── mqtt/publisher.py
    └── run_integrated.py
```
