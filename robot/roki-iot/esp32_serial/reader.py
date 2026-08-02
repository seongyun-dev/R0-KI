"""
ESP32 Serial 메시지 수신 관리자.

이 클래스는 다른 세부 객체를 조합해 다음 흐름을 관리한다.

SerialConnection
    → JsonFrameDecoder
    → Esp32MessageParser
    → 최신 메시지 저장

프레임 추출 방식이나 JSON 필드 검증을
직접 구현하지 않고 각 전용 객체에 위임한다.
"""

from __future__ import annotations

import json
from threading import Event, Lock, Thread
from typing import Any

import serial

from esp32_serial.connection import SerialConnection
from esp32_serial.frame_decoder import JsonFrameDecoder
from esp32_serial.message_parser import (
    Esp32MessageParser,
    InvalidEsp32MessageError,
    UnknownEsp32MessageError,
)
from esp32_serial.models import (
    CommandAckMessage,
    HardwareStatusMessage,
    OdometryMessage,
)


class ESP32SerialReader:
    """
    MQTT Publisher와 ROS2 모듈이 사용하는
    ESP32 Serial Reader 공개 클래스.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        debug: bool = False,
    ) -> None:
        self._connection = SerialConnection(
            port=port,
            baudrate=baudrate,
        )

        self._frame_decoder = JsonFrameDecoder()
        self._message_parser = Esp32MessageParser()

        # bool 대신 Event를 사용하면
        # 스레드 간 실행 상태를 더 안전하게 공유할 수 있다.
        self._stop_event = Event()
        self._thread: Thread | None = None

        # 최신 상태를 읽고 쓰는 작업을 보호한다.
        self._state_lock = Lock()

        # Serial 쓰기는 여러 모듈이 동시에 명령을 보낼 수 있어
        # 별도의 Lock으로 보호한다.
        self._write_lock = Lock()

        self._debug = debug

        self._latest_hardware_status: (
            HardwareStatusMessage | None
        ) = None

        self._latest_odometry: (
            OdometryMessage | None
        ) = None

        self._latest_command_ack: (
            CommandAckMessage | None
        ) = None

    def start(self) -> None:
        """Serial 포트를 열고 수신 스레드를 시작한다."""

        if self.is_running():
            return

        self._connection.open()
        self._frame_decoder.reset()
        self._stop_event.clear()

        self._thread = Thread(
            target=self._read_loop,
            name="esp32-serial-reader",
            daemon=True,
        )

        self._thread.start()

        print(
            "[SERIAL] 연결 완료: "
            f"{self._connection.port} @ "
            f"{self._connection.baudrate}"
        )

    def stop(self) -> None:
        """수신 스레드와 Serial 연결을 종료한다."""

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        self._connection.close()

        print("[SERIAL] 연결 종료")

    def is_running(self) -> bool:
        """수신 스레드가 실행 중인지 반환한다."""

        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop_event.is_set()
        )

    def get_latest_status(self) -> dict[str, Any]:
        """
        최신 하드웨어 상태를 기존 dict 형식으로 반환한다.

        현재 mqtt/publisher.py와 호환하기 위한 메서드다.
        최초 메시지를 받기 전에는 기본값을 반환한다.
        """

        with self._state_lock:
            if self._latest_hardware_status is None:
                return {
                    "battery": None,
                    "motor": "DISCONNECTED",
                    "lineSensor": "DISCONNECTED",
                }

            return (
                self._latest_hardware_status
                .to_legacy_dict()
            )

    def get_latest_hardware_status(
        self,
    ) -> HardwareStatusMessage | None:
        """최신 HardwareStatusMessage를 반환한다."""

        with self._state_lock:
            return self._latest_hardware_status

    def get_latest_odometry(
        self,
    ) -> OdometryMessage | None:
        """최신 OdometryMessage를 반환한다."""

        with self._state_lock:
            return self._latest_odometry

    def get_latest_command_ack(
        self,
    ) -> CommandAckMessage | None:
        """가장 최근 명령 응답을 반환한다."""

        with self._state_lock:
            return self._latest_command_ack

    def send_command(
        self,
        command: str,
        **parameters: Any,
    ) -> None:
        """
        Jetson 명령을 JSON 한 줄 형식으로 전송한다.

        추가 명령 인자는 keyword argument로 전달한다.

        예:
        send_command(
            "START_PATROL",
            patrolId=15,
        )
        """

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
            self._connection.write(
                message.encode("utf-8")
            )

        print(
            "[COMMAND] Jetson → ESP32: "
            f"{message.strip()}"
        )

    def _read_loop(self) -> None:
        """Serial 데이터를 반복해서 읽고 처리한다."""

        while not self._stop_event.is_set():
            try:
                raw_chunk = (
                    self._connection.read_chunk()
                )
            except serial.SerialException as error:
                print(f"[SERIAL ERROR] {error}")
                self._stop_event.set()
                break
            except RuntimeError as error:
                print(f"[SERIAL ERROR] {error}")
                self._stop_event.set()
                break

            if not raw_chunk:
                continue

            text_chunk = raw_chunk.decode(
                "utf-8",
                errors="ignore",
            )

            frames = self._frame_decoder.feed(
                text_chunk
            )

            for frame in frames:
                self._process_frame(frame)

    def _process_frame(
        self,
        frame: str,
    ) -> None:
        """완성된 JSON 프레임 하나를 처리한다."""

        try:
            message = self._message_parser.parse(
                frame
            )
        except InvalidEsp32MessageError as error:
            print(f"[SERIAL SKIP] {error}")
            return
        except UnknownEsp32MessageError as error:
            print(f"[SERIAL SKIP] {error}")
            return

        if isinstance(
            message,
            HardwareStatusMessage,
        ):
            self._save_hardware_status(message)
            return

        if isinstance(message, OdometryMessage):
            self._save_odometry(message)
            return

        if isinstance(message, CommandAckMessage):
            self._save_command_ack(message)

    def _save_hardware_status(
        self,
        message: HardwareStatusMessage,
    ) -> None:
        """최신 ESP32 하드웨어 상태를 저장한다."""

        with self._state_lock:
            previous_status = (
                self._latest_hardware_status
            )

            self._latest_hardware_status = message

        # 같은 상태가 1초마다 반복 수신되더라도
        # 터미널 로그가 계속 쌓이지 않게 변경 시에만 출력한다.
        if message != previous_status:
            print(
                "[HARDWARE STATUS] ESP32 → Jetson: "
                f"{message.to_legacy_dict()}"
            )

    def _save_odometry(
        self,
        message: OdometryMessage,
    ) -> None:
        """최신 엔코더 누적 Tick을 저장한다."""

        with self._state_lock:
            self._latest_odometry = message

        # Odometry는 약 20Hz로 들어오므로
        # 일반 실행에서는 매번 출력하지 않는다.
        if self._debug:
            print(
                "[ODOMETRY] ESP32 → Jetson: "
                f"seq={message.seq}, "
                f"left={message.left_ticks}, "
                f"right={message.right_ticks}"
            )

    def _save_command_ack(
        self,
        message: CommandAckMessage,
    ) -> None:
        """최신 명령 처리 응답을 저장한다."""

        with self._state_lock:
            self._latest_command_ack = message

        print(
            "[ACK] ESP32 → Jetson: "
            f"command={message.command}, "
            f"accepted={message.accepted}, "
            f"message={message.message}"
        )
