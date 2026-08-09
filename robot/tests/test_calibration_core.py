from __future__ import annotations

import sys
import unittest
from pathlib import Path


HARDWARE_ROOT = Path(__file__).resolve().parents[1] / "hardware"
sys.path.insert(0, str(HARDWARE_ROOT))

from calibration_core import (
    parse_telemetry_line,
    summarize_records,
    ticks_per_revolution,
)


class CalibrationCoreTest(unittest.TestCase):
    def test_parses_operating_json_and_line_debug_text(self) -> None:
        self.assertEqual(
            parse_telemetry_line(b'{"type":"hello","protocol":1}\r\n'),
            {"type": "hello", "protocol": 1},
        )
        self.assertEqual(
            parse_telemetry_line("S1:1 S2:0 S3:0 S4:1 S5:1"),
            {
                "type": "hardwareStatus",
                "source": "line-debug-text",
                "lineValues": [1, 0, 0, 1, 1],
            },
        )
        self.assertIsNone(parse_telemetry_line("not telemetry"))

    def test_summarizes_line_encoder_and_battery_without_polarity_guess(self) -> None:
        records = [
            {
                "payload": {
                    "type": "hardwareStatus",
                    "batteryVoltage": 12.4,
                    "lineValues": [1, 1, 0, 1, 1],
                }
            },
            {
                "payload": {
                    "type": "odometry",
                    "leftTicks": 0,
                    "rightTicks": 0,
                }
            },
            {
                "payload": {
                    "type": "hardwareStatus",
                    "batteryVoltage": 12.2,
                    "lineValues": [1, 0, 0, 1, 1],
                }
            },
            {
                "payload": {
                    "type": "odometry",
                    "leftTicks": -100,
                    "rightTicks": 105,
                }
            },
        ]

        summary = summarize_records(records)

        self.assertEqual(summary["line"]["patterns"], {"11011": 1, "10011": 1})
        self.assertEqual(summary["line"]["channels"][1]["transitionCount"], 1)
        self.assertEqual(summary["encoder"]["leftDelta"], -100)
        self.assertEqual(summary["encoder"]["rightDelta"], 105)
        self.assertAlmostEqual(summary["battery"]["averageVoltage"], 12.3)

    def test_ticks_per_revolution_uses_magnitude_and_validates_input(self) -> None:
        self.assertEqual(ticks_per_revolution(-1000, 10), 100)
        with self.assertRaises(ValueError):
            ticks_per_revolution(100, 0)

    def test_ignores_incomplete_odometry_without_crashing(self) -> None:
        summary = summarize_records(
            [
                {"payload": {"type": "odometry", "seq": 1}},
                {
                    "payload": {
                        "type": "odometry",
                        "leftTicks": 10,
                        "rightTicks": 12,
                    }
                },
            ]
        )

        self.assertEqual(summary["encoder"]["sampleCount"], 1)
        self.assertEqual(summary["encoder"]["invalidSampleCount"], 1)


if __name__ == "__main__":
    unittest.main()
