from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any


class RobotStateStore:
    """Jetson 내부에서 로봇의 최신 상태를 공유하는 저장소."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        self._pose: dict[str, float] | None = None

        self._status: dict[str, Any] = {
            "battery": None,
            "state": "IDLE",
            "motor": "DISCONNECTED",
            "camera": "DISCONNECTED",
            "lidar": "DISCONNECTED",
            "lineSensor": "DISCONNECTED",
            "obstacle": {
                "status": "CLEAR",
                "direction": "NONE",
                "reasonMessage": None,
            },
        }

    def update_hardware_status(
        self,
        *,
        battery: float | None = None,
        motor: str | None = None,
        line_sensor: str | None = None,
    ) -> None:
        with self._lock:
            if battery is not None:
                self._status["battery"] = float(battery)

            if motor is not None:
                self._status["motor"] = motor

            if line_sensor is not None:
                self._status["lineSensor"] = line_sensor

    def update_robot_state(self, state: str) -> None:
        with self._lock:
            self._status["state"] = state

    def update_camera_status(self, camera: str) -> None:
        with self._lock:
            self._status["camera"] = camera

    def update_lidar_status(self, lidar: str) -> None:
        with self._lock:
            self._status["lidar"] = lidar

    def update_obstacle(
        self,
        *,
        status: str,
        direction: str,
        reason_message: str | None,
    ) -> None:
        with self._lock:
            self._status["obstacle"] = {
                "status": status,
                "direction": direction,
                "reasonMessage": reason_message,
            }

            if status == "STOP":
                self._status["state"] = "OBSTACLE_STOP"

    def update_pose(
        self,
        *,
        x: float,
        y: float,
        heading: float,
    ) -> None:
        with self._lock:
            self._pose = {
                "x": float(x),
                "y": float(y),
                "heading": float(heading),
            }

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._status)

    def get_pose(self) -> dict[str, float] | None:
        with self._lock:
            return deepcopy(self._pose)
