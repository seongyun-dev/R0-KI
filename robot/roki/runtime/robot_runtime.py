"""Serial 메시지를 Controller와 RobotStateStore로 분기하는 Runtime."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from control.motion_controller import MotionController, MotionState, MotionTarget
from mission.mission_controller import MissionController
from safety.safety_controller import SafetyController, SafetyDecision
from serial_comm.protocol import (
    HardwareStatus,
    MessageType,
    Odometry,
    ProtocolSettings,
    SequenceCounter,
    build_control_command,
    build_encoder_zero_command,
    build_hello_command,
    build_status_command,
    build_stop_command,
    parse_hardware_status,
    parse_message,
    parse_odometry,
)
from serial_comm.serial_bridge import SerialBridge
from state.robot_state import RobotStateStore

logger = logging.getLogger(__name__)
OdometryListener = Callable[[Odometry, MotionState], None]
HardwareStatusListener = Callable[[HardwareStatus], None]


@dataclass(frozen=True)
class RuntimeSettings:
    disconnected_poll_sec: float


class RobotRuntime:
    """연결, protocol 분기, Controller 호출과 상태 갱신을 조율한다."""

    def __init__(
        self,
        *,
        bridge: SerialBridge,
        protocol_settings: ProtocolSettings,
        mission: MissionController,
        motion: MotionController,
        safety: SafetyController,
        state_store: RobotStateStore,
        settings: RuntimeSettings,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._bridge = bridge
        self._protocol_settings = protocol_settings
        self._mission = mission
        self._motion = motion
        self._safety = safety
        self._state_store = state_store
        self._settings = settings
        self._clock = clock
        self._sleep = sleep
        self._sequence = SequenceCounter()
        self._odometry_listeners: list[OdometryListener] = []
        self._hardware_status_listeners: list[HardwareStatusListener] = []
        self._stop_requested = False
        self._latest_hardware_status: HardwareStatus | None = None
        self._last_logged_line_values: tuple[int, ...] | None = None
        self._last_odometry_uptime_ms: int | None = None
        self._odometry_baseline_pending = True
        self._encoder_zero_acknowledged = False

    @property
    def mission(self) -> MissionController:
        return self._mission

    @property
    def state_store(self) -> RobotStateStore:
        """향후 MQTT Publisher가 snapshot을 읽는 경계."""

        return self._state_store

    def add_odometry_listener(self, listener: OdometryListener) -> None:
        self._odometry_listeners.append(listener)

    def add_hardware_status_listener(
        self, listener: HardwareStatusListener
    ) -> None:
        self._hardware_status_listeners.append(listener)

    def request_stop(self) -> None:
        self._stop_requested = True
        self._mission.emergency_stop()

    def run_forever(self) -> None:
        logger.info("RO-KI headless runtime started")
        try:
            while not self._stop_requested:
                if self._bridge.ensure_connected():
                    self._on_connected()
                if not self._bridge.is_connected():
                    self._sleep(self._settings.disconnected_poll_sec)
                    continue
                raw = self._bridge.read_line()
                if raw is None:
                    self._evaluate_idle_safety()
                    continue
                message = parse_message(raw, self._protocol_settings)
                if message is None:
                    logger.warning("Invalid protocol message ignored")
                    self._send_stop("INVALID_PROTOCOL_MESSAGE")
                    continue
                if message.message_type is MessageType.ERROR:
                    fault = str(message.payload["fault"])
                    self._safety.latch(f"ESP32_{fault}")
                    self._send_stop(fault)
                elif message.message_type is MessageType.HELLO:
                    logger.info(
                        "ESP32 HELLO: firmware=%s protocol=%s sequence=%s",
                        message.payload["firmware"],
                        message.payload["protocol"],
                        message.payload["sequence"],
                    )
                elif message.message_type is MessageType.ACK:
                    logger.debug(
                        "ESP32 ACK: command=%s sequence=%s",
                        message.payload["command"],
                        message.payload["sequence"],
                    )
                    self._handle_ack(str(message.payload["command"]))
                elif message.message_type is MessageType.ODOMETRY:
                    self._handle_odometry(parse_odometry(message.payload))
                elif message.message_type is MessageType.HARDWARE_STATUS:
                    self._handle_hardware_status(
                        parse_hardware_status(message.payload)
                    )
        finally:
            self._bridge.close(build_stop_command(self._sequence.next()))
            logger.info("RO-KI headless runtime stopped")

    def _on_connected(self) -> None:
        self._latest_hardware_status = None
        self._last_logged_line_values = None
        self._last_odometry_uptime_ms = None
        self._odometry_baseline_pending = True
        self._encoder_zero_acknowledged = False
        self._motion.reset()
        self._safety.reset_connection()
        self._state_store.reset_connection()
        if not self._bridge.write_line(build_stop_command(self._sequence.next())):
            return
        self._bridge.write_line(build_hello_command(self._sequence.next()))
        self._bridge.write_line(build_encoder_zero_command(self._sequence.next()))
        self._bridge.write_line(build_status_command(self._sequence.next()))
        logger.info("Serial handshake sent after mandatory STOP")

    def _handle_ack(self, command: str) -> None:
        if command.upper() != "ENCODER_ZERO":
            return
        self._latest_hardware_status = None
        self._last_logged_line_values = None
        self._last_odometry_uptime_ms = None
        self._odometry_baseline_pending = True
        self._motion.reset()
        self._safety.reset_connection()
        self._state_store.reset_connection()
        self._encoder_zero_acknowledged = True
        logger.info("ENCODER_ZERO acknowledged; awaiting fresh operating data")

    def _handle_odometry(self, odometry: Odometry) -> None:
        if not self._encoder_zero_acknowledged:
            self._send_stop("ENCODER_ZERO_NOT_ACKNOWLEDGED")
            return
        now = self._clock()
        if (
            self._last_odometry_uptime_ms is not None
            and odometry.uptime_ms <= self._last_odometry_uptime_ms
        ):
            logger.warning(
                "ESP32 uptime reset detected: previous=%d current=%d",
                self._last_odometry_uptime_ms,
                odometry.uptime_ms,
            )
            self._latest_hardware_status = None
            self._last_logged_line_values = None
            self._motion.reset()
            self._safety.reset_connection()
            self._state_store.reset_connection()
            self._odometry_baseline_pending = True
        self._last_odometry_uptime_ms = odometry.uptime_ms
        logger.debug(
            "Odometry: seq=%d uptimeMs=%d leftTicks=%d rightTicks=%d",
            odometry.seq,
            odometry.uptime_ms,
            odometry.left_ticks,
            odometry.right_ticks,
        )
        self._safety.record_odometry(now)
        decision = self._evaluate_safety(now)
        mission = self._mission.current()
        target = MotionTarget(
            speed=(
                mission.speed
                if decision.allowed and not self._odometry_baseline_pending
                else 0
            ),
            steering_deg=mission.steering_deg,
        )
        command, motion_state = self._motion.update(odometry, target)
        self._state_store.update_odometry(odometry, motion_state)
        for listener in tuple(self._odometry_listeners):
            listener(odometry, motion_state)
        if self._odometry_baseline_pending:
            self._odometry_baseline_pending = False
            self._send_stop(
                decision.fault if not decision.allowed else "ODOMETRY_BASELINE"
            )
            return
        latest_decision = self._evaluate_safety(self._clock())
        if not latest_decision.allowed or command.speed == 0:
            self._send_stop(latest_decision.fault)
            return
        if not self._bridge.write_line(
            build_control_command(
                command.speed,
                command.steering_deg,
                self._sequence.next(),
                self._protocol_settings,
            )
        ):
            logger.warning("CONTROL write failed; ESP32 watchdog will stop motors")

    def _handle_hardware_status(
        self, hardware_status: HardwareStatus
    ) -> None:
        if not self._encoder_zero_acknowledged:
            self._send_stop("ENCODER_ZERO_NOT_ACKNOWLEDGED")
            return
        now = self._clock()
        logger.debug(
            "HardwareStatus: battery=%.2f motor=%s lineSensor=%s",
            hardware_status.battery_percent,
            hardware_status.motor.value,
            hardware_status.line_sensor.value,
        )
        if (
            hardware_status.line_values is not None
            and hardware_status.line_values != self._last_logged_line_values
        ):
            logger.info(
                "[LINE] raw=%s",
                list(hardware_status.line_values),
            )
            self._last_logged_line_values = hardware_status.line_values
        self._latest_hardware_status = hardware_status
        self._safety.record_hardware_status(now)
        self._state_store.update_hardware_status(hardware_status)
        for listener in tuple(self._hardware_status_listeners):
            listener(hardware_status)
        decision = self._evaluate_safety(now)
        if not decision.allowed:
            self._send_stop(decision.fault)

    def _evaluate_safety(self, now: float) -> SafetyDecision:
        decision = self._safety.evaluate(
            now=now,
            connected=self._bridge.is_connected(),
            hardware_status=self._latest_hardware_status,
            emergency_stop=self._mission.current().emergency_stop,
        )
        self._state_store.update_safety(decision)
        return decision

    def _evaluate_idle_safety(self) -> None:
        decision = self._evaluate_safety(self._clock())
        if not decision.allowed:
            self._send_stop(decision.fault)

    def _send_stop(self, reason: str) -> None:
        if self._bridge.is_connected():
            self._bridge.write_line(build_stop_command(self._sequence.next()))
        if reason != "NONE":
            logger.warning("STOP enforced: reason=%s", reason)
