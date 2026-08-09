from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from integration.runtime_state_backend_adapter import FinalRuntimeService
from backend_mqtt.command_handler import PatrolCommandHandler
from backend_mqtt.publisher import RokiPublisherApplication
from navigation.route import parse_route
from navigation.service import WaypointNavigationService
from backend_state.models import HardwareState
from backend_state.robot_state_store import RobotStateStore


class SimulationStore(RobotStateStore):
    def snapshot(self):
        return SimpleNamespace(
            motion_state=SimpleNamespace(
                left_distance_m=0.0,
                right_distance_m=0.0,
            ),
            safety_decision=SimpleNamespace(allowed=True, fault="NONE"),
        )


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


class FakeEsp32Runtime:
    def __init__(self) -> None:
        self.state_store = SimulationStore()
        self.state_store.update_hardware(HardwareState(80.0, "NORMAL", "DISCONNECTED"))
        self.state_store.update_lidar_status("NORMAL")
        self.mission = FakeMission()
        self.listeners = []
        self.stop_reasons: list[str] = []
        self.started = threading.Event()
        self.finished = threading.Event()
        self.run_count = 0

    def add_odometry_listener(self, listener) -> None:
        self.listeners.append(listener)

    def run_forever(self) -> None:
        self.run_count += 1
        self.started.set()
        self.finished.wait(timeout=2.0)

    def request_stop(self) -> None:
        self.finished.set()

    def stop_patrol(self, reason: str) -> None:
        self.stop_reasons.append(reason)
        self.mission.stop_patrol()


class FakeMqtt:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def publish(self, *, topic: str, payload: dict) -> None:
        self.messages.append((topic, payload))


class FakeAi:
    def __init__(self) -> None:
        self.active_patrol: int | None = None
        self.disabled = False

    def readiness(self):
        return True, "AI_READY"

    def enable(self, patrol_id: int) -> None:
        self.active_patrol = patrol_id

    def disable(self, _reason: str) -> None:
        self.active_patrol = None
        self.disabled = True


def route():
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "dummy",
            "map_version": 1,
            "route_id": "software-e2e",
            "frame_id": "map",
            "waypoints": [
                {"sequence": 1, "name": "CHECKPOINT", "x": 1.2, "y": 2.5, "yaw_deg": 0, "acceptance_radius_m": 0.04, "action": "PASS"},
                {"sequence": 2, "name": "SCAN", "x": 1.4, "y": 2.5, "yaw_deg": 0, "acceptance_radius_m": 0.04, "action": "SCAN"},
                {"sequence": 3, "name": "DESTINATION", "x": 1.6, "y": 2.5, "yaw_deg": 0, "acceptance_radius_m": 0.04, "action": "DESTINATION"},
            ],
        }
    )


class FullPatrolSimulationTest(unittest.TestCase):
    def test_start_destination_backend_stop_ack_and_idle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            now = datetime(2026, 8, 3, tzinfo=timezone.utc)
            settings = SimpleNamespace(
                schema_version=1,
                robot_key="ROKI-01",
                command_topic="hanbakwi/v1/robots/ROKI-01/command",
                command_response_topic="hanbakwi/v1/robots/ROKI-01/command/ack",
                pose_topic="hanbakwi/v1/robots/ROKI-01/pose",
                status_topic="hanbakwi/v1/robots/ROKI-01/status",
                pose_publish_interval_seconds=1.0,
                status_publish_interval_seconds=5.0,
                ai_required_for_patrol=True,
                lidar_required_for_patrol=True,
                obstacle_clear_hold_seconds=1.0,
                service_token_file=str(Path(directory) / "token"),
                command_cache_file=str(Path(directory) / "commands.json"),
            )
            runtime = FakeEsp32Runtime()
            navigation = WaypointNavigationService(route())
            service = FinalRuntimeService(
                runtime,
                patrol_drive_speed_pwm=45,
                patrol_steering_degrees=80,
                navigation_service=navigation,
                encoder_fallback_enabled=True,
                wall_clock=lambda: now,
            )
            mqtt = FakeMqtt()
            ai = FakeAi()
            handler = PatrolCommandHandler(
                settings=settings,
                mqtt_client=mqtt,
                serial_reader=service,
                state_store=runtime.state_store,
                pipeline_runner=SimpleNamespace(stop=lambda: None),
                ai_controller=ai,
                command_cache_path=settings.command_cache_file,
                wall_clock=lambda: now,
            )
            app = RokiPublisherApplication(
                settings=settings,
                serial_reader=service,
                state_store=runtime.state_store,
                mqtt_client=mqtt,
                command_handler=handler,
                pipeline_runner=SimpleNamespace(stop=lambda: None),
            )
            handler.set_flush_telemetry(app.publish_now)
            service.set_destination_listener(handler.on_destination_reached)
            service.start()
            self.addCleanup(service.stop)
            self.assertTrue(runtime.started.wait(timeout=0.5))

            def command(name: str, command_id: str, patrol_id=None):
                body = {
                    "schemaVersion": 1,
                    "command": name,
                    "commandId": command_id,
                    "issuedAt": now.isoformat(),
                    "expiresAt": (now + timedelta(seconds=10)).isoformat(),
                }
                if patrol_id is not None:
                    body["patrolId"] = patrol_id
                return body

            handler.handle(
                settings.command_topic,
                command("START_PATROL", "start-31", patrol_id=31),
            )
            self.assertTrue(runtime.mission.active)
            self.assertEqual((runtime.mission.speed, runtime.mission.steering), (45, 80))
            self.assertEqual(ai.active_patrol, 31)

            listener = runtime.listeners[0]
            for distance in (0.2, 0.4, 0.6):
                listener(
                    SimpleNamespace(),
                    SimpleNamespace(
                        left_distance_m=distance,
                        right_distance_m=distance,
                    ),
                )

            destination_poses = [
                body
                for topic, body in mqtt.messages
                if topic == settings.pose_topic and body["x"] >= 1.56
            ]
            self.assertTrue(destination_poses, mqtt.messages)
            self.assertFalse(runtime.mission.active)
            self.assertIn("DESTINATION_REACHED", runtime.stop_reasons)
            self.assertTrue(ai.disabled)
            self.assertIsNone(ai.active_patrol)

            handler.handle(
                settings.command_topic,
                command("STOP_PATROL", "stop-31"),
            )
            acks = [
                body
                for topic, body in mqtt.messages
                if topic == settings.command_response_topic
            ]
            self.assertEqual(
                [(ack["command"], ack["status"]) for ack in acks],
                [("START_PATROL", "SUCCEEDED"), ("STOP_PATROL", "SUCCEEDED")],
            )
            self.assertEqual(runtime.state_store.get_status().state, "IDLE")
            self.assertTrue(ai.disabled)
            self.assertEqual(runtime.run_count, 1)


if __name__ == "__main__":
    unittest.main()
