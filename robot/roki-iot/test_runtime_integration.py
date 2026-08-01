from __future__ import annotations

import threading
import time
import unittest
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

    def add_hardware_status_listener(self, listener: object) -> None:
        self.hardware_listeners.append(listener)

    def add_odometry_listener(self, listener: object) -> None:
        self.odometry_listeners.append(listener)

    def run_forever(self) -> None:
        self.started.set()
        self.stopped.wait(timeout=1.0)

    def request_stop(self) -> None:
        self.stopped.set()


class RuntimeStateBackendAdapterTest(unittest.TestCase):
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
        self.assertEqual(runtime.mission.speed, 51)
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
            "FinalRuntimeService",
        )

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


if __name__ == "__main__":
    unittest.main()
