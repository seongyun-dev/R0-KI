from __future__ import annotations

import threading
import time
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from integration.runtime_state_backend_adapter import (
    FinalRuntimeService,
    RuntimeStateBackendAdapter,
)
from state.robot_state_store import RobotStateStore


class FakeMissionController:
    def __init__(self) -> None:
        self.patrol_active = False
        self.start_calls = 0
        self.stop_calls = 0
        self.speed = 0
        self.steering_deg = 80

    def start_patrol(
        self,
        *,
        speed: int = 0,
        steering_deg: int | None = None,
    ) -> None:
        self.start_calls += 1
        self.patrol_active = True
        self.speed = speed
        if steering_deg is not None:
            self.steering_deg = steering_deg

    def stop_patrol(self) -> None:
        self.stop_calls += 1
        self.patrol_active = False
        self.speed = 0


class FakeRuntime:
    def __init__(self) -> None:
        self.hardware_listeners: list[object] = []
        self.odometry_listeners: list[object] = []
        self.mission = FakeMissionController()
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.stop_reasons: list[str] = []
        self.state_store = SimpleNamespace(
            snapshot=lambda: SimpleNamespace(
                motion_state=SimpleNamespace(
                    left_distance_m=0.0,
                    right_distance_m=0.0,
                ),
                safety_decision=SimpleNamespace(
                    allowed=True,
                    fault="NONE",
                ),
            )
        )

    def add_hardware_status_listener(self, listener: object) -> None:
        self.hardware_listeners.append(listener)

    def add_odometry_listener(self, listener: object) -> None:
        self.odometry_listeners.append(listener)

    def run_forever(self) -> None:
        self.started.set()
        self.stopped.wait(timeout=1.0)

    def request_stop(self) -> None:
        self.stopped.set()

    def stop_patrol(self, reason: str = "PATROL_STOP") -> None:
        self.stop_reasons.append(reason)
        self.mission.stop_patrol()


class FakeNavigationService:
    def __init__(self) -> None:
        self.listeners: list[object] = []
        self.start_calls: list[int | None] = []
        self.stop_calls = 0
        self.pose_updates: list[object] = []

    def add_event_listener(self, listener: object) -> None:
        self.listeners.append(listener)

    def start_patrol(self, *, patrol_id: int | None) -> None:
        self.start_calls.append(patrol_id)

    def stop_patrol(self) -> None:
        self.stop_calls += 1

    def update_pose(self, pose: object) -> tuple[object, ...]:
        self.pose_updates.append(pose)
        return ()

    def emit(self, event_type: str) -> None:
        event = SimpleNamespace(
            mission_event=SimpleNamespace(
                event_type=SimpleNamespace(value=event_type)
            )
        )
        for listener in tuple(self.listeners):
            listener(event)  # type: ignore[operator]


class RuntimeStateBackendAdapterTest(unittest.TestCase):
    def test_navigation_builder_loads_route_and_rejects_missing_file(self) -> None:
        from run_integrated import _build_navigation_service

        with self.assertRaisesRegex(RuntimeError, "refusing fixed straight"):
            _build_navigation_service("/definitely/missing/route.yaml")

        with tempfile.TemporaryDirectory() as directory:
            route_path = Path(directory) / "route.yaml"
            route_path.write_text(
                """schema_version: 1
map_id: demo
map_version: 1
route_id: route
frame_id: map
waypoints:
  - sequence: 1
    x: 0.6
    y: 0.0
    yaw_deg: 0.0
    acceptance_radius_m: 0.2
    action: DESTINATION
""",
                encoding="utf-8",
            )
            service = _build_navigation_service(route_path)
            self.assertEqual(service._route.route_id, "route")

    def test_listener_updates_only_legacy_hardware_fields(self) -> None:
        runtime = FakeRuntime()
        store = RobotStateStore()
        adapter = RuntimeStateBackendAdapter(
            runtime=runtime,
            backend_state_store=store,
        )

        adapter.connect()
        adapter.connect()
        self.assertEqual(len(runtime.hardware_listeners), 1)
        self.assertEqual(len(runtime.odometry_listeners), 0)

        listener = runtime.hardware_listeners[0]
        listener(  # type: ignore[operator]
            SimpleNamespace(
                battery_percent=82.5,
                motor=SimpleNamespace(value="NORMAL"),
                line_sensor=SimpleNamespace(value="FAULT"),
            )
        )

        status = store.get_status()
        self.assertEqual(status.battery, 82.5)
        self.assertEqual(status.motor, "NORMAL")
        self.assertEqual(status.line_sensor, "FAULT")
        self.assertEqual(status.camera, "DISCONNECTED")
        self.assertEqual(status.lidar, "DISCONNECTED")
        self.assertEqual(status.obstacle.status, "CLEAR")
        self.assertEqual(status.obstacle.direction, "NONE")

    def test_final_runtime_service_owns_one_runtime_thread(self) -> None:
        runtime = FakeRuntime()
        service = FinalRuntimeService(runtime)

        service.start()
        service.start()
        self.assertTrue(runtime.started.wait(timeout=0.5))
        self.assertTrue(service.is_running())
        self.assertEqual(
            [thread.name for thread in threading.enumerate()].count(
                "robot-runtime"
            ),
            1,
        )

        service.send_command("START_PATROL", patrolId=7)
        self.assertTrue(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.start_calls, 1)
        self.assertEqual(runtime.mission.speed, 45)
        self.assertEqual(runtime.mission.steering_deg, 80)

        service.send_command("STOP_PATROL")
        self.assertFalse(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.stop_calls, 1)

        with self.assertRaisesRegex(ValueError, "unsupported"):
            service.send_command("CONTROL")

        service.stop()
        time.sleep(0.01)
        self.assertFalse(service.is_running())

    def test_integrated_di_does_not_construct_legacy_serial_reader(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        with patch(
            "serial_reader.ESP32SerialReader.__init__",
            side_effect=AssertionError("legacy SerialReader must not be built"),
        ):
            application = create_integrated_application(
                final_runtime=runtime
            )

        self.assertEqual(len(runtime.hardware_listeners), 1)
        self.assertEqual(
            application._serial_reader.__class__.__name__,
            "EncoderWaypointRuntimeService",
        )

    def test_waypoint_navigation_replaces_fixed_straight_start(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        navigation = FakeNavigationService()
        application = create_integrated_application(
            final_runtime=runtime,
            navigation_service=navigation,
        )
        application._serial_reader.start()
        self.addCleanup(application._serial_reader.stop)

        application._serial_reader.send_command("START_PATROL", patrolId=17)
        self.assertEqual(navigation.start_calls, [17])
        self.assertTrue(runtime.mission.patrol_active)
        self.assertEqual(
            runtime.mission.speed,
            application._settings.patrol_drive_speed_pwm,
        )

        odometry_listener = runtime.odometry_listeners[0]
        odometry_listener(
            SimpleNamespace(),
            SimpleNamespace(
                left_distance_m=0.2,
                right_distance_m=0.2,
            ),
        )
        self.assertGreater(len(navigation.pose_updates), 0)
        self.assertAlmostEqual(navigation.pose_updates[-1].x, 0.2)

        navigation.emit("DESTINATION_REACHED")
        self.assertFalse(runtime.mission.patrol_active)
        self.assertIn("DESTINATION_REACHED", runtime.stop_reasons)
        self.assertEqual(application._state_store.get_status().state, "IDLE")

        application._serial_reader.send_command("STOP_PATROL")
        self.assertEqual(navigation.stop_calls, 1)

    def test_real_short_route_stops_runtime_at_destination(self) -> None:
        from run_integrated import (
            _build_navigation_service,
            create_integrated_application,
        )

        runtime = FakeRuntime()
        route_path = (
            Path(__file__).resolve().parents[1]
            / "roki"
            / "maps"
            / "dummy_rectangle"
            / "route.odom-demo.yaml"
        )
        navigation = _build_navigation_service(route_path)
        application = create_integrated_application(
            final_runtime=runtime,
            navigation_service=navigation,
        )
        application._serial_reader.start()
        self.addCleanup(application._serial_reader.stop)

        application._serial_reader.send_command("START_PATROL", patrolId=18)
        odometry_listener = runtime.odometry_listeners[0]
        for distance_m in (0.20, 0.40, 0.60):
            odometry_listener(
                SimpleNamespace(),
                SimpleNamespace(
                    left_distance_m=distance_m,
                    right_distance_m=distance_m,
                ),
            )

        self.assertFalse(runtime.mission.patrol_active)
        self.assertIn("DESTINATION_REACHED", runtime.stop_reasons)
        self.assertEqual(navigation.state.value, "COMPLETED")
        self.assertEqual(application._state_store.get_status().state, "IDLE")

    def test_existing_publisher_reads_adapter_updated_backend_store(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        application = create_integrated_application(final_runtime=runtime)
        listener = runtime.hardware_listeners[0]
        listener(  # type: ignore[operator]
            SimpleNamespace(
                battery_percent=74.5,
                motor=SimpleNamespace(value="NORMAL"),
                line_sensor=SimpleNamespace(value="NORMAL"),
            )
        )
        application._mqtt_client.publish = Mock()

        application._publish_status_if_needed(current_time=100.0)

        application._mqtt_client.publish.assert_called_once()
        call = application._mqtt_client.publish.call_args.kwargs
        self.assertEqual(call["topic"], application._settings.status_topic)
        self.assertEqual(call["payload"]["battery"], 74.5)
        self.assertEqual(call["payload"]["motor"], "NORMAL")
        self.assertEqual(call["payload"]["lineSensor"], "NORMAL")
        self.assertEqual(
            set(call["payload"]),
            {
                "schemaVersion",
                "robotKey",
                "battery",
                "state",
                "motor",
                "camera",
                "lidar",
                "lineSensor",
                "obstacle",
                "timestamp",
            },
        )

    def test_existing_command_handler_controls_final_mission_and_publishes_ack(
        self,
    ) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        application = create_integrated_application(final_runtime=runtime)
        application._pipeline_runner.is_running = Mock(return_value=False)
        application._pipeline_runner.start = Mock()
        application._pipeline_runner.stop = Mock()
        application._mqtt_client.publish = Mock()
        application._command_handler._pipeline_enabled = True
        application._serial_reader.start()
        self.addCleanup(application._serial_reader.stop)

        application._command_handler.handle(
            application._settings.command_topic,
            {
                "command": "START_PATROL",
                "commandId": "command-start",
                "patrolId": 17,
            },
        )

        self.assertTrue(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.start_calls, 1)
        self.assertEqual(
            application._state_store.get_status().state,
            "PATROLLING",
        )
        application._pipeline_runner.start.assert_called_once()
        start_ack = application._mqtt_client.publish.call_args.kwargs
        self.assertEqual(
            start_ack["topic"],
            application._settings.command_response_topic,
        )
        self.assertEqual(start_ack["payload"]["commandId"], "command-start")
        self.assertEqual(start_ack["payload"]["command"], "START_PATROL")
        self.assertEqual(start_ack["payload"]["status"], "SUCCEEDED")
        self.assertEqual(
            set(start_ack["payload"]),
            {
                "schemaVersion",
                "commandId",
                "command",
                "status",
                "receivedAt",
            },
        )

        application._mqtt_client.publish.reset_mock()
        application._pipeline_runner.is_running.return_value = True
        application._command_handler.handle(
            application._settings.command_topic,
            {
                "command": "STOP_PATROL",
                "commandId": "command-stop",
            },
        )

        self.assertFalse(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.stop_calls, 1)
        self.assertEqual(application._state_store.get_status().state, "IDLE")
        application._pipeline_runner.stop.assert_called_once()
        stop_ack = application._mqtt_client.publish.call_args.kwargs
        self.assertEqual(
            stop_ack["topic"],
            application._settings.command_response_topic,
        )
        self.assertEqual(stop_ack["payload"]["commandId"], "command-stop")
        self.assertEqual(stop_ack["payload"]["command"], "STOP_PATROL")
        self.assertEqual(stop_ack["payload"]["status"], "SUCCEEDED")

    def test_mqtt_start_odometry_destination_then_stop_ack(self) -> None:
        from run_integrated import _build_navigation_service, create_integrated_application

        with tempfile.TemporaryDirectory() as directory:
            route_path = Path(directory) / "route.yaml"
            route_path.write_text(
                """schema_version: 1
map_id: dummy-rectangle
map_version: 1
route_id: mqtt-physical-demo
frame_id: map
waypoints:
  - sequence: 1
    name: CHECKPOINT_20CM
    x: 0.2
    y: 0.0
    yaw_deg: 0.0
    acceptance_radius_m: 0.04
    action: PASS
  - sequence: 2
    name: SCAN_POINT_40CM
    x: 0.4
    y: 0.0
    yaw_deg: 0.0
    acceptance_radius_m: 0.04
    action: SCAN
  - sequence: 3
    name: DESTINATION_60CM
    x: 0.6
    y: 0.0
    yaw_deg: 0.0
    acceptance_radius_m: 0.04
    action: DESTINATION
""",
                encoding="utf-8",
            )
            runtime = FakeRuntime()
            navigation = _build_navigation_service(route_path)
            application = create_integrated_application(
                final_runtime=runtime,
                navigation_service=navigation,
            )
            application._pipeline_runner.start = Mock()
            application._pipeline_runner.stop = Mock()
            application._command_handler._pipeline_enabled = False
            application._mqtt_client.publish = Mock()
            application._serial_reader.start()
            self.addCleanup(application._serial_reader.stop)

            application._command_handler.handle(
                application._settings.command_topic,
                {
                    "command": "START_PATROL",
                    "commandId": "start-demo",
                    "patrolId": 23,
                },
            )
            self.assertTrue(runtime.mission.patrol_active)
            listener = runtime.odometry_listeners[0]
            for distance in (0.17, 0.37, 0.57):
                listener(
                    SimpleNamespace(),
                    SimpleNamespace(
                        left_distance_m=distance,
                        right_distance_m=distance,
                    ),
                )

            self.assertFalse(runtime.mission.patrol_active)
            self.assertIn("DESTINATION_REACHED", runtime.stop_reasons)
            self.assertEqual(application._state_store.get_status().state, "IDLE")

            application._command_handler.handle(
                application._settings.command_topic,
                {
                    "command": "STOP_PATROL",
                    "commandId": "stop-demo",
                },
            )
            self.assertIn("MQTT_STOP_PATROL", runtime.stop_reasons)
            ack = application._mqtt_client.publish.call_args.kwargs["payload"]
            self.assertEqual(ack["commandId"], "stop-demo")
            self.assertEqual(ack["status"], "SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
