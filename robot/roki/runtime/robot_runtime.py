"""Serial 메시지를 Controller와 RobotStateStore로 분기하는 Runtime."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
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

# 제어 루프 출구 집계 주기. 루프는 20 Hz 라 매 회 찍으면 저널이 묻힌다.
CONTROL_CENSUS_INTERVAL_SEC = 5.0
CONTROL_SEQUENCE_CENSUS_INTERVAL_SEC = 5.0
CONTROL_SEQUENCE_DETAIL_THRESHOLD_SEC = 0.2
CONTROL_ACK_MISS_THRESHOLD_SEC = 0.4
CONTROL_TRACE_RING_SIZE = 10
CONTROL_SAMPLE_WINDOW_SIZE = 1024
CONTROL_REFRESH_INTERVAL_SEC = 0.1
CONTROL_REFRESH_LATE_DETAIL_SEC = 0.15
CONTROL_REFRESH_SEND_DETAIL_SEC = 0.2
CALLBACK_QUEUE_SIZE = 64
OUTBOUND_WRITES_PER_CYCLE = 8

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
    control_refresh_interval_sec: float = CONTROL_REFRESH_INTERVAL_SEC
    outbound_write_timeout_sec: float = 2.0

    def __post_init__(self) -> None:
        if self.encoder_zero_retry_interval_sec <= 0:
            raise ValueError("encoder zero retry interval must be positive")
        if self.encoder_zero_max_attempts < 1:
            raise ValueError("encoder zero max attempts must be at least one")
        if self.control_refresh_interval_sec <= 0:
            raise ValueError("control refresh interval must be positive")
        if self.outbound_write_timeout_sec <= 0:
            raise ValueError("outbound write timeout must be positive")


@dataclass(frozen=True)
class _MotionRequest:
    speed: int
    steering_deg: int
    stationary_steering: bool = False


@dataclass(frozen=True)
class _AuthorizedControl:
    speed: int
    steering_deg: int
    mission_generation: int
    connection_generation: int
    authorized_at: float
    one_shot: bool = False


@dataclass
class _OutboundWrite:
    message: str
    completed: threading.Event
    result: bool | None = None


@dataclass(frozen=True)
class _DeferredCallback:
    name: str
    operation: Callable[[], None]


@dataclass
class _ControlTrace:
    ordinal: int
    sequence: int
    connection_generation: int
    generated_at: float
    write_started_at: float
    write_completed_at: float
    write_ok: bool
    send_gap_sec: float | None
    write_duration_sec: float
    ack_received_at: float | None = None
    ack_latency_sec: float | None = None
    ack_missed: bool = False


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
        self._control_gate_was_writing = False
        self._control_census: dict[str, int] = {}
        self._control_census_started_at: float | None = None
        self._control_trace_ordinal = 0
        self._control_trace_ring: deque[_ControlTrace] = deque(
            maxlen=CONTROL_TRACE_RING_SIZE
        )
        self._control_pending: dict[int, _ControlTrace] = {}
        self._control_acked_sequences: deque[int] = deque(
            maxlen=CONTROL_SAMPLE_WINDOW_SIZE
        )
        self._control_metrics_started_at: float | None = None
        self._control_generated_count = 0
        self._control_write_count = 0
        self._control_ack_count = 0
        self._control_ack_miss_count = 0
        self._control_duplicate_ack_count = 0
        self._control_out_of_order_ack_count = 0
        self._control_orphan_ack_count = 0
        self._control_last_write_completed_at: float | None = None
        self._control_last_ack_ordinal: int | None = None
        self._control_max_send_gap_sec = 0.0
        self._control_write_durations_sec: deque[float] = deque(
            maxlen=CONTROL_SAMPLE_WINDOW_SIZE
        )
        self._control_ack_latencies_sec: deque[float] = deque(
            maxlen=CONTROL_SAMPLE_WINDOW_SIZE
        )
        self._latest_hardware_status: HardwareStatus | None = None
        self._last_logged_line_values: tuple[int, ...] | None = None
        self._last_odometry_uptime_ms: int | None = None
        self._last_odometry_received_at: float | None = None
        self._last_hardware_received_at: float | None = None
        self._telemetry_recovery_generation: int | None = None
        self._parse_error_count = 0
        self._odometry_baseline_pending = True
        self._encoder_zero_acknowledged = False
        self._encoder_zero_attempts = 0
        self._encoder_zero_last_sent_at: float | None = None
        self._encoder_zero_wait_logged = False
        # The Serial owner remains the only thread that touches the transport.
        # Cross-thread STOP requests are synchronously marshalled through this
        # mailbox instead of writing the FD from their caller.
        self._serial_owner_thread_id: int | None = None
        self._scheduler_active = False
        self._outbound_condition = threading.Condition()
        self._priority_outbound_writes: deque[_OutboundWrite] = deque()
        self._outbound_writes: deque[_OutboundWrite] = deque()

        # Potentially slow StateStore/integration listeners run outside the
        # Serial owner.  Safety state, motion generation, and Serial I/O stay on
        # the owner thread; this queue contains observation work only.
        self._callback_condition = threading.Condition()
        self._callback_queue: deque[_DeferredCallback] = deque()
        self._reliable_callback_queue: deque[_DeferredCallback] = deque()
        self._callback_take_reliable_next = True
        self._callback_thread: threading.Thread | None = None
        self._callback_shutdown = False
        self._callback_coalesced_count = 0

        # Keep requested, authorized, and transmitted state distinct.  Only an
        # authorized target from the current connection/mission generation may
        # be refreshed.
        self._refresh_state_lock = threading.Lock()
        self._latest_requested_target: MissionCommand | None = None
        self._latest_authorized_control: _AuthorizedControl | None = None
        self._last_transmitted_control: _AuthorizedControl | None = None
        self._next_control_deadline: float | None = None
        self._last_refresh_actual_at: float | None = None
        self._refresh_max_generation_gap_sec = 0.0
        self._refresh_max_lateness_sec = 0.0
        self._refresh_count = 0
        self._refresh_skip_count = 0
        self._refresh_last_skip_reason: str | None = None
        self._inbound_processed_since_refresh = 0
        self._inbound_budget_started_at: float | None = None

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
        self._serial_owner_thread_id = threading.get_ident()
        self._scheduler_active = True
        self._next_control_deadline = (
            self._clock() + self._settings.control_refresh_interval_sec
        )
        self._start_callback_dispatcher()
        try:
            while not self._stop_requested:
                # One owner services priority writes, then accepts at most one
                # inbound record before re-checking the monotonic deadline.
                # This lets a due ODOMETRY record refresh its mission generation
                # without allowing an RX backlog to monopolise the loop.
                self._service_outbound_writes()
                self._drain_motion_requests()
                if self._bridge.ensure_connected():
                    self._count_control_outcome("reconnected")
                    self._on_connected()
                if not self._bridge.is_connected():
                    # Silent before: the only log on this branch was the INFO in
                    # ensure_connected, so a permanently unreachable ESP32 looked
                    # exactly like a healthy idle robot.
                    self._count_control_outcome("disconnected")
                    self._sleep(self._settings.disconnected_poll_sec)
                    continue
                self._maintain_encoder_zero_handshake()
                if not self._bridge.is_connected():
                    self._count_control_outcome("dropped_in_handshake")
                    continue
                raw = self._bridge.read_line()
                if raw is None:
                    self._count_control_outcome(
                        "no_data"
                        if self._encoder_zero_acknowledged
                        else "no_data_awaiting_ack"
                    )
                    self._evaluate_idle_safety()
                    self._service_outbound_writes()
                    self._service_control_refresh()
                    continue
                self._count_control_outcome("rx")
                self._inbound_processed_since_refresh += 1
                message = parse_message(raw, self._protocol_settings)
                if message is None:
                    self._parse_error_count += 1
                    logger.warning("Invalid protocol message ignored")
                    self._handle_serial_protocol_fault(
                        "INVALID_PROTOCOL_MESSAGE",
                        active_only=True,
                    )
                    self._service_outbound_writes()
                    self._service_control_refresh()
                    continue
                if message.message_type is MessageType.ERROR:
                    fault = str(message.payload["fault"])
                    if fault.upper() == "COMMAND_TIMEOUT":
                        self._dump_recent_control_traces("ESP32_COMMAND_TIMEOUT")
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
                    self._handle_ack(
                        str(message.payload["command"]),
                        int(message.payload["sequence"]),
                    )
                elif message.message_type is MessageType.ODOMETRY:
                    self._handle_odometry(parse_odometry(message.payload))
                elif message.message_type is MessageType.HARDWARE_STATUS:
                    self._handle_hardware_status(
                        parse_hardware_status(message.payload)
                    )
                self._service_outbound_writes()
                self._service_control_refresh()
        finally:
            with self._request_lock:
                self._pending_motion_request = None
                self._pending_motion_stop = None
                self._manual_motion_active = False
                self._stationary_steering_pending = False
            self._clear_refresh_targets("RUNTIME_SHUTDOWN")
            # Still on the owner thread: preserve final STOP-before-close.
            self._bridge.close(build_stop_command(self._sequence.next()))
            self._scheduler_active = False
            self._fail_pending_outbound_writes()
            self._stop_callback_dispatcher()
            self._serial_owner_thread_id = None
            logger.info("RO-KI headless runtime stopped")

    def _write_line(self, message: str, *, priority: bool = False) -> bool:
        """Write only on the Serial owner while the scheduler is active."""

        owner = self._serial_owner_thread_id
        if not self._scheduler_active or owner == threading.get_ident():
            return self._bridge.write_line(message)
        request = _OutboundWrite(message, threading.Event())
        with self._outbound_condition:
            if priority:
                # Separate FIFO keeps STOP/fault ordering while still placing
                # them ahead of ordinary transport requests.
                self._priority_outbound_writes.append(request)
            else:
                self._outbound_writes.append(request)
            self._outbound_condition.notify_all()
        if not request.completed.wait(
            timeout=self._settings.outbound_write_timeout_sec
        ):
            logger.error("Serial owner mailbox timed out before write")
            return False
        return bool(request.result)

    def _service_outbound_writes(self) -> None:
        """Drain a bounded batch so queued writes cannot starve CONTROL."""

        for _ in range(OUTBOUND_WRITES_PER_CYCLE):
            with self._outbound_condition:
                if self._priority_outbound_writes:
                    request = self._priority_outbound_writes.popleft()
                elif self._outbound_writes:
                    request = self._outbound_writes.popleft()
                else:
                    return
            try:
                request.result = self._bridge.write_line(request.message)
            except Exception:
                request.result = False
                logger.exception("Serial owner mailbox write raised")
            finally:
                request.completed.set()
            # A deadline always wins over the rest of a non-STOP backlog.
            deadline = self._next_control_deadline
            if deadline is not None and self._clock() >= deadline:
                return

    def _fail_pending_outbound_writes(self) -> None:
        with self._outbound_condition:
            pending = tuple(self._priority_outbound_writes) + tuple(
                self._outbound_writes
            )
            self._priority_outbound_writes.clear()
            self._outbound_writes.clear()
        for request in pending:
            request.result = False
            request.completed.set()

    def _start_callback_dispatcher(self) -> None:
        with self._callback_condition:
            self._callback_shutdown = False
        self._callback_thread = threading.Thread(
            target=self._run_callback_dispatcher,
            name="robot-runtime-observers",
            daemon=True,
        )
        self._callback_thread.start()

    def _stop_callback_dispatcher(self) -> None:
        with self._callback_condition:
            self._callback_shutdown = True
            self._callback_condition.notify_all()
        thread = self._callback_thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._callback_thread = None

    def _run_callback_dispatcher(self) -> None:
        while True:
            with self._callback_condition:
                while (
                    not self._callback_queue
                    and not self._reliable_callback_queue
                    and not self._callback_shutdown
                ):
                    self._callback_condition.wait()
                if (
                    not self._callback_queue
                    and not self._reliable_callback_queue
                    and self._callback_shutdown
                ):
                    return
                if self._callback_queue and self._reliable_callback_queue:
                    take_reliable = self._callback_take_reliable_next
                    self._callback_take_reliable_next = not take_reliable
                else:
                    take_reliable = bool(self._reliable_callback_queue)
                callback = (
                    self._reliable_callback_queue.popleft()
                    if take_reliable
                    else self._callback_queue.popleft()
                )
            try:
                callback.operation()
            except Exception as exc:
                logger.error(
                    "Deferred runtime callback failed: name=%s type=%s",
                    callback.name,
                    type(exc).__name__,
                )

    def _defer_latest_callback(
        self,
        name: str,
        operation: Callable[[], None],
    ) -> None:
        """Publish latest-value observer state without telemetry backlog.

        This queue is intentionally limited to observational snapshots. STOP,
        emergency, fault, mission and connection transitions never enter it;
        their synchronous/owner-mailbox paths are reliable and non-dropping.
        """

        # Private-handler unit tests do not start run_forever; keep their
        # historical synchronous semantics.
        if not self._scheduler_active:
            operation()
            return
        with self._callback_condition:
            for index in range(len(self._callback_queue) - 1, -1, -1):
                if self._callback_queue[index].name == name:
                    self._callback_queue[index] = _DeferredCallback(
                        name,
                        operation,
                    )
                    self._callback_coalesced_count += 1
                    self._callback_condition.notify()
                    return
            if len(self._callback_queue) >= CALLBACK_QUEUE_SIZE:
                # Only latest-value observer types are accepted here.  This is
                # defensive; three production keys cannot reach the bound.
                replaced = self._callback_queue.popleft()
                self._callback_coalesced_count += 1
                logger.warning(
                    "Latest-value observer queue replaced oldest snapshot: "
                    "name=%s coalescedCount=%d",
                    replaced.name,
                    self._callback_coalesced_count,
                )
            self._callback_queue.append(_DeferredCallback(name, operation))
            self._callback_condition.notify()

    def _defer_reliable_callback(
        self,
        name: str,
        operation: Callable[[], None],
    ) -> None:
        """Queue a potentially control-significant callback without loss."""

        if not self._scheduler_active:
            operation()
            return
        with self._callback_condition:
            self._reliable_callback_queue.append(
                _DeferredCallback(name, operation)
            )
            backlog = len(self._reliable_callback_queue)
            self._callback_condition.notify()
        if backlog == CALLBACK_QUEUE_SIZE or (
            backlog > CALLBACK_QUEUE_SIZE
            and backlog % CALLBACK_QUEUE_SIZE == 0
        ):
            logger.warning(
                "Reliable observer backlog is growing: name=%s backlog=%d",
                name,
                backlog,
            )

    def _clear_refresh_targets(self, reason: str) -> None:
        with self._refresh_state_lock:
            self._latest_requested_target = None
            self._latest_authorized_control = None
        if self._refresh_last_skip_reason != reason:
            self._refresh_last_skip_reason = reason
            logger.debug("CONTROL refresh target cleared: reason=%s", reason)

    def _on_connected(self) -> None:
        if self._control_pending:
            self._dump_recent_control_traces("SERIAL_RECONNECT")
        self._control_pending.clear()
        self._control_acked_sequences.clear()
        self._control_last_write_completed_at = None
        self._control_last_ack_ordinal = None
        self._connection_generation += 1
        connection_generation = self._connection_generation
        # A new Serial generation may represent an ESP32 reboot. Never carry a
        # previous mission across it; only a subsequent START may arm motion.
        self._fail_closed_mission("SERIAL_CONNECTION_RESET", log=False)
        self._latest_hardware_status = None
        self._last_logged_line_values = None
        self._last_odometry_uptime_ms = None
        self._last_odometry_received_at = None
        self._last_hardware_received_at = None
        self._telemetry_recovery_generation = None
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
        logger.warning(
            "Serial connection generation ready for handshake: "
            "reconnectGeneration=%d parseErrorCount=%d",
            connection_generation,
            self._parse_error_count,
        )
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
        if not self._write_line(build_stop_command(self._sequence.next())):
            self._count_control_outcome("handshake_stop_write_failed")
            return
        self._write_line(build_hello_command(self._sequence.next()))
        self._send_encoder_zero_attempt(retry=False)
        logger.info("Serial handshake sent after mandatory STOP")

    def _send_encoder_zero_attempt(self, *, retry: bool) -> None:
        if retry:
            if not self._write_line(
                build_stop_command(self._sequence.next())
            ):
                self._count_control_outcome("zero_retry_stop_write_failed")
                return
        if not self._write_line(
            build_encoder_zero_command(self._sequence.next())
        ):
            self._count_control_outcome("zero_write_failed")
            return
        self._encoder_zero_attempts += 1
        self._encoder_zero_last_sent_at = self._clock()
        self._write_line(build_status_command(self._sequence.next()))
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

    def _handle_ack(self, command: str, sequence: int | None = None) -> None:
        normalized_command = command.upper()
        if normalized_command == "CONTROL":
            if sequence is not None:
                self._record_control_ack(sequence)
            return
        if normalized_command != "ENCODER_ZERO":
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
        # This warning-level marker is intentionally stable: the field
        # preparation command waits for it before claiming that mapping is
        # ready. The production logger defaults to WARNING, so INFO would
        # create a false-positive readiness result.
        logger.warning(
            "ESP32_HANDSHAKE_READY encoder_zero_attempt=%d",
            self._encoder_zero_attempts,
        )

    def _ignore_operating_data_until_encoder_zero(self) -> None:
        if self._encoder_zero_wait_logged:
            return
        self._encoder_zero_wait_logged = True
        logger.warning("Operating data ignored until ENCODER_ZERO ACK")

    def _handle_odometry(self, odometry: Odometry) -> None:
        if not self._encoder_zero_acknowledged:
            self._count_control_outcome("odom_before_ack")
            self._ignore_operating_data_until_encoder_zero()
            return
        self._count_control_outcome("odom")
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
        self._last_odometry_received_at = now
        decision = self._evaluate_safety(now)
        self._enforce_active_patrol_fault(decision)
        mission = self._mission.snapshot()
        with self._refresh_state_lock:
            self._latest_requested_target = mission.command
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
        odom_pose = None
        if self._encoder_pose_estimator is not None:
            odom_pose = self._encoder_pose_estimator.update(
                motion_state,
                steering_command=command.steering_deg,
                timestamp=now,
            )

        observer_generation = self._connection_generation

        def publish_odometry_state() -> None:
            if observer_generation != self._connection_generation:
                return
            self._state_store.update_odometry(odometry, motion_state)
            if odom_pose is not None:
                self._state_store.update_odom_pose(odom_pose)

        def publish_odometry_listeners() -> None:
            if observer_generation != self._connection_generation:
                return
            for listener in tuple(self._odometry_listeners):
                listener(odometry, motion_state)

        self._defer_latest_callback("odometry_state", publish_odometry_state)
        if self._odometry_listeners:
            self._defer_reliable_callback(
                "odometry_listeners",
                publish_odometry_listeners,
            )
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
                # fault=NONE stops leave no trace in _send_stop, which made
                # "commands flow but wheels stay still" undiagnosable in the
                # field. Log the gate's inputs once per closing transition.
                if self._control_gate_was_writing:
                    self._control_gate_was_writing = False
                    logger.warning(
                        "CONTROL gate closed: allowed=%s fault=%s estop=%s "
                        "authorized=%s ramp_speed=%s mission_speed=%s",
                        latest_decision.allowed,
                        latest_decision.fault,
                        current.command.emergency_stop,
                        authorized,
                        command.speed,
                        current.command.speed,
                    )
                # Name the first failing term so the census says *why*, not just
                # that it was blocked. Order matches the condition above.
                if not latest_decision.allowed:
                    self._count_control_outcome(f"unsafe:{latest_decision.fault}")
                elif current.command.emergency_stop:
                    self._count_control_outcome("estop")
                elif not authorized:
                    self._count_control_outcome("unauthorized")
                else:
                    self._count_control_outcome("zero_speed")
                self._send_stop(latest_decision.fault)
                return
            authorized_control = _AuthorizedControl(
                speed=command.speed,
                steering_deg=command.steering_deg,
                mission_generation=current.generation,
                connection_generation=self._connection_generation,
                authorized_at=self._clock(),
                one_shot=stationary_steering,
            )
            with self._refresh_state_lock:
                self._latest_authorized_control = authorized_control
            if self._scheduler_active:
                self._count_control_outcome("authorized_for_refresh")
                # Do not wait up to one full period to open a newly authorized
                # gate.  Subsequent writes remain on the fixed monotonic
                # deadline; this immediate owner-thread write only establishes
                # the first watchdog lease.
                if not self._control_gate_was_writing:
                    if not self._transmit_authorized_control(
                        authorized_control
                    ):
                        self._count_control_outcome("write_failed")
                return
            if not self._transmit_authorized_control(authorized_control):
                self._count_control_outcome("write_failed")
                logger.warning(
                    "CONTROL write failed; ESP32 watchdog will stop motors"
                )
                return
            self._count_control_outcome("wrote")
            self._stationary_steering_pending = False
            self._mark_control_gate_open(command.speed, command.steering_deg)

        if not self._mission.run_if_current(
            mission.generation,
            write_if_safe,
        ):
            self._stationary_steering_pending = False
            # Every cmd_vel bumps the mission generation. Patrol used to set it
            # once per waypoint, so losing the race was rare; Nav2 sets it at the
            # controller rate, so this exit can dominate and it wrote no log.
            self._count_control_outcome("mission_changed")
            self._clear_refresh_targets("MISSION_CHANGED_BEFORE_CONTROL")
            self._send_stop("MISSION_CHANGED_BEFORE_CONTROL")

    def _mark_control_gate_open(self, speed: int, steering_deg: int) -> None:
        if self._control_gate_was_writing:
            return
        self._control_gate_was_writing = True
        # WARNING on purpose: production currently hides INFO records.
        logger.warning(
            "CONTROL gate open: speed=%s steering=%s",
            speed,
            steering_deg,
        )

    def _transmit_authorized_control(
        self,
        target: _AuthorizedControl,
    ) -> bool:
        delivered = self._write_instrumented_control(
            target.speed,
            target.steering_deg,
        )
        if delivered:
            with self._refresh_state_lock:
                self._last_transmitted_control = target
                if target.one_shot:
                    self._latest_authorized_control = None
            self._stationary_steering_pending = False
            self._mark_control_gate_open(target.speed, target.steering_deg)
        return delivered

    def _service_control_refresh(self) -> None:
        """Run at most one monotonic deadline; never catch up with a burst."""

        if not self._scheduler_active:
            return
        now = self._clock()
        deadline = self._next_control_deadline
        interval = self._settings.control_refresh_interval_sec
        if deadline is None:
            self._next_control_deadline = now + interval
            return
        if now < deadline:
            return
        self._next_control_deadline = deadline + interval
        while self._next_control_deadline <= now:
            self._next_control_deadline += interval

        lateness = max(0.0, now - deadline)
        generation_gap = (
            None
            if self._last_refresh_actual_at is None
            else now - self._last_refresh_actual_at
        )
        self._last_refresh_actual_at = now
        self._refresh_count += 1
        self._refresh_max_lateness_sec = max(
            self._refresh_max_lateness_sec,
            lateness,
        )
        if generation_gap is not None:
            self._refresh_max_generation_gap_sec = max(
                self._refresh_max_generation_gap_sec,
                generation_gap,
            )
        inbound_count = self._inbound_processed_since_refresh
        inbound_started = self._inbound_budget_started_at
        inbound_elapsed = (
            0.0 if inbound_started is None else max(0.0, now - inbound_started)
        )
        self._inbound_processed_since_refresh = 0
        self._inbound_budget_started_at = now

        if lateness >= CONTROL_REFRESH_LATE_DETAIL_SEC:
            print(
                "[CONTROL REFRESH DETAIL] "
                f"scheduledDeadlineMono={deadline:.6f} "
                f"actualRefreshMono={now:.6f} "
                f"refreshLatenessMs={self._milliseconds(lateness)} "
                f"generationGapMs={self._milliseconds(generation_gap)} "
                f"inboundProcessed={inbound_count} "
                f"inboundBudgetMs={self._milliseconds(inbound_elapsed)}",
                flush=True,
            )
        self._attempt_control_refresh(deadline, now)

    def _attempt_control_refresh(self, deadline: float, now: float) -> None:
        with self._refresh_state_lock:
            target = self._latest_authorized_control
        mission = self._mission.snapshot()
        decision = self._safety.evaluate(
            now=now,
            connected=self._bridge.is_connected(),
            hardware_status=self._latest_hardware_status,
            emergency_stop=mission.command.emergency_stop,
        )
        self._defer_latest_callback(
            "safety",
            lambda decision=decision: self._state_store.update_safety(decision),
        )

        reason = self._refresh_rejection_reason(target, mission, decision)
        if reason is not None:
            self._reject_control_refresh(reason, decision)
            return
        assert target is not None
        delivered = False

        def transmit_if_still_current(current: MissionSnapshot) -> None:
            nonlocal delivered
            with self._refresh_state_lock:
                latest = self._latest_authorized_control
            latest_decision = self._safety.evaluate(
                now=self._clock(),
                connected=self._bridge.is_connected(),
                hardware_status=self._latest_hardware_status,
                emergency_stop=current.command.emergency_stop,
            )
            if (
                latest != target
                or not latest_decision.allowed
                or not current.patrol_active and not self._manual_motion_active
                or current.command.emergency_stop
                or self._connection_generation != target.connection_generation
                or not self._encoder_zero_acknowledged
                or self._odometry_baseline_pending
            ):
                return
            delivered = self._transmit_authorized_control(target)

        generation_current = self._mission.run_if_current(
            target.mission_generation,
            transmit_if_still_current,
        )
        if not generation_current or not delivered:
            self._reject_control_refresh("STATE_CHANGED_DURING_REFRESH", decision)
            return
        self._refresh_last_skip_reason = None
        self._count_control_outcome("refreshed")

    def _refresh_rejection_reason(
        self,
        target: _AuthorizedControl | None,
        mission: MissionSnapshot,
        decision: SafetyDecision,
    ) -> str | None:
        if not self._bridge.is_connected():
            return "SERIAL_DISCONNECTED"
        if not self._encoder_zero_acknowledged:
            return "HANDSHAKE_NOT_READY"
        if self._odometry_baseline_pending:
            return "FRESH_TELEMETRY_NOT_READY"
        if not decision.allowed:
            return decision.fault
        if mission.command.emergency_stop:
            return "EMERGENCY_STOP"
        if not (mission.patrol_active or self._manual_motion_active):
            return "MOTION_UNAUTHORIZED"
        if target is None:
            return "AUTHORIZED_TARGET_NOT_READY"
        if target.connection_generation != self._connection_generation:
            return "STALE_CONNECTION_GENERATION"
        if target.mission_generation != mission.generation:
            return "STALE_MISSION_GENERATION"
        # A speed/steering update inside the same mission does not revoke the
        # watchdog lease of the last owner-authorised target.  The next
        # ODOMETRY cycle authorises and replaces it.  Lifecycle epoch,
        # connection generation, emergency, STOP and safety checks above still
        # invalidate old CONTROL immediately.
        return None

    def _reject_control_refresh(
        self,
        reason: str,
        decision: SafetyDecision,
    ) -> None:
        self._refresh_skip_count += 1
        changed = reason != self._refresh_last_skip_reason
        self._refresh_last_skip_reason = reason
        if changed and reason not in {
            "HANDSHAKE_NOT_READY",
            "FRESH_TELEMETRY_NOT_READY",
            "AUTHORIZED_TARGET_NOT_READY",
            "MOTION_UNAUTHORIZED",
        }:
            logger.warning(
                "CONTROL refresh rejected: reason=%s "
                "reconnectGeneration=%d",
                reason,
                self._connection_generation,
            )
        if decision.fault in ACTIVE_PATROL_FAULTS:
            self._enforce_active_patrol_fault(decision)
            return
        # Once the gate has emitted motion, every authorization/generation
        # rejection is linearized as STOP.  Idle preflight skips remain quiet.
        if self._control_gate_was_writing:
            self._control_gate_was_writing = False
            self._clear_refresh_targets(reason)
            self._send_stop(reason)

    def _write_instrumented_control(self, speed: int, steering_deg: int) -> bool:
        """Write one CONTROL and retain bounded, schema-neutral timing data."""

        sequence = self._sequence.next()
        generated_at = self._clock()
        write_started_at = self._clock()
        write_ok = self._write_line(
            build_control_command(
                speed,
                steering_deg,
                sequence,
                self._protocol_settings,
            )
        )
        write_completed_at = self._clock()
        write_duration_sec = write_completed_at - write_started_at
        send_gap_sec = (
            None
            if self._control_last_write_completed_at is None
            else write_completed_at - self._control_last_write_completed_at
        )
        self._control_last_write_completed_at = write_completed_at
        self._control_trace_ordinal += 1
        trace = _ControlTrace(
            ordinal=self._control_trace_ordinal,
            sequence=sequence,
            connection_generation=self._connection_generation,
            generated_at=generated_at,
            write_started_at=write_started_at,
            write_completed_at=write_completed_at,
            write_ok=write_ok,
            send_gap_sec=send_gap_sec,
            write_duration_sec=write_duration_sec,
        )
        self._control_trace_ring.append(trace)
        self._control_generated_count += 1
        self._control_write_durations_sec.append(write_duration_sec)
        if self._control_metrics_started_at is None:
            self._control_metrics_started_at = generated_at
        if send_gap_sec is not None:
            self._control_max_send_gap_sec = max(
                self._control_max_send_gap_sec,
                send_gap_sec,
            )
        if write_ok:
            self._control_write_count += 1
            self._control_pending[sequence] = trace
        if (
            (send_gap_sec or 0.0) >= CONTROL_SEQUENCE_DETAIL_THRESHOLD_SEC
            or write_duration_sec >= CONTROL_SEQUENCE_DETAIL_THRESHOLD_SEC
        ):
            print(
                "[CONTROL SEQUENCE DETAIL] "
                f"sequence={sequence} generation={self._connection_generation} "
                f"sendGapMs={self._milliseconds(send_gap_sec)} "
                f"writeDurationMs={self._milliseconds(write_duration_sec)} "
                f"writeOk={write_ok}",
                flush=True,
            )
        self._maybe_emit_control_sequence_census(write_completed_at)
        return write_ok

    def _record_control_ack(self, sequence: int) -> None:
        now = self._clock()
        if sequence in self._control_acked_sequences:
            self._control_duplicate_ack_count += 1
            print(
                "[CONTROL ACK DETAIL] "
                f"sequence={sequence} duplicate=true "
                f"generation={self._connection_generation}",
                flush=True,
            )
            return
        trace = self._control_pending.pop(sequence, None)
        self._control_acked_sequences.append(sequence)
        if trace is None:
            self._control_orphan_ack_count += 1
            print(
                "[CONTROL ACK DETAIL] "
                f"sequence={sequence} orphan=true "
                f"generation={self._connection_generation}",
                flush=True,
            )
            return
        trace.ack_received_at = now
        trace.ack_latency_sec = now - trace.write_completed_at
        self._control_ack_count += 1
        self._control_ack_latencies_sec.append(trace.ack_latency_sec)
        if (
            self._control_last_ack_ordinal is not None
            and trace.ordinal < self._control_last_ack_ordinal
        ):
            self._control_out_of_order_ack_count += 1
            print(
                "[CONTROL ACK DETAIL] "
                f"sequence={sequence} outOfOrder=true "
                f"ordinal={trace.ordinal} "
                f"lastAckOrdinal={self._control_last_ack_ordinal}",
                flush=True,
            )
        self._control_last_ack_ordinal = max(
            trace.ordinal,
            self._control_last_ack_ordinal or trace.ordinal,
        )
        if trace.ack_latency_sec >= CONTROL_SEQUENCE_DETAIL_THRESHOLD_SEC:
            print(
                "[CONTROL ACK DETAIL] "
                f"sequence={sequence} "
                f"ackLatencyMs={self._milliseconds(trace.ack_latency_sec)} "
                f"generation={trace.connection_generation}",
                flush=True,
            )
        self._maybe_emit_control_sequence_census(now)

    def _mark_control_ack_misses(self, now: float) -> None:
        for trace in self._control_pending.values():
            if (
                not trace.ack_missed
                and now - trace.write_completed_at >= CONTROL_ACK_MISS_THRESHOLD_SEC
            ):
                trace.ack_missed = True
                self._control_ack_miss_count += 1
                print(
                    "[CONTROL ACK DETAIL] "
                    f"sequence={trace.sequence} ackMissing=true "
                    f"ageMs={self._milliseconds(now - trace.write_completed_at)} "
                    f"generation={trace.connection_generation}",
                    flush=True,
                )

    def _maybe_emit_control_sequence_census(self, now: float) -> None:
        started_at = self._control_metrics_started_at
        if started_at is None:
            return
        self._mark_control_ack_misses(now)
        elapsed = now - started_at
        if elapsed < CONTROL_SEQUENCE_CENSUS_INTERVAL_SEC:
            return
        generation_rate = self._control_generated_count / elapsed
        write_rate = self._control_write_count / elapsed
        ack_rate = self._control_ack_count / elapsed
        print(
            "[CONTROL SEQUENCE CENSUS] "
            f"elapsedSec={elapsed:.3f} "
            f"generationRateHz={generation_rate:.3f} "
            f"writeRateHz={write_rate:.3f} "
            f"ackRateHz={ack_rate:.3f} "
            f"maxSendGapMs={self._milliseconds(self._control_max_send_gap_sec)} "
            f"writeP95Ms={self._percentile_ms(self._control_write_durations_sec, 0.95)} "
            f"writeP99Ms={self._percentile_ms(self._control_write_durations_sec, 0.99)} "
            f"writeMaxMs={self._maximum_ms(self._control_write_durations_sec)} "
            f"ackP95Ms={self._percentile_ms(self._control_ack_latencies_sec, 0.95)} "
            f"ackP99Ms={self._percentile_ms(self._control_ack_latencies_sec, 0.99)} "
            f"ackMaxMs={self._maximum_ms(self._control_ack_latencies_sec)} "
            f"ackMiss={self._control_ack_miss_count} "
            f"duplicate={self._control_duplicate_ack_count} "
            f"outOfOrder={self._control_out_of_order_ack_count} "
            f"orphan={self._control_orphan_ack_count} "
            f"pending={len(self._control_pending)} "
            f"reconnectGeneration={self._connection_generation}",
            flush=True,
        )
        self._control_metrics_started_at = now
        self._control_generated_count = 0
        self._control_write_count = 0
        self._control_ack_count = 0

    def _dump_recent_control_traces(self, reason: str) -> None:
        now = self._clock()
        self._mark_control_ack_misses(now)
        traces = " | ".join(
            (
                f"seq={trace.sequence},gen={trace.connection_generation},"
                f"generatedAtMonoSec={trace.generated_at:.6f},"
                f"writeStartMonoSec={trace.write_started_at:.6f},"
                f"writeCompleteMonoSec={trace.write_completed_at:.6f},"
                f"sendGapMs={self._milliseconds(trace.send_gap_sec)},"
                f"writeMs={self._milliseconds(trace.write_duration_sec)},"
                f"writeOk={trace.write_ok},"
                f"ackAtMonoSec="
                f"{('NA' if trace.ack_received_at is None else f'{trace.ack_received_at:.6f}')},"
                f"ackMs={self._milliseconds(trace.ack_latency_sec)},"
                f"ackMissed={trace.ack_missed}"
            )
            for trace in self._control_trace_ring
        )
        print(
            f"[CONTROL SEQUENCE RING] reason={reason} recent={traces or 'empty'}",
            flush=True,
        )

    @staticmethod
    def _milliseconds(value: float | None) -> str:
        return "NA" if value is None else f"{value * 1000.0:.3f}"

    @classmethod
    def _percentile_ms(cls, values: deque[float], quantile: float) -> str:
        if not values:
            return "NA"
        ordered = sorted(values)
        index = max(
            0,
            min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1),
        )
        return cls._milliseconds(ordered[index])

    @classmethod
    def _maximum_ms(cls, values: deque[float]) -> str:
        return "NA" if not values else cls._milliseconds(max(values))

    def _count_control_outcome(self, outcome: str) -> None:
        """Tally every control-loop exit and summarise on a fixed interval.

        The transition logs above only fire when the gate *changes* state, so a
        gate that never opens once produces no output at all -- which is exactly
        the "commands flow but the wheels never turn" case that took a full field
        session to narrow down. A census is unconditional, so silence here now
        means the loop is not running rather than the loop declining to write.

        Rate-limited because the loop runs at the controller frequency: a line
        per iteration would bury the journal at 20 Hz.
        """

        now = self._clock()
        self._maybe_emit_control_sequence_census(now)
        if self._control_census_started_at is None:
            self._control_census_started_at = now
        self._control_census[outcome] = self._control_census.get(outcome, 0) + 1
        elapsed = now - self._control_census_started_at
        if elapsed < CONTROL_CENSUS_INTERVAL_SEC:
            return
        self._control_census_started_at = now
        census = self._control_census
        self._control_census = {}
        # print, not logger: the field journal for this service contains 4,299
        # lines and not one of them came from a ``logger`` call, while every
        # ``print`` shows up. Until that is understood, a diagnostic that has to
        # be readable must not depend on the logging configuration.
        print(
            f"[RUNTIME CENSUS] {elapsed:.0f}s "
            + " ".join(f"{name}={count}" for name, count in sorted(census.items()))
            + " "
            + (
                "lastOdometryAgeMs="
                f"{self._telemetry_age_ms(now, self._last_odometry_received_at)} "
                "lastHardwareAgeMs="
                f"{self._telemetry_age_ms(now, self._last_hardware_received_at)} "
                f"reconnectGeneration={self._connection_generation} "
                f"parseErrorCount={self._parse_error_count} "
                f"refreshCount={self._refresh_count} "
                f"refreshSkipped={self._refresh_skip_count} "
                "maxGenerationGapMs="
                f"{self._milliseconds(self._refresh_max_generation_gap_sec)} "
                "maxRefreshLatenessMs="
                f"{self._milliseconds(self._refresh_max_lateness_sec)}"
            ),
            flush=True,
        )

    def _drain_motion_requests(self) -> bool:
        """Apply cross-thread manual requests only on the Serial owner thread."""

        mission_changed = False
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
                requested_command = MissionCommand(
                    request.speed,
                    request.steering_deg,
                )
                current = self._mission.snapshot()
                duplicate_active_target = (
                    self._manual_motion_active
                    and current.command == requested_command
                    and self._stationary_steering_pending
                    == request.stationary_steering
                )
                if not duplicate_active_target:
                    self._mission.submit(requested_command)
                    mission_changed = True
                self._manual_motion_active = True
                self._stationary_steering_pending = (
                    request.stationary_steering
                )
        if stop_steering is not None:
            self._send_stop("MANUAL_STOP")
            return True
        if request is None:
            return False
        # A newly applied target invalidates the mission snapshot already
        # calculated by _handle_odometry(), so that cycle must stop here.
        # Identical gamepad refreshes keep the generation unchanged and may
        # continue to the CONTROL write; otherwise a 20 Hz input loop can
        # starve a similarly paced odometry loop forever.
        return mission_changed

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
            with self._refresh_state_lock:
                self._latest_requested_target = None
                self._latest_authorized_control = None
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
        self._last_hardware_received_at = now

        observer_generation = self._connection_generation

        def publish_hardware_state() -> None:
            if observer_generation != self._connection_generation:
                return
            self._state_store.update_hardware_status(hardware_status)

        def publish_hardware_listeners() -> None:
            if observer_generation != self._connection_generation:
                return
            for listener in tuple(self._hardware_status_listeners):
                listener(hardware_status)

        self._defer_latest_callback(
            "hardware_state",
            publish_hardware_state,
        )
        if self._hardware_status_listeners:
            self._defer_reliable_callback(
                "hardware_listeners",
                publish_hardware_listeners,
            )
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
        self._defer_latest_callback(
            "safety",
            lambda decision=decision: self._state_store.update_safety(decision),
        )
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
        self._recover_silent_connection(decision.fault)

    def _recover_silent_connection(self, reason: str) -> None:
        """Close one silent transport per generation after best-effort STOP."""

        if reason not in {"ODOMETRY_TIMEOUT", "HARDWARE_STATUS_TIMEOUT"}:
            return
        generation = self._connection_generation
        if self._telemetry_recovery_generation == generation:
            return
        self._telemetry_recovery_generation = generation
        now = self._clock()
        logger.warning(
            "Serial telemetry timeout; forcing reconnect: reason=%s "
            "lastOdometryAgeMs=%d lastHardwareAgeMs=%d "
            "reconnectGeneration=%d parseErrorCount=%d",
            reason,
            self._telemetry_age_ms(now, self._last_odometry_received_at),
            self._telemetry_age_ms(now, self._last_hardware_received_at),
            generation,
            self._parse_error_count,
        )
        self._bridge.close()

    @staticmethod
    def _telemetry_age_ms(now: float, received_at: float | None) -> int:
        if received_at is None:
            return -1
        return max(0, int((now - received_at) * 1000))

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
                    self._write_line(
                        build_stop_command(self._sequence.next()),
                        priority=True,
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
