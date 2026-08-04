# 라인트레이싱 1차 현장 시험

> [!WARNING]
> **폐기된 이전 시험 절차**: 금요일 시연과 운영 주행에서는 라인센서를 사용하지 않는다.
> 현재 기준은 사전 제작 지도, LiDAR localization, Nav2 waypoint, encoder odometry다.
> 이 문서는 과거 센서 진단 기록으로만 보존하며 로봇 서비스나 ESP32를 이 절차에 맞춰
> 변경하지 않는다.

이 시험의 목적은 목적지 판정이나 MQTT 통합이 아니라, 검은 테이프를 따라
저속으로 조향하는지와 라인 유실 시 즉시 멈추는지만 확인하는 것이다.

## 확정 입력

- 검은색: `0`, 바닥: `1`
- 정상 중앙선: `11011`
- 서보: `60도=왼쪽`, `80도=정면`, `100도=오른쪽`
- 휠 지름: `65 mm`
- 바퀴 1회전: 설정값 `329 ticks/rev`
  - LEFT 평균 `329.0`, RIGHT 평균 `328.0`
  - 약 `0.621 mm/tick`, 약 `1611 ticks/m`
- 넓은 목적지 마커는 아직 일반 선과 확실히 구분되지 않으므로 1차 시험에서 끈다.

## 바닥 준비

1. 직선 검은 테이프 코스를 짧게 만든다. 첫 시험은 1 m 이내가 적당하다.
2. 로봇 전방 라인센서 중앙에 테이프가 오도록 놓는다.
3. 앞·뒤·좌·우에 사람과 물건이 없는지 확인한다.
4. 로봇을 손으로 즉시 들어 올릴 수 있는 위치에서 실행한다.
5. 다른 `hw_test.py`, `mqtt.publisher`, Robot 서비스가 Serial 포트를 잡고 있지 않아야 한다.

## Jetson 실행

Battery B는 코스 배치와 명령 입력을 마친 뒤 연결한다. 아래 명령은 3초 카운트다운
후 최대 5초 동안 PWM 45, 중앙 기준 최대 `±20도`로 동작하며 목적지 마커
판정은 사용하지 않는다.

```bash
cd ~/robot-hw-test
./.venv/bin/python line_follow_field_test.py \
  --port /dev/roki_esp32 \
  --confirm LINE_COURSE_CLEAR \
  --seconds 5 \
  --speed 45 \
  --destination-min-black 0
```

정상이면 `line=[...] mode=FOLLOWING speed=45 steering=...`가 출력되고 마지막에
`FIELD_TEST_STOPPED reason=TIME_LIMIT`가 표시된다.

## 판정과 중단

- 중앙선에서 조향이 거의 `80`이면 정상이다.
- 테이프가 왼쪽에 있을 때 조향이 `80`보다 작아져야 하며 끝 센서는 `60`이다.
- 테이프가 오른쪽에 있을 때 조향이 `80`보다 커져야 하며 끝 센서는 `100`이다.
- 반대로 꺾이면 다음 시험에서만 `--steering-sign -1`을 추가한다.
- 라인을 잃으면 첫 프레임부터 속도 `0`, 두 프레임째 `LINE_LOST`로 종료해야 한다.
- 이상 동작 시 로봇을 들어 올리고 Battery B를 분리한다. `Ctrl+C`가 발생해도 종료 처리에서 STOP을 세 번 전송한다.

로그는 `~/robot-hw-test/logs/line-follow/field-test.jsonl`에 남는다.
