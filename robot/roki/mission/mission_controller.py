"""외부 adapter와 주행 Runtime 사이의 thread-safe Mission 상태."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class MissionCommand:
    speed: int
    steering_deg: int
    emergency_stop: bool = False


class MissionController:
    """마지막 Mission 명령을 보관한다.

    현재는 headless 정지 명령으로 시작한다. 향후 MQTT adapter는
    submit()만 호출하고 Serial/Protocol 계층에는 접근하지 않는다.
    """

    def __init__(self, steering_center_deg: int) -> None:
        self._lock = threading.Lock()
        self._command = MissionCommand(0, steering_center_deg)
        self._patrol_active = False

    def submit(self, command: MissionCommand) -> None:
        with self._lock:
            self._command = command

    def current(self) -> MissionCommand:
        with self._lock:
            return self._command

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

    def stop_patrol(self) -> None:
        """Mission을 비활성화하고 정상 정지 목표를 설정한다."""

        with self._lock:
            self._patrol_active = False
            self._command = MissionCommand(0, self._command.steering_deg)

    def emergency_stop(self) -> None:
        with self._lock:
            self._patrol_active = False
            self._command = MissionCommand(
                0, self._command.steering_deg, emergency_stop=True
            )
