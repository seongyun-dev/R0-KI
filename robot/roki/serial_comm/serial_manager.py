"""시리얼 연결과 데이터 송수신을 관리하는 모듈.

이 모듈은 전달받은 시리얼 포트에 연결하고,
문자열 데이터를 송수신하는 책임만 가진다.

장치 탐색은 device_finder.py가 담당하며,
메시지 형식의 생성과 해석은 protocol.py가 담당한다.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import serial
from serial import SerialException


logger = logging.getLogger(__name__)
MAX_SERIAL_LINE_BYTES = 4096


@dataclass(frozen=True)
class SerialConnectionSettings:
    """시리얼 연결에 필요한 설정값을 보관한다.

    설정값을 하나의 객체로 묶으면 함수 인자가 과도하게 늘어나는 것을
    방지하고, 이후 설정 항목이 추가되더라도 수정 범위를 줄일 수 있다.
    """

    port: str
    baudrate: int
    timeout_sec: float
    startup_wait_sec: float = 2.0


class SerialManager:
    """시리얼 포트 연결과 한 줄 단위 송수신을 관리한다.

    SerialManager는 장치를 자동 탐색하지 않는다.
    사용할 포트는 외부에서 결정한 후 생성자에 전달해야 한다.
    """

    def __init__(self, settings: SerialConnectionSettings) -> None:
        """시리얼 관리자를 생성한다.

        Args:
            settings:
                연결할 포트, 통신 속도, 읽기 제한 시간을 포함한 설정 객체.
        """

        self._settings = settings
        self._serial: Optional[serial.Serial] = None
        self._read_buffer = bytearray()

        # 여러 스레드가 동시에 데이터를 전송하면 문자열이 섞일 수 있으므로
        # 쓰기 작업은 Lock으로 보호한다.
        self._write_lock = threading.Lock()

    @property
    def port(self) -> str:
        """설정된 시리얼 포트 경로를 반환한다."""

        return self._settings.port

    def is_connected(self) -> bool:
        """현재 시리얼 포트가 열려 있는지 반환한다."""

        return self._serial is not None and self._serial.is_open

    def connect(self) -> bool:
        """설정된 시리얼 포트에 연결한다.

        이미 연결되어 있으면 추가 연결을 시도하지 않는다.

        Returns:
            연결되어 있거나 새 연결에 성공하면 True,
            연결에 실패하면 False.
        """

        if self.is_connected():
            return True

        try:
            connection = serial.Serial(
                port=None,
                baudrate=self._settings.baudrate,
                timeout=self._settings.timeout_sec,
                exclusive=True,
            )
            # Opening a CP2102 with pyserial defaults can pulse DTR/RTS and
            # reset the ESP32. Configure both lines before opening, matching
            # the field-proven hardware tools and preserving the running
            # operating firmware across Robot service restarts.
            connection.dtr = False
            connection.rts = False
            connection.port = self._settings.port
            connection.open()
            self._serial = connection
            self._read_buffer.clear()

            # Allow any already-running telemetry record to finish, then start
            # the mandatory STOP/HELLO/ENCODER_ZERO handshake on a clean RX
            # boundary.
            time.sleep(self._settings.startup_wait_sec)
            self._serial.reset_input_buffer()
            original_timeout = self._serial.timeout
            self._serial.timeout = max(0.25, self._settings.timeout_sec)
            self._serial.readline()
            self._serial.timeout = original_timeout

            logger.info(
                "Serial port connected: port=%s, baudrate=%d",
                self._settings.port,
                self._settings.baudrate,
            )
            return True

        except (SerialException, OSError) as error:
            # USB 장치 부재나 권한 문제는 로봇 전체 프로세스를
            # 즉시 종료할 이유가 아니므로 실패 결과만 반환한다.
            logger.warning(
                "Serial connection failed: port=%s, reason=%s",
                self._settings.port,
                error,
            )
            self._serial = None
            return False

    def disconnect(self) -> None:
        """열려 있는 시리얼 포트를 안전하게 닫는다."""

        serial_port = self._serial
        self._serial = None
        self._read_buffer.clear()

        if serial_port is None:
            return

        try:
            if serial_port.is_open:
                serial_port.close()
                logger.info(
                    "Serial port disconnected: port=%s",
                    self._settings.port,
                )

        except (SerialException, OSError) as error:
            # 종료 중 발생한 오류도 전체 프로그램 종료를 막지 않도록
            # 기록만 남기고 메서드는 정상적으로 끝낸다.
            logger.warning(
                "Serial disconnection failed: port=%s, reason=%s",
                self._settings.port,
                error,
            )

    def write_line(self, message: str) -> bool:
        """문자열 한 줄을 UTF-8 형식으로 전송한다.

        메시지 끝에 줄바꿈 문자가 없으면 자동으로 추가한다.
        ESP32에서는 줄바꿈을 기준으로 명령 하나를 구분할 수 있다.

        Args:
            message:
                ESP32로 보낼 문자열.

        Returns:
            전송에 성공하면 True, 실패하면 False.
        """

        if not self.is_connected() or self._serial is None:
            logger.warning(
                "Serial write skipped because the port is not connected."
            )
            return False

        normalized_message = message.rstrip("\r\n") + "\n"
        encoded_message = normalized_message.encode("utf-8")

        try:
            with self._write_lock:
                self._serial.write(encoded_message)
                self._serial.flush()

            return True

        except (SerialException, OSError) as error:
            logger.warning(
                "Serial write failed: port=%s, reason=%s",
                self._settings.port,
                error,
            )
            self.disconnect()
            return False

    def _take_buffered_line(self) -> Optional[str]:
        """버퍼에 완결된 줄이 있으면 꺼낸다. 없으면 None.

        빈 문자열은 "줄은 있었지만 내용이 없다"는 뜻이라 호출자가 구분한다.
        """

        if b"\n" not in self._read_buffer:
            return None
        complete_line, _, remainder = self._read_buffer.partition(b"\n")
        self._read_buffer = bytearray(remainder)
        return complete_line.decode("utf-8", errors="replace").strip()

    def _read_available(self) -> bytes:
        """대기 중인 바이트를 **한 번에** 가져온다.

        ``pyserial.readline()`` 을 쓰면 안 된다. ``Serial`` 은 ``RawIOBase``
        상속이라 그 readline 이 ``peek`` 없이 **1바이트씩** 읽는다 -- 130바이트
        레코드 하나에 ``read(1)`` 이 130회, 각각 ``select()`` + ``os.read()`` 이고
        매번 GIL 을 놓았다 잡는다.

        2026-08-09 젯슨 실측(동일 경로 복제): 경쟁 파이썬 스레드가 **하나만**
        있어도 한 레코드 읽기가 p50 1.73ms -> 2297ms 로 무너진다. 같은 조건
        ``read(4096)`` 벌크는 10.4ms 였다(220배).

        그 지연이 그대로 CONTROL 송신 간격이 된다. run_forever 가 단일
        스레드로 읽기·파싱·쓰기를 다 하고, CONTROL 갱신은 read_line() 뒤에서만
        돌기 때문이다. 실측 2026-08-09 07:51:57 ``sendGapMs=457.411`` ->
        펌웨어 워치독(400ms) 발화 -> ESP32_COMMAND_TIMEOUT 으로 매핑 중단.

        ``in_waiting`` 이 0 일 때는 예전처럼 1바이트 블로킹 읽기를 유지한다.
        여기서 즉시 반환하면 호출 루프가 CPU 를 100% 태운다.
        """

        pending = 0
        in_waiting = getattr(self._serial, "in_waiting", None)
        if isinstance(in_waiting, int):
            pending = in_waiting
        if pending > 0:
            return self._serial.read(pending)
        return self._serial.read(1)

    def read_line(self) -> Optional[str]:
        """시리얼 포트에서 문자열 한 줄을 읽는다.

        데이터가 없거나 연결되어 있지 않으면 None을 반환한다.
        수신된 줄바꿈 문자는 제거한다.

        Returns:
            수신한 문자열 또는 수신 데이터가 없을 경우 None.
        """

        if not self.is_connected() or self._serial is None:
            return None

        try:
            # 이미 완결된 줄이 버퍼에 있으면 포트를 만지지 않고 바로 돌려준다.
            # 벌크로 읽으면 한 번에 여러 줄이 들어오므로 이 경로가 대부분이다.
            buffered = self._take_buffered_line()
            if buffered is not None:
                return buffered or None

            raw_data = self._read_available()

            if not raw_data:
                return None

            # 부분 레코드는 계속 모은다. 타임아웃이 LF 앞에서 끊기면
            # pyserial 이 조각을 돌려주는데, 예전 코드는 그 조각을 각각
            # JSON 으로 파싱하려 했다. ROS/SLAM 기동 부하에서 늘 그랬다.
            self._read_buffer.extend(raw_data)
            if b"\n" not in self._read_buffer:
                if len(self._read_buffer) > MAX_SERIAL_LINE_BYTES:
                    logger.warning(
                        "Serial record exceeded %d bytes; dropping partial data",
                        MAX_SERIAL_LINE_BYTES,
                    )
                    self._read_buffer.clear()
                return None

            decoded = self._take_buffered_line()
            # A CP2102/ESP32 reset can leave CR/LF-only records in the RX
            # queue. They carry no protocol information and must be treated
            # like a read timeout, not as a hardware/protocol fault.
            return decoded or None

        except (SerialException, OSError) as error:
            logger.warning(
                "Serial read failed: port=%s, reason=%s",
                self._settings.port,
                error,
            )
            self.disconnect()
            return None

    def __enter__(self) -> "SerialManager":
        """with 문에서 사용할 때 연결을 시도한다."""

        self.connect()
        return self

    def __exit__(
        self,
        exception_type: object,
        exception_value: object,
        traceback: object,
    ) -> None:
        """with 문이 끝날 때 시리얼 포트를 닫는다."""

        self.disconnect()
