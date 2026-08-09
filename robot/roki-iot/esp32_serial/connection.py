"""
ESP32 Serial 포트 연결 관리 모듈.

이 클래스의 책임:

1. 포트 열기
2. byte 데이터 읽기
3. byte 데이터 쓰기
4. 포트 닫기

JSON 해석이나 로봇 상태 저장은 수행하지 않는다.
"""

from __future__ import annotations

import time

import serial


class SerialConnection:
    """pyserial 연결을 감싸는 클래스."""

    def __init__(
        self,
        *,
        port: str,
        baudrate: int,
        timeout_seconds: float = 0.2,
        startup_wait_seconds: float = 2.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout_seconds = timeout_seconds
        self._startup_wait_seconds = (
            startup_wait_seconds
        )

        self._serial: serial.Serial | None = None

    @property
    def port(self) -> str:
        """설정된 Serial 포트 이름을 반환한다."""

        return self._port

    @property
    def baudrate(self) -> int:
        """설정된 baudrate를 반환한다."""

        return self._baudrate

    @property
    def is_open(self) -> bool:
        """Serial 포트가 열려 있는지 반환한다."""

        return (
            self._serial is not None
            and self._serial.is_open
        )

    def open(self) -> None:
        """
        Serial 포트를 연다.

        ESP32는 USB Serial 포트가 열릴 때
        자동 재부팅될 수 있어 잠시 기다린 후
        기존 입력 버퍼를 비운다.
        """

        if self.is_open:
            return

        self._serial = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            timeout=self._timeout_seconds,
        )

        time.sleep(self._startup_wait_seconds)
        self._serial.reset_input_buffer()

    def read_chunk(self) -> bytes:
        """
        현재 수신 가능한 데이터를 읽는다.

        최소 한 줄 단위로 읽되, 이미 버퍼에 더 많은
        데이터가 있으면 함께 읽어 호출 횟수를 줄인다.
        """

        serial_port = self._require_open_port()

        waiting_bytes = serial_port.in_waiting

        read_size = max(
            1,
            waiting_bytes,
        )

        return serial_port.read(read_size)

    def write(self, data: bytes) -> None:
        """byte 데이터를 Serial 포트로 전송한다."""

        serial_port = self._require_open_port()

        serial_port.write(data)
        serial_port.flush()

    def close(self) -> None:
        """Serial 포트가 열려 있으면 닫는다."""

        if not self.is_open:
            return

        assert self._serial is not None
        self._serial.close()

    def _require_open_port(self) -> serial.Serial:
        """열린 Serial 객체를 반환한다."""

        if not self.is_open:
            raise RuntimeError(
                "시리얼 포트가 열려 있지 않습니다."
            )

        assert self._serial is not None
        return self._serial
