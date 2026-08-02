# RO-KI 안전 하드웨어 테스트 환경

## 현장 캘리브레이션

라인 센서와 엔코더를 실제 주행 전에 한 번만 확정하려면 다음 문서를 먼저 따른다.

- [라인트레이싱 현장 통합 계획](../docs/line-tracing-field-plan.md)
- `jetson_field_audit.sh`: USB, 카메라, ROS 환경을 변경 없이 수집
- `field_calibration.py line-session`: 5채널 순서·검은색 극성·테이프 폭 수집
- `field_calibration.py encoder-manual`: 전원 없이 엔코더 부호와 tick/회전 수집

두 Python 명령은 ESP32에 `STOP`, `HELLO`, `STATUS`, `ENCODER_ZERO`만 보낸다.
모터, 서보, `CONTROL` 명령은 보내지 않는다.

`line-session`은 운영 JSON 펌웨어와 `S1:1 S2:... S5:1` 형식의 라인센서
확인용 펌웨어를 자동으로 구분한다. `encoder-manual`은 엔코더 텔레메트리가 있는
운영 펌웨어 2.2.0에서만 실행되며, 라인센서 전용 펌웨어에서는 안전하게 거부한다.

현재 배선 기준:

- LEFT BTS: RPWM GPIO25, LPWM GPIO26
- RIGHT BTS: RPWM GPIO27, LPWM GPIO33
- 공통 Enable 예정: GPIO13
- LEFT Encoder: C1 GPIO34, C2 GPIO35
- RIGHT Encoder: C1 GPIO36, C2 GPIO39
- Battery B voltage sensor: GPIO32
- PCA9685: SDA GPIO21, SCL GPIO22, 실측 주소 0x60
- MG996R: PCA9685 CH0
- Line sensor 예정: GPIO16/17/18/19/23

## 핵심 안전 특성

- 부팅 시 모터 PWM 4개와 GPIO13 Enable을 LOW로 설정한다.
- 부팅만으로 모터나 서보가 움직이지 않는다.
- 모터는 `ARM MOTORS` 후 5초 안에 유효한 단발 명령이 있어야 한다.
- 모터 출력은 최대 25%, 최대 500ms로 제한한다.
- 단발 출력 종료 후 자동 정지하고 자동으로 disarm한다.
- 직진 주행 시 LEFT B와 RIGHT A를 동시에 사용한다.
- 후진 주행 시 LEFT A와 RIGHT B를 동시에 사용한다.
- 연속 주행 명령은 400ms 안에 갱신되지 않으면 자동 정지한다.
- 직진·후진 시연은 최대 20%로 제한하고 조향 서보를 사용하지 않는다.
- 서보 최초 시험 범위는 95~105도로 제한한다.
- 서보 출력은 1.5초 후 자동으로 꺼진다.
- 잘못된 명령, 긴 명령, 타임아웃에서 정지한다.

하드웨어적으로 가장 확실한 정지를 위해 최종적으로 BTS 네 Enable을 GPIO13에
연결하고 GPIO13-그라운드 사이에 10kΩ 풀다운을 추가하는 것이 권장된다.

## 돌아온 뒤 실행 순서

모든 첫 구동 시험은 바퀴를 바닥에서 띄우고 전원 차단 담당자가 Battery B
커넥터를 잡은 상태에서 수행한다.

### 1. Battery B 분리 상태 사전점검

```bash
cd ~/robot-hw-test
./preflight.sh
```

### 2. 센서 상태 감시

Battery B를 연결하지 않은 상태에서도 엔코더를 손으로 돌리고 라인 입력을
확인할 수 있다.

```bash
./.venv/bin/python hw_test.py monitor --seconds 20
```

### 3. Battery B 연결 후 왼쪽 모터 단발 시험

```bash
./.venv/bin/python hw_test.py motor \
  --side L --channel A --speed 15 --ms 250 \
  --confirm WHEELS_OFF_GROUND
```

방향 A/B는 전진/후진을 뜻하지 않는다. 관찰 후 극성을 기록한다.

### 4. 오른쪽 모터 시험

```bash
./.venv/bin/python hw_test.py motor \
  --side R --channel A --speed 15 --ms 250 \
  --confirm WHEELS_OFF_GROUND
```

### 5. 엔코더 확인

각 모터 펄스 후 출력되는 `leftEncoder`, `rightEncoder` 값이 변하는지 확인한다.
반대쪽 값이 변하거나 값이 0이면 엔코더 배선을 점검한다.

### 6. 전압센서 확인

`STATUS`의 `batteryVoltage`가 멀티미터로 측정한 Battery B 전압과 비슷한지
확인한다. 오차가 있으면 분압비를 보정한다.

### 7. PCA9685와 서보 시험

먼저 `I2C_SCAN` 결과에 `"60"`이 나타나는지 확인한다. `"70"`은 PCA9685의
ALLCALL 주소이므로 장치 주소로 사용하지 않는다. 서보혼과 조향 링크가
걸리지 않는 상태에서만 실행한다.

```bash
./.venv/bin/python hw_test.py servo \
  --angle 100 \
  --confirm LINKAGE_CLEAR
```

이후 99, 101, 98, 102 순서로 조금씩 범위를 넓힌다. 최초 시험은 95~105도
밖으로 나가지 않는다.

### 비상 정지

```bash
./.venv/bin/python hw_test.py estop
```

소프트웨어 정지는 물리적 전원 차단을 대신하지 않는다. 명령하지 않은 동작,
지속 회전, 냄새, 연기, 발열, 서보 버징이 있으면 Battery B를 즉시 분리한다.

## 직진·후진 원격 시연

이 기능은 조향 서보를 전혀 명령하지 않는다. 조향을 정면에 고정한 상태에서
충분히 넓은 직선 구간에서만 사용한다. ESP32 펌웨어 1.2.0 이상이 필요하다.

```bash
cd ~/robot-hw-test
./start_drive_demo.sh
```

키 조작:

- `W`: 전진 유지
- `S`: 후진 유지
- `Space` 또는 `X`: 정지
- `Q`: 정지 후 종료

키보드 프로그램이 400ms 이상 명령을 갱신하지 못하면 ESP32가 자체적으로
정지한다. 전진과 후진을 바로 바꾸지 않고 중간에 350ms 정지한다.

## 조향 중앙 미세 시험

PCA9685 CH0와 Battery B 전압을 확인한 뒤 서보를
`80 → 85 → 80 → 75 → 80` 순서로만 움직인다. 각 각도는 약 1초 유지한 뒤
출력을 끈다.

```bash
cd ~/robot-hw-test
./.venv/bin/python hw_test.py servo-mini --confirm LINKAGE_CLEAR
```

75도 또는 85도에서 움직이지 않고 버징하거나 링크가 걸리면 전원을 차단하고
서보혼을 80도 기준으로 다시 체결한다. 넓은 `servo-sweep`은 이 미세 시험이
양방향으로 통과한 뒤에만 사용한다.

80도 아래쪽만 5도 간격으로 확인하려면 다음을 사용한다.

```bash
cd ~/robot-hw-test
./.venv/bin/python hw_test.py servo-low --confirm LINKAGE_CLEAR
```

순서는 `80 → 75 → 70 → 65 → 70 → 75 → 80`이며, 65도보다 낮게 내려가지는
않는다. 버징이나 물리적 걸림이 있으면 `Ctrl+C`로 중단한다.
