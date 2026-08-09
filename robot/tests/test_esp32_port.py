from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HARDWARE_ROOT = Path(__file__).resolve().parents[1] / "hardware"
sys.path.insert(0, str(HARDWARE_ROOT))

import esp32_port  # noqa: E402


def cp2102(device: str) -> SimpleNamespace:
    return SimpleNamespace(
        device=device,
        vid=esp32_port.CP2102_VID,
        pid=esp32_port.CP2102_PID,
    )


class Esp32PortResolutionTest(unittest.TestCase):
    def test_explicit_existing_path_wins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            device = Path(directory) / "tty"
            device.touch()
            self.assertEqual(
                esp32_port.resolve_esp32_port(str(device)),
                str(device),
            )

    def test_environment_path_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            device = Path(directory) / "tty"
            device.touch()
            with patch.dict(os.environ, {"ESP32_PORT": str(device)}):
                self.assertEqual(
                    esp32_port.resolve_esp32_port(),
                    str(device),
                )

    def test_project_alias_precedes_usb_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / "roki_esp32"
            alias.touch()
            with patch.object(esp32_port, "ESP32_ALIAS", str(alias)):
                with patch.object(esp32_port.list_ports, "comports") as ports:
                    self.assertEqual(
                        esp32_port.resolve_esp32_port(),
                        str(alias),
                    )
                    ports.assert_not_called()

    def test_duplicate_cp2102_devices_fail_closed(self) -> None:
        with patch.object(esp32_port, "ESP32_ALIAS", "/missing/alias"):
            with patch.object(
                esp32_port.list_ports,
                "comports",
                return_value=[cp2102("/dev/ttyUSB0"), cp2102("/dev/ttyUSB1")],
            ):
                with self.assertRaisesRegex(
                    esp32_port.Esp32PortError,
                    "Multiple indistinguishable CP2102",
                ):
                    esp32_port.resolve_esp32_port()

    def test_single_cp2102_can_use_by_id_fallback(self) -> None:
        by_id = "/dev/serial/by-id/cp2102"
        with patch.object(esp32_port, "ESP32_ALIAS", "/missing/alias"):
            with patch.object(
                esp32_port.list_ports,
                "comports",
                return_value=[cp2102("/dev/ttyUSB0")],
            ):
                with patch.object(
                    esp32_port.glob,
                    "glob",
                    return_value=[by_id],
                ):
                    self.assertEqual(esp32_port.resolve_esp32_port(), by_id)


if __name__ == "__main__":
    unittest.main()
