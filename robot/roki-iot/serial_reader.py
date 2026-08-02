"""
ESP32와 Jetson 사이의 USB Serial 통신 모듈.

주요 역할:
1. ESP32 Serial 포트 연결 및 종료
2. ESP32 JSON 메시지 수신
3. 최신 하드웨어 상태 저장
4. Jetson 명령 전송

현재 ESP32의 기존 상태 형식과
향후 hardwareStatus 형식을 모두 지원한다.
"""

from __future__ import annotations

import json
import time
from json import JSONDecodeError
from threading import Event, Lock, Thread
from typing import Any

import serial
from state.models import HardwareState
from state.robot_state_store import RobotStateStore


class JsonFrameBuffer:
    """
    Serial에서 잘려 들어온 JSON 문자열을 누적한다.

    완성된 중괄호 객체만 추출하여 반환하고,
    아직 완성되지 않은 데이터는 다음 수신까지 보관한다.
    """

    MAX_BUFFER_SIZE = 16_384

    def __init__(self) -> None:
        self._buffer = ""

    def clear(self) -> None:
        """현재 누적된 문자열을 제거한다."""

        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        """
        문자열 조각을 버퍼에 추가하고
        완성된 JSON 객체들을 반환한다.
        """

        if not text:
            return []

        self._buffer += text
        self._limit_buffer_size()

        frames, remaining = self._extract_json_objects(
            self._buffer
        )

        self._buffer = remaining

        return frames

    def _limit_buffer_size(self) -> None:
        """깨진 데이터가 무한히 누적되지 않게 제한한다."""

        if len(self._buffer) <= self.MAX_BUFFER_SIZE:
            return

        latest_start = self._buffer.rfind("{")

        if latest_start == -1:
            self._buffer = ""
            return

        self._buffer = self._buffer[latest_start:]

    @staticmethod
    def _extract_json_objects(
        source: str,
    ) -> tuple[list[str], str]:
        """
        문자열에서 완성된 JSON 객체를 추출한다.

        JSON 문자열 내부의 중괄호는 구조로 판단하지 않는다.
        """

        frames: list[str] = []

        object_start: int | None = None
        brace_depth = 0
        inside_string = False
        escape_next = False

        for index, character in enumerate(source):
            if object_start is None:
                if character != "{":
                    continue

                object_start = index
                brace_depth = 1
                inside_string = False
                escape_next = False
                continue

            if inside_string:
                if escape_next:
                    escape_next = False
                    continue

                if character == "\\":
                    escape_next = True
                    continue

                if character == '"':
                    inside_string = False

                continue

            if character == '"':
                inside_string = True
                continue

            if character == "{":
                brace_depth += 1
                continue

            if character != "}":
                continue

            brace_depth -= 1

            if brace_depth != 0:
                continue

            frame = source[object_start:index + 1]
            frames.append(frame)

            object_start = None
            inside_string = False
            escape_next = False

        if object_start is None:
            return frames, ""

        return frames, source[object_start:]


class ESP32SerialReader:
    """
    ESP32 Serial 메시지를 수신하고
    가장 최신 하드웨어 상태를 관리한다.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        timeout_seconds: float = 0.2,
        debug: bool = False,
        state_store: RobotStateStore | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.debug = debug
        self.state_store = state_store

        self._serial: serial.Serial | None = None
        self._thread: Thread | None = None

        # 스레드 종료 요청을 안전하게 공유한다.
        self._stop_event = Event()

        # 상태 읽기와 쓰기를 보호한다.
        self._status_lock = Lock()

        # 여러 곳에서 동시에 명령을 보내는 경우를 보호한다.
        self._write_lock = Lock()

        # 잘려 들어온 JSON을 복원하는 버퍼다.
        self._frame_buffer = JsonFrameBuffer()

        self._latest_status: dict[str, Any] = {
            "battery": None,
            "motor": "DISCONNECTED",
            "lineSensor": "DISCONNECTED",
        }

    def start(self) -> None:
        """
        Serial 포트를 열고 수신 스레드를 시작한다.

        이미 실행 중이면 중복 실행하지 않는다.
        """

        if self.is_running():
            return

        self._open_serial_port()

        self._frame_buffer.clear()
        self._stop_event.clear()

        self._thread = Thread(
            target=self._read_loop,
            name="esp32-serial-reader",
            daemon=True,
        )
        self._thread.start()

        print(
            f"[SERIAL] 연결 완료: "
            f"{self.port} @ {self.baudrate}"
        )

    def stop(self) -> None:
        """수신 스레드와 Serial 포트를 종료한다."""

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._serial is not None and self._serial.is_open:
            self._serial.close()

        self._serial = None

        print("[SERIAL] 연결 종료")

    def is_running(self) -> bool:
        """Serial 수신 스레드가 실행 중인지 반환한다."""

        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop_event.is_set()
        )

    def get_latest_status(self) -> dict[str, Any]:
        """
        ESP32에서 받은 최신 하드웨어 상태를 반환한다.

        복사본을 반환하여 외부 코드가
        내부 상태를 직접 수정하지 못하게 한다.
        """

        with self._status_lock:
            return self._latest_status.copy()

    def send_command(
        self,
        command: str,
        **parameters: Any,
    ) -> None:
        """
        Jetson 명령을 ESP32에 JSON 한 줄로 전송한다.

        예:
        reader.send_command("START_PATROL")

        reader.send_command(
            "START_PATROL",
            patrolId=15,
        )
        """

        serial_port = self._require_open_serial()

        payload: dict[str, Any] = {
            "type": "command",
            "command": command,
        }

        payload.update(parameters)

        message = (
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

        with self._write_lock:
            serial_port.write(message.encode("utf-8"))
            serial_port.flush()

        print(
            "[COMMAND] Jetson → ESP32: "
            f"{message.strip()}"
        )

    def _open_serial_port(self) -> None:
        """Serial 포트를 열고 ESP32 재부팅을 기다린다."""

        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout_seconds,
        )

        # ESP32는 Serial 포트 연결 시 재부팅될 수 있다.
        time.sleep(1.0)

        # 삭제
        # self._serial.reset_input_buffer()

    def _read_loop(self) -> None:
        """Serial 데이터를 반복해서 읽고 처리한다."""

        while not self._stop_event.is_set():
            serial_port = self._serial

            if serial_port is None:
                break

            try:
                raw_data = self._read_available_data(
                    serial_port
                )
            except serial.SerialException as error:
                print(f"[SERIAL ERROR] {error}")
                self._stop_event.set()
                break

            if not raw_data:
                continue

            text = raw_data.decode(
                "utf-8",
                errors="ignore",
            )

            frames = self._frame_buffer.feed(text)

            for frame in frames:
                self._process_frame(frame)

    @staticmethod
    def _read_available_data(
        serial_port: serial.Serial,
    ) -> bytes:
        """
        현재 수신 가능한 Serial 데이터를 읽는다.

        버퍼에 데이터가 없다면 1바이트 읽기를 요청하고,
        timeout 동안 기다린다.
        """

        read_size = max(
            1,
            serial_port.in_waiting,
        )

        return serial_port.read(read_size)

    def _process_frame(self, frame: str) -> None:
        """완성된 JSON 프레임 하나를 처리한다."""

        try:
            data = json.loads(frame)
        except JSONDecodeError:
            print(f"[SERIAL SKIP] 잘못된 JSON: {frame}")
            return

        if not isinstance(data, dict):
            print(
                "[SERIAL SKIP] JSON 최상위 값이 "
                "객체가 아닙니다."
            )
            return

        message_type = data.get("type")

        if message_type == "commandAck":
            self._handle_command_ack(data)
            return

        if message_type == "hardwareStatus":
            self._handle_hardware_status(data)
            return

        # 현재 ESP32 테스트 코드와의 임시 호환이다.
        if self._is_legacy_status(data):
            self._handle_legacy_status(data)
            return

        # 추후 엔코더 기능에서 사용한다.
        if message_type == "odometry":
            self._handle_odometry(data)
            return

        print(f"[SERIAL SKIP] 알 수 없는 메시지: {data}")

    def _handle_hardware_status(
        self,
        data: dict[str, Any],
    ) -> None:
        """
        최종 hardwareStatus 메시지를 처리한다.

        예상 형식:
        {
          "type": "hardwareStatus",
          "battery": 82.5,
          "motor": "NORMAL",
          "lineSensor": "NORMAL"
        }
        """

        required_keys = (
            "battery",
            "motor",
            "lineSensor",
        )

        if not all(key in data for key in required_keys):
            print(
                "[SERIAL SKIP] hardwareStatus "
                f"필수 필드 누락: {data}"
            )
            return

        status = {
            "battery": data["battery"],
            "motor": data["motor"],
            "lineSensor": data["lineSensor"],
        }

        self._save_status(status)
        self._update_state_store(status)

    def _handle_legacy_status(
        self,
        data: dict[str, Any],
    ) -> None:
        """
        현재 ESP32의 기존 메시지 형식을 처리한다.

        예상 형식:
        {
          "battery": 0.0,
          "motor": "NORMAL",
          "state": "PATROLLING"
        }

        state는 현재 MQTT Publisher와의
        임시 호환을 위해 유지한다.
        """

        status = {
            "battery": data["battery"],
            "motor": data["motor"],
            "lineSensor": data.get(
                "lineSensor",
                "DISCONNECTED",
            ),
            "state": data["state"],
        }

        self._save_status(status)
        self._update_state_store(status)

    def _update_state_store(
        self,
        status: dict[str, Any],
    ) -> None:
        """
        ESP32 하드웨어 상태를 RobotStateStore에 반영한다.

        state 필드는 Jetson이 관리하므로 하드웨어 상태만 갱신한다.
        """

        if self.state_store is None:
            return

        hardware = HardwareState(
            battery=status["battery"],
            motor=status["motor"],
            line_sensor=status["lineSensor"],
        )

        self.state_store.update_hardware(hardware)

    def _save_status(
        self,
        status: dict[str, Any],
    ) -> None:
        """
        최신 하드웨어 상태를 저장한다.

        이전 상태와 달라졌을 때만 로그를 출력한다.
        """

        with self._status_lock:
            previous_status = self._latest_status
            self._latest_status = status

        if status == previous_status:
            return

        print(
            "[HARDWARE STATUS] ESP32 → Jetson: "
            f"{status}"
        )

    def _handle_command_ack(
        self,
        data: dict[str, Any],
    ) -> None:
        """ESP32 명령 처리 결과를 출력한다."""

        print(f"[ACK] ESP32 → Jetson: {data}")

    def _handle_odometry(
        self,
        data: dict[str, Any],
    ) -> None:
        """
        엔코더 Odometry 메시지를 처리한다.

        현재는 디버그 로그만 제공한다.
        ROS2 Odometry 연동 단계에서 저장소를 추가한다.
        """

        if not self.debug:
            return

        print(f"[ODOMETRY] ESP32 → Jetson: {data}")

    @staticmethod
    def _is_legacy_status(
        data: dict[str, Any],
    ) -> bool:
        """현재 ESP32의 기존 상태 형식인지 확인한다."""

        return all(
            key in data
            for key in (
                "battery",
                "motor",
                "state",
            )
        )

    def _require_open_serial(self) -> serial.Serial:
        """열려 있는 Serial 객체를 반환한다."""

        if self._serial is None or not self._serial.is_open:
            raise RuntimeError(
                "시리얼 포트가 열려 있지 않습니다."
            )

        return self._serial


def main() -> None:
    """ESP32 Serial → RobotStateStore 연동 테스트."""

    state_store = RobotStateStore()

    reader = ESP32SerialReader(
        debug=True,
        state_store=state_store,
    )

    try:
        reader.start()

        while True:
            time.sleep(1)

            print(
                "[SERIAL LATEST] "
                f"{reader.get_latest_status()}"
            )

            print(
                "[STATE STORE] "
                f"{state_store.get_snapshot().status}"
            )

    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")

    finally:
        reader.stop()


if __name__ == "__main__":
    main()