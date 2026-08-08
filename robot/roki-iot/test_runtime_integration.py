from __future__ import annotations

import threading
import time
import unittest
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from control.manual_drive_controller import (
    ManualDriveController,
    ManualDriveSettings,
)
from integration.runtime_state_backend_adapter import (
    FinalRuntimeService,
    PatrolStartExpired,
    RuntimeStateBackendAdapter,
)
from backend_state.robot_state_store import RobotStateStore
from backend_state.models import HardwareState, ObstacleState
from navigation.route import parse_route
from navigation.service import WaypointNavigationService


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
        self.stop_reasons: list[str] = []
        self.stop_error: Exception | None = None
        self.connection_generation = 0
        self.connection_listeners: list[object] = []
        self.safety_fault_listeners: list[object] = []
        self.motion_targets: list[tuple[int, int, bool]] = []
        self.motion_stops: list[int] = []

    def add_hardware_status_listener(self, listener: object) -> None:
        self.hardware_listeners.append(listener)

    def add_odometry_listener(self, listener: object) -> None:
        self.odometry_listeners.append(listener)

    def add_connection_listener(self, listener: object) -> None:
        self.connection_listeners.append(listener)

    def add_safety_fault_listener(self, listener: object) -> None:
        self.safety_fault_listeners.append(listener)

    def run_forever(self) -> None:
        self.started.set()
        self.stopped.wait(timeout=1.0)

    def request_stop(self) -> None:
        self.stopped.set()

    def stop_patrol(self, reason: str) -> None:
        self.stop_reasons.append(reason)
        self.mission.stop_patrol()
        if self.stop_error is not None:
            raise self.stop_error

    def request_motion_target(
        self,
        speed: int,
        steering_deg: int,
        *,
        stationary_steering: bool = False,
    ) -> None:
        self.motion_targets.append(
            (speed, steering_deg, stationary_steering)
        )

    def request_motion_stop(self, steering_deg: int) -> None:
        self.motion_stops.append(steering_deg)

    def simulate_connection(self) -> None:
        self.connection_generation += 1
        for listener in tuple(self.connection_listeners):
            listener(self.connection_generation)  # type: ignore[operator]

    def simulate_safety_fault(self, reason: str) -> None:
        self.mission.stop_patrol()
        for listener in tuple(self.safety_fault_listeners):
            listener(reason)  # type: ignore[operator]


class BlockingManualController:
    def __init__(self) -> None:
        self.active = False
        self.activate_entered = threading.Event()
        self.release_activate = threading.Event()
        self.deactivate_calls = 0

    def activate(self, _patrol_id: int) -> None:
        self.activate_entered.set()
        if not self.release_activate.wait(timeout=2.0):
            raise TimeoutError("test did not release manual activation")
        self.active = True

    def deactivate(self) -> None:
        self.deactivate_calls += 1
        self.active = False


class RuntimeStateBackendAdapterTest(unittest.TestCase):
    def test_obstacle_activity_tracks_patrol_lifecycle(self) -> None:
        runtime = FakeRuntime()
        service = FinalRuntimeService(runtime)
        service.start()
        self.addCleanup(service.stop)

        self.assertFalse(service.is_obstacle_detection_active())
        service.send_command("START_PATROL", patrolId=17)
        self.assertTrue(service.is_obstacle_detection_active())
        service.send_command("STOP_PATROL")
        self.assertFalse(service.is_obstacle_detection_active())

    def test_obstacle_activity_uses_mapping_motion_lifecycle(self) -> None:
        service = FinalRuntimeService(FakeRuntime())
        mapping = SimpleNamespace(motion_active=False)
        service.set_mapping_runtime(mapping)

        self.assertFalse(service.is_obstacle_detection_active())
        mapping.motion_active = True
        self.assertTrue(service.is_obstacle_detection_active())
        mapping.motion_active = False
        self.assertFalse(service.is_obstacle_detection_active())

    def test_manual_demo_starts_stationary_only_after_mqtt_start(self) -> None:
        runtime = FakeRuntime()
        manual = Mock()
        keyboard = Mock()
        service = FinalRuntimeService(
            runtime,
            manual_controller=manual,
            keyboard_input=keyboard,
        )

        service.start()
        keyboard.start.assert_called_once_with()
        manual.activate.assert_not_called()

        service.send_command("START_PATROL", patrolId=17)
        manual.activate.assert_called_once_with(17)
        self.assertEqual(service.active_patrol_id, 17)

        service.send_command("STOP_PATROL")
        manual.deactivate.assert_called_once_with()
        self.assertIsNone(service.active_patrol_id)
        service.stop()
        keyboard.stop.assert_called_once_with()

    def test_publisher_exits_when_single_serial_runtime_dies(self) -> None:
        from backend_mqtt.publisher import RokiPublisherApplication

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

    def test_prepare_patrol_replaces_local_route_with_fresh_backend_route(self) -> None:
        runtime = FakeRuntime()
        local_navigation = Mock()
        remote_navigation = Mock()
        provider = Mock()
        provider.load_navigation.return_value = remote_navigation
        service = FinalRuntimeService(
            runtime,
            navigation_service=local_navigation,
            navigation_provider=provider,
            local_navigation_fallback_enabled=False,
            navigation_driver=Mock(),
        )

        self.assertEqual(service.prepare_patrol(), (True, "READY"))

        provider.load_navigation.assert_called_once_with()
        remote_navigation.add_event_listener.assert_called_once_with(
            service._on_navigation_event
        )
        self.assertIs(service._navigation_service, remote_navigation)

    def test_prepare_patrol_fails_closed_when_backend_route_is_unavailable(self) -> None:
        runtime = FakeRuntime()
        provider = Mock()
        failure = RuntimeError("hidden transport detail")
        failure.reason = "NAVIGATION_CONFIG_UNAVAILABLE"
        provider.load_navigation.side_effect = failure
        service = FinalRuntimeService(
            runtime,
            navigation_provider=provider,
            local_navigation_fallback_enabled=False,
            navigation_driver=Mock(),
        )

        self.assertEqual(
            service.prepare_patrol(),
            (False, "NAVIGATION_CONFIG_UNAVAILABLE"),
        )
        self.assertIsNone(service._navigation_service)

    def test_prepare_patrol_uses_only_explicit_local_fallback(self) -> None:
        runtime = FakeRuntime()
        local_navigation = Mock()
        provider = Mock()
        failure = RuntimeError("unavailable")
        failure.reason = "NAVIGATION_CONFIG_UNAVAILABLE"
        failure.local_fallback_allowed = True
        provider.load_navigation.side_effect = failure
        service = FinalRuntimeService(
            runtime,
            navigation_service=local_navigation,
            navigation_provider=provider,
            local_navigation_fallback_enabled=True,
            navigation_driver=Mock(),
        )

        self.assertEqual(
            service.prepare_patrol(),
            (True, "READY"),
        )
        self.assertIs(service._navigation_service, local_navigation)

    def test_local_fallback_rejects_contract_and_map_safety_failures(self) -> None:
        for reason in (
            "NAVIGATION_MAP_MISMATCH",
            "NAVIGATION_MAP_METADATA_MISMATCH",
            "NAVIGATION_CONFIG_INVALID",
            "NAVIGATION_ROUTE_INVALID",
        ):
            with self.subTest(reason=reason):
                runtime = FakeRuntime()
                local_navigation = Mock()
                provider = Mock()
                failure = RuntimeError("unsafe")
                failure.reason = reason
                failure.local_fallback_allowed = False
                provider.load_navigation.side_effect = failure
                service = FinalRuntimeService(
                    runtime,
                    navigation_service=local_navigation,
                    navigation_provider=provider,
                    local_navigation_fallback_enabled=True,
                    navigation_driver=Mock(),
                )

                self.assertEqual(service.prepare_patrol(), (False, reason))
                self.assertIs(service._navigation_service, local_navigation)

    def test_prepare_passes_command_deadline_and_cancel_discards_remote_route(
        self,
    ) -> None:
        runtime = FakeRuntime()
        remote_navigation = Mock()
        provider = Mock()
        provider.load_navigation.return_value = remote_navigation
        service = FinalRuntimeService(
            runtime,
            navigation_provider=provider,
            navigation_driver=Mock(),
        )
        deadline = datetime(2026, 8, 5, tzinfo=timezone.utc)

        self.assertEqual(
            service.prepare_patrol(expires_at=deadline),
            (True, "READY"),
        )
        provider.load_navigation.assert_called_once_with(deadline=deadline)
        self.assertIs(service._navigation_service, remote_navigation)

        service.cancel_prepared_patrol()

        self.assertIsNone(service._navigation_service)

    def test_stop_write_failure_cleans_navigation_and_releases_lease(
        self,
    ) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        guard = Mock()
        guard.acquire.return_value = (True, "READY")
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
            deployment_guard=guard,
        )
        service.start()
        self.addCleanup(service.stop)
        self.assertEqual(service.prepare_patrol(), (True, "READY"))
        service.send_command("START_PATROL", patrolId=91)
        service._paused = True
        runtime.stop_error = RuntimeError("serial STOP write failed")

        with self.assertRaisesRegex(RuntimeError, "serial STOP write failed"):
            service.send_command("STOP_PATROL")

        self.assertIn("MQTT_STOP_PATROL", runtime.stop_reasons)
        navigation.stop_patrol.assert_called_once_with()
        driver.stop_patrol.assert_called_once_with()
        self.assertIsNone(service.active_patrol_id)
        self.assertFalse(service.paused)
        guard.release.assert_called_once_with()

    def test_stop_write_failure_still_deactivates_manual_demo(self) -> None:
        runtime = FakeRuntime()
        manual = Mock()
        keyboard = Mock()
        service = FinalRuntimeService(
            runtime,
            manual_controller=manual,
            keyboard_input=keyboard,
        )
        service.start()
        self.addCleanup(service.stop)
        service.send_command("START_PATROL", patrolId=92)
        runtime.stop_error = RuntimeError("serial STOP write failed")

        with self.assertRaisesRegex(RuntimeError, "serial STOP write failed"):
            service.send_command("STOP_PATROL")

        manual.deactivate.assert_called_once_with()
        self.assertIsNone(service.active_patrol_id)
        self.assertFalse(service.paused)

    def test_start_rollback_preserves_start_error_when_stop_write_fails(
        self,
    ) -> None:
        runtime = FakeRuntime()
        runtime.stop_error = RuntimeError("serial STOP write failed")
        navigation = Mock()
        driver = Mock()
        driver.start_patrol.side_effect = ValueError("Nav2 start failed")
        guard = Mock()
        guard.acquire.return_value = (True, "READY")
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
            deployment_guard=guard,
        )
        service.start()
        self.addCleanup(service.stop)
        self.assertEqual(service.prepare_patrol(), (True, "READY"))

        with self.assertRaisesRegex(ValueError, "Nav2 start failed"):
            service.send_command("START_PATROL", patrolId=93)

        self.assertIn("START_PATROL_ROLLBACK", runtime.stop_reasons)
        navigation.stop_patrol.assert_called_once_with()
        driver.stop_patrol.assert_called_once_with()
        self.assertIsNone(service.active_patrol_id)
        guard.release.assert_called_once_with()

    def test_fail_patrol_remains_non_throwing_when_stop_write_fails(self) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        guard = Mock()
        guard.acquire.return_value = (True, "READY")
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
            deployment_guard=guard,
        )
        service.start()
        self.addCleanup(service.stop)
        self.assertEqual(service.prepare_patrol(), (True, "READY"))
        service.send_command("START_PATROL", patrolId=94)
        runtime.stop_error = RuntimeError("serial STOP write failed")

        service.fail_patrol("DEMO_SAFETY_FAULT")

        self.assertIn("DEMO_SAFETY_FAULT", runtime.stop_reasons)
        navigation.stop_patrol.assert_called_once_with()
        driver.stop_patrol.assert_called_once_with()
        self.assertIsNone(service.active_patrol_id)
        self.assertFalse(service.paused)
        guard.release.assert_called_once_with()
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def test_reconnect_invalidates_nav2_and_rejects_stale_cmd_vel(self) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        guard = Mock()
        guard.acquire.return_value = (True, "READY")
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
            deployment_guard=guard,
        )
        service.start()
        self.addCleanup(service.stop)
        runtime.simulate_connection()
        navigation.reset_mock()
        driver.reset_mock()
        self.assertEqual(service.prepare_patrol(), (True, "READY"))
        service.send_command("START_PATROL", patrolId=95)
        motion = SimpleNamespace(
            speed_pwm=45,
            steering_deg=80,
            stop_reason=None,
        )
        service.apply_motion_command(motion)
        self.assertEqual(runtime.mission.start_calls, 1)

        runtime.simulate_connection()
        service.apply_motion_command(motion)

        self.assertIsNone(service.active_patrol_id)
        self.assertFalse(service.paused)
        self.assertFalse(runtime.mission.patrol_active)
        self.assertEqual(runtime.mission.start_calls, 1)
        navigation.stop_patrol.assert_called_once_with()
        driver.stop_patrol.assert_called_once_with()
        guard.release.assert_called_once_with()
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def _interlocked_service(self) -> tuple:
        """순찰이 끝난 직후 -- 그런데 cmd_vel 은 아직 날아오는 상태를 만든다."""

        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        guard = Mock()
        guard.acquire.return_value = (True, "READY")
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
            deployment_guard=guard,
        )
        service.start()
        self.addCleanup(service.stop)
        runtime.simulate_connection()
        self.assertEqual(service.prepare_patrol(), (True, "READY"))
        service.send_command("START_PATROL", patrolId=95)
        motion = SimpleNamespace(speed_pwm=45, steering_deg=80, stop_reason=None)
        service.apply_motion_command(motion)
        # 순찰을 무효화한다. 이후 cmd_vel 은 전부 인터락으로 떨어진다.
        runtime.simulate_connection()
        return service, runtime, motion

    def test_interlocked_cmd_vel_flood_delivers_one_stop(self) -> None:
        """램프다운 cmd_vel 마다 STOP 을 다시 쓰면 시리얼이 그 속도로 잠긴다.

        2026-08-09 실측: 세션 종료마다 20Hz 로 수십 건(88건), 그 중 55건이
        살아 있는 링크에 실제 STOP 프레임을 썼다. mapping_motion_sink._stop 은
        같은 이유로 이미 같은 가드를 둔다 -- 그쪽 주석이 대가를 적어뒀다.
        """

        service, runtime, motion = self._interlocked_service()
        runtime.stop_reasons.clear()

        for _ in range(20):
            service.apply_motion_command(motion)

        self.assertEqual(
            runtime.stop_reasons.count("MOTION_INTERLOCK"),
            1,
            "인터락 STOP 은 램프다운 한 번에 한 번만 나가야 한다",
        )

    def test_interlock_stop_is_retried_until_it_lands(self) -> None:
        """실패한 STOP 을 전달됐다고 기억하면 섀시가 명령 없이 남는다."""

        service, runtime, motion = self._interlocked_service()
        runtime.stop_reasons.clear()
        runtime.stop_error = RuntimeError("serial closed")

        service.apply_motion_command(motion)
        service.apply_motion_command(motion)
        runtime.stop_error = None
        service.apply_motion_command(motion)
        service.apply_motion_command(motion)

        # 실패 2회는 기록하지 않으므로 계속 재시도하고, 세 번째에 전달된다.
        # 네 번째는 이미 전달됐으므로 다시 쓰지 않는다.
        self.assertEqual(runtime.stop_reasons.count("MOTION_INTERLOCK"), 3)

    def test_reauthorized_motion_rearms_the_interlock_stop(self) -> None:
        """다음 순찰이 끝날 때는 STOP 이 다시 나가야 한다.

        플래그를 한 번 세우고 두면 두 번째 순찰의 램프다운은 STOP 없이 지나간다.
        """

        service, runtime, motion = self._interlocked_service()
        service.apply_motion_command(motion)

        # 다시 순찰을 인가하고 명령을 하나 받아들인다.
        self.assertEqual(service.prepare_patrol(), (True, "READY"))
        service.send_command("START_PATROL", patrolId=96)
        service.apply_motion_command(motion)
        runtime.simulate_connection()
        runtime.stop_reasons.clear()

        service.apply_motion_command(motion)
        service.apply_motion_command(motion)

        self.assertEqual(runtime.stop_reasons.count("MOTION_INTERLOCK"), 1)

    def test_runtime_safety_fault_cleans_nav_lease_and_notifies_ai_owner(
        self,
    ) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        guard = Mock()
        guard.acquire.return_value = (True, "READY")
        failures: list[str] = []
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
            deployment_guard=guard,
        )
        service.set_fault_listener(failures.append)
        service.start()
        self.addCleanup(service.stop)
        self.assertEqual(service.prepare_patrol(), (True, "READY"))
        service.send_command("START_PATROL", patrolId=97)
        self.assertTrue(service.confirm_patrol_started(97))
        self.assertEqual(
            runtime.state_store.get_status().state,
            "PATROLLING",
        )

        runtime.simulate_safety_fault("MOTOR_FAULT")

        self.assertIsNone(service.active_patrol_id)
        self.assertFalse(service.paused)
        navigation.stop_patrol.assert_called_once_with()
        driver.stop_patrol.assert_called_once_with()
        guard.release.assert_called_once_with()
        self.assertEqual(failures, ["MOTOR_FAULT"])
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")
        self.assertFalse(service.confirm_patrol_started(97))

    def test_serial_reconnect_notifies_active_mapping_owner(self) -> None:
        runtime = FakeRuntime()
        mapping = SimpleNamespace(motion_active=True)
        failures: list[str] = []
        service = FinalRuntimeService(runtime)
        service.set_mapping_runtime(mapping)
        service.set_fault_listener(failures.append)
        service.start()
        self.addCleanup(service.stop)

        runtime.simulate_connection()

        self.assertEqual(failures, ["SERIAL_CONNECTION_RESET"])
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def test_runtime_safety_fault_notifies_active_mapping_owner(self) -> None:
        runtime = FakeRuntime()
        mapping = SimpleNamespace(motion_active=True)
        failures: list[str] = []
        service = FinalRuntimeService(runtime)
        service.set_mapping_runtime(mapping)
        service.set_fault_listener(failures.append)
        service.start()
        self.addCleanup(service.stop)

        runtime.simulate_safety_fault("MOTOR_FAULT")

        self.assertEqual(failures, ["MOTOR_FAULT"])
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def test_pause_component_failure_still_stops_and_abandons_patrol(self) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        driver.pause_patrol.side_effect = RuntimeError("cancel failed")
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
        )
        service.start()
        self.addCleanup(service.stop)
        service.send_command("START_PATROL", patrolId=98)

        self.assertFalse(service.pause_patrol("OBSTACLE"))

        self.assertIsNone(service.active_patrol_id)
        self.assertIn("OBSTACLE", runtime.stop_reasons)
        self.assertIn("OBSTACLE_PAUSE_FAILED", runtime.stop_reasons)
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def test_resume_component_failure_cannot_leave_patrol_unpaused(self) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
        )
        service.start()
        self.addCleanup(service.stop)
        service.send_command("START_PATROL", patrolId=99)
        self.assertTrue(service.pause_patrol("OBSTACLE"))
        driver.resume_patrol.side_effect = RuntimeError("resume failed")

        self.assertFalse(service.resume_patrol())

        self.assertIsNone(service.active_patrol_id)
        self.assertFalse(service.paused)
        self.assertTrue(
            any(reason.startswith("RESUME_FAILED") for reason in runtime.stop_reasons)
        )
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def test_navigation_health_exception_fails_patrol_without_killing_loop(
        self,
    ) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
        )
        service.start()
        self.addCleanup(service.stop)
        service.send_command("START_PATROL", patrolId=100)
        driver.check_health.side_effect = RuntimeError("health crashed")

        service.tick()

        self.assertIsNone(service.active_patrol_id)
        self.assertTrue(
            any(
                reason.startswith("NAVIGATION_HEALTH_ERROR")
                for reason in runtime.stop_reasons
            )
        )
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def test_reconnect_deactivates_manual_before_stale_key(self) -> None:
        runtime = FakeRuntime()
        runtime.state_store.update_lidar_status("NORMAL")
        manual = ManualDriveController(
            runtime=runtime,
            state_store=runtime.state_store,
            settings=ManualDriveSettings(),
        )
        keyboard = Mock()
        service = FinalRuntimeService(
            runtime,
            manual_controller=manual,
            keyboard_input=keyboard,
        )
        service.start()
        self.addCleanup(service.stop)
        runtime.simulate_connection()
        service.send_command("START_PATROL", patrolId=96)
        self.assertTrue(manual.active)

        runtime.simulate_connection()

        self.assertFalse(manual.active)
        self.assertIsNone(service.active_patrol_id)
        target_count = len(runtime.motion_targets)
        self.assertEqual(manual.handle_key("w"), "IGNORED")
        self.assertEqual(len(runtime.motion_targets), target_count)
        self.assertEqual(runtime.state_store.get_status().state, "ERROR")

    def test_reconnect_during_nav2_start_rolls_back_before_success(self) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        entered = threading.Event()
        release = threading.Event()

        def blocking_start(**_kwargs) -> None:
            entered.set()
            if not release.wait(timeout=2.0):
                raise TimeoutError("test did not release Nav2 START")

        driver.start_patrol.side_effect = blocking_start
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
        )
        service.start()
        self.addCleanup(service.stop)
        failures: list[Exception] = []

        start_thread = threading.Thread(
            target=lambda: self._capture_error(
                failures,
                lambda: service.send_command("START_PATROL", patrolId=101),
            )
        )
        start_thread.start()
        self.assertTrue(entered.wait(timeout=0.5))
        reconnect_thread = threading.Thread(target=runtime.simulate_connection)
        reconnect_thread.start()
        deadline = time.monotonic() + 0.5
        while runtime.connection_generation == 0 and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertEqual(runtime.connection_generation, 1)
        release.set()
        start_thread.join(timeout=1.0)
        reconnect_thread.join(timeout=1.0)

        self.assertFalse(start_thread.is_alive())
        self.assertFalse(reconnect_thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertRegex(str(failures[0]), "lifecycle changed")
        self.assertIsNone(service.active_patrol_id)
        self.assertFalse(runtime.mission.patrol_active)
        self.assertGreaterEqual(driver.stop_patrol.call_count, 1)

    def test_start_expiring_while_waiting_for_lifecycle_lock_never_activates(
        self,
    ) -> None:
        class ObservableRLock:
            def __init__(self) -> None:
                self._lock = threading.RLock()
                self.enter_attempted = threading.Event()

            def acquire(self) -> bool:
                return self._lock.acquire()

            def release(self) -> None:
                self._lock.release()

            def __enter__(self) -> "ObservableRLock":
                self.enter_attempted.set()
                self._lock.acquire()
                return self

            def __exit__(self, *_args: object) -> None:
                self._lock.release()

        runtime = FakeRuntime()
        manual = Mock()
        manual.active = False
        now = [datetime(2026, 8, 5, tzinfo=timezone.utc)]
        deadline = now[0] + timedelta(seconds=10)
        service = FinalRuntimeService(
            runtime,
            manual_controller=manual,
            keyboard_input=Mock(),
            wall_clock=lambda: now[0],
        )
        service.is_running = Mock(return_value=True)
        service.readiness = Mock(return_value=(True, "READY"))
        lifecycle_lock = ObservableRLock()
        service._lifecycle_lock = lifecycle_lock
        failures: list[Exception] = []

        def start_after_handler_check() -> None:
            self._capture_error(
                failures,
                lambda: service.send_command(
                    "START_PATROL",
                    patrolId=103,
                    expires_at=deadline,
                ),
            )

        service._lifecycle_lock.acquire()
        try:
            start_thread = threading.Thread(target=start_after_handler_check)
            start_thread.start()
            self.assertTrue(lifecycle_lock.enter_attempted.wait(timeout=0.5))
            self.assertTrue(start_thread.is_alive())
            now[0] = deadline
        finally:
            service._lifecycle_lock.release()
        start_thread.join(timeout=1.0)

        self.assertFalse(start_thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], PatrolStartExpired)
        self.assertEqual(
            getattr(failures[0], "reason", None),
            "COMMAND_EXPIRED_DURING_START",
        )
        manual.activate.assert_not_called()
        self.assertEqual(runtime.mission.start_calls, 0)
        self.assertEqual(runtime.mission.stop_calls, 0)
        self.assertEqual(runtime.stop_reasons, [])
        self.assertIsNone(service.active_patrol_id)

    def test_nav2_deadline_crossing_after_route_start_never_starts_driver(
        self,
    ) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()
        now = [datetime(2026, 8, 5, tzinfo=timezone.utc)]
        deadline = now[0] + timedelta(seconds=10)

        def prepare_first_event(*, patrol_id: int) -> object:
            self.assertEqual(patrol_id, 104)
            now[0] = deadline
            return object()

        navigation.start_patrol.side_effect = prepare_first_event
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
            wall_clock=lambda: now[0],
        )
        service.is_running = Mock(return_value=True)
        service.readiness = Mock(return_value=(True, "READY"))

        with self.assertRaises(PatrolStartExpired):
            service.send_command(
                "START_PATROL",
                patrolId=104,
                expires_at=deadline,
            )

        navigation.start_patrol.assert_called_once_with(patrol_id=104)
        driver.start_patrol.assert_not_called()
        driver.stop_patrol.assert_not_called()
        self.assertEqual(runtime.mission.start_calls, 0)
        self.assertEqual(runtime.mission.stop_calls, 0)
        self.assertEqual(runtime.stop_reasons, [])
        self.assertIsNone(service.active_patrol_id)

    def test_encoder_deadline_crossing_before_motor_start_never_starts_motor(
        self,
    ) -> None:
        runtime = FakeRuntime()
        runtime.state_store = Mock()
        runtime.state_store.snapshot.return_value = SimpleNamespace(
            motion_state=SimpleNamespace(
                left_distance_m=0.0,
                right_distance_m=0.0,
            ),
            safety_decision=SimpleNamespace(allowed=True),
        )
        navigation = Mock()
        now = [datetime(2026, 8, 5, tzinfo=timezone.utc)]
        deadline = now[0] + timedelta(seconds=10)

        def prepare_route(*, patrol_id: int) -> object:
            self.assertEqual(patrol_id, 105)
            now[0] = deadline
            return object()

        navigation.start_patrol.side_effect = prepare_route
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            wall_clock=lambda: now[0],
        )
        service._encoder_progress = Mock()
        service.is_running = Mock(return_value=True)
        service.readiness = Mock(return_value=(True, "READY"))

        with self.assertRaises(PatrolStartExpired):
            service.send_command(
                "START_PATROL",
                patrolId=105,
                expires_at=deadline,
            )

        service._encoder_progress.start.assert_called_once_with(
            left_distance_m=0.0,
            right_distance_m=0.0,
        )
        navigation.start_patrol.assert_called_once_with(patrol_id=105)
        self.assertEqual(runtime.mission.start_calls, 0)
        self.assertEqual(runtime.mission.stop_calls, 0)
        self.assertEqual(runtime.stop_reasons, [])
        self.assertIsNone(service.active_patrol_id)

    def test_safety_fault_during_manual_start_cannot_ack_active_patrol(self) -> None:
        runtime = FakeRuntime()
        manual = BlockingManualController()
        service = FinalRuntimeService(
            runtime,
            manual_controller=manual,
            keyboard_input=Mock(),
        )
        service.start()
        self.addCleanup(service.stop)
        failures: list[Exception] = []

        start_thread = threading.Thread(
            target=lambda: self._capture_error(
                failures,
                lambda: service.send_command("START_PATROL", patrolId=102),
            )
        )
        start_thread.start()
        self.assertTrue(manual.activate_entered.wait(timeout=0.5))
        fault_thread = threading.Thread(
            target=lambda: runtime.simulate_safety_fault("MOTOR_FAULT")
        )
        fault_thread.start()
        deadline = time.monotonic() + 0.5
        while service._runtime_fault_generation == 0 and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertEqual(service._runtime_fault_generation, 1)
        manual.release_activate.set()
        start_thread.join(timeout=1.0)
        fault_thread.join(timeout=1.0)

        self.assertEqual(len(failures), 1)
        self.assertRegex(str(failures[0]), "lifecycle changed")
        self.assertFalse(manual.active)
        self.assertIsNone(service.active_patrol_id)
        self.assertGreaterEqual(manual.deactivate_calls, 1)

    @staticmethod
    def _capture_error(
        failures: list[Exception],
        operation: object,
    ) -> None:
        try:
            operation()  # type: ignore[operator]
        except Exception as exc:
            failures.append(exc)

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
        self.assertEqual(status.line_sensor, "ERROR")
        self.assertEqual(status.camera, "DISCONNECTED")
        self.assertEqual(status.lidar, "DISCONNECTED")
        self.assertEqual(status.obstacle.status, "CLEAR")
        self.assertEqual(status.obstacle.direction, "NONE")

    def test_nav2_registers_events_without_encoder_map_pose_writer(self) -> None:
        runtime = FakeRuntime()
        navigation = Mock()
        driver = Mock()

        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
        )

        navigation.add_event_listener.assert_called_once_with(
            service._on_navigation_event
        )
        self.assertIsNone(service._encoder_progress)
        self.assertEqual(runtime.odometry_listeners, [])

        event = SimpleNamespace(
            mission_event=SimpleNamespace(
                event_type=SimpleNamespace(value="WAYPOINT_REACHED"),
                waypoint=SimpleNamespace(name="PASS-1"),
            )
        )
        navigation.add_event_listener.call_args.args[0](event)
        driver.on_navigation_event.assert_called_once_with(event)

    def test_nav2_start_resets_driver_then_confirms_waypoint_one_anchor(self) -> None:
        runtime = FakeRuntime()
        route = parse_route(
            {
                "schema_version": 1,
                "map_id": "demo-map",
                "map_version": 1,
                "route_id": "start-anchor",
                "frame_id": "map",
                "waypoints": [
                    {
                        "sequence": 1,
                        "x": 1.0,
                        "y": 1.0,
                        "yaw_deg": 0.0,
                        "acceptance_radius_m": 0.2,
                        "action": "PASS",
                    },
                    {
                        "sequence": 2,
                        "x": 2.0,
                        "y": 1.0,
                        "yaw_deg": 0.0,
                        "acceptance_radius_m": 0.2,
                        "action": "DESTINATION",
                    },
                ],
            }
        )
        navigation = WaypointNavigationService(route)
        driver = Mock()
        order = []
        driver.start_patrol.side_effect = lambda **_kwargs: order.append(
            "initial-pose-reset"
        )
        driver.wait_for_first_goal_acceptance.side_effect = lambda: order.append(
            "first-goal-accepted"
        )
        driver.on_navigation_event.side_effect = lambda event: order.append(
            event.mission_event.event_type.value
        )
        service = FinalRuntimeService(
            runtime,
            navigation_service=navigation,
            navigation_driver=driver,
        )
        service.readiness = Mock(return_value=(True, "READY"))

        service._start_nav2_patrol(patrol_id=7)

        self.assertEqual(
            order,
            [
                "STARTED",
                "initial-pose-reset",
                "WAYPOINT_REACHED",
                "first-goal-accepted",
            ],
        )
        self.assertEqual(navigation._mission.current_waypoint.sequence, 2)

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

    def test_mapping_can_be_ready_when_patrol_route_is_not_configured(self) -> None:
        runtime = FakeRuntime()
        service = FinalRuntimeService(
            runtime,
            allow_legacy_direct_patrol=False,
        )
        service.start()
        self.addCleanup(service.stop)

        self.assertEqual(
            service.readiness(),
            (False, "PATROL_ROUTE_NOT_CONFIGURED"),
        )
        self.assertEqual(service.mapping_readiness(), (True, "READY"))
        with self.assertRaisesRegex(RuntimeError, "PATROL_ROUTE_NOT_CONFIGURED"):
            service.send_command("START_PATROL", patrolId=7)

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

    def test_integrated_mapping_failure_routes_to_command_handler(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        mapping_runtime = Mock()
        application = create_integrated_application(
            final_runtime=runtime,
            mapping_runtime=mapping_runtime,
        )

        mapping_runtime.set_failure_listener.assert_called_once_with(
            application._command_handler.on_runtime_failure
        )

    def test_integrated_lidar_gate_uses_final_runtime_lifecycle(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        mapping_runtime = Mock()
        mapping_runtime.motion_active = False
        lidar_bridge = Mock()
        application = create_integrated_application(
            final_runtime=runtime,
            mapping_runtime=mapping_runtime,
            lidar_health_bridge=lidar_bridge,
        )

        lidar_bridge.set_obstacle_activity_check.assert_called_once()
        activity_check = (
            lidar_bridge.set_obstacle_activity_check.call_args.args[0]
        )
        self.assertFalse(activity_check())
        mapping_runtime.motion_active = True
        self.assertTrue(activity_check())
        self.assertIs(application._state_store, runtime.state_store)

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

    def test_status_is_rate_limited_even_when_hardware_values_change(self) -> None:
        from backend_mqtt.publisher import RokiPublisherApplication

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
        self.assertEqual(client.publish.call_count, 1)
        application._publish_status_if_needed(104.999)
        self.assertEqual(client.publish.call_count, 1)

        application._publish_status_if_needed(105.1)
        self.assertEqual(client.publish.call_count, 2)

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

    def test_mapping_suppresses_only_backend_obstacle_alert_fields(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        mapping_runtime = Mock()
        mapping_runtime.active = True
        application = create_integrated_application(
            final_runtime=runtime,
            mapping_runtime=mapping_runtime,
        )
        runtime.state_store.update_lidar_status("NORMAL")
        runtime.state_store.update_obstacle(
            ObstacleState(
                status="STOP",
                direction="FRONT",
                reason_message="front obstacle",
            )
        )
        application._mqtt_client.publish = Mock()

        application._publish_status_if_needed(100.0)

        payload = application._mqtt_client.publish.call_args.kwargs["payload"]
        self.assertEqual(
            payload["obstacle"],
            {
                "status": "CLEAR",
                "direction": "NONE",
                "reasonMessage": None,
            },
        )
        self.assertEqual(payload["lidar"], "NORMAL")
        self.assertEqual(
            runtime.state_store.get_status().obstacle.status,
            "STOP",
        )

        mapping_runtime.active = False
        application._publish_status_if_needed(101.0, force=True)
        payload = application._mqtt_client.publish.call_args.kwargs["payload"]
        self.assertEqual(payload["obstacle"]["status"], "STOP")

    def test_pose_publisher_keeps_one_second_interval(self) -> None:
        from backend_mqtt.publisher import RokiPublisherApplication
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

    def test_pose_lifecycle_gate_does_not_gate_status(self) -> None:
        from backend_mqtt.publisher import RokiPublisherApplication
        from backend_state.models import PoseState

        settings = SimpleNamespace(
            pose_publish_interval_seconds=1.0,
            status_publish_interval_seconds=5.0,
            schema_version=1,
            robot_key="ROKI-01",
            pose_topic="hanbakwi/v1/robots/ROKI-01/pose",
            status_topic="hanbakwi/v1/robots/ROKI-01/status",
        )
        store = Mock()
        store.get_pose.return_value = PoseState(1.0, 2.0, 90.0)
        store.get_status.return_value = SimpleNamespace(
            battery=80.0,
            state="IDLE",
            motor="NORMAL",
            camera="NORMAL",
            lidar="NORMAL",
            line_sensor="NORMAL",
            obstacle=SimpleNamespace(
                status="CLEAR",
                direction="NONE",
                reason_message=None,
            ),
        )
        activity = {"active": False}
        client = Mock()
        application = RokiPublisherApplication(
            settings=settings,
            serial_reader=Mock(),
            state_store=store,
            mqtt_client=client,
            command_handler=Mock(),
            pipeline_runner=Mock(),
            pose_publish_activity_check=lambda: activity["active"],
        )

        application._publish_status_if_needed(100.0)
        application._publish_pose_if_needed(100.0)

        self.assertEqual(client.publish.call_count, 1)
        self.assertEqual(
            client.publish.call_args.kwargs["topic"],
            settings.status_topic,
        )
        store.get_pose.assert_not_called()

        activity["active"] = True
        application._publish_pose_if_needed(100.0)
        self.assertEqual(client.publish.call_count, 2)
        self.assertEqual(
            client.publish.call_args.kwargs["topic"],
            settings.pose_topic,
        )

        activity["active"] = False
        application._publish_pose_if_needed(101.0, force=True)
        self.assertEqual(client.publish.call_count, 2)

    def test_integrated_pose_publish_remains_active_while_idle(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        mapping_runtime = Mock()
        mapping_runtime.motion_active = False
        application = create_integrated_application(
            final_runtime=runtime,
            mapping_runtime=mapping_runtime,
        )

        self.assertTrue(application._pose_publish_activity_check())
        mapping_runtime.motion_active = True
        self.assertTrue(application._pose_publish_activity_check())
        mapping_runtime.motion_active = False
        self.assertTrue(application._pose_publish_activity_check())

    def test_integrated_pose_publish_remains_active_after_patrol(self) -> None:
        from run_integrated import create_integrated_application

        runtime = FakeRuntime()
        application = create_integrated_application(final_runtime=runtime)
        service = application._serial_reader
        service.start()
        self.addCleanup(service.stop)

        self.assertTrue(application._pose_publish_activity_check())
        service.send_command("START_PATROL", patrolId=17)
        self.assertTrue(application._pose_publish_activity_check())
        service.send_command("STOP_PATROL")
        self.assertTrue(application._pose_publish_activity_check())

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
