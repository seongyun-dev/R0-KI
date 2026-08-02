"""Final Runtime 상태를 기존 Backend Store에 전달하는 listener adapter."""

from __future__ import annotations

import threading
from typing import Any

from state.models import HardwareState
from state.robot_state_store import RobotStateStore


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
        self._backend_state_store.update_hardware(
            HardwareState(
                battery=hardware_status.battery_percent,
                motor=hardware_status.motor.value,
                line_sensor=hardware_status.line_sensor.value,
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
    ) -> None:
        self._runtime = runtime
        self._patrol_drive_speed_pwm = patrol_drive_speed_pwm
        self._patrol_steering_degrees = patrol_steering_degrees
        self._navigation_service = navigation_service
        self._encoder_progress: Any | None = None
        self._thread: threading.Thread | None = None
        if navigation_service is not None:
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
        self._thread = threading.Thread(
            target=self._runtime.run_forever,
            name="robot-runtime",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._runtime.request_stop()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def send_command(self, command: str, **parameters: Any) -> None:
        """기존 MQTT 명령을 Final Runtime의 Mission 목표로 전달한다."""

        if not self.is_running():
            raise RuntimeError("Final RobotRuntime is not running")
        if command == "START_PATROL":
            if self._navigation_service is not None:
                self._start_encoder_waypoint_patrol(
                    patrol_id=parameters.get("patrolId")
                )
                return
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
            self._stop_runtime_patrol("MQTT_STOP_PATROL")
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
            self._runtime.mission.start_patrol(
                speed=self._patrol_drive_speed_pwm,
                steering_deg=self._patrol_steering_degrees,
            )
        except Exception:
            self._encoder_progress.stop()
            self._navigation_service.stop_patrol()
            self._stop_runtime_patrol("START_PATROL_ROLLBACK")
            raise

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
                navigation.update_pose(pose)
        except Exception as error:
            self._fail_encoder_waypoint(str(error))

    def _fail_encoder_waypoint(self, reason: str) -> None:
        if self._encoder_progress is not None:
            self._encoder_progress.stop()
        if self._navigation_service is not None:
            self._navigation_service.stop_patrol()
        self._stop_runtime_patrol("ENCODER_WAYPOINT_FAULT")
        self._update_runtime_state("ERROR")
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
        if event_type == "DESTINATION_REACHED":
            if self._encoder_progress is not None:
                self._encoder_progress.stop()
            self._stop_runtime_patrol("DESTINATION_REACHED")
            self._update_runtime_state("IDLE")
