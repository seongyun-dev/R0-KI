"""Temporary demo keyboard commands for the single RobotRuntime owner."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ManualDriveSettings:
    forward_target_pwm: int = 45
    reverse_target_pwm: int = 40
    drive_pulse_sec: float = 0.2
    steering_center_deg: int = 80
    steering_min_deg: int = 70
    steering_max_deg: int = 90
    steering_step_deg: int = 2
    steering_pulse_sec: float = 0.5

    def __post_init__(self) -> None:
        if self.forward_target_pwm <= 0 or self.reverse_target_pwm <= 0:
            raise ValueError("manual drive PWM targets must be positive")
        if self.drive_pulse_sec <= 0 or self.steering_pulse_sec <= 0:
            raise ValueError("manual pulse durations must be positive")
        if not (
            self.steering_min_deg
            <= self.steering_center_deg
            <= self.steering_max_deg
        ):
            raise ValueError("steering center must be inside steering range")
        if self.steering_step_deg <= 0:
            raise ValueError("steering step must be positive")


class ManualDriveController:
    """Gate short manual pulses behind an active backend patrol."""

    def __init__(
        self,
        *,
        runtime: Any,
        state_store: Any,
        settings: ManualDriveSettings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runtime = runtime
        self._mission = runtime.mission
        self._state_store = state_store
        self._settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._active = False
        self._steering_deg = settings.steering_center_deg
        self._pulse_deadline: float | None = None
        self._pulse_kind: str | None = None
        self._pulse_generation = 0
        self._active_pulse_generation = 0

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def steering_deg(self) -> int:
        with self._lock:
            return self._steering_deg

    def activate(self, patrol_id: int) -> None:
        if isinstance(patrol_id, bool) or not isinstance(patrol_id, int):
            raise ValueError("patrolId must be a positive integer")
        if patrol_id <= 0:
            raise ValueError("patrolId must be a positive integer")
        with self._lock:
            self._cancel_pulse_locked()
            self._active = True
            self._steering_deg = self._settings.steering_center_deg
            steering = self._steering_deg
        self._mission.start_patrol(speed=0, steering_deg=steering)
        self._runtime.request_motion_stop(steering)

    def deactivate(self) -> None:
        with self._lock:
            self._cancel_pulse_locked()
            self._active = False
            self._steering_deg = self._settings.steering_center_deg
            steering = self._steering_deg
        self._mission.stop_patrol()
        self._runtime.request_motion_stop(steering)

    def handle_key(self, key: str) -> str:
        normalized = key.lower()
        with self._lock:
            if not self._active or normalized not in {
                "w",
                "a",
                "s",
                "d",
                " ",
                "q",
            }:
                return "IGNORED"
            if normalized in {" ", "q"}:
                self._cancel_pulse_locked()
                steering = self._steering_deg
                action = "LOCAL_STOP" if normalized == "q" else "STOP"
            elif normalized == "w":
                if not self._forward_allowed():
                    self._cancel_pulse_locked()
                    steering = self._steering_deg
                    action = "FORWARD_BLOCKED"
                else:
                    steering = self._steering_deg
                    self._start_pulse_locked(
                        "FORWARD",
                        self._settings.drive_pulse_sec,
                    )
                    action = "FORWARD"
            elif normalized == "s":
                steering = self._steering_deg
                self._start_pulse_locked(
                    "REVERSE",
                    self._settings.drive_pulse_sec,
                )
                action = "REVERSE"
            else:
                delta = (
                    -self._settings.steering_step_deg
                    if normalized == "a"
                    else self._settings.steering_step_deg
                )
                self._steering_deg = max(
                    self._settings.steering_min_deg,
                    min(
                        self._settings.steering_max_deg,
                        self._steering_deg + delta,
                    ),
                )
                steering = self._steering_deg
                self._start_pulse_locked(
                    "STEERING",
                    self._settings.steering_pulse_sec,
                )
                action = "STEER_LEFT" if normalized == "a" else "STEER_RIGHT"

        if action in {"STOP", "LOCAL_STOP", "FORWARD_BLOCKED"}:
            self._runtime.request_motion_stop(steering)
        elif action == "FORWARD":
            self._runtime.request_motion_target(
                self._settings.forward_target_pwm,
                steering,
            )
        elif action == "REVERSE":
            self._runtime.request_motion_target(
                -self._settings.reverse_target_pwm,
                steering,
            )
        else:
            self._runtime.request_motion_target(
                0,
                steering,
                stationary_steering=True,
            )
        return action

    def tick(self) -> str | None:
        with self._lock:
            if not self._active or self._pulse_deadline is None:
                return None
            must_stop = (
                self._pulse_kind == "FORWARD" and not self._forward_allowed()
            )
            expired = self._clock() >= self._pulse_deadline
            generation = self._active_pulse_generation
            if not must_stop and not expired:
                return None
            if generation != self._pulse_generation:
                return None
            steering = self._steering_deg
            self._cancel_pulse_locked()
        self._runtime.request_motion_stop(steering)
        return "SAFETY_STOP" if must_stop else "PULSE_STOP"

    def _forward_allowed(self) -> bool:
        status = self._state_store.get_status()
        return status.lidar == "NORMAL" and status.obstacle.status != "STOP"

    def _start_pulse_locked(self, kind: str, duration: float) -> None:
        self._pulse_generation += 1
        self._active_pulse_generation = self._pulse_generation
        self._pulse_kind = kind
        self._pulse_deadline = self._clock() + duration

    def _cancel_pulse_locked(self) -> None:
        self._pulse_generation += 1
        self._active_pulse_generation = self._pulse_generation
        self._pulse_kind = None
        self._pulse_deadline = None
