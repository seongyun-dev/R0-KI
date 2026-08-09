from __future__ import annotations

import math
import unittest

from control.motion_controller import (
    MotionController,
    MotionControllerSettings,
    MotionTarget,
)
from serial_comm.protocol import Odometry


def odometry(ms: int, left: int, right: int, seq: int = 1) -> Odometry:
    return Odometry(
        seq=seq,
        uptime_ms=ms,
        left_ticks=left,
        right_ticks=right,
    )


class MotionControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = MotionController(
            MotionControllerSettings(
                wheel_diameter_m=0.065,
                encoder_ticks_per_revolution=100,
                speed_min=10,
                speed_max=255,
                speed_ramp_per_update=10,
                straight_correction_kp_deg_per_tick=1.0,
                maximum_straight_correction_deg=5,
                steering_center_deg=80,
                steering_min_deg=60,
                steering_max_deg=100,
            )
        )

    def test_odometry_ramp_and_straight_steering_correction(self) -> None:
        command, _ = self.controller.update(
            odometry(100, 0, 0), MotionTarget(50, 80)
        )
        self.assertEqual((command.speed, command.steering_deg), (10, 80))
        command, state = self.controller.update(
            odometry(200, 12, 10, seq=2), MotionTarget(50, 80)
        )
        self.assertEqual((command.speed, command.steering_deg), (20, 78))
        self.assertAlmostEqual(state.left_distance_m or 0, 12 * math.pi * 0.065 / 100)
        self.assertEqual(state.encoder_error_ticks, 2)

    def test_uncalibrated_controller_never_creates_speed(self) -> None:
        controller = MotionController(
            MotionControllerSettings(0.065, None, None, 255, None, None, None, 80, 60, 100)
        )
        command, state = controller.update(
            odometry(100, 0, 0), MotionTarget(100, 80)
        )
        self.assertEqual(command.speed, 0)
        self.assertIsNone(state.average_distance_m)

    def test_stop_bypasses_ramp(self) -> None:
        self.controller.update(
            odometry(100, 0, 0), MotionTarget(50, 80)
        )
        self.assertEqual(self.controller.stop_command().speed, 0)

    def test_non_monotonic_odometry_is_rejected(self) -> None:
        self.controller.update(
            odometry(100, 0, 0), MotionTarget(0, 80)
        )
        with self.assertRaises(ValueError):
            self.controller.update(
                odometry(100, 1, 1, seq=2), MotionTarget(0, 80)
            )


if __name__ == "__main__":
    unittest.main()
