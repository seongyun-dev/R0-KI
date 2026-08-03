from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


HARDWARE_ROOT = Path(__file__).resolve().parents[1] / "hardware"
sys.path.insert(0, str(HARDWARE_ROOT))

from line_follow_field_test import (  # noqa: E402
    FieldTestError,
    OperatingClient,
)


def hardware_status(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "hardwareStatus",
        "motor": "NORMAL",
        "lineSensor": "NORMAL",
        "batteryVoltage": 11.9,
        "lineValues": [1, 1, 0, 1, 1],
    }
    payload.update(overrides)
    return payload


class LineFollowFieldTestSafetyTest(unittest.TestCase):
    def test_hardware_validation_accepts_only_safe_operating_values(self) -> None:
        values = OperatingClient.validate_hardware(hardware_status())
        self.assertEqual(values, (1, 1, 0, 1, 1))

        for overrides in (
            {"motor": "FAULT"},
            {"lineSensor": "DISCONNECTED"},
            {"batteryVoltage": 0.71},
            {"batteryVoltage": 13.1},
            {"lineValues": [1, 1, 1]},
            {"lineValues": [1, 1, 2, 1, 1]},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(FieldTestError):
                    OperatingClient.validate_hardware(
                        hardware_status(**overrides)
                    )

    def test_handshake_requires_hello_encoder_odometry_and_hardware(self) -> None:
        client = OperatingClient("/dev/fake")
        messages = iter(
            (
                {
                    "type": "hello",
                    "firmware": "roki-operating",
                    "version": "3.0.0",
                    "protocol": 1,
                },
                {"type": "ack", "command": "ENCODER_ZERO"},
                {
                    "type": "odometry",
                    "uptimeMs": 100,
                    "leftTicks": 0,
                    "rightTicks": 0,
                },
                hardware_status(),
            )
        )
        client.send = Mock()  # type: ignore[method-assign]
        client.read = Mock(side_effect=lambda: next(messages))  # type: ignore[method-assign]

        result = client.mandatory_handshake()

        self.assertEqual(result["batteryVoltage"], 11.9)
        self.assertEqual(
            [call.args[0] for call in client.send.call_args_list],
            ["stop", "hello", "encoder_zero", "status"],
        )

    def test_fresh_sample_discards_backlog_before_allowing_control(self) -> None:
        client = OperatingClient("/dev/fake")
        client.port = SimpleNamespace(reset_input_buffer=Mock())  # type: ignore[assignment]
        messages = iter(
            (
                hardware_status(),
                {
                    "type": "odometry",
                    "uptimeMs": 200,
                    "leftTicks": 0,
                    "rightTicks": 0,
                },
            )
        )
        client.send = Mock()  # type: ignore[method-assign]
        client.read = Mock(side_effect=lambda: next(messages))  # type: ignore[method-assign]

        result = client.fresh_operating_sample()

        client.port.reset_input_buffer.assert_called_once()
        client.send.assert_called_once_with("status")
        self.assertEqual(result["lineValues"], [1, 1, 0, 1, 1])

    def test_invalid_firmware_never_completes_handshake(self) -> None:
        client = OperatingClient("/dev/fake")
        client.send = Mock()  # type: ignore[method-assign]
        client.read = Mock(
            return_value={
                "type": "hello",
                "firmware": "unknown",
                "version": "0.0.0",
                "protocol": 1,
            }
        )  # type: ignore[method-assign]
        times = iter((0.0, 0.0, 5.0))
        with patch(
            "line_follow_field_test.time.monotonic",
            side_effect=lambda: next(times),
        ):
            with self.assertRaisesRegex(FieldTestError, "handshake incomplete"):
                client.mandatory_handshake()


if __name__ == "__main__":
    unittest.main()
