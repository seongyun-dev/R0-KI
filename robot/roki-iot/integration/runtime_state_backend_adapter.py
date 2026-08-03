"""Final Runtime 상태를 기존 Backend Store에 전달하는 listener adapter."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

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
        self._backend_state_store.update_hardware(
            HardwareState(
                battery=hardware_status.battery_percent,
                motor=motor,
                line_sensor="DISCONNECTED",
            )
        )


class FinalRuntimeService:
    """Final RobotRuntime을 전용 thread에서 실행하는 lifecycle facade."""

    def __init__(
        self,
        runtime: Any,
        *,
        patrol_drive_speed_pwm: int = 51,
        patrol_steering_degrees: int = 80,
        navigation_service: Any | None = None,
        navigation_start_x_m: float = 1.0,
        navigation_start_y_m: float = 2.5,
        navigation_maximum_travel_m: float = 0.70,
        encoder_fallback_enabled: bool = True,
        navigation_driver: Any | None = None,
        destination_listener: Any | None = None,
        deployment_guard: Any | None = None,
    ) -> None:
        self._runtime = runtime
        self._patrol_drive_speed_pwm = patrol_drive_speed_pwm
        self._patrol_steering_degrees = patrol_steering_degrees
        self._navigation_service = navigation_service
        self._navigation_driver = navigation_driver
        self._destination_listener = destination_listener
        self._deployment_guard = deployment_guard
        self._patrol_lease_held = False
        self._encoder_fallback_enabled = encoder_fallback_enabled
        self._encoder_progress: Any | None = None
        self._thread: threading.Thread | None = None
        self._active_patrol_id: int | None = None
        self._paused = False
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
            navigation_service.add_event_listener(self._on_navigation_event)
            runtime.add_odometry_listener(self._on_odometry)

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

    def stop(self) -> None:
        try:
            if self._active_patrol_id is not None:
                self.send_command("STOP_PATROL")
        except Exception as exc:
            print(f"[RUNTIME] final STOP failed type={type(exc).__name__}")
        finally:
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
        return self._active_patrol_id

    @property
    def paused(self) -> bool:
        return self._paused

    def set_destination_listener(self, listener: Any) -> None:
        self._destination_listener = listener

    def readiness(self) -> tuple[bool, str]:
        """Return the physical/navigation gate without issuing a command."""

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

    def send_command(self, command: str, **parameters: Any) -> None:
        """기존 MQTT 명령을 Final Runtime의 Mission 목표로 전달한다."""

        if not self.is_running():
            raise RuntimeError("Final RobotRuntime is not running")
        if command == "START_PATROL":
            if self._active_patrol_id is not None:
                raise RuntimeError("a patrol is already active")
            if self._navigation_service is not None:
                if self._navigation_driver is not None:
                    self._start_nav2_patrol(patrol_id=parameters.get("patrolId"))
                else:
                    self._start_encoder_waypoint_patrol(
                        patrol_id=parameters.get("patrolId")
                    )
                return
            self._active_patrol_id = parameters.get("patrolId")
            self._runtime.mission.start_patrol(
                speed=self._patrol_drive_speed_pwm,
                steering_deg=self._patrol_steering_degrees,
            )
            return
        if command == "STOP_PATROL":
            if self._encoder_progress is not None:
                self._encoder_progress.stop()
            if self._navigation_service is not None:
                self._navigation_service.stop_patrol()
            if self._navigation_driver is not None:
                self._navigation_driver.stop_patrol()
            self._stop_runtime_patrol("MQTT_STOP_PATROL")
            self._active_patrol_id = None
            self._paused = False
            self._release_patrol_lease()
            return
        raise ValueError(f"unsupported Final RobotRuntime command: {command}")

    def _start_encoder_waypoint_patrol(self, *, patrol_id: Any) -> None:
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

        self._encoder_progress.start(
            left_distance_m=motion_state.left_distance_m,
            right_distance_m=motion_state.right_distance_m,
        )
        try:
            self._navigation_service.start_patrol(patrol_id=patrol_id)
            self._active_patrol_id = int(patrol_id)
            self._paused = False
            self._runtime.mission.start_patrol(
                speed=self._patrol_drive_speed_pwm,
                steering_deg=self._patrol_steering_degrees,
            )
        except Exception:
            self._active_patrol_id = None
            self._encoder_progress.stop()
            self._navigation_service.stop_patrol()
            self._stop_runtime_patrol("START_PATROL_ROLLBACK")
            self._release_patrol_lease()
            raise

    def _start_nav2_patrol(self, *, patrol_id: Any) -> None:
        if self._navigation_service is None or self._navigation_driver is None:
            raise RuntimeError("Nav2 navigation is not configured")
        ready, reason = self.readiness()
        if not ready:
            raise RuntimeError(f"runtime is not ready: {reason}")
        event = self._navigation_service.start_patrol(patrol_id=patrol_id)
        self._active_patrol_id = int(patrol_id)
        self._paused = False
        try:
            self._navigation_driver.start_patrol(
                route=self._navigation_service.route,
                first_event=event,
            )
        except Exception:
            self._active_patrol_id = None
            self._navigation_service.stop_patrol()
            self._stop_runtime_patrol("START_PATROL_ROLLBACK")
            self._release_patrol_lease()
            raise

    def apply_motion_command(self, command: Any) -> None:
        """Apply a calibrated Nav2 cmd_vel target through the single runtime."""

        if self._active_patrol_id is None or self._paused:
            self._stop_runtime_patrol("MOTION_INTERLOCK")
            return
        if int(command.speed_pwm) == 0:
            self._stop_runtime_patrol(command.stop_reason or "NAV2_STOP")
            return
        self._runtime.mission.start_patrol(
            speed=int(command.speed_pwm),
            steering_deg=int(command.steering_deg),
        )

    def pause_patrol(self, reason: str = "OBSTACLE") -> bool:
        if self._active_patrol_id is None or self._paused:
            return False
        self._paused = True
        if self._navigation_driver is not None:
            pause = getattr(self._navigation_driver, "pause_patrol", None)
            if callable(pause):
                pause()
        self._stop_runtime_patrol(reason)
        return True

    def resume_patrol(self) -> bool:
        if self._active_patrol_id is None or not self._paused:
            return False
        self._paused = False
        if self._navigation_driver is not None:
            resume = getattr(self._navigation_driver, "resume_patrol", None)
            if callable(resume):
                resume()
            return True
        self._runtime.mission.start_patrol(
            speed=self._patrol_drive_speed_pwm,
            steering_deg=self._patrol_steering_degrees,
        )
        return True

    def fail_patrol(self, reason: str) -> None:
        if self._encoder_progress is not None:
            self._encoder_progress.stop()
        if self._navigation_service is not None:
            self._navigation_service.stop_patrol()
        if self._navigation_driver is not None:
            self._navigation_driver.stop_patrol()
        self._stop_runtime_patrol(reason)
        self._active_patrol_id = None
        self._paused = False
        self._release_patrol_lease()
        self._update_runtime_state("ERROR")

    def prepare_patrol(self) -> tuple[bool, str]:
        """Acquire the OTA interlock before AI or actuators can be enabled."""

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
        if self._active_patrol_id is None:
            self._release_patrol_lease()

    def tick(self) -> None:
        """Advance a map-pose mission without taking ownership of ROS."""

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

        self._navigation_service.update_pose(
            Pose2D(float(pose.x), float(pose.y), float(pose.heading))
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

    def _update_runtime_state(self, state: str) -> None:
        update = getattr(self._runtime.state_store, "update_robot_state", None)
        if callable(update):
            update(state)

    def _on_navigation_event(self, event: Any) -> None:
        event_type = getattr(event.mission_event.event_type, "value", "")
        waypoint = getattr(event.mission_event, "waypoint", None)
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
            self._stop_runtime_patrol("DESTINATION_REACHED")
            if self._navigation_driver is not None:
                self._navigation_driver.stop_patrol()
            self._active_patrol_id = None
            self._paused = False
            self._release_patrol_lease()
            self._update_runtime_state("IDLE")
            if callable(self._destination_listener):
                self._destination_listener(event)

    def _release_patrol_lease(self) -> None:
        if not self._patrol_lease_held:
            return
        self._patrol_lease_held = False
        if self._deployment_guard is not None:
            self._deployment_guard.release()
