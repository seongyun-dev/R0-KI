from __future__ import annotations

import threading
import time
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1] / "roki"))

from integration.runtime_state_backend_adapter import FinalRuntimeService
from navigation.route import parse_route
from navigation.service import WaypointNavigationService


class FakeMission:
    def __init__(self) -> None:
        self.active = False
        self.speed = 0
        self.steering = 80

    def start_patrol(self, *, speed: int, steering_deg: int) -> None:
        self.active = True
        self.speed = speed
        self.steering = steering_deg

    def stop_patrol(self) -> None:
        self.active = False
        self.speed = 0


class FakeStore:
    def __init__(self) -> None:
        self.state = "IDLE"

    def snapshot(self) -> object:
        return SimpleNamespace(
            motion_state=SimpleNamespace(
                left_distance_m=0.0,
                right_distance_m=0.0,
            ),
            safety_decision=SimpleNamespace(allowed=True, fault="NONE"),
        )

    def update_robot_state(self, state: str) -> None:
        self.state = state


class FakeRuntime:
    def __init__(self) -> None:
        self.mission = FakeMission()
        self.state_store = FakeStore()
        self.odometry_listeners: list[object] = []
        self.stop_reasons: list[str] = []
        self._finished = threading.Event()

    def add_odometry_listener(self, listener: object) -> None:
        self.odometry_listeners.append(listener)

    def run_forever(self) -> None:
        self._finished.wait(timeout=1.0)

    def request_stop(self) -> None:
        self._finished.set()

    def stop_patrol(self, reason: str) -> None:
        self.stop_reasons.append(reason)
        self.mission.stop_patrol()


def short_route():
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "dummy-rectangle",
            "map_version": 1,
            "route_id": "status-merge-test",
            "frame_id": "map",
            "waypoints": [
                {
                    "sequence": 1,
                    "name": "CHECKPOINT_20CM",
                    "x": 1.2,
                    "y": 2.5,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.04,
                    "action": "PASS",
                },
                {
                    "sequence": 2,
                    "name": "SCAN_POINT_40CM",
                    "x": 1.4,
                    "y": 2.5,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.04,
                    "action": "SCAN",
                },
                {
                    "sequence": 3,
                    "name": "DESTINATION_60CM",
                    "x": 1.6,
                    "y": 2.5,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.04,
                    "action": "DESTINATION",
                },
            ],
        }
    )


class StatusMergeWaypointTest(unittest.TestCase):
    def test_start_odometry_destination_and_explicit_stop(self) -> None:
        runtime = FakeRuntime()
        navigation = WaypointNavigationService(short_route())
        service = FinalRuntimeService(
            runtime,
            patrol_drive_speed_pwm=45,
            navigation_service=navigation,
        )
        service.start()
        self.addCleanup(service.stop)

        service.send_command("START_PATROL", patrolId=23)
        self.assertTrue(runtime.mission.active)
        self.assertEqual(runtime.mission.speed, 45)
        listener = runtime.odometry_listeners[0]
        for distance in (0.17, 0.37, 0.57):
            listener(
                SimpleNamespace(),
                SimpleNamespace(
                    left_distance_m=distance,
                    right_distance_m=distance,
                ),
            )

        self.assertFalse(runtime.mission.active)
        self.assertIn("DESTINATION_REACHED", runtime.stop_reasons)
        self.assertEqual(runtime.state_store.state, "IDLE")

        service.send_command("STOP_PATROL")
        self.assertIn("MQTT_STOP_PATROL", runtime.stop_reasons)
        time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
