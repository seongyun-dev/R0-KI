"""RobotRuntime과 향후 adapter 사이의 최신 상태 저장소."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable

from control.motion_controller import MotionState
from localization.pose import PoseEstimate, PoseFrame, PoseSource
from localization.pose_arbitrator import PoseArbitrator
from safety.safety_controller import SafetyDecision
from serial_comm.protocol import HardwareStatus, Odometry


@dataclass(frozen=True)
class RobotStateSnapshot:
    odometry: Odometry | None
    hardware_status: HardwareStatus | None
    motion_state: MotionState | None
    safety_decision: SafetyDecision | None


@dataclass(frozen=True)
class PoseState:
    """MQTT adapter 경계의 지도 기준 Pose. heading은 degree다."""

    x: float
    y: float
    heading: float


@dataclass(frozen=True)
class ObstacleState:
    """Backend 변환 전의 장애물 상태."""

    status: str = "CLEAR"
    direction: str = "NONE"
    reason_message: str | None = None


@dataclass(frozen=True)
class RobotStatusState:
    """MQTT adapter가 읽는 최신 운영 상태."""

    battery: float | None = None
    state: str = "IDLE"
    motor: str = "DISCONNECTED"
    camera: str = "DISCONNECTED"
    lidar: str = "DISCONNECTED"
    line_sensor: str = "DISCONNECTED"
    obstacle: ObstacleState = field(default_factory=ObstacleState)


class RobotStateStore:
    """최신 운영 상태를 thread-safe snapshot으로 제공한다."""

    def __init__(
        self,
        *,
        map_pose_timeout_sec: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._odometry: Odometry | None = None
        self._hardware_status: HardwareStatus | None = None
        self._motion_state: MotionState | None = None
        self._safety_decision: SafetyDecision | None = None
        self._odom_pose: PoseEstimate | None = None
        self._map_pose: PoseEstimate | None = None
        self._pose_arbitrator = PoseArbitrator(map_pose_timeout_sec)
        self._clock = clock
        self._status = RobotStatusState()
        self._status_changed = False

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
            self._set_status_if_changed(
                replace(
                    self._status,
                    battery=hardware_status.battery_percent,
                    motor=hardware_status.motor.value,
                    line_sensor=hardware_status.line_sensor.value,
                )
            )

    def update_safety(self, decision: SafetyDecision) -> None:
        with self._lock:
            self._safety_decision = decision

    def reset_connection(self) -> None:
        with self._lock:
            self._odometry = None
            self._hardware_status = None
            self._motion_state = None
            self._safety_decision = None
            self._set_status_if_changed(
                replace(
                    self._status,
                    battery=None,
                    motor="DISCONNECTED",
                    line_sensor="DISCONNECTED",
                )
            )

    def snapshot(self) -> RobotStateSnapshot:
        with self._lock:
            return RobotStateSnapshot(
                odometry=self._odometry,
                hardware_status=self._hardware_status,
                motion_state=self._motion_state,
                safety_decision=self._safety_decision,
            )

    def update_robot_state(self, state: str) -> None:
        with self._lock:
            self._set_status_if_changed(replace(self._status, state=state))

    def update_camera_status(self, camera_status: str) -> None:
        with self._lock:
            self._set_status_if_changed(
                replace(self._status, camera=camera_status)
            )

    def update_lidar_status(self, lidar_status: str) -> None:
        with self._lock:
            self._set_status_if_changed(
                replace(self._status, lidar=lidar_status)
            )

    def update_obstacle(self, obstacle: ObstacleState) -> None:
        with self._lock:
            self._set_status_if_changed(
                replace(self._status, obstacle=obstacle)
            )

    def update_odom_pose(self, pose: PoseEstimate) -> None:
        if pose.frame_id is not PoseFrame.ODOM:
            raise ValueError("odom pose must use odom frame")
        with self._lock:
            self._odom_pose = pose

    def get_odom_pose(self) -> PoseEstimate | None:
        with self._lock:
            return self._odom_pose

    def update_map_pose(self, pose: PoseEstimate) -> None:
        if pose.frame_id is not PoseFrame.MAP:
            raise ValueError("map pose must use map frame")
        with self._lock:
            self._map_pose = pose

    def get_map_pose(self) -> PoseEstimate | None:
        with self._lock:
            return self._map_pose

    def update_pose(self, pose: PoseState) -> None:
        """기존 Localization adapter 호환 API. 입력은 map Pose로 취급한다."""

        self.update_map_pose(
            PoseEstimate(
                x_m=pose.x,
                y_m=pose.y,
                heading_rad=math.radians(pose.heading),
                frame_id=PoseFrame.MAP,
                source=PoseSource.LOCALIZATION_MAP,
                valid=True,
                timestamp=self._clock(),
            )
        )

    def get_pose(self) -> PoseState | None:
        """유효하고 fresh한 map Pose만 MQTT 호환 모델로 반환한다."""

        with self._lock:
            selected = self._pose_arbitrator.select(
                map_pose=self._map_pose,
                odom_pose=self._odom_pose,
                now=self._clock(),
            )
            if selected is None:
                return None
            return PoseState(
                x=selected.x_m,
                y=selected.y_m,
                heading=math.degrees(selected.heading_rad),
            )

    def get_status(self) -> RobotStatusState:
        with self._lock:
            return self._status

    def has_status_changed(self) -> bool:
        with self._lock:
            return self._status_changed

    def mark_status_published(self) -> None:
        with self._lock:
            self._status_changed = False

    def _set_status_if_changed(self, updated: RobotStatusState) -> None:
        if updated == self._status:
            return
        self._status = updated
        self._status_changed = True
