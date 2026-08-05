"""Final Runtime 상태를 기존 Backend Store에 전달하는 listener adapter."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable

from backend_state.models import HardwareState
from backend_state.robot_state_store import RobotStateStore


class RuntimeStateBackendAdapter:
    """매핑 가능한 ESP32 hardware 상태만 기존 Store에 전달한다."""

    def __init__(
        self,
        *,
        runtime: Any,
        backend_state_store: RobotStateStore,
    ) -> None:
        self._runtime = runtime
        self._backend_state_store = backend_state_store
        self._connected = False

    def connect(self) -> None:
        """Final Runtime의 HardwareStatus listener를 한 번만 등록한다."""

        if self._connected:
            return
        self._runtime.add_hardware_status_listener(
            self._on_hardware_status
        )
        self._connected = True

    def _on_hardware_status(self, hardware_status: Any) -> None:
        motor = hardware_status.motor.value
        if motor == "FAULT":
            motor = "ERROR"
        line_sensor = hardware_status.line_sensor.value
        if line_sensor == "FAULT":
            line_sensor = "ERROR"
        self._backend_state_store.update_hardware(
            HardwareState(
                battery=hardware_status.battery_percent,
                motor=motor,
                line_sensor=line_sensor,
            )
        )


class PatrolStartExpired(RuntimeError):
    """A validated START expired before this runtime could activate motion."""

    reason = "COMMAND_EXPIRED_DURING_START"

    def __init__(self) -> None:
        super().__init__(self.reason)


class FinalRuntimeService:
    """Final RobotRuntime을 전용 thread에서 실행하는 lifecycle facade."""

    def __init__(
        self,
        runtime: Any,
        *,
        patrol_drive_speed_pwm: int = 51,
        patrol_steering_degrees: int = 80,
        navigation_service: Any | None = None,
        navigation_provider: Any | None = None,
        local_navigation_fallback_enabled: bool = False,
        navigation_start_x_m: float = 1.0,
        navigation_start_y_m: float = 2.5,
        navigation_maximum_travel_m: float = 0.70,
        encoder_fallback_enabled: bool = True,
        navigation_driver: Any | None = None,
        destination_listener: Any | None = None,
        deployment_guard: Any | None = None,
        manual_controller: Any | None = None,
        keyboard_input: Any | None = None,
        allow_legacy_direct_patrol: bool = True,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (manual_controller is None) != (keyboard_input is None):
            raise ValueError(
                "manual_controller and keyboard_input must be configured together"
            )
        self._runtime = runtime
        self._patrol_drive_speed_pwm = patrol_drive_speed_pwm
        self._patrol_steering_degrees = patrol_steering_degrees
        self._navigation_service = navigation_service
        self._navigation_provider = navigation_provider
        self._navigation_prepared_from_provider = False
        self._local_navigation_service = (
            navigation_service if local_navigation_fallback_enabled else None
        )
        self._local_navigation_fallback_enabled = bool(
            local_navigation_fallback_enabled
        )
        self._navigation_driver = navigation_driver
        self._destination_listener = destination_listener
        self._deployment_guard = deployment_guard
        self._manual_controller = manual_controller
        self._keyboard_input = keyboard_input
        self._mapping_runtime: Any | None = None
        self._allow_legacy_direct_patrol = allow_legacy_direct_patrol
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._patrol_lease_held = False
        self._encoder_fallback_enabled = encoder_fallback_enabled
        self._encoder_progress: Any | None = None
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.RLock()
        self._runtime_fault_generation = 0
        self._active_patrol_id: int | None = None
        self._paused = False
        self._fault_listener: Any | None = None
        self._scan_context_listener: Any | None = None
        if navigation_service is not None:
            # Both navigation modes need mission events.  In Nav2 mode this is
            # the only path that advances PASS/SCAN waypoints and observes the
            # final DESTINATION; encoder odometry must not write map pose.
            navigation_service.add_event_listener(self._on_navigation_event)
        if navigation_service is not None and navigation_driver is None:
            from navigation.encoder_waypoint import (
                EncoderWaypointProgress,
                EncoderWaypointSettings,
            )

            self._encoder_progress = EncoderWaypointProgress(
                EncoderWaypointSettings(
                    start_x_m=navigation_start_x_m,
                    start_y_m=navigation_start_y_m,
                    maximum_travel_m=navigation_maximum_travel_m,
                )
            )
            runtime.add_odometry_listener(self._on_odometry)
        add_connection_listener = getattr(
            runtime,
            "add_connection_listener",
            None,
        )
        if callable(add_connection_listener):
            add_connection_listener(self._on_runtime_connected)
        add_safety_fault_listener = getattr(
            runtime,
            "add_safety_fault_listener",
            None,
        )
        if callable(add_safety_fault_listener):
            add_safety_fault_listener(self._on_runtime_safety_fault)

    def start(self) -> None:
        if self.is_running():
            return
        if self._navigation_driver is not None:
            self._navigation_driver.start()
        self._thread = threading.Thread(
            target=self._runtime.run_forever,
            name="robot-runtime",
            daemon=True,
        )
        self._thread.start()
        try:
            if self._keyboard_input is not None:
                self._keyboard_input.start()
        except Exception:
            self._runtime.request_stop()
            self._thread.join(timeout=2.0)
            self._thread = None
            if self._navigation_driver is not None:
                self._navigation_driver.stop()
            raise

    def stop(self) -> None:
        try:
            if self._active_patrol_id is not None:
                self.send_command("STOP_PATROL")
        except Exception as exc:
            print(f"[RUNTIME] final STOP failed type={type(exc).__name__}")
        finally:
            if self._keyboard_input is not None:
                self._keyboard_input.stop()
            if self._navigation_driver is not None:
                self._navigation_driver.stop()
            self._runtime.request_stop()
            self._release_patrol_lease()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def active_patrol_id(self) -> int | None:
        with self._lifecycle_lock:
            return self._active_patrol_id

    @property
    def paused(self) -> bool:
        with self._lifecycle_lock:
            return self._paused

    def set_destination_listener(self, listener: Any) -> None:
        self._destination_listener = listener

    def set_fault_listener(self, listener: Any) -> None:
        """Receive asynchronous patrol failures after local fail-close."""

        self._fault_listener = listener

    def set_scan_context_listener(self, listener: Any) -> None:
        """Expose SCAN waypoint context without coupling navigation to AI."""

        self._scan_context_listener = listener

    def update_scan_context(self, waypoint: Any | None) -> None:
        """Apply a Nav2 SCAN dwell lifecycle update on the runtime lock."""

        with self._lifecycle_lock:
            self._publish_scan_context_locked(waypoint)

    def current_heading_deg(self) -> float | None:
        """Return the latest localized map heading for a one-point null-yaw route."""

        get_pose = getattr(self._runtime.state_store, "get_pose", None)
        if not callable(get_pose):
            return None
        pose = get_pose()
        heading = getattr(pose, "heading", None) if pose is not None else None
        try:
            return None if heading is None else float(heading)
        except (TypeError, ValueError):
            return None

    def set_mapping_runtime(self, mapping_runtime: Any) -> None:
        """Attach manual mapping to the same reconnect/fault lifecycle."""

        with self._lifecycle_lock:
            self._mapping_runtime = mapping_runtime

    def is_obstacle_detection_active(self) -> bool:
        """Return whether patrol or mapping still owns an operation lifecycle.

        ``active_patrol_id`` intentionally remains present while an obstacle
        pauses patrol, allowing CLEAR detection to resume the same patrol.
        Mapping is internal and keeps the public Backend state IDLE, so its
        dedicated lifecycle flag is consulted without changing MQTT enums.
        """

        with self._lifecycle_lock:
            if self._active_patrol_id is not None:
                return True
            mapping_runtime = self._mapping_runtime
        return bool(getattr(mapping_runtime, "motion_active", False))

    def mapping_lifecycle_marker(self) -> tuple[int | None, int]:
        """Return a conservative lock-free snapshot for mapping START races.

        Mapping START must not acquire ``_lifecycle_lock`` while the runtime
        fault callback is waiting for the command handler's mapping lock.  A
        changed or mixed snapshot is therefore treated as a safe START failure.
        """

        return self._runtime_lifecycle_marker()

    def readiness(self) -> tuple[bool, str]:
        """Return the physical/navigation gate without issuing a command."""

        if not self.is_running():
            return False, "SERIAL_RUNTIME_NOT_RUNNING"
        if (
            self._manual_controller is None
            and self._navigation_service is None
            and self._navigation_provider is None
            and not self._allow_legacy_direct_patrol
        ):
            return False, "PATROL_ROUTE_NOT_CONFIGURED"
        snapshot_method = getattr(self._runtime.state_store, "snapshot", None)
        if not callable(snapshot_method):
            return True, "READY"
        snapshot = snapshot_method()
        motion_state = getattr(snapshot, "motion_state", None)
        if (
            motion_state is None
            or getattr(motion_state, "left_distance_m", None) is None
            or getattr(motion_state, "right_distance_m", None) is None
        ):
            return False, "ODOMETRY_NOT_READY"
        safety = getattr(snapshot, "safety_decision", None)
        if safety is None or not getattr(safety, "allowed", False):
            return False, str(getattr(safety, "fault", "SAFETY_NOT_READY"))
        if self._navigation_driver is not None:
            get_pose = getattr(self._runtime.state_store, "get_pose", None)
            if not callable(get_pose) or get_pose() is None:
                return False, "MAP_POSE_NOT_READY"
            ready = getattr(self._navigation_driver, "is_ready", None)
            if callable(ready):
                decision = ready()
                if isinstance(decision, tuple):
                    if not decision[0]:
                        return False, str(decision[1])
                elif not decision:
                    return False, "NAV2_NOT_READY"
        return True, "READY"

    def mapping_readiness(self) -> tuple[bool, str]:
        """Require only the Serial/odometry safety needed for manual mapping."""

        if not self.is_running():
            return False, "SERIAL_RUNTIME_NOT_RUNNING"
        snapshot_method = getattr(self._runtime.state_store, "snapshot", None)
        if not callable(snapshot_method):
            return True, "READY"
        snapshot = snapshot_method()
        motion_state = getattr(snapshot, "motion_state", None)
        if (
            motion_state is None
            or getattr(motion_state, "left_distance_m", None) is None
            or getattr(motion_state, "right_distance_m", None) is None
        ):
            return False, "ODOMETRY_NOT_READY"
        safety = getattr(snapshot, "safety_decision", None)
        if safety is None or not getattr(safety, "allowed", False):
            return False, str(getattr(safety, "fault", "SAFETY_NOT_READY"))
        return True, "READY"

    def send_command(self, command: str, **parameters: Any) -> None:
        """기존 MQTT 명령을 Final Runtime의 Mission 목표로 전달한다."""

        with self._lifecycle_lock:
            if not self.is_running():
                raise RuntimeError("Final RobotRuntime is not running")
            if command == "START_PATROL":
                if self._active_patrol_id is not None:
                    raise RuntimeError("a patrol is already active")
                ready, reason = self.readiness()
                if not ready:
                    raise RuntimeError(f"runtime is not ready: {reason}")
                lifecycle_marker = self._runtime_lifecycle_marker()
                patrol_id = parameters.get("patrolId")
                expires_at = parameters.get("expires_at")
                try:
                    if self._manual_controller is not None:
                        self._ensure_start_not_expired(expires_at)
                        self._manual_controller.activate(patrol_id)
                        self._active_patrol_id = int(patrol_id)
                        self._paused = False
                    elif self._navigation_service is not None:
                        if self._navigation_driver is not None:
                            self._start_nav2_patrol(
                                patrol_id=patrol_id,
                                expires_at=expires_at,
                            )
                        else:
                            self._start_encoder_waypoint_patrol(
                                patrol_id=patrol_id,
                                expires_at=expires_at,
                            )
                    else:
                        if not self._allow_legacy_direct_patrol:
                            raise RuntimeError("PATROL_ROUTE_NOT_CONFIGURED")
                        self._ensure_start_not_expired(expires_at)
                        self._active_patrol_id = int(patrol_id)
                        self._paused = False
                        self._runtime.mission.start_patrol(
                            speed=self._patrol_drive_speed_pwm,
                            steering_deg=self._patrol_steering_degrees,
                        )
                    if lifecycle_marker != self._runtime_lifecycle_marker():
                        raise RuntimeError(
                            "runtime lifecycle changed during START_PATROL"
                        )
                except PatrolStartExpired:
                    self._rollback_expired_start()
                    raise
                except Exception:
                    self._rollback_failed_start()
                    raise
                return
            if command == "STOP_PATROL":
                self._stop_patrol_from_command()
                return
            raise ValueError(
                f"unsupported Final RobotRuntime command: {command}"
            )

    def confirm_patrol_started(self, patrol_id: int) -> bool:
        """Linearize PATROLLING publication with reconnect/fault cleanup."""

        with self._lifecycle_lock:
            if self._active_patrol_id != patrol_id or self._paused:
                return False
            self._update_runtime_state("PATROLLING")
            return True

    def _start_encoder_waypoint_patrol(
        self,
        *,
        patrol_id: Any,
        expires_at: datetime | None = None,
    ) -> None:
        if self._encoder_progress is None or self._navigation_service is None:
            raise RuntimeError("encoder waypoint navigation is not configured")
        snapshot = self._runtime.state_store.snapshot()
        motion_state = snapshot.motion_state
        safety_decision = snapshot.safety_decision
        if (
            motion_state is None
            or motion_state.left_distance_m is None
            or motion_state.right_distance_m is None
        ):
            raise RuntimeError(
                "fresh calibrated odometry is required before START_PATROL"
            )
        if safety_decision is None or not safety_decision.allowed:
            fault = (
                getattr(safety_decision, "fault", "RUNTIME_NOT_READY")
                if safety_decision is not None
                else "RUNTIME_NOT_READY"
            )
            raise RuntimeError(f"runtime safety is not ready: {fault}")

        self._ensure_start_not_expired(expires_at)
        self._encoder_progress.start(
            left_distance_m=motion_state.left_distance_m,
            right_distance_m=motion_state.right_distance_m,
        )
        self._navigation_service.start_patrol(patrol_id=patrol_id)
        self._active_patrol_id = int(patrol_id)
        self._paused = False
        self._ensure_start_not_expired(expires_at)
        self._runtime.mission.start_patrol(
            speed=self._patrol_drive_speed_pwm,
            steering_deg=self._patrol_steering_degrees,
        )

    def _start_nav2_patrol(
        self,
        *,
        patrol_id: Any,
        expires_at: datetime | None = None,
    ) -> None:
        if self._navigation_service is None or self._navigation_driver is None:
            raise RuntimeError("Nav2 navigation is not configured")
        ready, reason = self.readiness()
        if not ready:
            raise RuntimeError(f"runtime is not ready: {reason}")
        self._ensure_start_not_expired(expires_at)
        event = self._navigation_service.start_patrol(patrol_id=patrol_id)
        self._active_patrol_id = int(patrol_id)
        self._paused = False
        self._ensure_start_not_expired(expires_at)
        self._navigation_driver.start_patrol(
            route=self._navigation_service.route,
            first_event=event,
        )

    def _ensure_start_not_expired(
        self, expires_at: datetime | None
    ) -> None:
        if expires_at is None:
            return
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            raise RuntimeError("START_PATROL deadline must be timezone-aware")
        now = self._wall_clock()
        if now.tzinfo is None:
            raise RuntimeError("runtime wall clock must be timezone-aware")
        if now >= expires_at:
            raise PatrolStartExpired()

    def apply_motion_command(self, command: Any) -> None:
        """Apply a calibrated Nav2 cmd_vel target through the single runtime."""

        with self._lifecycle_lock:
            self._apply_motion_command_locked(command)

    def _apply_motion_command_locked(self, command: Any) -> None:
        if self._active_patrol_id is None or self._paused:
            self._best_effort_stop_runtime_patrol("MOTION_INTERLOCK")
            return
        if int(command.speed_pwm) == 0:
            self._best_effort_stop_runtime_patrol(
                command.stop_reason or "NAV2_STOP"
            )
            return
        self._runtime.mission.start_patrol(
            speed=int(command.speed_pwm),
            steering_deg=int(command.steering_deg),
        )

    def pause_patrol(self, reason: str = "OBSTACLE") -> bool:
        with self._lifecycle_lock:
            return self._pause_patrol_locked(reason)

    def _pause_patrol_locked(self, reason: str) -> bool:
        if self._active_patrol_id is None or self._paused:
            return False
        self._paused = True
        self._publish_scan_context_locked(None)
        component_failure: Exception | None = None
        try:
            if self._manual_controller is not None:
                self._manual_controller.deactivate()
            elif self._navigation_driver is not None:
                pause = getattr(self._navigation_driver, "pause_patrol", None)
                if callable(pause):
                    pause()
        except Exception as exc:
            component_failure = exc
        stop_confirmed = self._best_effort_stop_runtime_patrol(reason)
        if component_failure is not None or not stop_confirmed:
            self._fail_patrol_locked(f"{reason}_PAUSE_FAILED")
            return False
        return True

    def resume_patrol(self) -> bool:
        with self._lifecycle_lock:
            return self._resume_patrol_locked()

    def _resume_patrol_locked(self) -> bool:
        if self._active_patrol_id is None or not self._paused:
            return False
        try:
            if self._manual_controller is not None:
                assert self._active_patrol_id is not None
                self._manual_controller.activate(self._active_patrol_id)
            elif self._navigation_driver is not None:
                resume = getattr(self._navigation_driver, "resume_patrol", None)
                if callable(resume):
                    resume()
            else:
                self._runtime.mission.start_patrol(
                    speed=self._patrol_drive_speed_pwm,
                    steering_deg=self._patrol_steering_degrees,
                )
        except Exception as exc:
            self._fail_patrol_locked(
                f"RESUME_FAILED_{type(exc).__name__}"
            )
            return False
        self._paused = False
        return True

    def fail_patrol(self, reason: str) -> None:
        with self._lifecycle_lock:
            self._fail_patrol_locked(reason)

    def _fail_patrol_locked(
        self, reason: str, *, external_motion_active: bool = False
    ) -> None:
        had_patrol = (
            self._active_patrol_id is not None
            or bool(getattr(self._manual_controller, "active", False))
            or self._patrol_lease_held
            or external_motion_active
        )
        try:
            self._best_effort_stop_runtime_patrol(reason)
        finally:
            cleanup_failure = self._cleanup_patrol_components()
            self._active_patrol_id = None
            self._paused = False
            try:
                self._release_patrol_lease()
            except Exception as exc:
                if cleanup_failure is None:
                    cleanup_failure = exc
            self._update_runtime_state("ERROR")
            if had_patrol:
                self._notify_fault_listener(reason)
            if cleanup_failure is not None:
                print(
                    "[RUNTIME] patrol failure cleanup incomplete "
                    f"type={type(cleanup_failure).__name__}"
                )

    def prepare_patrol(
        self, *, expires_at: datetime | None = None
    ) -> tuple[bool, str]:
        """Refresh the route, then acquire OTA interlock before AI or motion."""

        with self._lifecycle_lock:
            ready, reason = self._refresh_navigation_locked(deadline=expires_at)
            if not ready:
                return ready, reason
            return self._prepare_patrol_locked()

    def _refresh_navigation_locked(
        self, *, deadline: datetime | None = None
    ) -> tuple[bool, str]:
        if self._navigation_provider is None:
            return True, "READY"
        if self._active_patrol_id is not None:
            return False, "PATROL_ALREADY_ACTIVE"
        try:
            navigation = (
                self._navigation_provider.load_navigation()
                if deadline is None
                else self._navigation_provider.load_navigation(deadline=deadline)
            )
        except Exception as exc:
            reason = str(getattr(exc, "reason", "NAVIGATION_CONFIG_UNAVAILABLE"))
            if (
                self._local_navigation_fallback_enabled
                and self._local_navigation_service is not None
                and bool(getattr(exc, "local_fallback_allowed", False))
            ):
                self._install_navigation_service_locked(
                    self._local_navigation_service
                )
                self._navigation_prepared_from_provider = True
                print(
                    "[NAVIGATION] backend config unavailable; "
                    f"using explicit local fallback reason={reason}"
                )
                return True, "LOCAL_ROUTE_FALLBACK"
            return False, reason
        self._install_navigation_service_locked(navigation)
        self._navigation_prepared_from_provider = True
        return True, "READY"

    def _install_navigation_service_locked(self, navigation: Any) -> None:
        if navigation is None:
            raise RuntimeError("NAVIGATION_CONFIG_INVALID")
        add_listener = getattr(navigation, "add_event_listener", None)
        if not callable(add_listener):
            raise RuntimeError("NAVIGATION_CONFIG_INVALID")
        add_listener(self._on_navigation_event)
        self._navigation_service = navigation

    def _prepare_patrol_locked(self) -> tuple[bool, str]:
        if self._patrol_lease_held or self._deployment_guard is None:
            return True, "READY"
        decision = self._deployment_guard.acquire()
        ready, reason = (
            decision if isinstance(decision, tuple) else (bool(decision), "READY")
        )
        if ready:
            self._patrol_lease_held = True
        return bool(ready), str(reason)

    def cancel_prepared_patrol(self) -> None:
        with self._lifecycle_lock:
            if self._active_patrol_id is None:
                self._release_patrol_lease()
                if self._navigation_prepared_from_provider:
                    self._navigation_service = None
                    self._navigation_prepared_from_provider = False
                self._publish_scan_context_locked(None)

    def tick(self) -> None:
        """Advance a map-pose mission without taking ownership of ROS."""

        with self._lifecycle_lock:
            self._tick_locked()

    def _tick_locked(self) -> None:
        if self._navigation_driver is not None and self._active_patrol_id is not None:
            check_health = getattr(
                self._navigation_driver,
                "check_health",
                None,
            )
            if callable(check_health):
                try:
                    healthy = check_health()
                except Exception as exc:
                    self._fail_patrol_locked(
                        f"NAVIGATION_HEALTH_ERROR_{type(exc).__name__}"
                    )
                    return
                if healthy is False and self._active_patrol_id is not None:
                    self._fail_patrol_locked("NAVIGATION_HEALTH_FAILED")
                    return
        if (
            self._navigation_service is None
            or self._active_patrol_id is None
            or self._paused
        ):
            return
        pose = self._runtime.state_store.get_pose()
        if pose is None:
            return
        from navigation.waypoint_mission import Pose2D

        try:
            self._navigation_service.update_pose(
                Pose2D(float(pose.x), float(pose.y), float(pose.heading))
            )
        except Exception as exc:
            self._fail_patrol_locked(
                f"NAVIGATION_UPDATE_ERROR_{type(exc).__name__}"
            )

    def _on_odometry(self, _odometry: Any, motion_state: Any) -> None:
        progress = self._encoder_progress
        navigation = self._navigation_service
        if progress is None or navigation is None or not progress.active:
            return
        left_distance = motion_state.left_distance_m
        right_distance = motion_state.right_distance_m
        if left_distance is None or right_distance is None:
            self._fail_encoder_waypoint("calibrated wheel distance disappeared")
            return
        try:
            poses = progress.update(
                left_distance_m=left_distance,
                right_distance_m=right_distance,
            )
            for pose in poses:
                if self._encoder_fallback_enabled:
                    update_pose = getattr(
                        self._runtime.state_store, "update_pose", None
                    )
                    if callable(update_pose):
                        update_pose(
                            SimpleNamespace(
                                x=float(pose.x),
                                y=float(pose.y),
                                heading=float(pose.yaw_deg),
                            )
                        )
                navigation.update_pose(pose)
        except Exception as error:
            self._fail_encoder_waypoint(str(error))

    def _fail_encoder_waypoint(self, reason: str) -> None:
        self.fail_patrol("ENCODER_WAYPOINT_FAULT")
        print(f"[NAVIGATION ERROR] {reason}")

    def _stop_runtime_patrol(self, reason: str) -> None:
        stop_patrol = getattr(self._runtime, "stop_patrol", None)
        if callable(stop_patrol):
            stop_patrol(reason)
            return
        self._runtime.mission.stop_patrol()

    def _best_effort_stop_runtime_patrol(self, reason: str) -> bool:
        """Keep safety/idle callbacks non-throwing after fail-closing motion."""

        try:
            self._stop_runtime_patrol(reason)
        except Exception as exc:
            print(
                "[RUNTIME] physical STOP not confirmed "
                f"reason={reason} type={type(exc).__name__}"
            )
            return False
        return True

    def _on_runtime_connected(self, generation: int) -> None:
        """Invalidate all cross-thread patrol state on every Serial generation."""

        with self._lifecycle_lock:
            self._on_runtime_connected_locked(generation)

    def _on_runtime_connected_locked(self, generation: int) -> None:
        had_active_patrol = self._active_patrol_id is not None
        manual_active = bool(
            getattr(self._manual_controller, "active", False)
        )
        lease_held = self._patrol_lease_held
        mapping_motion_active = self._mapping_motion_active()
        # Clear the public interlock before component cleanup. Any concurrent
        # stale cmd_vel callback then takes MOTION_INTERLOCK instead of rearming.
        self._active_patrol_id = None
        self._paused = False
        cleanup_failure = self._cleanup_patrol_components()
        try:
            self._release_patrol_lease()
        except Exception as exc:
            if cleanup_failure is None:
                cleanup_failure = exc
        if had_active_patrol or manual_active or lease_held or mapping_motion_active:
            self._update_runtime_state("ERROR")
            self._notify_fault_listener("SERIAL_CONNECTION_RESET")
            print(
                "[RUNTIME] patrol invalidated by Serial connection reset "
                f"generation={generation}"
            )
        if cleanup_failure is not None:
            # RobotRuntime catches listener errors too, but this adapter keeps
            # cleanup failures local so every connection can finish handshake.
            print(
                "[RUNTIME] connection reset cleanup incomplete "
                f"generation={generation} "
                f"type={type(cleanup_failure).__name__}"
            )

    def _on_runtime_safety_fault(self, reason: str) -> bool:
        """Linearize an ESP/runtime fault with START and abandon the patrol."""

        # Increment before waiting for the lifecycle lock.  A START blocked in
        # a component call can then observe that a fault arrived and roll back
        # instead of returning a successful ACK before this callback runs.
        self._runtime_fault_generation += 1
        with self._lifecycle_lock:
            had_active_patrol = self._active_patrol_id is not None
            manual_active = bool(
                getattr(self._manual_controller, "active", False)
            )
            mapping_motion_active = self._mapping_motion_active()
            if not (
                had_active_patrol
                or manual_active
                or self._patrol_lease_held
                or mapping_motion_active
            ):
                return False
            self._fail_patrol_locked(
                reason,
                external_motion_active=mapping_motion_active,
            )
            return True

    def _mapping_motion_active(self) -> bool:
        return bool(getattr(self._mapping_runtime, "motion_active", False))

    def _runtime_lifecycle_marker(self) -> tuple[int | None, int]:
        generation = getattr(self._runtime, "connection_generation", None)
        if not isinstance(generation, int):
            generation = None
        return generation, self._runtime_fault_generation

    def _notify_fault_listener(self, reason: str) -> None:
        if not callable(self._fault_listener):
            return
        try:
            self._fault_listener(reason)
        except Exception as exc:
            print(
                "[RUNTIME] fault listener failed "
                f"reason={reason} type={type(exc).__name__}"
            )

    def _rollback_failed_start(self) -> None:
        """Preserve the START failure while completing best-effort rollback."""

        self._best_effort_stop_runtime_patrol("START_PATROL_ROLLBACK")
        cleanup_failure = self._cleanup_patrol_components()
        self._active_patrol_id = None
        self._paused = False
        try:
            self._release_patrol_lease()
        except Exception as exc:
            if cleanup_failure is None:
                cleanup_failure = exc
        if cleanup_failure is not None:
            print(
                "[RUNTIME] START rollback cleanup incomplete "
                f"type={type(cleanup_failure).__name__}"
            )

    def _rollback_expired_start(self) -> None:
        """Cancel prepared route state without sending a physical STOP."""

        cleanup_failure: Exception | None = None
        operations = []
        if self._encoder_progress is not None:
            operations.append(self._encoder_progress.stop)
        if self._navigation_service is not None:
            operations.append(self._navigation_service.stop_patrol)
        for operation in operations:
            try:
                operation()
            except Exception as exc:
                if cleanup_failure is None:
                    cleanup_failure = exc
                else:
                    print(
                        "[RUNTIME] additional expired START cleanup failure "
                        f"type={type(exc).__name__}"
                    )
        self._active_patrol_id = None
        self._paused = False
        try:
            self._release_patrol_lease()
        except Exception as exc:
            if cleanup_failure is None:
                cleanup_failure = exc
        if self._navigation_prepared_from_provider:
            self._navigation_service = None
            self._navigation_prepared_from_provider = False
        self._publish_scan_context_locked(None)
        if cleanup_failure is not None:
            print(
                "[RUNTIME] expired START cleanup incomplete "
                f"type={type(cleanup_failure).__name__}"
            )

    def _stop_patrol_from_command(self) -> None:
        """Stop once, always clean local state, then surface delivery failure."""

        failure: Exception | None = None
        try:
            self._stop_runtime_patrol("MQTT_STOP_PATROL")
        except Exception as exc:
            failure = exc
        finally:
            cleanup_failure = self._cleanup_patrol_components()
            if failure is None:
                failure = cleanup_failure
            elif cleanup_failure is not None:
                print(
                    "[RUNTIME] additional STOP cleanup failure "
                    f"type={type(cleanup_failure).__name__}"
                )
            self._active_patrol_id = None
            self._paused = False
            try:
                self._release_patrol_lease()
            except Exception as exc:
                if failure is None:
                    failure = exc
                else:
                    print(
                        "[RUNTIME] additional lease release failure "
                        f"type={type(exc).__name__}"
                    )
        if failure is not None:
            raise failure

    def _cleanup_patrol_components(self) -> Exception | None:
        """Attempt every local stop even when one component cleanup fails."""

        failure: Exception | None = None
        operations = []
        if self._manual_controller is not None:
            operations.append(self._manual_controller.deactivate)
        if self._encoder_progress is not None:
            operations.append(self._encoder_progress.stop)
        if self._navigation_service is not None:
            operations.append(self._navigation_service.stop_patrol)
        if self._navigation_driver is not None:
            operations.append(self._navigation_driver.stop_patrol)
        for operation in operations:
            try:
                operation()
            except Exception as exc:
                if failure is None:
                    failure = exc
                else:
                    print(
                        "[RUNTIME] additional patrol cleanup failure "
                        f"type={type(exc).__name__}"
                    )
        self._publish_scan_context_locked(None)
        return failure

    def _update_runtime_state(self, state: str) -> None:
        update = getattr(self._runtime.state_store, "update_robot_state", None)
        if callable(update):
            update(state)

    def _on_navigation_event(self, event: Any) -> None:
        with self._lifecycle_lock:
            self._on_navigation_event_locked(event)

    def _on_navigation_event_locked(self, event: Any) -> None:
        event_type = getattr(event.mission_event.event_type, "value", "")
        waypoint = getattr(event.mission_event, "waypoint", None)
        if event_type == "WAYPOINT_REACHED":
            self._publish_scan_context_locked(None)
        elif event_type == "ACTION_REQUIRED":
            self._publish_scan_context_locked(waypoint)
        if event_type in {"WAYPOINT_REACHED", "ACTION_REQUIRED"}:
            print(
                "[NAVIGATION] "
                f"event={event_type} "
                f"waypoint={getattr(waypoint, 'name', None)}"
            )
        if self._navigation_driver is not None:
            callback = getattr(self._navigation_driver, "on_navigation_event", None)
            if callable(callback):
                callback(event)
        if event_type == "DESTINATION_REACHED":
            if self._encoder_progress is not None:
                self._encoder_progress.stop()
            stop_confirmed = self._best_effort_stop_runtime_patrol(
                "DESTINATION_REACHED"
            )
            if self._navigation_driver is not None:
                self._navigation_driver.stop_patrol()
            self._active_patrol_id = None
            self._paused = False
            self._release_patrol_lease()
            self._update_runtime_state("IDLE" if stop_confirmed else "ERROR")
            if callable(self._destination_listener):
                self._destination_listener(event)

    def _publish_scan_context_locked(self, waypoint: Any | None) -> None:
        if not callable(self._scan_context_listener):
            return
        try:
            self._scan_context_listener(waypoint)
        except Exception as exc:
            print(
                "[NAVIGATION] scan context listener failed "
                f"type={type(exc).__name__}"
            )

    def _release_patrol_lease(self) -> None:
        if not self._patrol_lease_held:
            return
        self._patrol_lease_held = False
        if self._deployment_guard is not None:
            self._deployment_guard.release()
