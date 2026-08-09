from __future__ import annotations

import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from integration.encoder_waypoint_runtime_service import (
    EncoderWaypointRuntimeService,
)
from navigation.route import load_route
from navigation.service import WaypointNavigationService


class FakeMission:
    def __init__(self) -> None:
        self.active = False
        self.speed = 0

    def start_patrol(self, *, speed: int, steering_deg: int) -> None:
        del steering_deg
        self.active = True
        self.speed = speed

    def stop_patrol(self) -> None:
        self.active = False
        self.speed = 0


class FakeStateStore:
    def __init__(self) -> None:
        self.robot_state = "IDLE"

    def snapshot(self) -> object:
        return SimpleNamespace(
            motion_state=SimpleNamespace(
                left_distance_m=0.0,
                right_distance_m=0.0,
            ),
            safety_decision=SimpleNamespace(allowed=True, fault="NONE"),
        )

    def update_robot_state(self, state: str) -> None:
        self.robot_state = state


class FakeRuntime:
    def __init__(self) -> None:
        self.mission = FakeMission()
        self.state_store = FakeStateStore()
        self.listeners: list[object] = []
        self.stopped = threading.Event()
        self.stop_reasons: list[str] = []

    def add_odometry_listener(self, listener: object) -> None:
        self.listeners.append(listener)

    def run_forever(self) -> None:
        self.stopped.wait(timeout=1.0)

    def request_stop(self) -> None:
        self.stopped.set()

    def stop_patrol(self, reason: str) -> None:
        self.stop_reasons.append(reason)
        self.mission.stop_patrol()


class EncoderWaypointRuntimeServiceTest(unittest.TestCase):
    def test_start_odometry_destination_and_immediate_stop(self) -> None:
        runtime = FakeRuntime()
        route_path = (
            Path(__file__).resolve().parents[1]
            / "roki"
            / "maps"
            / "dummy_rectangle"
            / "route.odom-demo.yaml"
        )
        navigation = WaypointNavigationService(load_route(route_path))
        service = EncoderWaypointRuntimeService(
            runtime,
            navigation_service=navigation,
        )
        service.start()
        self.addCleanup(service.stop)

        service.send_command("START_PATROL", patrolId=19)
        self.assertTrue(runtime.mission.active)
        self.assertEqual(runtime.mission.speed, 45)

        listener = runtime.listeners[0]
        for distance in (0.2, 0.4, 0.6):
            listener(
                SimpleNamespace(),
                SimpleNamespace(
                    left_distance_m=distance,
                    right_distance_m=distance,
                ),
            )

        self.assertFalse(runtime.mission.active)
        self.assertIn("DESTINATION_REACHED", runtime.stop_reasons)
        self.assertEqual(runtime.state_store.robot_state, "IDLE")
        self.assertEqual(navigation.state.value, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
