"""RobotRuntime과 향후 adapter 사이의 최신 상태 저장소."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from control.motion_controller import MotionState
from safety.safety_controller import SafetyDecision
from serial_comm.protocol import HardwareStatus, Odometry


@dataclass(frozen=True)
class RobotStateSnapshot:
    odometry: Odometry | None
    hardware_status: HardwareStatus | None
    motion_state: MotionState | None
    safety_decision: SafetyDecision | None


class RobotStateStore:
    """최신 운영 상태를 thread-safe snapshot으로 제공한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._odometry: Odometry | None = None
        self._hardware_status: HardwareStatus | None = None
        self._motion_state: MotionState | None = None
        self._safety_decision: SafetyDecision | None = None

    def update_odometry(
        self, odometry: Odometry, motion_state: MotionState
    ) -> None:
        with self._lock:
            self._odometry = odometry
            self._motion_state = motion_state

    def update_hardware_status(
        self, hardware_status: HardwareStatus
    ) -> None:
        with self._lock:
            self._hardware_status = hardware_status

    def update_safety(self, decision: SafetyDecision) -> None:
        with self._lock:
            self._safety_decision = decision

    def reset_connection(self) -> None:
        with self._lock:
            self._odometry = None
            self._hardware_status = None
            self._motion_state = None
            self._safety_decision = None

    def snapshot(self) -> RobotStateSnapshot:
        with self._lock:
            return RobotStateSnapshot(
                odometry=self._odometry,
                hardware_status=self._hardware_status,
                motion_state=self._motion_state,
                safety_decision=self._safety_decision,
            )
