from __future__ import annotations

import unittest

from navigation.cmd_vel_adapter import (
    AckermannCommandSettings,
    CmdVelToEsp32Adapter,
    MemoryControlTransport,
)


class CmdVelAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = CmdVelToEsp32Adapter(
            AckermannCommandSettings(
                wheelbase_m=0.25,
                maximum_road_wheel_angle_deg=30.0,
            )
        )

    def test_stop_and_in_place_rotation_fail_closed(self) -> None:
        stopped = self.adapter.convert(0.0, 0.0)
        self.assertEqual((stopped.speed_pwm, stopped.steering_deg), (0, 80))
        self.assertEqual(stopped.stop_reason, "STOPPED")

        rotation = self.adapter.convert(0.0, 0.5)
        self.assertTrue(rotation.stopped)
        self.assertEqual(rotation.stop_reason, "IN_PLACE_ROTATION_REJECTED")

    def test_straight_and_curves_are_bounded(self) -> None:
        straight = self.adapter.convert(0.2, 0.0)
        self.assertEqual(straight.steering_deg, 80)
        self.assertGreaterEqual(straight.speed_pwm, 45)

        left = self.adapter.convert(0.2, 2.0)
        right = self.adapter.convert(0.2, -2.0)
        self.assertEqual(left.steering_deg, 60)
        self.assertEqual(right.steering_deg, 100)
        self.assertLessEqual(abs(left.speed_pwm), 51)

    def test_reverse_and_missing_calibration(self) -> None:
        reverse_left_yaw = self.adapter.convert(-0.2, 1.0)
        self.assertLess(reverse_left_yaw.speed_pwm, 0)
        self.assertGreater(reverse_left_yaw.steering_deg, 80)

        uncalibrated = CmdVelToEsp32Adapter(
            AckermannCommandSettings(
                wheelbase_m=None,
                maximum_road_wheel_angle_deg=None,
            )
        )
        command = uncalibrated.convert(0.2, 0.5)
        self.assertTrue(command.stopped)
        self.assertEqual(command.stop_reason, "STEERING_NOT_CALIBRATED")
        self.assertGreater(uncalibrated.convert(0.2, 0.0).speed_pwm, 0)

    def test_memory_transport_does_not_touch_hardware(self) -> None:
        transport = MemoryControlTransport()
        command = self.adapter.convert(0.2, 0.0)
        transport.send(command)
        self.assertEqual(transport.commands, [command])


if __name__ == "__main__":
    unittest.main()
