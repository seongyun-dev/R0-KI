"""재연결 가능한 USB serial transport 경계.

포트 탐색, open/close, line read/write, 재연결 간격은 이 파일에 격리한다.
프로토콜 JSON의 의미와 로봇 제어 정책은 알지 못한다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from serial_comm.device_finder import SerialDeviceFinder
from serial_comm.serial_manager import SerialConnectionSettings, SerialManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SerialBridgeSettings:
    port: str
    baudrate: int
    read_timeout_sec: float
    reconnect_interval_sec: float
    allowed_port_prefixes: tuple[str, ...]
    preferred_vid: int | None = None
    preferred_pid: int | None = None


class SerialBridge:
    """상위 Runtime에 안정적인 line transport를 제공한다."""

    def __init__(
        self,
        settings: SerialBridgeSettings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._manager: SerialManager | None = None
        self._next_reconnect_at = 0.0
        self._connection_generation = 0

    @property
    def connection_generation(self) -> int:
        """연결될 때마다 증가하며 상위 계층의 handshake 기준이 된다."""

        return self._connection_generation

    def is_connected(self) -> bool:
        return self._manager is not None and self._manager.is_connected()

    def ensure_connected(self) -> bool:
        """재연결 시각이 되면 연결하며 새 연결에서만 True를 반환한다."""

        if self.is_connected():
            return False
        now = self._clock()
        if now < self._next_reconnect_at:
            return False
        self._close_manager()
        port = self._resolve_port()
        if port is None:
            self._schedule_reconnect(now)
            return False
        manager = SerialManager(
            SerialConnectionSettings(
                port=port,
                baudrate=self._settings.baudrate,
                timeout_sec=self._settings.read_timeout_sec,
            )
        )
        if not manager.connect():
            self._schedule_reconnect(now)
            return False
        self._manager = manager
        self._connection_generation += 1
        logger.info(
            "Serial bridge connected: port=%s generation=%d",
            port,
            self._connection_generation,
        )
        return True

    def write_line(self, message: str) -> bool:
        manager = self._manager
        if manager is None or not manager.write_line(message):
            self._handle_disconnect()
            return False
        return True

    def read_line(self) -> str | None:
        manager = self._manager
        if manager is None:
            return None
        line = manager.read_line()
        if not manager.is_connected():
            self._handle_disconnect()
        return line

    def close(self, final_message: str | None = None) -> None:
        """가능하면 마지막 안전 명령을 전송하고 포트를 닫는다."""

        if final_message is not None and self.is_connected():
            self.write_line(final_message)
        self._close_manager()

    def _resolve_port(self) -> str | None:
        if self._settings.port != "auto":
            return self._settings.port
        device = SerialDeviceFinder(
            self._settings.allowed_port_prefixes
        ).find_device(
            preferred_vid=self._settings.preferred_vid,
            preferred_pid=self._settings.preferred_pid,
        )
        return device.port if device is not None else None

    def _handle_disconnect(self) -> None:
        self._close_manager()
        self._schedule_reconnect(self._clock())
        logger.warning("Serial bridge disconnected; reconnect scheduled")

    def _close_manager(self) -> None:
        manager = self._manager
        self._manager = None
        if manager is not None:
            manager.disconnect()

    def _schedule_reconnect(self, now: float) -> None:
        self._next_reconnect_at = now + self._settings.reconnect_interval_sec
