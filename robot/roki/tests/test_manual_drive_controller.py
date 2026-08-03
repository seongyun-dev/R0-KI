from __future__ import annotations

import unittest

from control.manual_drive_controller import ManualDriveController, ManualDriveSettings
from mission.mission_controller import MissionController
from state.robot_state import ObstacleState, RobotStateStore


class FakeRuntime:
    def __init__(self) -> None:
        self.mission = MissionController(80)
        self.targets: list[tuple[int, int, bool]] = []
        self.stops: list[int] = []

    def request_motion_target(
        self,
        speed: int,
        steering_deg: int,
        *,
        stationary_steering: bool = False,
    ) -> None:
        self.targets.append((speed, steering_deg, stationary_steering))

    def request_motion_stop(self, steering_deg: int) -> None:
        self.stops.append(steering_deg)


class ManualDriveControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 0.0
        self.runtime = FakeRuntime()
        self.store = RobotStateStore()
        self.store.update_lidar_status("NORMAL")
        self.controller = ManualDriveController(
            runtime=self.runtime,
            state_store=self.store,
            settings=ManualDriveSettings(),
            clock=lambda: self.now,
        )

    def test_keys_are_ignored_until_backend_patrol_is_active(self) -> None:
        self.assertEqual(self.controller.handle_key("w"), "IGNORED")
        self.controller.activate(17)
        self.assertTrue(self.controller.active)
        self.assertEqual(self.runtime.stops, [80])
        self.assertEqual(self.runtime.mission.current().speed, 0)

    def test_short_drive_pulse_stops_at_deadline(self) -> None:
        self.controller.activate(17)
        self.assertEqual(self.controller.handle_key("w"), "FORWARD")
        self.assertEqual(self.runtime.targets[-1], (45, 80, False))
        self.now = 0.2
        self.assertEqual(self.controller.tick(), "PULSE_STOP")
        self.assertEqual(self.runtime.stops[-1], 80)

    def test_forward_is_blocked_by_lidar_or_obstacle(self) -> None:
        self.controller.activate(17)
        self.store.update_lidar_status("DISCONNECTED")
        self.assertEqual(self.controller.handle_key("w"), "FORWARD_BLOCKED")
        self.store.update_lidar_status("NORMAL")
        self.assertEqual(self.controller.handle_key("w"), "FORWARD")
        self.store.update_obstacle(ObstacleState("STOP", "FRONT", "blocked"))
        self.assertEqual(self.controller.tick(), "SAFETY_STOP")

    def test_steering_is_clamped_and_stop_disables_motion(self) -> None:
        self.controller.activate(17)
        for _ in range(10):
            self.controller.handle_key("a")
        self.assertEqual(self.controller.steering_deg, 70)
        self.assertEqual(self.runtime.targets[-1], (0, 70, True))
        self.assertEqual(self.controller.handle_key(" "), "STOP")
        self.assertEqual(self.controller.handle_key("q"), "LOCAL_STOP")
        self.assertTrue(self.controller.active)
        self.controller.deactivate()
        self.assertFalse(self.controller.active)
        self.assertFalse(self.runtime.mission.patrol_active)


if __name__ == "__main__":
    unittest.main()
