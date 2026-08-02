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
    ) -> None:
        self._runtime = runtime
        self._patrol_drive_speed_pwm = patrol_drive_speed_pwm
        self._patrol_steering_degrees = patrol_steering_degrees
        self._thread: threading.Thread | None = None

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

        del parameters
        if not self.is_running():
            raise RuntimeError("Final RobotRuntime is not running")
        if command == "START_PATROL":
            self._runtime.mission.start_patrol(
                speed=self._patrol_drive_speed_pwm,
                steering_deg=self._patrol_steering_degrees,
            )
            return
        if command == "STOP_PATROL":
            self._runtime.mission.stop_patrol()
            return
        raise ValueError(f"unsupported Final RobotRuntime command: {command}")
