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

    ``generation`` changes for every submitted, started, or stopped mission so
    the Serial owner can reject a control command calculated from stale state.
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
        """Mission을 활성화하고 명시적으로 전달된 주행 목표를 보관한다."""

        with self._lock:
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
