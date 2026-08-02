from __future__ import annotations

import unittest

from navigation.cmd_vel_adapter import AckermannCommandSettings
from navigation.ros_nav2_bridge import RosNav2Bridge, RosNav2BridgeSettings


class RosNav2BridgeTest(unittest.TestCase):
    def test_cmd_vel_uses_calibrated_adapter_without_serial_ownership(self) -> None:
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                ackermann=AckermannCommandSettings(
                    wheelbase_m=0.24,
                    maximum_road_wheel_angle_deg=25,
                    minimum_drive_pwm=45,
                    maximum_drive_pwm=51,
                )
            ),
            motion_sink=commands.append,
        )

        command = bridge.record_cmd_vel(0.2, 0.2)

        self.assertEqual(commands, [command])
        self.assertGreater(command.speed_pwm, 0)
        self.assertLess(command.steering_deg, 80)
        self.assertFalse(hasattr(bridge, "_serial"))

    def test_uncalibrated_turn_is_stopped(self) -> None:
        commands = []
        bridge = RosNav2Bridge(
            settings=RosNav2BridgeSettings(
                ackermann=AckermannCommandSettings(None, None)
            ),
            motion_sink=commands.append,
        )
        command = bridge.record_cmd_vel(0.2, 0.3)
        self.assertTrue(command.stopped)
        self.assertEqual(command.stop_reason, "STEERING_NOT_CALIBRATED")


if __name__ == "__main__":
    unittest.main()
