import unittest
from unittest.mock import patch

from serial_comm.device_finder import SerialDevice, SerialDeviceFinder


class SerialDeviceFinderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.device = SerialDevice(
            port="/dev/ttyUSB0",
            description="CP2102 USB to UART Bridge Controller",
            manufacturer="Silicon Labs",
            vid=0x10C4,
            pid=0xEA60,
            serial_number="0001",
        )
        self.finder = SerialDeviceFinder()

    def test_by_id_symlink_selects_same_real_device(self) -> None:
        configured_port = (
            "/dev/serial/by-id/"
            "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_"
            "0001-if00-port0"
        )

        with (
            patch.object(self.finder, "list_devices", return_value=[self.device]),
            patch(
                "serial_comm.device_finder.os.path.realpath",
                side_effect=lambda path: (
                    "/dev/ttyUSB0" if path == configured_port else path
                ),
            ),
        ):
            selected = self.finder.find_device(configured_port=configured_port)

        self.assertIs(selected, self.device)

    def test_direct_real_path_is_selected_as_before(self) -> None:
        with patch.object(
            self.finder,
            "list_devices",
            return_value=[self.device],
        ):
            selected = self.finder.find_device(
                configured_port="/dev/ttyUSB0"
            )

        self.assertIs(selected, self.device)

    def test_missing_configured_path_returns_none(self) -> None:
        with patch.object(
            self.finder,
            "list_devices",
            return_value=[self.device],
        ):
            selected = self.finder.find_device(
                configured_port="/dev/serial/by-id/does-not-exist"
            )

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
