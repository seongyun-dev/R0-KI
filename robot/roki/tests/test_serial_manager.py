from __future__ import annotations

import unittest
from unittest.mock import patch

from serial_comm.serial_manager import SerialConnectionSettings, SerialManager


class FakeSerial:
    """실제 포트처럼 ``in_waiting`` + ``read(n)`` 을 제공한다.

    read_line 은 더 이상 ``readline()`` 을 쓰지 않는다 -- pyserial 의 그것이
    1바이트씩 읽어 GIL 을 갈아먹기 때문이다(serial_manager._read_available).
    더블이 그 형태를 안 따라가면 테스트가 실기와 다른 경로를 덮게 된다.
    """

    def __init__(self, *payloads: bytes) -> None:
        self.is_open = True
        self._payloads = list(payloads)
        self._pending = bytearray()
        self.bulk_reads = 0
        self.single_reads = 0

    def _refill(self) -> None:
        if not self._pending and self._payloads:
            self._pending.extend(self._payloads.pop(0))

    @property
    def in_waiting(self) -> int:
        self._refill()
        return len(self._pending)

    def read(self, size: int = 1) -> bytes:
        self._refill()
        if size > 1:
            self.bulk_reads += 1
        else:
            self.single_reads += 1
        chunk = bytes(self._pending[:size])
        del self._pending[: len(chunk)]
        return chunk

    def readline(self) -> bytes:  # pragma: no cover - 더 이상 쓰이지 않는다
        raise AssertionError("read_line 은 readline() 을 쓰면 안 된다")


class FakeOpeningSerial:
    def __init__(self) -> None:
        self.is_open = False
        self.dtr = True
        self.rts = True
        self.port: str | None = None
        self.timeout = 0.05
        self.opened_without_reset = False

    def open(self) -> None:
        self.opened_without_reset = self.dtr is False and self.rts is False
        self.is_open = True

    def reset_input_buffer(self) -> None:
        return None

    @property
    def in_waiting(self) -> int:
        return 0

    def read(self, size: int = 1) -> bytes:
        return b""

    def readline(self) -> bytes:
        return b""

    def close(self) -> None:
        self.is_open = False


class SerialManagerTest(unittest.TestCase):
    def manager_with_payloads(self, *payloads: bytes) -> SerialManager:
        manager = SerialManager(SerialConnectionSettings("/dev/fake", 115200, 0.05))
        manager._serial = FakeSerial(*payloads)
        return manager

    def test_blank_serial_record_is_treated_as_no_data(self) -> None:
        self.assertIsNone(self.manager_with_payloads(b"\r\n").read_line())

    def test_json_serial_record_is_preserved(self) -> None:
        self.assertEqual(
            self.manager_with_payloads(b'{"type":"ack"}\r\n').read_line(),
            '{"type":"ack"}',
        )

    def test_fragmented_json_is_assembled_until_newline(self) -> None:
        manager = self.manager_with_payloads(
            b'{"type":"ack","command":"ENCODER_ZERO",',
            b'"sequence":2}\n',
        )

        self.assertIsNone(manager.read_line())
        self.assertEqual(
            manager.read_line(),
            '{"type":"ack","command":"ENCODER_ZERO","sequence":2}',
        )

    def test_available_bytes_are_read_in_one_call(self) -> None:
        """레코드당 read(1) 을 130번 하면 그만큼 GIL 을 놓았다 잡는다.

        2026-08-09 젯슨 실측: 경쟁 스레드 하나만 있어도 한 레코드 읽기가
        p50 1.73ms -> 2297ms 로 무너졌고, 같은 조건 벌크 read 는 10.4ms 였다.
        그 지연이 그대로 CONTROL 송신 간격이 되어 07:51:57 에
        sendGapMs=457.411 -> 펌웨어 워치독(400ms) 발화로 매핑이 끊겼다.
        """

        manager = self.manager_with_payloads(b'{"a":1}\n')
        port = manager._serial

        self.assertEqual(manager.read_line(), '{"a":1}')

        self.assertEqual(port.bulk_reads, 1, "대기 바이트는 한 번에 가져와야 한다")
        self.assertEqual(port.single_reads, 0)

    def test_bulk_read_yields_every_line_without_touching_the_port(self) -> None:
        """한 번 읽어 여러 줄이 들어오면 나머지는 포트를 안 만지고 내보낸다."""

        manager = self.manager_with_payloads(b'{"a":1}\n{"b":2}\n{"c":3}\n')
        port = manager._serial

        lines = [manager.read_line() for _ in range(3)]

        self.assertEqual(lines, ['{"a":1}', '{"b":2}', '{"c":3}'])
        self.assertEqual(
            port.bulk_reads + port.single_reads,
            1,
            "세 줄이 한 번의 읽기로 들어왔으면 포트 접근도 한 번이어야 한다",
        )

    def test_idle_port_still_blocks_on_one_byte(self) -> None:
        """대기 바이트가 없을 때 즉시 반환하면 호출 루프가 CPU 를 태운다.

        기존 readline() 은 타임아웃까지 블로킹했다. 그 성질을 유지해야
        run_forever 가 빈 루프를 돌지 않는다.
        """

        manager = self.manager_with_payloads()
        port = manager._serial

        self.assertIsNone(manager.read_line())

        self.assertEqual(port.single_reads, 1, "타임아웃 대기는 read(1) 이 맡는다")
        self.assertEqual(port.bulk_reads, 0)

    @patch("serial_comm.serial_manager.time.sleep", return_value=None)
    @patch("serial_comm.serial_manager.serial.Serial")
    def test_connect_opens_cp2102_without_dtr_rts_reset(
        self,
        serial_constructor: object,
        _sleep: object,
    ) -> None:
        connection = FakeOpeningSerial()
        serial_constructor.return_value = connection
        manager = SerialManager(
            SerialConnectionSettings("/dev/roki_esp32", 115200, 0.05)
        )

        self.assertTrue(manager.connect())
        self.assertTrue(connection.opened_without_reset)
        self.assertEqual(connection.port, "/dev/roki_esp32")


if __name__ == "__main__":
    unittest.main()
