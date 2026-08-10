"""외부 adapter와 주행 Runtime 사이의 thread-safe Mission 상태."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MissionCommand:
    speed: int
    steering_deg: int
    emergency_stop: bool = False


@dataclass(frozen=True)
class MissionSnapshot:
    """One atomically observed mission state.

    ``generation`` is the motion-authorisation epoch.  It changes when a
    mission becomes active or is invalidated, but not for speed/steering
    updates inside the same active mission.  The Serial owner can therefore
    refresh the last authorised command while still rejecting commands from a
    stopped or replaced mission.
    """

    command: MissionCommand
    patrol_active: bool
    generation: int


class MissionController:
    """마지막 Mission 명령을 보관한다.

    현재는 headless 정지 명령으로 시작한다. 향후 MQTT adapter는
    submit()만 호출하고 Serial/Protocol 계층에는 접근하지 않는다.
    """

    def __init__(self, steering_center_deg: int) -> None:
        self._lock = threading.Lock()
        self._command = MissionCommand(0, steering_center_deg)
        self._patrol_active = False
        self._generation = 0

    def submit(self, command: MissionCommand) -> None:
        with self._lock:
            self._command = command
            self._generation += 1

    def current(self) -> MissionCommand:
        with self._lock:
            return self._command

    def snapshot(self) -> MissionSnapshot:
        with self._lock:
            return MissionSnapshot(
                self._command,
                self._patrol_active,
                self._generation,
            )

    def run_if_current(
        self,
        expected_generation: int,
        operation: Callable[[MissionSnapshot], None],
    ) -> bool:
        """Run ``operation`` while the expected mission remains locked.

        Holding the mission lock through the Serial write linearizes CONTROL
        against ``stop_patrol``: a concurrent STOP either follows the CONTROL
        on the wire, or invalidates it before it can be written.
        """

        with self._lock:
            if self._generation != expected_generation:
                return False
            operation(
                MissionSnapshot(
                    self._command,
                    self._patrol_active,
                    self._generation,
                )
            )
            return True

    @property
    def patrol_active(self) -> bool:
        with self._lock:
            return self._patrol_active

    def start_patrol(
        self,
        *,
        speed: int = 0,
        steering_deg: int | None = None,
    ) -> None:
        """Activate a mission or update the target of the active mission.

        Nav2 publishes a new speed/steering target continuously.  Repeating
        this call while already active is therefore a target update, not a new
        lifecycle transition.  STOP/emergency still advance the generation,
        so a later inactive-to-active call always starts a new epoch.
        """

        with self._lock:
            was_active = self._patrol_active
            target_steering = (
                self._command.steering_deg
                if steering_deg is None
                else steering_deg
            )
            self._patrol_active = True
            self._command = MissionCommand(
                speed,
                target_steering,
                emergency_stop=False,
            )
            if not was_active:
                self._generation += 1

    def stop_patrol(self) -> None:
        """Mission을 비활성화하고 정상 정지 목표를 설정한다."""

        with self._lock:
            self._patrol_active = False
            self._command = MissionCommand(0, self._command.steering_deg)
            self._generation += 1

    def emergency_stop(self) -> None:
        with self._lock:
            self._patrol_active = False
            self._command = MissionCommand(
                0, self._command.steering_deg, emergency_stop=True
            )
            self._generation += 1
