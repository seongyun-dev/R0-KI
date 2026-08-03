from __future__ import annotations

import threading
import time
import unittest
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from integration.runtime_state_backend_adapter import (
    FinalRuntimeService,
    RuntimeStateBackendAdapter,
)
from backend_state.robot_state_store import RobotStateStore
from backend_state.models import HardwareState, ObstacleState


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
        self.state_store = RobotStateStore()
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
    def test_publisher_exits_when_single_serial_runtime_dies(self) -> None:
        from mqtt.publisher import RokiPublisherApplication

        serial_service = Mock()
        serial_service.is_running.return_value = False
        store = Mock()
        application = RokiPublisherApplication(
            settings=Mock(),
            serial_reader=serial_service,
            state_store=store,
            mqtt_client=Mock(),
            command_handler=Mock(),
            pipeline_runner=Mock(),
        )
        application._serial_reader_started = True

        with self.assertRaisesRegex(RuntimeError, "stopped unexpectedly"):
            application._run_publish_loop()

        store.update_robot_state.assert_called_once_with("ERROR")

    def test_patrol_holds_ota_guard_until_stop(self) -> None:
        runtime = FakeRuntime()
        guard = Mock()
        guard.acquire.return_value = (True, "READY")
        service = FinalRuntimeService(runtime, deployment_guard=guard)
        service.start()
        self.assertEqual(service.prepare_patrol(), (True, "READY"))

        service.send_command("START_PATROL", patrolId=7)
        guard.release.assert_not_called()
        service.send_command("STOP_PATROL")
        guard.release.assert_called_once_with()
        service.stop()

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
        self.assertEqual(status.line_sensor, "DISCONNECTED")
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

        self.assertEqual(len(runtime.hardware_listeners), 0)
        self.assertIs(application._state_store, runtime.state_store)
        self.assertEqual(
            application._serial_reader.__class__.__name__,
            "FinalRuntimeService",
        )

    def test_pose_bridge_and_publisher_share_final_runtime_store(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        pose_bridge = SimpleNamespace(
            state_store=runtime.state_store,
            start=Mock(),
            stop=Mock(),
        )
        application = create_integrated_application(
            final_runtime=runtime,
            pose_bridge=pose_bridge,
            start_serial_runtime=False,
        )

        self.assertIs(application._state_store, runtime.state_store)
        self.assertIs(application._pose_source, pose_bridge)
        self.assertIs(pose_bridge.state_store, application._state_store)
        self.assertFalse(application._start_serial_reader)

    def test_existing_publisher_reads_final_runtime_store_directly(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        application = create_integrated_application(final_runtime=runtime)
        runtime.state_store.update_hardware(
            HardwareState(
                battery=74.5,
                motor="NORMAL",
                line_sensor="NORMAL",
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

    def test_status_is_published_immediately_on_change_and_every_five_seconds(self) -> None:
        from mqtt.publisher import RokiPublisherApplication

        settings = SimpleNamespace(
            status_publish_interval_seconds=5.0,
            schema_version=1,
            robot_key="ROKI-01",
            status_topic="hanbakwi/v1/robots/ROKI-01/status",
        )
        store = RobotStateStore()
        store.update_hardware(
            HardwareState(
                battery=80.0,
                motor="NORMAL",
                line_sensor="NORMAL",
            )
        )
        client = Mock()
        application = RokiPublisherApplication(
            settings=settings,
            serial_reader=Mock(),
            state_store=store,
            mqtt_client=client,
            command_handler=Mock(),
            pipeline_runner=Mock(),
        )

        application._publish_status_if_needed(100.0)
        self.assertEqual(client.publish.call_count, 1)

        store.update_hardware(
            HardwareState(
                battery=79.9,
                motor="NORMAL",
                line_sensor="NORMAL",
            )
        )
        application._publish_status_if_needed(100.1)
        self.assertEqual(client.publish.call_count, 2)
        application._publish_status_if_needed(104.999)
        self.assertEqual(client.publish.call_count, 2)

        application._publish_status_if_needed(105.1)
        self.assertEqual(client.publish.call_count, 3)

    def test_lidar_bridge_is_injected_without_changing_camera(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        lidar_bridge = SimpleNamespace(
            state_store=runtime.state_store,
            start=Mock(),
            stop=Mock(),
        )
        application = create_integrated_application(
            final_runtime=runtime,
            lidar_health_bridge=lidar_bridge,
        )

        self.assertIs(application._lidar_health_source, lidar_bridge)
        self.assertIs(lidar_bridge.state_store, application._state_store)
        self.assertEqual(
            application._state_store.get_status().camera,
            "DISCONNECTED",
        )

    def test_existing_status_payload_reflects_obstacle_contract(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        application = create_integrated_application(final_runtime=runtime)
        runtime.state_store.update_hardware(
            HardwareState(80.0, "NORMAL", "NORMAL")
        )
        runtime.state_store.update_lidar_status("NORMAL")
        runtime.state_store.update_obstacle(
            ObstacleState(
                status="STOP",
                direction="FRONT",
                reason_message="전방에 장애물이 있습니다.",
            )
        )
        application._mqtt_client.publish = Mock()

        application._publish_status_if_needed(100.0)

        payload = application._mqtt_client.publish.call_args.kwargs["payload"]
        self.assertEqual(
            payload["obstacle"],
            {
                "status": "STOP",
                "direction": "FRONT",
                "reasonMessage": "전방에 장애물이 있습니다.",
            },
        )
        self.assertEqual(payload["camera"], "DISCONNECTED")
        self.assertEqual(payload["lidar"], "NORMAL")
        self.assertEqual(payload["motor"], "NORMAL")
        self.assertEqual(payload["lineSensor"], "NORMAL")

    def test_pose_publisher_keeps_one_second_interval(self) -> None:
        from mqtt.publisher import RokiPublisherApplication
        from backend_state.models import PoseState

        settings = SimpleNamespace(
            pose_publish_interval_seconds=1.0,
            schema_version=1,
            robot_key="ROKI-01",
            pose_topic="hanbakwi/v1/robots/ROKI-01/pose",
        )
        store = Mock()
        store.get_pose.return_value = PoseState(1.0, 2.0, 90.0)
        client = Mock()
        application = RokiPublisherApplication(
            settings=settings,
            serial_reader=Mock(),
            state_store=store,
            mqtt_client=client,
            command_handler=Mock(),
            pipeline_runner=Mock(),
        )
        application._last_pose_publish_time = 100.0

        application._publish_pose_if_needed(100.9)
        client.publish.assert_not_called()
        application._publish_pose_if_needed(101.0)

        client.publish.assert_called_once()
        payload = client.publish.call_args.kwargs["payload"]
        self.assertEqual(payload["heading"], 90.0)
        self.assertEqual(
            set(payload),
            {"schemaVersion", "robotKey", "x", "y", "heading", "timestamp"},
        )

    def test_existing_command_handler_controls_final_mission_and_publishes_ack(
        self,
    ) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        with patch.dict(
            os.environ,
            {
                "AIOT_AI_REQUIRED_FOR_PATROL": "false",
                "AIOT_LIDAR_REQUIRED_FOR_PATROL": "false",
            },
        ):
            deployment_guard = Mock()
            deployment_guard.acquire.return_value = (True, "READY")
            application = create_integrated_application(
                final_runtime=runtime,
                deployment_guard=deployment_guard,
            )
        application._pipeline_runner.is_running = Mock(return_value=False)
        application._pipeline_runner.start = Mock()
        application._pipeline_runner.stop = Mock()
        application._mqtt_client.publish = Mock()
        application._command_handler._pipeline_enabled = True
        application._serial_reader.start()
        self.addCleanup(application._serial_reader.stop)

        now = datetime.now().astimezone()
        application._command_handler.handle(
            application._settings.command_topic,
            {
                "schemaVersion": 1,
                "command": "START_PATROL",
                "commandId": "command-start",
                "patrolId": 17,
                "issuedAt": now.isoformat(),
                "expiresAt": (now + timedelta(seconds=10)).isoformat(),
            },
        )

        self.assertTrue(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.start_calls, 1)
        self.assertEqual(
            application._state_store.get_status().state,
            "PATROLLING",
        )
        application._pipeline_runner.start.assert_called_once()
        start_ack = next(
            call.kwargs
            for call in application._mqtt_client.publish.call_args_list
            if call.kwargs["topic"]
            == application._settings.command_response_topic
        )
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
                "schemaVersion": 1,
                "command": "STOP_PATROL",
                "commandId": "command-stop",
                "issuedAt": now.isoformat(),
                "expiresAt": (now + timedelta(seconds=10)).isoformat(),
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
