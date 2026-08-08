# RO-KI / RO-KI-IOT 프로젝트 설명서

이 문서는 이 프로젝트가 무엇을 하는지, 각 파일이 무엇을 담당하는지, 데이터가 어떻게 흐르는지 초보자도 이해할 수 있게 정리한 문서입니다.

---

## 1. 이 프로젝트는 무엇을 하는가?

이 프로젝트는 로봇이 움직이면서 상태를 보고, 장애물을 감지하고, 그 정보를 MQTT나 ROS2를 통해 외부 시스템에 전달하는 구조입니다.

간단히 말하면:

1. 로봇의 설정을 읽는다.
2. 하드웨어(ESP32, 카메라, LiDAR 등)로부터 정보를 받는다.
3. 그 정보를 상태 객체로 저장한다.
4. MQTT나 ROS2로 외부에 전달한다.

즉, 이 프로젝트는 “로봇의 눈과 귀, 상태 관리, 통신”을 연결하는 시스템입니다.

---

## 2. 프로젝트를 두 부분으로 나누면

### A. roki
이 폴더는 “메인 로봇 애플리케이션” 쪽입니다.

여기서는 주로:
- 로봇 설정 관리
- MQTT 통신
- 시리얼 통신
- 안전 제어
- 상태 정보 발행

을 담당합니다.

### B. roki-iot
이 폴더는 “하드웨어 연결/IoT 연결” 쪽입니다.

여기서는 주로:
- ESP32로부터 시리얼 데이터 받기
- 하드웨어 상태 저장
- MQTT로 상태 보내기

를 담당합니다.

---

## 3. 데이터는 어떻게 흐르는가?

가장 핵심적인 흐름은 아래와 같습니다.

1. 설정 파일 읽기
   - YAML 설정 파일을 읽는다.
   - 예: 로봇 이름, MQTT 주소, 시리얼 포트 등

2. 시리얼로 데이터 받기
   - ESP32가 보내는 메시지를 받는다.
   - 예: 배터리 상태, 모터 상태, 엔코더 값

3. 상태 객체로 저장
   - 받은 데이터를 구조화된 객체로 보관한다.
   - 예: 배터리, 모터, 라인센서, 위치 정보

4. MQTT로 전송
   - 저장된 상태를 JSON 형태로 만들어 MQTT 토픽으로 보낸다.

5. ROS2로도 연결 가능
   - ROS2 노드가 장애물 정보 등을 받아 MQTT로 전달한다.

---

## 4. 어떤 데이터형식이 나오나?

### 4-1 YAML 설정 파일
YAML은 사람이 읽기 쉬운 설정 파일 형식입니다.

예시:

```yaml
robot:
  id: "ROKI-01"
  name: "RO-KI"
```

이 파일은 로봇의 이름, 통신 포트, MQTT 정보 같은 것을 담습니다.

### 4-2 시리얼 데이터
시리얼은 문자열 기반으로 주고받습니다.

예시:

```text
{"type":"hardwareStatus","battery":82.5,"motor":"NORMAL","lineSensor":"NORMAL"}
```

이 데이터는 ESP32가 Jetson으로 보내는 하드웨어 상태입니다.

### 4-3 MQTT JSON payload
MQTT는 JSON 형태로 상태를 보냅니다.

예시:

```json
{
  "schemaVersion": 1,
  "robotKey": "ROKI-01",
  "battery": 82.5,
  "state": "IDLE",
  "motor": "NORMAL",
  "camera": "NORMAL",
  "lidar": "NORMAL",
  "lineSensor": "NORMAL",
  "obstacle": {
    "status": "CLEAR",
    "reasonMessage": "전방 주행 경로가 확보되었습니다."
  },
  "timestamp": "2026-07-31T10:00:00+09:00"
}
```

### 4-4 ROS2 메시지
ROS2는 보통 문자열이나 메시지 객체를 사용합니다.

예시:

```json
{"status":"STOP","reasonMessage":"장애물이 감지되었습니다."}
```

이 값이 ROS2 노드로 들어와서 MQTT 상태로 바뀝니다.

---

## 5. 폴더별 파일 설명

## 5-1 [roki/config](roki/config)
이 폴더는 로봇이 동작하기 위한 설정값을 담고 있습니다.

- [roki/config/robot.yaml](roki/config/robot.yaml)
  - 로봇 이름, 속도 제한, 기본 상태 같은 정보를 담습니다.

- [roki/config/serial.yaml](roki/config/serial.yaml)
  - 시리얼 포트, 통신 속도, 재연결 간격을 담습니다.

- [roki/config/mqtt.yaml](roki/config/mqtt.yaml)
  - MQTT 브로커 주소, 포트, QoS 같은 정보를 담습니다.

- [roki/config/lidar.yaml](roki/config/lidar.yaml)
  - LiDAR 설정을 담습니다.

- [roki/config/ai.yaml](roki/config/ai.yaml)
  - AI 모델 경로 같은 설정을 담습니다.

### 역할 요약
- 설정값을 한 곳에 모아두는 역할입니다.
- 코드에서 하드코딩하지 않도록 도와줍니다.

---

## 5-2 [roki/common](roki/common)

- [roki/common/config_loader.py](roki/common/config_loader.py)
  - YAML 설정 파일을 읽어오는 공용 함수들을 모아둔 파일입니다.
  - “설정 파일을 읽는 도우미”라고 보면 됩니다.

---

## 5-3 [roki/mqtt](roki/mqtt)
이 폴더는 MQTT 통신을 담당합니다.

- [roki/mqtt/client.py](roki/mqtt/client.py)
  - MQTT 브로커와 연결하고 메시지를 보내는 실질적인 통신 도구입니다.

- [roki/mqtt/config.py](roki/mqtt/config.py)
  - MQTT 설정 객체를 정의합니다.

- [roki/mqtt/models.py](roki/mqtt/models.py)
  - 로봇 위치, 로봇 상태 같은 데이터를 데이터클래스로 정의합니다.

- [roki/mqtt/payloads.py](roki/mqtt/payloads.py)
  - MQTT로 보낼 payload 형태를 관리합니다.

- [roki/mqtt/publisher.py](roki/mqtt/publisher.py)
  - 로봇 상태를 MQTT로 발행하는 역할입니다.
  - 배터리, 상태, 장애물 정보를 JSON으로 만들어 보냅니다.

- [roki/mqtt/subscriber.py](roki/mqtt/subscriber.py)
  - MQTT 메시지를 받는 쪽입니다.
  - 현재는 수신용 구조로 보이며, 실제 동작은 확장 가능성이 있습니다.

- [roki/mqtt/topics.py](roki/mqtt/topics.py)
  - 어떤 토픽으로 보낼지 정해둔 파일입니다.

### 역할 요약
- 외부 시스템과 통신하는 “문 앞” 역할입니다.
- 상태 정보를 JSON으로 만들어 인터넷/브로커로 보냅니다.

---

## 5-4 [roki/serial_comm](roki/serial_comm)
이 폴더는 시리얼 통신을 담당합니다.

- [roki/serial_comm/serial_manager.py](roki/serial_comm/serial_manager.py)
  - 시리얼 포트를 열고, 데이터를 읽고, 데이터를 쓰는 기본 기능을 담당합니다.

- [roki/serial_comm/device_finder.py](roki/serial_comm/device_finder.py)
  - 어떤 USB 포트가 ESP32인지 찾는 역할을 합니다.

- [roki/serial_comm/protocol.py](roki/serial_comm/protocol.py)
  - Jetson과 ESP32가 주고받는 메시지 형식을 정의합니다.
  - 예: 명령 문자열, 상태 문자열, 엔코더 값 등을 해석합니다.

- [roki/serial_comm/serial_controller.py](roki/serial_comm/serial_controller.py)
  - 시리얼 제어 로직을 담당하는 파일로 보입니다.

### 역할 요약
- 로봇과 하드웨어(ESP32 등)를 연결하는 통로입니다.
- 문자열 기반 데이터를 주고받습니다.

---

## 5-5 [roki/safety](roki/safety)
이 폴더는 안전 관련 기능입니다.

- [roki/safety/emergency_stop.py](roki/safety/emergency_stop.py)
  - 긴급 정지 로직을 넣을 수 있는 파일입니다.

- [roki/safety/obstacle_guard.py](roki/safety/obstacle_guard.py)
  - 장애물 감지와 정지 로직을 담당할 예정인 파일입니다.

- [roki/safety/watchdog.py](roki/safety/watchdog.py)
  - 시스템이 멈추지 않았는지 감시하는 파일입니다.

### 역할 요약
- 로봇이 위험 상황에서 안전하게 멈추도록 돕습니다.

---

## 5-6 [roki/state](roki/state)
이 폴더는 로봇의 현재 상태를 저장하는 역할입니다.

- [roki/state/robot_state.py](roki/state/robot_state.py)
  - 현재는 비어 있는 파일이며, 상태 저장 구조를 확장할 위치입니다.

### 역할 요약
- “지금 로봇이 어떤 상태인가?”를 기억하는 공간입니다.

---

## 5-7 [roki/scripts](roki/scripts)
이 폴더는 테스트와 실행용 스크립트입니다.

> 실행 진입점은 이 폴더가 아니라
> [roki-iot/run_integrated.py](../roki-iot/run_integrated.py) 입니다.
> 운영 서비스(`aiot-robot`)가 그 파일을 띄웁니다.

- [roki/scripts/test_serial.py](roki/scripts/test_serial.py)
  - 시리얼 통신 테스트용입니다.

- [roki/scripts/test_mqtt.py](roki/scripts/test_mqtt.py)
  - MQTT 통신 테스트용입니다.

- [roki/scripts/test_config.py](roki/scripts/test_config.py)
  - 설정 파일이 정상인지 확인하는 테스트용입니다.

### 역할 요약
- 개발 중에 기능을 확인하는 도구입니다.

---

## 6. [roki-iot](roki-iot) 폴더의 핵심 파일들

## 6-1 [roki-iot/config](roki-iot/config)

- [roki-iot/config/settings.py](roki-iot/config/settings.py)
  - MQTT 호스트, 포트, 로봇 키 같은 환경 설정을 관리합니다.
  - 이 파일은 “설정을 읽는 책임만 있는 모듈”입니다.

---

## 6-2 [roki-iot/esp32_serial](roki-iot/esp32_serial)
이 폴더는 ESP32와의 통신을 담당합니다.

- [roki-iot/esp32_serial/connection.py](roki-iot/esp32_serial/connection.py)
  - 시리얼 포트 연결을 담당합니다.

- [roki-iot/esp32_serial/frame_decoder.py](roki-iot/esp32_serial/frame_decoder.py)
  - 시리얼에서 잘려 들어온 JSON 프레임을 조합합니다.

- [roki-iot/esp32_serial/message_parser.py](roki-iot/esp32_serial/message_parser.py)
  - JSON 문자열을 해석해 내부 메시지 객체로 바꿉니다.

- [roki-iot/esp32_serial/models.py](roki-iot/esp32_serial/models.py)
  - 하드웨어 상태, odometry, command ack 같은 데이터 구조를 정의합니다.

- [roki-iot/esp32_serial/reader.py](roki-iot/esp32_serial/reader.py)
  - 시리얼 데이터를 읽고 최신 상태를 저장하는 핵심 클래스입니다.

### 역할 요약
- ESP32로부터 데이터를 받는 “입구”입니다.
- 여기서 들어온 값이 상태 저장과 MQTT 발행의 시작점이 됩니다.

---

## 6-3 [roki-iot/mqtt](roki-iot/mqtt)

- [roki-iot/mqtt/client.py](roki-iot/mqtt/client.py)
  - MQTT 브로커 연결과 발행을 담당합니다.

- [roki-iot/mqtt/payload_builder.py](roki-iot/mqtt/payload_builder.py)
  - 내부 상태 객체를 MQTT payload로 바꿉니다.

- [roki-iot/mqtt/publisher.py](roki-iot/mqtt/publisher.py)
  - 실제로 상태를 발행하는 실행 모듈입니다.

### 역할 요약
- 하드웨어 상태를 외부로 보내는 “출구”입니다.

---

## 6-4 [roki-iot/state](roki-iot/state)

- [roki-iot/state/models.py](roki-iot/state/models.py)
  - PoseState, RobotStatusState 같은 상태 모델을 정의합니다.

- [roki-iot/state/robot_state_store.py](roki-iot/state/robot_state_store.py)
  - 현재 로봇의 위치, 상태를 저장하는 저장소입니다.

- [roki-iot/state/robot_state.py](roki-iot/state/robot_state.py)
  - 예전 형태의 상태 저장 코드로 보이며, 현재 구조와는 조금 다르게 동작할 수 있습니다.

### 역할 요약
- “로봇의 현재 상태를 메모리에 기록하는 메인 저장소”입니다.

---

## 6-5 [roki-iot/serial_reader.py](roki-iot/serial_reader.py)
이 파일은 ESP32와 USB 시리얼 통신을 직접 처리하는 중심 파일입니다.

- JSON 프레임을 모아서 처리합니다.
- 최신 하드웨어 상태를 갱신합니다.
- 이후 MQTT publisher가 그 값을 사용합니다.

### 핵심 의미
- 이 파일이 “입력”의 중심입니다.

---

## 7. 좌표는 어디서 나오나?

좌표는 주로 위치 정보와 관련된 데이터로 다뤄집니다.

### 현재 코드에서의 의미
- [roki-iot/esp32_serial/message_parser.py](roki-iot/esp32_serial/message_parser.py)
  - odometry 메시지를 해석합니다.

- [roki-iot/esp32_serial/models.py](roki-iot/esp32_serial/models.py)
  - odometry 데이터 구조를 정의합니다.

- [roki-iot/state/models.py](roki-iot/state/models.py)
  - PoseState라는 위치 객체를 정의합니다.

즉, 좌표는 “odometry 메시지”를 통해 들어오는 구조로 보입니다.

실제로는:
1. 시리얼로 odometry 데이터 받기
2. 파서가 그것을 해석하기
3. PoseState에 저장하기
4. MQTT로 publish하기

이 흐름으로 이어집니다.

---

## 8. 이 프로젝트에서 가장 중요한 파일 5개

아래 5개는 프로젝트의 핵심 흐름을 이해할 때 가장 중요합니다.

1. [roki-iot/run_integrated.py](../roki-iot/run_integrated.py)
   - 실행 진입점입니다. `aiot-robot` 서비스가 이 파일을 띄웁니다.

2. [roki/serial_comm/serial_manager.py](roki/serial_comm/serial_manager.py)
   - 시리얼 통신의 기본 기능입니다.

3. [roki/mqtt/publisher.py](roki/mqtt/publisher.py)
   - 상태를 MQTT로 보내는 핵심입니다.

4. [roki-iot/esp32_serial/reader.py](roki-iot/esp32_serial/reader.py)
   - ESP32로부터 데이터를 받는 핵심입니다.

5. [roki-iot/state/robot_state_store.py](roki-iot/state/robot_state_store.py)
   - 상태를 저장하는 핵심입니다.

---

## 9. 초보자를 위한 한 줄 요약

- [roki](roki) : 로봇의 메인 로직과 통신/상태 관리
- [roki-iot](roki-iot) : ESP32와 하드웨어를 연결하는 IoT/시리얼 모듈
- 설정은 YAML로 관리한다.
- 하드웨어 데이터는 시리얼로 받는다.
- 상태는 객체로 저장한다.
- MQTT로 외부에 보낸다.

---

## 10. 참고 사항

이 프로젝트에는 일부 파일이 비어 있거나, 백업 파일이 존재합니다.

예:
- [roki/state/robot_state.py](roki/state/robot_state.py)
- [roki/safety/obstacle_guard.py](roki/safety/obstacle_guard.py)

이 경우 아직 구현이 덜 되었거나, 향후 확장할 준비가 된 파일입니다.

즉, 이 프로젝트는 “완성형”보다는 “구조를 만드는 중인 로봇 시스템”에 가깝습니다.

---

## 11. 읽는 팁

처음 볼 때는 아래 순서로 보면 이해가 쉽습니다.

1. [roki-iot/run_integrated.py](../roki-iot/run_integrated.py) 읽기
2. [roki/serial_comm/serial_manager.py](roki/serial_comm/serial_manager.py) 읽기
3. [roki/mqtt/publisher.py](roki/mqtt/publisher.py) 읽기
4. [roki-iot/esp32_serial/reader.py](roki-iot/esp32_serial/reader.py) 읽기
5. [roki-iot/state/robot_state_store.py](roki-iot/state/robot_state_store.py) 읽기

이 순서대로 보면 “입력 → 저장 → 출력” 흐름이 자연스럽게 보입니다.
