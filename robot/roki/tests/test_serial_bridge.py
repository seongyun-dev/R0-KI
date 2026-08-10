from __future__ import annotations

import unittest
from unittest.mock import patch

from serial_comm.serial_bridge import SerialBridge, SerialBridgeSettings


class FakeManager:
    instances: list["FakeManager"] = []

    def __init__(self, _settings: object) -> None:
        self.connected = False
        self.lines: list[str] = []
        self.__class__.instances.append(self)

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def write_line(self, line: str) -> bool:
        if not self.connected:
            return False
        self.lines.append(line)
        return True

    def read_line(self) -> str | None:
        return None


class SerialBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeManager.instances.clear()
        self.now = 0.0
        self.bridge = SerialBridge(
            SerialBridgeSettings("/dev/fake", 115200, 0.05, 2.0, ("/dev/ttyUSB",)),
            clock=lambda: self.now,
        )

    @patch("serial_comm.serial_bridge.SerialManager", FakeManager)
    def test_connect_close_and_generation(self) -> None:
        self.assertTrue(self.bridge.ensure_connected())
        self.assertEqual(self.bridge.connection_generation, 1)
        self.assertFalse(self.bridge.ensure_connected())
        self.bridge.close("STOP")
        self.assertEqual(FakeManager.instances[0].lines, ["STOP"])

    @patch("serial_comm.serial_bridge.SerialManager", FakeManager)
    def test_write_failure_schedules_reconnect(self) -> None:
        self.bridge.ensure_connected()
        FakeManager.instances[0].connected = False
        self.assertFalse(self.bridge.write_line("CONTROL"))
        self.assertFalse(self.bridge.ensure_connected())
        self.now = 2.0
        self.assertTrue(self.bridge.ensure_connected())
        self.assertEqual(self.bridge.connection_generation, 2)


if __name__ == "__main__":
    unittest.main()
