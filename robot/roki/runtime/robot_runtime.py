"""Serial 메시지를 Controller와 RobotStateStore로 분기하는 Runtime."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from control.motion_controller import MotionController, MotionState, MotionTarget
from mission.mission_controller import (
    MissionCommand,
    MissionController,
    MissionSnapshot,
)
from localization.encoder_pose_estimator import EncoderPoseEstimator
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
ConnectionListener = Callable[[int], None]
SafetyFaultListener = Callable[[str], bool | None]


ACTIVE_PATROL_FAULTS = frozenset(
    {
        "ODOMETRY_TIMEOUT",
        "HARDWARE_STATUS_TIMEOUT",
        "MOTOR_FAULT",
        "MOTOR_DISCONNECTED",
        "LINE_SENSOR_FAULT",
        "LINE_SENSOR_DISCONNECTED",
        "LOW_BATTERY",
    }
)


@dataclass(frozen=True)
class RuntimeSettings:
    disconnected_poll_sec: float
    encoder_zero_retry_interval_sec: float = 0.5
    encoder_zero_max_attempts: int = 3

    def __post_init__(self) -> None:
        if self.encoder_zero_retry_interval_sec <= 0:
            raise ValueError("encoder zero retry interval must be positive")
        if self.encoder_zero_max_attempts < 1:
            raise ValueError("encoder zero max attempts must be at least one")


@dataclass(frozen=True)
class _MotionRequest:
    speed: int
    steering_deg: int
    stationary_steering: bool = False


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
        encoder_pose_estimator: EncoderPoseEstimator | None = None,
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
        self._encoder_pose_estimator = encoder_pose_estimator
        self._clock = clock
        self._sleep = sleep
        self._sequence = SequenceCounter()
        self._odometry_listeners: list[OdometryListener] = []
        self._hardware_status_listeners: list[HardwareStatusListener] = []
        self._connection_listeners: list[ConnectionListener] = []
        self._safety_fault_listeners: list[SafetyFaultListener] = []
        self._connection_generation = 0
        self._stop_requested = False
        self._request_lock = threading.Lock()
        self._pending_motion_request: _MotionRequest | None = None
        self._pending_motion_stop: int | None = None
        self._manual_motion_active = False
        self._stationary_steering_pending = False
        self._latest_hardware_status: HardwareStatus | None = None
        self._last_logged_line_values: tuple[int, ...] | None = None
        self._last_odometry_uptime_ms: int | None = None
        self._odometry_baseline_pending = True
        self._encoder_zero_acknowledged = False
        self._encoder_zero_attempts = 0
        self._encoder_zero_last_sent_at: float | None = None
        self._encoder_zero_wait_logged = False

    @property
    def mission(self) -> MissionController:
        return self._mission

    @property
    def state_store(self) -> RobotStateStore:
        """향후 MQTT Publisher가 snapshot을 읽는 경계."""

        return self._state_store

    @property
    def connection_generation(self) -> int:
        return self._connection_generation

    def add_odometry_listener(self, listener: OdometryListener) -> None:
        self._odometry_listeners.append(listener)

    def add_hardware_status_listener(
        self, listener: HardwareStatusListener
    ) -> None:
        self._hardware_status_listeners.append(listener)

    def add_connection_listener(self, listener: ConnectionListener) -> None:
        """Observe every new Serial generation on the Serial owner thread."""

        self._connection_listeners.append(listener)

    def add_safety_fault_listener(self, listener: SafetyFaultListener) -> None:
        """Observe faults that require the active patrol to be abandoned."""

        self._safety_fault_listeners.append(listener)

    def request_stop(self) -> None:
        with self._request_lock:
            self._stop_requested = True
            self._pending_motion_request = None
            self._pending_motion_stop = None
            self._manual_motion_active = False
            self._stationary_steering_pending = False
            self._mission.emergency_stop()

    def request_motion_target(
        self,
        speed: int,
        steering_deg: int,
        *,
        stationary_steering: bool = False,
    ) -> None:
        """Queue a manual target without writing Serial from another thread."""

        if not self._protocol_settings.speed_min <= speed <= self._protocol_settings.speed_max:
            raise ValueError("speed is outside protocol range")
        if not (
            self._protocol_settings.steering_min_deg
            <= steering_deg
            <= self._protocol_settings.steering_max_deg
        ):
            raise ValueError("steering_deg is outside protocol range")
        if stationary_steering and speed != 0:
            raise ValueError("stationary steering requires speed=0")
        with self._request_lock:
            if self._stop_requested:
                raise RuntimeError("RobotRuntime is stopping")
            self._pending_motion_request = _MotionRequest(
                speed,
                steering_deg,
                stationary_steering,
            )

    def request_motion_stop(self, steering_deg: int) -> None:
        """Queue a STOP that takes priority over any pending manual target."""

        if not (
            self._protocol_settings.steering_min_deg
            <= steering_deg
            <= self._protocol_settings.steering_max_deg
        ):
            raise ValueError("steering_deg is outside protocol range")
        with self._request_lock:
            if self._stop_requested:
                return
            self._pending_motion_request = None
            self._pending_motion_stop = steering_deg

    def stop_patrol(self, reason: str = "PATROL_STOP") -> None:
        """Clear the motion target and send STOP without waiting for telemetry."""

        self._fail_closed_mission(reason)
        if not self._send_stop(reason):
            raise RuntimeError(
                "ESP32 STOP was not delivered; mission is fail-closed and "
                "the firmware watchdog is the remaining stop path"
            )

    def run_forever(self) -> None:
        logger.info("RO-KI headless runtime started")
        try:
            while not self._stop_requested:
                self._drain_motion_requests()
                if self._bridge.ensure_connected():
                    self._on_connected()
                if not self._bridge.is_connected():
                    self._sleep(self._settings.disconnected_poll_sec)
                    continue
                self._maintain_encoder_zero_handshake()
                if not self._bridge.is_connected():
                    continue
                raw = self._bridge.read_line()
                if raw is None:
                    self._evaluate_idle_safety()
                    continue
                message = parse_message(raw, self._protocol_settings)
                if message is None:
                    logger.warning("Invalid protocol message ignored")
                    self._handle_serial_protocol_fault(
                        "INVALID_PROTOCOL_MESSAGE",
                        active_only=True,
                    )
                    continue
                if message.message_type is MessageType.ERROR:
                    fault = str(message.payload["fault"])
                    self._handle_serial_protocol_fault(f"ESP32_{fault}")
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
            with self._request_lock:
                self._pending_motion_request = None
                self._pending_motion_stop = None
                self._manual_motion_active = False
                self._stationary_steering_pending = False
            self._bridge.close(build_stop_command(self._sequence.next()))
            logger.info("RO-KI headless runtime stopped")

    def _on_connected(self) -> None:
        self._connection_generation += 1
        connection_generation = self._connection_generation
        # A new Serial generation may represent an ESP32 reboot. Never carry a
        # previous mission across it; only a subsequent START may arm motion.
        self._fail_closed_mission("SERIAL_CONNECTION_RESET", log=False)
        self._latest_hardware_status = None
        self._last_logged_line_values = None
        self._last_odometry_uptime_ms = None
        self._odometry_baseline_pending = True
        self._encoder_zero_acknowledged = False
        self._encoder_zero_attempts = 0
        self._encoder_zero_last_sent_at = None
        self._encoder_zero_wait_logged = False
        self._motion.reset()
        if self._encoder_pose_estimator is not None:
            self._encoder_pose_estimator.reset_baseline()
        self._safety.reset_connection()
        self._state_store.reset_connection()
        for listener in tuple(self._connection_listeners):
            try:
                listener(connection_generation)
            except Exception as exc:
                # A lifecycle adapter must never terminate the only Serial
                # owner. The post-listener fail-close below also invalidates
                # motion that a failing callback may have partially rearmed.
                logger.error(
                    "Serial connection listener failed: generation=%d "
                    "type=%s",
                    connection_generation,
                    type(exc).__name__,
                )
        # Close the window where a stale Nav2/manual callback raced the first
        # reset or a connection listener partially changed mission state.
        self._fail_closed_mission("SERIAL_CONNECTION_RESET")
        if not self._bridge.write_line(build_stop_command(self._sequence.next())):
            return
        self._bridge.write_line(build_hello_command(self._sequence.next()))
        self._send_encoder_zero_attempt(retry=False)
        logger.info("Serial handshake sent after mandatory STOP")

    def _send_encoder_zero_attempt(self, *, retry: bool) -> None:
        if retry:
            if not self._bridge.write_line(
                build_stop_command(self._sequence.next())
            ):
                return
        if not self._bridge.write_line(
            build_encoder_zero_command(self._sequence.next())
        ):
            return
        self._encoder_zero_attempts += 1
        self._encoder_zero_last_sent_at = self._clock()
        self._bridge.write_line(build_status_command(self._sequence.next()))
        if retry:
            logger.warning(
                "ENCODER_ZERO ACK timeout; retrying handshake attempt=%d/%d",
                self._encoder_zero_attempts,
                self._settings.encoder_zero_max_attempts,
            )

    def _maintain_encoder_zero_handshake(self) -> None:
        if self._encoder_zero_acknowledged:
            return
        now = self._clock()
        last_sent_at = self._encoder_zero_last_sent_at
        if (
            last_sent_at is not None
            and now - last_sent_at
            < self._settings.encoder_zero_retry_interval_sec
        ):
            return
        if self._encoder_zero_attempts < self._settings.encoder_zero_max_attempts:
            self._send_encoder_zero_attempt(retry=True)
            return
        logger.error(
            "ENCODER_ZERO ACK missing after %d attempts; reconnecting Serial",
            self._encoder_zero_attempts,
        )
        self._fail_closed_mission("ENCODER_ZERO_HANDSHAKE_FAILED")
        self._bridge.close(build_stop_command(self._sequence.next()))
        self._encoder_zero_attempts = 0
        self._encoder_zero_last_sent_at = None

    def _handle_ack(self, command: str) -> None:
        if command.upper() != "ENCODER_ZERO":
            return
        self._latest_hardware_status = None
        self._last_logged_line_values = None
        self._last_odometry_uptime_ms = None
        self._odometry_baseline_pending = True
        self._motion.reset()
        if self._encoder_pose_estimator is not None:
            self._encoder_pose_estimator.reset_baseline()
        self._safety.reset_connection()
        self._state_store.reset_connection()
        self._encoder_zero_acknowledged = True
        self._encoder_zero_wait_logged = False
        logger.info(
            "ENCODER_ZERO acknowledged after attempt=%d; awaiting fresh operating data",
            self._encoder_zero_attempts,
        )

    def _ignore_operating_data_until_encoder_zero(self) -> None:
        if self._encoder_zero_wait_logged:
            return
        self._encoder_zero_wait_logged = True
        logger.warning("Operating data ignored until ENCODER_ZERO ACK")

    def _handle_odometry(self, odometry: Odometry) -> None:
        if not self._encoder_zero_acknowledged:
            self._ignore_operating_data_until_encoder_zero()
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
            self._handle_serial_protocol_fault("ESP32_UPTIME_RESET")
            return
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
        self._enforce_active_patrol_fault(decision)
        mission = self._mission.snapshot()
        motion_authorized = mission.patrol_active or self._manual_motion_active
        target = MotionTarget(
            speed=(
                mission.command.speed
                if (
                    decision.allowed
                    and not self._odometry_baseline_pending
                    and motion_authorized
                )
                else 0
            ),
            steering_deg=mission.command.steering_deg,
        )
        command, motion_state = self._motion.update(odometry, target)
        self._state_store.update_odometry(odometry, motion_state)
        if self._encoder_pose_estimator is not None:
            odom_pose = self._encoder_pose_estimator.update(
                motion_state,
                steering_command=command.steering_deg,
                timestamp=now,
            )
            self._state_store.update_odom_pose(odom_pose)
        for listener in tuple(self._odometry_listeners):
            listener(odometry, motion_state)
        if self._odometry_baseline_pending:
            self._odometry_baseline_pending = False
            self._send_stop(
                decision.fault if not decision.allowed else "ODOMETRY_BASELINE"
            )
            return
        if self._drain_motion_requests():
            return
        latest_decision = self._evaluate_safety(self._clock())
        stationary_steering = self._stationary_steering_pending

        def write_if_safe(current: MissionSnapshot) -> None:
            authorized = current.patrol_active or self._manual_motion_active
            if (
                not latest_decision.allowed
                or current.command.emergency_stop
                or not authorized
                or (
                    (command.speed == 0 or current.command.speed == 0)
                    and not stationary_steering
                )
            ):
                self._stationary_steering_pending = False
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
                logger.warning(
                    "CONTROL write failed; ESP32 watchdog will stop motors"
                )
            else:
                self._stationary_steering_pending = False

        if not self._mission.run_if_current(
            mission.generation,
            write_if_safe,
        ):
            self._stationary_steering_pending = False
            self._send_stop("MISSION_CHANGED_BEFORE_CONTROL")

    def _drain_motion_requests(self) -> bool:
        """Apply cross-thread manual requests only on the Serial owner thread."""

        with self._request_lock:
            stop_steering = self._pending_motion_stop
            request = self._pending_motion_request
            self._pending_motion_stop = None
            self._pending_motion_request = None
            if stop_steering is not None:
                self._stationary_steering_pending = False
                self._manual_motion_active = False
                self._mission.submit(MissionCommand(0, stop_steering))
            elif request is not None:
                # Keep mailbox removal and mission application atomic against
                # _fail_closed_mission(), using the same request->mission lock
                # order. Otherwise STOP can land in this gap and the stale
                # request can resurrect motion afterwards.
                self._mission.submit(
                    MissionCommand(request.speed, request.steering_deg)
                )
                self._manual_motion_active = True
                self._stationary_steering_pending = (
                    request.stationary_steering
                )
        if stop_steering is not None:
            self._send_stop("MANUAL_STOP")
            return True
        if request is None:
            return False
        return True

    def _fail_closed_mission(self, reason: str, *, log: bool = True) -> None:
        """Invalidate queued and active motion before a mandatory STOP.

        The request lock prevents a pre-reset manual request from being queued
        between mailbox cleanup and mission invalidation. ``stop_patrol`` also
        increments the mission generation used to guard the final Serial write.
        """

        with self._request_lock:
            self._pending_motion_request = None
            self._pending_motion_stop = None
            self._manual_motion_active = False
            self._stationary_steering_pending = False
            self._mission.stop_patrol()
        if log:
            logger.warning("Motion authorization cleared: reason=%s", reason)

    def _handle_hardware_status(
        self, hardware_status: HardwareStatus
    ) -> None:
        if not self._encoder_zero_acknowledged:
            self._ignore_operating_data_until_encoder_zero()
            return
        now = self._clock()
        logger.debug(
            "HardwareStatus: batteryPercent=%s batteryVoltage=%s motor=%s "
            "lineSensor=%s",
            hardware_status.battery_percent,
            hardware_status.battery_voltage,
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
        self._enforce_active_patrol_fault(decision)
        if not decision.allowed and decision.fault not in ACTIVE_PATROL_FAULTS:
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
        self._enforce_active_patrol_fault(decision)
        if not decision.allowed and decision.fault not in ACTIVE_PATROL_FAULTS:
            self._send_stop(decision.fault)

    def _enforce_active_patrol_fault(
        self,
        decision: SafetyDecision,
    ) -> None:
        """Fail the whole patrol for faults that cannot safely auto-resume.

        ``*_NOT_READY`` remains a START/readiness gate.  Once operation has
        begun, stale telemetry and physical component faults invalidate the
        mission generation before STOP and notify the integration lifecycle so
        Nav2/manual control, AI and the deployment lease can be cleared too.
        """

        if decision.allowed or decision.fault not in ACTIVE_PATROL_FAULTS:
            return
        self._fail_closed_mission(decision.fault)
        self._send_stop(decision.fault)
        self._notify_safety_fault(decision.fault)

    def _handle_serial_protocol_fault(
        self,
        reason: str,
        *,
        active_only: bool = False,
    ) -> None:
        """STOP/abandon and reconnect, except idle malformed boot output."""

        mission = self._mission.snapshot()
        local_motion_active = mission.patrol_active or self._manual_motion_active
        listener_handled = False
        if active_only and not local_motion_active:
            # ESP bootloader/banner fragments can be non-JSON before the
            # ENCODER_ZERO ACK.  STOP and consume them without reopening the
            # port forever.  A lifecycle listener can still report an outer
            # Nav2 patrol that is goal-pending before the first cmd_vel.
            listener_handled = self._notify_safety_fault(reason)
            if not listener_handled:
                self._send_stop(reason)
                return
        self._safety.latch(reason)
        self._fail_closed_mission(reason)
        self._evaluate_safety(self._clock())
        self._send_stop(reason)
        if not listener_handled:
            self._notify_safety_fault(reason)
        # A valid frame following an ESP ERROR or malformed frame must not
        # silently re-arm the old mission.  Re-open only through mandatory
        # STOP/HELLO/ENCODER_ZERO and fresh telemetry in ``_on_connected``.
        self._bridge.close()

    def _notify_safety_fault(self, reason: str) -> bool:
        handled = False
        for listener in tuple(self._safety_fault_listeners):
            try:
                handled = bool(listener(reason)) or handled
            except Exception as exc:
                # A reporting/cleanup adapter must never kill the only Serial
                # owner; the mission has already been fail-closed above.
                logger.error(
                    "Safety fault listener failed: reason=%s type=%s",
                    reason,
                    type(exc).__name__,
                )
        return handled

    def _send_stop(self, reason: str) -> bool:
        """Best-effort STOP used by safety loops; never raise to the caller."""

        delivered = False
        if self._bridge.is_connected():
            try:
                delivered = bool(
                    self._bridge.write_line(
                        build_stop_command(self._sequence.next())
                    )
                )
            except Exception as exc:
                logger.error(
                    "STOP write raised; firmware watchdog fallback remains: "
                    "type=%s",
                    type(exc).__name__,
                )
        if not delivered:
            logger.error(
                "STOP delivery is unconfirmed; firmware watchdog fallback "
                "remains (serialConnected=%s)",
                self._bridge.is_connected(),
            )
        if reason != "NONE":
            logger.warning("STOP enforced: reason=%s", reason)
        return delivered
