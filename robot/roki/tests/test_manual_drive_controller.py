from __future__ import annotations

import threading
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


class BlockingRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.target_entered = threading.Event()
        self.release_target = threading.Event()
        self.order: list[str] = []

    def request_motion_target(
        self,
        speed: int,
        steering_deg: int,
        *,
        stationary_steering: bool = False,
    ) -> None:
        self.target_entered.set()
        if not self.release_target.wait(timeout=2.0):
            raise TimeoutError("test did not release manual target")
        super().request_motion_target(
            speed,
            steering_deg,
            stationary_steering=stationary_steering,
        )
        self.order.append("target")

    def request_motion_stop(self, steering_deg: int) -> None:
        super().request_motion_stop(steering_deg)
        self.order.append("stop")


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

    def test_concurrent_deactivate_enqueues_stop_after_inflight_key(self) -> None:
        runtime = BlockingRuntime()
        controller = ManualDriveController(
            runtime=runtime,
            state_store=self.store,
            settings=ManualDriveSettings(),
            clock=lambda: self.now,
        )
        controller.activate(17)
        runtime.order.clear()

        key_thread = threading.Thread(target=lambda: controller.handle_key("w"))
        key_thread.start()
        self.assertTrue(runtime.target_entered.wait(timeout=1.0))

        deactivate_done = threading.Event()

        def deactivate() -> None:
            controller.deactivate()
            deactivate_done.set()

        deactivate_thread = threading.Thread(target=deactivate)
        deactivate_thread.start()
        self.assertFalse(deactivate_done.wait(timeout=0.1))

        runtime.release_target.set()
        key_thread.join(timeout=1.0)
        deactivate_thread.join(timeout=1.0)

        self.assertFalse(key_thread.is_alive())
        self.assertFalse(deactivate_thread.is_alive())
        self.assertEqual(runtime.order, ["target", "stop"])
        self.assertFalse(controller.active)

    def test_mapping_mode_does_not_block_forward_on_obstacle(self) -> None:
        controller = ManualDriveController(
            runtime=self.runtime,
            state_store=self.store,
            settings=ManualDriveSettings(
                steering_min_deg=60,
                steering_max_deg=100,
                require_clear_path=False,
            ),
            clock=lambda: self.now,
        )
        controller.activate(9)
        self.store.update_lidar_status("DISCONNECTED")
        self.store.update_obstacle(ObstacleState("STOP", "FRONT", "mapped"))

        self.assertEqual(controller.handle_key("w"), "FORWARD")
        self.assertEqual(self.runtime.targets[-1], (45, 80, False))


if __name__ == "__main__":
    unittest.main()
