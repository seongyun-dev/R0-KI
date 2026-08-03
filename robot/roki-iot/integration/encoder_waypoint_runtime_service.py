"""MQTT-facing runtime facade for bounded encoder waypoint patrols.

The completed status/pose stack keeps ownership of publishing and the shared
RobotStateStore.  This facade only translates START/STOP plus Runtime odometry
callbacks into the waypoint mission and physical motion target.
"""

from __future__ import annotations

from typing import Any

from integration.runtime_state_backend_adapter import FinalRuntimeService
from navigation.encoder_waypoint import (
    EncoderWaypointProgress,
    EncoderWaypointSettings,
)


class EncoderWaypointRuntimeService(FinalRuntimeService):
    def __init__(
        self,
        runtime: Any,
        *,
        navigation_service: Any | None,
        patrol_drive_speed_pwm: int = 45,
        patrol_steering_degrees: int = 80,
        navigation_start_x_m: float = 0.0,
        navigation_start_y_m: float = 0.0,
        navigation_maximum_travel_m: float = 0.70,
    ) -> None:
        super().__init__(
            runtime,
            patrol_drive_speed_pwm=patrol_drive_speed_pwm,
            patrol_steering_degrees=patrol_steering_degrees,
        )
        self._navigation_service = navigation_service
        self._encoder_progress: EncoderWaypointProgress | None = None
        if navigation_service is not None:
            self._encoder_progress = EncoderWaypointProgress(
                EncoderWaypointSettings(
                    start_x_m=navigation_start_x_m,
                    start_y_m=navigation_start_y_m,
                    maximum_travel_m=navigation_maximum_travel_m,
                )
            )
            navigation_service.add_event_listener(self._on_navigation_event)
            runtime.add_odometry_listener(self._on_odometry)

    def send_command(self, command: str, **parameters: Any) -> None:
        if self._navigation_service is None:
            super().send_command(command, **parameters)
            return
        if not self.is_running():
            raise RuntimeError("Final RobotRuntime is not running")
        if command == "START_PATROL":
            self._start_patrol(patrol_id=parameters.get("patrolId"))
            return
        if command == "STOP_PATROL":
            self._stop_progress()
            self._navigation_service.stop_patrol()
            self._stop_runtime("MQTT_STOP_PATROL")
            return
        raise ValueError(f"unsupported Final RobotRuntime command: {command}")

    def _start_patrol(self, *, patrol_id: Any) -> None:
        progress = self._encoder_progress
        navigation = self._navigation_service
        if progress is None or navigation is None:
            raise RuntimeError("encoder waypoint navigation is not configured")
        snapshot = self._runtime.state_store.snapshot()
        motion_state = snapshot.motion_state
        safety = snapshot.safety_decision
        if (
            motion_state is None
            or motion_state.left_distance_m is None
            or motion_state.right_distance_m is None
        ):
            raise RuntimeError(
                "fresh calibrated odometry is required before START_PATROL"
            )
        if safety is None or not safety.allowed:
            fault = getattr(safety, "fault", "RUNTIME_NOT_READY")
            raise RuntimeError(f"runtime safety is not ready: {fault}")

        progress.start(
            left_distance_m=motion_state.left_distance_m,
            right_distance_m=motion_state.right_distance_m,
        )
        try:
            navigation.start_patrol(patrol_id=patrol_id)
            self._runtime.mission.start_patrol(
                speed=self._patrol_drive_speed_pwm,
                steering_deg=self._patrol_steering_degrees,
            )
        except Exception:
            progress.stop()
            navigation.stop_patrol()
            self._stop_runtime("START_PATROL_ROLLBACK")
            raise

    def _on_odometry(self, _odometry: Any, motion_state: Any) -> None:
        progress = self._encoder_progress
        navigation = self._navigation_service
        if progress is None or navigation is None or not progress.active:
            return
        if (
            motion_state.left_distance_m is None
            or motion_state.right_distance_m is None
        ):
            self._fail("calibrated wheel distance disappeared")
            return
        try:
            poses = progress.update(
                left_distance_m=motion_state.left_distance_m,
                right_distance_m=motion_state.right_distance_m,
            )
            for pose in poses:
                navigation.update_pose(pose)
        except Exception as error:
            self._fail(str(error))

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
            self._stop_progress()
            self._stop_runtime("DESTINATION_REACHED")
            update_state = getattr(
                self._runtime.state_store,
                "update_robot_state",
                None,
            )
            if callable(update_state):
                update_state("IDLE")

    def _fail(self, reason: str) -> None:
        self._stop_progress()
        if self._navigation_service is not None:
            self._navigation_service.stop_patrol()
        self._stop_runtime("ENCODER_WAYPOINT_FAULT")
        update_state = getattr(
            self._runtime.state_store,
            "update_robot_state",
            None,
        )
        if callable(update_state):
            update_state("ERROR")
        print(f"[NAVIGATION ERROR] {reason}")

    def _stop_progress(self) -> None:
        if self._encoder_progress is not None:
            self._encoder_progress.stop()

    def _stop_runtime(self, reason: str) -> None:
        stop_patrol = getattr(self._runtime, "stop_patrol", None)
        if callable(stop_patrol):
            stop_patrol(reason)
            return
        self._runtime.mission.stop_patrol()
