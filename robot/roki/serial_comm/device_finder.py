"""USB 시리얼 장치 탐색 모듈.

이 모듈의 책임은 다음 두 가지로 제한한다.

1. 운영체제가 인식한 시리얼 장치 목록 조회
2. 설정 조건에 맞는 ESP32 후보 장치 선택

실제 포트 연결과 데이터 송수신은 serial_manager.py가 담당한다.
"""

import os
from dataclasses import dataclass
from typing import Optional, Sequence

from serial.tools import list_ports
from serial.tools.list_ports_common import ListPortInfo


# ESP32 보드에서 자주 사용되는 USB-UART 칩과 장치 설명이다.
# 장치의 description 또는 manufacturer에 해당 문자열이 포함되면
# ESP32 후보로 판단한다.
ESP32_DEVICE_KEYWORDS: tuple[str, ...] = (
    "CP210",
    "CP2102",
    "CH340",
    "CH341",
    "ESP32",
    "SILICON LABS",
    "USB TO UART",
    "USB SERIAL",
)

DEFAULT_ALLOWED_PORT_PREFIXES: tuple[str, ...] = (
    "/dev/ttyUSB",
    "/dev/ttyACM",
)


@dataclass(frozen=True)
class SerialDevice:
    """운영체제가 인식한 시리얼 장치 정보를 표현한다.

    frozen=True를 사용하여 탐색된 장치 정보가
    실행 중 의도치 않게 변경되지 않도록 한다.
    """

    port: str
    description: str
    manufacturer: Optional[str]
    vid: Optional[int]
    pid: Optional[int]
    serial_number: Optional[str]

    @classmethod
    def from_port_info(cls, port_info: ListPortInfo) -> "SerialDevice":
        """pyserial 장치 정보를 프로젝트 장치 객체로 변환한다."""

        return cls(
            port=port_info.device,
            description=port_info.description or "",
            manufacturer=port_info.manufacturer,
            vid=port_info.vid,
            pid=port_info.pid,
            serial_number=port_info.serial_number,
        )

    def get_vid_pid_text(self) -> str:
        """VID와 PID를 사람이 읽기 쉬운 문자열로 반환한다."""

        if self.vid is None or self.pid is None:
            return "unknown"

        return f"{self.vid:04X}:{self.pid:04X}"

    def to_display_text(self) -> str:
        """로그와 테스트 출력에 사용할 장치 설명을 반환한다."""

        return (
            f"port={self.port}, "
            f"description={self.description or 'unknown'}, "
            f"manufacturer={self.manufacturer or 'unknown'}, "
            f"VID:PID={self.get_vid_pid_text()}, "
            f"serial={self.serial_number or 'unknown'}"
        )


class SerialDeviceFinder:
    """설정 조건에 맞는 USB 시리얼 장치를 탐색한다.

    장치 선택 우선순위:

    1. YAML에 고정된 포트
    2. 설정된 VID/PID와 일치하는 장치
    3. ESP32 관련 키워드를 가진 장치
    4. 허용된 포트 접두사에 해당하는 장치
    """

    def __init__(
        self,
        allowed_port_prefixes: Optional[Sequence[str]] = None,
    ) -> None:
        """장치 탐색기를 생성한다.

        Args:
            allowed_port_prefixes:
                자동 탐색 시 허용할 포트 접두사 목록.
                값이 없으면 ttyUSB와 ttyACM을 사용한다.
        """

        self._allowed_port_prefixes = tuple(
            allowed_port_prefixes or DEFAULT_ALLOWED_PORT_PREFIXES
        )

    def list_devices(self) -> list[SerialDevice]:
        """현재 운영체제가 인식한 시리얼 장치 목록을 반환한다."""

        return [
            SerialDevice.from_port_info(port_info)
            for port_info in list_ports.comports()
        ]

    def find_device(
        self,
        configured_port: str = "auto",
        preferred_vid: Optional[int] = None,
        preferred_pid: Optional[int] = None,
    ) -> Optional[SerialDevice]:
        """설정 조건에 가장 적합한 시리얼 장치를 반환한다.

        장치가 없더라도 예외를 발생시키지 않고 None을 반환한다.
        따라서 ESP32가 연결되지 않은 개발 환경에서도
        프로그램 전체가 비정상 종료되지 않는다.
        """

        devices = self.list_devices()

        if configured_port != "auto":
            return self._find_by_port(
                devices=devices,
                configured_port=configured_port,
            )

        device = self._find_by_vid_pid(
            devices=devices,
            preferred_vid=preferred_vid,
            preferred_pid=preferred_pid,
        )
        if device is not None:
            return device

        device = self._find_likely_esp32(devices)
        if device is not None:
            return device

        return self._find_by_allowed_prefix(devices)

    @staticmethod
    def _find_by_port(
        devices: Sequence[SerialDevice],
        configured_port: str,
    ) -> Optional[SerialDevice]:
        """심볼릭 링크를 포함해 같은 실제 포트를 가리키는 장치를 찾는다."""

        try:
            configured_real_path = os.path.realpath(configured_port)
        except (OSError, ValueError):
            return None

        for device in devices:
            try:
                device_real_path = os.path.realpath(device.port)
            except (OSError, ValueError):
                continue
            if device_real_path == configured_real_path:
                return device
        return None

    @staticmethod
    def _find_by_vid_pid(
        devices: Sequence[SerialDevice],
        preferred_vid: Optional[int],
        preferred_pid: Optional[int],
    ) -> Optional[SerialDevice]:
        """VID와 PID가 모두 일치하는 장치를 찾는다."""

        if preferred_vid is None or preferred_pid is None:
            return None

        return next(
            (
                device
                for device in devices
                if device.vid == preferred_vid
                and device.pid == preferred_pid
            ),
            None,
        )

    @staticmethod
    def _find_likely_esp32(
        devices: Sequence[SerialDevice],
    ) -> Optional[SerialDevice]:
        """장치 설명과 제조사 정보로 ESP32 후보를 찾는다."""

        for device in devices:
            searchable_text = " ".join(
                part
                for part in (
                    device.description,
                    device.manufacturer,
                )
                if part
            ).upper()

            if any(
                keyword in searchable_text
                for keyword in ESP32_DEVICE_KEYWORDS
            ):
                return device

        return None

    def _find_by_allowed_prefix(
        self,
        devices: Sequence[SerialDevice],
    ) -> Optional[SerialDevice]:
        """허용된 Linux 포트 접두사에 해당하는 장치를 찾는다."""

        return next(
            (
                device
                for device in devices
                if device.port.startswith(self._allowed_port_prefixes)
            ),
            None,
        )
