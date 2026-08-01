import unittest

from mission.mission_controller import MissionCommand, MissionController


class MissionControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = MissionController(steering_center_deg=80)

    def test_start_patrol_does_not_invent_motion_target(self) -> None:
        self.controller.start_patrol()

        self.assertTrue(self.controller.patrol_active)
        self.assertEqual(
            self.controller.current(),
            MissionCommand(speed=0, steering_deg=80),
        )

    def test_start_patrol_accepts_explicit_drive_and_steering_target(self) -> None:
        self.controller.start_patrol(speed=51, steering_deg=85)

        self.assertTrue(self.controller.patrol_active)
        self.assertEqual(
            self.controller.current(),
            MissionCommand(speed=51, steering_deg=85),
        )

    def test_stop_patrol_deactivates_and_requests_stationary_target(self) -> None:
        self.controller.submit(MissionCommand(speed=35, steering_deg=75))
        self.controller.start_patrol()

        self.controller.stop_patrol()

        self.assertFalse(self.controller.patrol_active)
        self.assertEqual(
            self.controller.current(),
            MissionCommand(speed=0, steering_deg=75),
        )

    def test_emergency_stop_deactivates_patrol(self) -> None:
        self.controller.start_patrol()

        self.controller.emergency_stop()

        self.assertFalse(self.controller.patrol_active)
        self.assertTrue(self.controller.current().emergency_stop)


if __name__ == "__main__":
    unittest.main()
