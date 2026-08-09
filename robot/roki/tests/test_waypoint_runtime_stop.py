from __future__ import annotations

import unittest

from serial_comm.protocol import HardwareStatus, LineSensorStatus, MotorStatus, Odometry
from tests.test_robot_runtime import FakeBridge, complete_handshake, create_runtime


class WaypointRuntimeStopTest(unittest.TestCase):
    def test_destination_listener_stop_prevents_stale_control_write(self) -> None:
        bridge = FakeBridge([])
        runtime, _store = create_runtime(bridge)
        runtime.mission.start_patrol(speed=30, steering_deg=80)
        bridge.connected = True
        runtime._on_connected()
        complete_handshake(runtime)
        runtime._handle_hardware_status(
            HardwareStatus(
                battery_percent=82.5,
                motor=MotorStatus.NORMAL,
                line_sensor=LineSensorStatus.NORMAL,
            )
        )
        runtime._handle_odometry(Odometry(1, 100, 0, 0))
        controls_before = sum(
            message["type"] == "control" for message in bridge.written
        )

        runtime.add_odometry_listener(
            lambda _odometry, _state: runtime.stop_patrol(
                "DESTINATION_REACHED"
            )
        )
        runtime._handle_odometry(Odometry(2, 200, 1, 1))

        controls_after = sum(
            message["type"] == "control" for message in bridge.written
        )
        self.assertEqual(controls_after, controls_before)
        self.assertEqual(bridge.written[-1]["type"], "stop")


if __name__ == "__main__":
    unittest.main()
