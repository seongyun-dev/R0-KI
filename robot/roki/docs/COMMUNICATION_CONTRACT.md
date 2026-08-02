# RO-KI ESP32 ↔ Jetson Serial 계약

이 문서는 ESP32와 Jetson 내부 USB Serial JSON Lines 계약만 정의한다.
Jetson ↔ Backend MQTT/REST 계약은 이 문서의 범위가 아니다.

## 확정 하드웨어 핀

- RIGHT BTS7960 RPWM: GPIO27
- RIGHT BTS7960 LPWM: GPIO33
- GPIO14: 미사용
- PCA9685 SDA/SCL: GPIO21/GPIO22
- PCA9685 I2C 주소: 미검증. 펌웨어의 `PCA9685_I2C_ADDRESS`는 기존
  하드웨어 테스트 값 `0x60`을 유지하며 실제 장치에서 확인하기 전까지
  확정값으로 취급하지 않는다.

## ESP32 → Jetson

각 메시지는 JSON 객체 하나와 줄바꿈(`\n`)으로 전송한다.

```json
{"type":"odometry","seq":1042,"uptimeMs":523010,"leftTicks":18240,"rightTicks":18192}
```

```json
{"type":"hardwareStatus","battery":71.11,"batteryVoltage":11.82,"motor":"NORMAL","lineSensor":"NORMAL","lineValues":[0,0,1,0,0]}
```

- `battery`: SoC 퍼센트(0~100). 현재는 3S LiPo 9.9V=0%, 12.6V=100%의
  임시 선형 환산값이며 실측 calibration 후 교체한다. 센서 오류 시 Jetson은
  `null`도 허용한다.
- `batteryVoltage`: GPIO32 ADC와 현재 분압비로 계산한 팩 전압. ADC/분압
  보정 전에는 참고 측정값이다.
- `motor`, `lineSensor`: `NORMAL`, `FAULT`, `DISCONNECTED` 중 하나다.
- `lineValues`: L2, L1, C, R1, R2 순서의 디지털 원시값이다.

`HELLO`, `ACK`, `ERROR`와 Jetson의 `CONTROL`, `STOP`, `STATUS`,
`ENCODER_ZERO` 제어 메시지는 기존 protocol version 1 계약을 유지한다.
