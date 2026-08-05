from __future__ import annotations

import unittest
from unittest.mock import patch

from serial_comm.serial_manager import SerialConnectionSettings, SerialManager


class FakeSerial:
    def __init__(self, *payloads: bytes) -> None:
        self.is_open = True
        self._payloads = list(payloads)

    def readline(self) -> bytes:
        return self._payloads.pop(0) if self._payloads else b""


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
