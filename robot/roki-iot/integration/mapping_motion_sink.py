"""Let Nav2 drive the chassis while a mapping session is running.

Patrol authorises Nav2 motion against an active patrol id. Autonomous mapping has
no patrol: the goals come from the frontier explorer, not from a stored route. So
the same converted command needs a different gate -- the mapping session itself.

This deliberately reuses ``RobotRuntime.mission`` exactly as the patrol path does
(``start_patrol`` for a bounded speed/steering target, ``stop_patrol`` for zero),
so the firmware watchdog, the hardware safety controller and the LiDAR obstacle
interlock all keep applying unchanged. The gamepad drive controller is not used
here: it is a discrete W/A/S/D pulse interface and cannot express a continuous
``cmd_vel``.
"""

from __future__ import annotations

import threading
from typing import Any, Callable


StopReporter = Callable[[str], None]


class MappingMotionSink:
    """Apply Nav2 ``cmd_vel`` output only while mapping is actively driving."""

    def __init__(
        self,
        runtime: Any,
        mapping_runtime_getter: Callable[[], Any | None],
        *,
        stop_reporter: StopReporter | None = None,
    ) -> None:
        self._runtime = runtime
        self._mapping_runtime_getter = mapping_runtime_getter
        self._stop_reporter = stop_reporter
        self._lock = threading.Lock()
        self._driving = False
        self._stopped = False

    @property
    def driving(self) -> bool:
        with self._lock:
            return self._driving

    def mapping_authorised(self) -> bool:
        """매핑 세션이 지금 움직여도 되는 상태인가.

        cmd_vel 라우터가 매핑 게이트와 순찰 게이트 중 하나를 고를 때 쓴다.
        내부 판단과 같은 질문이므로 같은 답을 내야 한다 -- 라우터가 여기로
        보냈는데 안에서 거부하면 정지 명령만 오가고 아무도 주행하지 않는다.
        """

        return self._authorised()

    def _authorised(self) -> bool:
        mapping_runtime = self._mapping_runtime_getter()
        if mapping_runtime is None:
            return False
        # ``motion_active`` is the mapping runtime's own statement that a session
        # is running and movement is permitted; do not second-guess it here.
        return bool(getattr(mapping_runtime, "motion_active", False))

    def _stop(self, reason: str) -> None:
        with self._lock:
            was_driving = self._driving
            self._driving = False
            # Nav2's velocity smoother keeps publishing while it ramps down, and it
            # publishes whether or not a mapping session is running. Re-sending an
            # already-delivered stop for every one of those messages floods the
            # serial link at the smoother's rate, which is enough to reset the ESP32
            # link and drop motion authorization. One delivered stop is enough: the
            # firmware watchdog holds the chassis, and ``_stopped`` stays false until
            # a stop actually succeeds so a failed one is always retried.
            if self._stopped:
                return
        try:
            self._runtime.mission.stop_patrol()
        except Exception:
            # A failed stop must still surface: the caller decides whether that
            # is terminal, but never let it look like the robot is stopped.
            if self._stop_reporter is not None:
                self._stop_reporter(f"{reason}_STOP_FAILED")
            raise
        with self._lock:
            self._stopped = True
        if was_driving and self._stop_reporter is not None:
            self._stop_reporter(reason)

    def __call__(self, command: Any) -> None:
        if not self._authorised():
            self._stop("MAPPING_NOT_DRIVING")
            return
        speed = int(getattr(command, "speed_pwm", 0))
        if speed == 0:
            reason = getattr(command, "stop_reason", None)

            if reason == "IN_PLACE_ROTATION_REJECTED":
                self._runtime.mission.start_patrol(
                    speed=0,
                    steering_deg=int(command.steering_deg),
                )
                with self._lock:
                    self._driving = False
                    self._stopped = False
                return

            self._stop(reason or "MAPPING_NAV2_STOP")
            return
        self._runtime.mission.start_patrol(
            speed=speed,
            steering_deg=int(command.steering_deg),
        )
        with self._lock:
            self._driving = True
            self._stopped = False
