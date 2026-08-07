"""ROS 2 Nav2 action and ``cmd_vel`` bridge for the Ackermann robot.

This component never opens the ESP32 serial port.  It translates Nav2 output
and delegates the resulting bounded target to the one RobotRuntime owner.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from navigation.cmd_vel_adapter import (
    AckermannCommandSettings,
    CmdVelCommand,
    CmdVelToEsp32Adapter,
)


MotionSink = Callable[[CmdVelCommand], None]
FailureSink = Callable[[str], None]
ObstacleSink = Callable[[str], None]
ScanContextSink = Callable[[Any | None], None]
HeadingSource = Callable[[], float | None]
TimerFactory = Callable[[float, Callable[[], None]], Any]
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RosNav2BridgeSettings:
    ackermann: AckermannCommandSettings
    cmd_vel_topic: str = "/cmd_vel"
    navigate_action: str = "/navigate_to_pose"
    map_frame: str = "map"
    scan_dwell_sec: float = 3.0
    cmd_vel_timeout_sec: float = 3.0
    initial_pose_topic: str = "/initialpose"
    initial_pose_settle_sec: float = 1.0
    first_goal_accept_timeout_sec: float = 5.0
    # Nav2 aborts the goal when the controller sees an obstacle on the path.
    # That is recoverable: hold position and let the obstacle-clear loop resume
    # the same waypoint.  Only give up once the same waypoint keeps aborting
    # without ever moving, which means waiting will not clear it.
    goal_abort_retry_limit: int = 3

    def __post_init__(self) -> None:
        for name, value in (
            ("cmd_vel_topic", self.cmd_vel_topic),
            ("navigate_action", self.navigate_action),
            ("map_frame", self.map_frame),
            ("initial_pose_topic", self.initial_pose_topic),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if (
            not math.isfinite(self.scan_dwell_sec)
            or not 0.1 <= self.scan_dwell_sec <= 60.0
        ):
            raise ValueError("scan_dwell_sec must be within 0.1..60.0 seconds")
        if (
            not math.isfinite(self.cmd_vel_timeout_sec)
            or not 0.2 <= self.cmd_vel_timeout_sec <= 5.0
        ):
            raise ValueError(
                "cmd_vel_timeout_sec must be within 0.2..5.0 seconds"
            )
        if (
            not math.isfinite(self.initial_pose_settle_sec)
            or not 0.1 <= self.initial_pose_settle_sec <= 3.0
        ):
            raise ValueError(
                "initial_pose_settle_sec must be within 0.1..3.0 seconds"
            )
        if (
            not math.isfinite(self.first_goal_accept_timeout_sec)
            or not 0.5 <= self.first_goal_accept_timeout_sec <= 15.0
        ):
            raise ValueError(
                "first_goal_accept_timeout_sec must be within 0.5..15.0 seconds"
            )
        if not 1 <= self.goal_abort_retry_limit <= 20:
            raise ValueError("goal_abort_retry_limit must be within 1..20")


class RosNav2Bridge:
    """Own the Nav2 ROS node while RobotRuntime remains the serial owner."""

    def __init__(
        self,
        *,
        settings: RosNav2BridgeSettings,
        motion_sink: MotionSink,
        failure_sink: FailureSink | None = None,
        obstacle_sink: ObstacleSink | None = None,
        scan_context_sink: ScanContextSink | None = None,
        heading_source: HeadingSource | None = None,
        timer_factory: TimerFactory = threading.Timer,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._adapter = CmdVelToEsp32Adapter(settings.ackermann)
        self._motion_sink = motion_sink
        self._failure_sink = failure_sink
        self._obstacle_sink = obstacle_sink
        self._scan_context_sink = scan_context_sink
        self._heading_source = heading_source
        self._timer_factory = timer_factory
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_started = False
        self._route: Any = None
        self._current_sequence: int | None = None
        self._paused = False
        self._goal_handle: Any = None
        self._goal_generation = 0
        self._cmd_vel_hold_reason: str | None = None
        self._last_cmd_vel_at: float | None = None
        self._scan_timer: Any = None
        self._scan_generation = 0
        self._pending_scan: tuple[int, int] | None = None
        self._patrol_failure_reported = False
        self._goal_aborts_at_sequence = 0
        self._first_goal_event = threading.Event()
        self._first_goal_failure: str | None = None
        self._first_goal_pending = False
        self._node: Any = None
        self._executor: Any = None
        self._action_client: Any = None
        self._subscription: Any = None
        self._initial_pose_publisher: Any = None
        self._rclpy: Any = None
        self._navigate_type: Any = None
        self._pose_type: Any = None
        self._initial_pose_type: Any = None
        self._owns_rclpy_context = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        try:
            import rclpy
            from geometry_msgs.msg import (
                PoseStamped,
                PoseWithCovarianceStamped,
                Twist,
            )
            from nav2_msgs.action import NavigateToPose
            from rclpy.action import ActionClient
            from rclpy.executors import SingleThreadedExecutor
        except ImportError as exc:
            raise RuntimeError(
                "Nav2 mode requires rclpy, geometry_msgs and nav2_msgs"
            ) from exc

        self._rclpy = rclpy
        self._owns_rclpy_context = not rclpy.ok()
        if self._owns_rclpy_context:
            rclpy.init(args=None)
        try:
            self._navigate_type = NavigateToPose
            self._pose_type = PoseStamped
            self._initial_pose_type = PoseWithCovarianceStamped
            self._node = rclpy.create_node("roki_nav2_bridge")
            self._action_client = ActionClient(
                self._node,
                NavigateToPose,
                self._settings.navigate_action,
            )
            self._subscription = self._node.create_subscription(
                Twist,
                self._settings.cmd_vel_topic,
                self._on_cmd_vel,
                10,
            )
            self._initial_pose_publisher = self._node.create_publisher(
                PoseWithCovarianceStamped,
                self._settings.initial_pose_topic,
                10,
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._spin,
                name="ros-nav2-bridge",
                daemon=True,
            )
            self._thread.start()
            self._thread_started = True
        except Exception:
            self._cleanup_ros()
            raise

    def stop(self) -> None:
        self.stop_patrol()
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._thread_started = False
        self._cleanup_ros()

    def is_ready(self) -> tuple[bool, str]:
        if self._thread is None or not self._thread.is_alive():
            return False, "NAV2_BRIDGE_NOT_RUNNING"
        if self._action_client is None or not self._action_client.server_is_ready():
            return False, "NAV2_ACTION_SERVER_NOT_READY"
        return True, "READY"

    def start_patrol(self, *, route: Any, first_event: Any) -> None:
        ready, reason = self.is_ready()
        if not ready:
            raise RuntimeError(reason)
        with self._lock:
            stale_timer = self._cancel_scan_dwell_locked()
            stale_handle = self._invalidate_goal_locked()
            self._route = route
            self._paused = False
            self._current_sequence = 1
            self._last_cmd_vel_at = None
            self._patrol_failure_reported = False
            self._goal_aborts_at_sequence = 0
            self._first_goal_event.clear()
            self._first_goal_failure = None
            self._first_goal_pending = True
        if stale_timer is not None:
            stale_timer.cancel()
        self._cancel_goal_best_effort(stale_handle)
        self._publish_scan_context(None)
        first_waypoint = getattr(first_event.mission_event, "waypoint", None)
        if first_waypoint is None or int(first_waypoint.sequence) != 1:
            self._fail("NAV2_START_ANCHOR_INVALID")
            raise RuntimeError("NAV2_START_ANCHOR_INVALID")
        # Waypoint 1 used to be force-fed to AMCL over /initialpose here, which
        # teleported the belief to wherever the route said the robot was. That is
        # exactly backwards: localization must come from the map and the scans,
        # not from the route. AMCL is seeded once at startup with the dock pose
        # (map origin -- mapping and patrol start from the same marked spot) and
        # scan-matching owns the estimate from then on. Waypoint 1 stays the
        # protocol anchor the outer service confirms; place it at the dock.

    def wait_for_first_goal_acceptance(self) -> None:
        """Wait until the first post-anchor Nav2 goal is accepted."""

        if not self._first_goal_event.wait(
            timeout=self._settings.first_goal_accept_timeout_sec
        ):
            self._fail("NAV2_FIRST_GOAL_ACCEPT_TIMEOUT")
        with self._lock:
            first_goal_failure = self._first_goal_failure
        if first_goal_failure is not None:
            raise RuntimeError(first_goal_failure)

    def stop_patrol(self) -> None:
        with self._lock:
            timer = self._cancel_scan_dwell_locked()
            handle = self._invalidate_goal_locked()
            self._route = None
            self._current_sequence = None
            self._paused = False
            self._cmd_vel_hold_reason = "NAV2_PATROL_STOPPED"
            self._last_cmd_vel_at = None
            self._patrol_failure_reported = True
            if not self._first_goal_event.is_set():
                self._first_goal_failure = "NAV2_PATROL_STOPPED_DURING_START"
                self._first_goal_pending = False
                self._first_goal_event.set()
        if timer is not None:
            timer.cancel()
        self._motion_sink(CmdVelCommand(0, 80, "NAV2_PATROL_STOPPED"))
        self._cancel_goal_best_effort(handle)
        self._publish_scan_context(None)

    def pause_patrol(self) -> None:
        with self._lock:
            timer = self._cancel_scan_dwell_locked(clear_pending=False)
            self._paused = True
            handle = self._invalidate_goal_locked()
            self._cmd_vel_hold_reason = "OBSTACLE"
            self._last_cmd_vel_at = None
        if timer is not None:
            timer.cancel()
        self._motion_sink(CmdVelCommand(0, 80, "OBSTACLE"))
        self._cancel_goal_best_effort(handle)
        self._publish_scan_context(None)

    def resume_patrol(self) -> None:
        with self._lock:
            sequence = self._current_sequence
            pending_scan = self._pending_scan
            self._paused = False
        if pending_scan is not None:
            self._schedule_scan_dwell(*pending_scan)
        elif sequence is not None:
            self._send_sequence(sequence)

    def on_navigation_event(self, event: Any) -> None:
        event_type = getattr(event.mission_event.event_type, "value", "")
        waypoint = getattr(event.mission_event, "waypoint", None)
        if event_type == "DESTINATION_REACHED":
            return
        if event_type != "WAYPOINT_REACHED" or waypoint is None:
            return
        action = getattr(getattr(waypoint, "action", None), "value", "")
        if action == "SCAN":
            self._begin_scan_dwell(waypoint)
            return
        next_sequence = int(waypoint.sequence) + 1
        with self._lock:
            route = self._route
            paused = self._paused
            if route is None or next_sequence > len(route.waypoints):
                return
            self._current_sequence = next_sequence
            # Reaching a waypoint proves the blockage cleared, so the next
            # waypoint starts with a full abort-retry budget.
            self._goal_aborts_at_sequence = 0
        if not paused:
            self._send_sequence(next_sequence)

    def _begin_scan_dwell(self, waypoint: Any) -> None:
        sequence = int(waypoint.sequence)
        next_sequence = sequence + 1
        self._schedule_scan_dwell(sequence, next_sequence)

    def _schedule_scan_dwell(
        self,
        scan_sequence: int,
        next_sequence: int,
    ) -> None:
        with self._lock:
            if (
                self._paused
                or self._route is None
                or self._current_sequence != scan_sequence
                or next_sequence > len(self._route.waypoints)
            ):
                return
            stale_timer = self._cancel_scan_dwell_locked()
            stale_handle = self._invalidate_goal_locked()
            generation = self._scan_generation
            self._pending_scan = (scan_sequence, next_sequence)
            scan_waypoint = self._route.waypoints[scan_sequence - 1]
            self._cmd_vel_hold_reason = "SCAN_DWELL"
            timer = self._timer_factory(
                self._settings.scan_dwell_sec,
                lambda: self._finish_scan_dwell(
                    generation=generation,
                    scan_sequence=scan_sequence,
                    next_sequence=next_sequence,
                ),
            )
            if hasattr(timer, "daemon"):
                timer.daemon = True
            self._scan_timer = timer
        if stale_timer is not None:
            stale_timer.cancel()
        self._motion_sink(
            CmdVelCommand(
                0,
                self._settings.ackermann.steering_center_deg,
                "SCAN_DWELL",
            )
        )
        self._cancel_goal_best_effort(stale_handle)
        self._publish_scan_context(scan_waypoint)
        timer.start()

    def _finish_scan_dwell(
        self,
        *,
        generation: int,
        scan_sequence: int,
        next_sequence: int,
    ) -> None:
        with self._lock:
            if (
                generation != self._scan_generation
                or self._scan_timer is None
                or self._paused
                or self._route is None
                or self._current_sequence != scan_sequence
            ):
                return
            self._scan_timer = None
            self._pending_scan = None
            self._current_sequence = next_sequence
        self._publish_scan_context(None)
        self._send_sequence(next_sequence)

    def _cancel_scan_dwell_locked(self, *, clear_pending: bool = True) -> Any:
        timer = self._scan_timer
        self._scan_timer = None
        self._scan_generation += 1
        if clear_pending:
            self._pending_scan = None
        return timer

    def _invalidate_goal_locked(self) -> Any:
        handle = self._goal_handle
        self._goal_handle = None
        self._goal_generation += 1
        self._last_cmd_vel_at = None
        return handle

    @staticmethod
    def _cancel_goal_best_effort(handle: Any) -> None:
        if handle is None:
            return
        try:
            handle.cancel_goal_async()
        except Exception as exc:
            LOGGER.warning("Nav2 goal cancellation failed: %s", type(exc).__name__)

    def check_health(self) -> bool:
        """Fail an active patrol if its Nav2 bridge or cmd_vel stream died."""

        reason = self._health_failure_reason(check_thread=True)
        if reason is None:
            return True
        self._fail(reason)
        return False

    def _health_failure_reason(self, *, check_thread: bool) -> str | None:
        with self._lock:
            active = self._route is not None and not self._paused
            if not active or self._patrol_failure_reported:
                return None
            if check_thread and self._thread_started:
                thread = self._thread
                if thread is None or not thread.is_alive():
                    return "NAV2_BRIDGE_THREAD_DEAD"
            if not self._cmd_vel_watchdog_armed_locked():
                return None
            last_cmd_vel_at = self._last_cmd_vel_at
            if last_cmd_vel_at is None:
                return "NAV2_CMD_VEL_TIMEOUT"
            if (
                self._clock() - last_cmd_vel_at
                > self._settings.cmd_vel_timeout_sec
            ):
                return "NAV2_CMD_VEL_TIMEOUT"
        return None

    def _cmd_vel_watchdog_armed_locked(self) -> bool:
        return (
            self._route is not None
            and not self._paused
            and self._pending_scan is None
            and self._goal_handle is not None
            and self._cmd_vel_hold_reason is None
        )

    def record_cmd_vel(
        self, linear_x_mps: float, angular_z_radps: float
    ) -> CmdVelCommand:
        """Pure test boundary shared with the ROS callback."""

        command = self._adapter.convert(linear_x_mps, angular_z_radps)
        with self._lock:
            hold_reason = self._cmd_vel_hold_reason
            if self._cmd_vel_watchdog_armed_locked():
                self._last_cmd_vel_at = self._clock()
        if hold_reason is not None and command.speed_pwm != 0:
            command = CmdVelCommand(
                0,
                self._settings.ackermann.steering_center_deg,
                hold_reason,
            )
        self._motion_sink(command)
        return command

    def _on_cmd_vel(self, message: Any) -> None:
        try:
            self.record_cmd_vel(float(message.linear.x), float(message.angular.z))
        except (TypeError, ValueError) as exc:
            self._fail(f"NAV2_CMD_VEL_INVALID:{exc}")

    def _send_sequence(self, sequence: int) -> None:
        with self._lock:
            if self._paused or self._route is None or self._pending_scan is not None:
                return
            waypoint = self._route.waypoints[sequence - 1]
            route = self._route
            stale_handle = self._invalidate_goal_locked()
            generation = self._goal_generation
            self._cmd_vel_hold_reason = "NAV2_GOAL_PENDING"
            self._last_cmd_vel_at = None
        self._cancel_goal_best_effort(stale_handle)
        try:
            yaw_deg = self._resolve_goal_yaw_deg(route, sequence)
        except (TypeError, ValueError) as exc:
            self._fail(f"NAV2_GOAL_YAW_UNRESOLVABLE:{exc}")
            return
        assert self._navigate_type is not None
        assert self._pose_type is not None
        assert self._node is not None
        goal = self._navigate_type.Goal()
        pose = self._pose_type()
        pose.header.frame_id = self._settings.map_frame
        pose.header.stamp = self._node.get_clock().now().to_msg()
        pose.pose.position.x = float(waypoint.x)
        pose.pose.position.y = float(waypoint.y)
        yaw = math.radians(yaw_deg)
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        goal.pose = pose
        try:
            future = self._action_client.send_goal_async(goal)
        except Exception as exc:
            self._fail(f"NAV2_GOAL_SEND_ERROR:{type(exc).__name__}")
            return
        future.add_done_callback(
            lambda completed: self._on_goal_response(completed, generation)
        )

    def _on_goal_response(self, future: Any, generation: int) -> None:
        try:
            handle = future.result()
            with self._lock:
                stale = (
                    generation != self._goal_generation
                    or self._paused
                    or self._route is None
                    or self._pending_scan is not None
                )
            if stale:
                if handle is not None and getattr(handle, "accepted", False):
                    self._cancel_goal_best_effort(handle)
                return
            if handle is None or not handle.accepted:
                self._fail("NAV2_GOAL_REJECTED")
                return
            with self._lock:
                if generation != self._goal_generation:
                    stale = True
                else:
                    stale = False
                    self._goal_handle = handle
                    self._cmd_vel_hold_reason = None
                    # Start the first-message deadline when Nav2 accepts the
                    # goal. Subsequent zero or non-zero cmd_vel messages both
                    # prove the controller/velocity-smoother chain is alive.
                    self._last_cmd_vel_at = self._clock()
                    if self._first_goal_pending:
                        self._first_goal_pending = False
                        self._first_goal_failure = None
                        self._first_goal_event.set()
            if stale:
                self._cancel_goal_best_effort(handle)
                return
            result_future = handle.get_result_async()
            result_future.add_done_callback(
                lambda completed: self._on_goal_result(completed, generation)
            )
        except Exception as exc:
            with self._lock:
                current = generation == self._goal_generation
            if current:
                self._fail(f"NAV2_GOAL_ERROR:{type(exc).__name__}")

    def _on_goal_result(self, future: Any, generation: int) -> None:
        try:
            wrapped = future.result()
            with self._lock:
                if generation != self._goal_generation:
                    return
                self._goal_handle = None
            status = int(getattr(wrapped, "status", -1))
            # Our pause/stop/transition paths invalidate the generation first,
            # so a CANCELED result on the current generation is unexpected.
            if status == 4:  # action_msgs/GoalStatus: SUCCEEDED == 4
                with self._lock:
                    self._goal_aborts_at_sequence = 0
                return
            if status == 6:  # ABORTED
                # The controller refuses to drive into something it can see.
                # Hold instead of ending the patrol so the obstacle-clear loop
                # can resume this same waypoint once the path opens up.
                self._hold_for_obstacle(f"NAV2_GOAL_STATUS_{status}")
                return
            self._fail(f"NAV2_GOAL_STATUS_{status}")
        except Exception as exc:
            with self._lock:
                current = generation == self._goal_generation
            if current:
                self._fail(f"NAV2_RESULT_ERROR:{type(exc).__name__}")

    def _hold_for_obstacle(self, reason: str) -> None:
        """Stop for a Nav2 abort while keeping the patrol resumable.

        Unlike :meth:`_fail` this preserves ``_route`` and ``_current_sequence``
        so :meth:`resume_patrol` re-sends the same waypoint.  Motion is held
        under the ``OBSTACLE`` reason, which is the same interlock the LiDAR
        obstacle stop uses, so the runtime's clear-detect loop owns the resume.
        """

        with self._lock:
            if self._patrol_failure_reported or self._route is None:
                return
            self._goal_aborts_at_sequence += 1
            exhausted = (
                self._goal_aborts_at_sequence
                > self._settings.goal_abort_retry_limit
            )
            sequence = self._current_sequence
        if exhausted:
            # Waiting is not clearing it: the blockage is static, so report a
            # real failure rather than holding the patrol open indefinitely.
            self._fail(f"NAV2_GOAL_ABORT_UNRECOVERABLE:{reason}")
            return
        with self._lock:
            timer = self._cancel_scan_dwell_locked(clear_pending=False)
            self._paused = True
            handle = self._invalidate_goal_locked()
            self._cmd_vel_hold_reason = "OBSTACLE"
            self._last_cmd_vel_at = None
            attempts = self._goal_aborts_at_sequence
        if timer is not None:
            timer.cancel()
        LOGGER.warning(
            "Nav2 aborted waypoint %s (%s); holding for obstacle clear "
            "(attempt %d/%d)",
            sequence,
            reason,
            attempts,
            self._settings.goal_abort_retry_limit,
        )
        self._motion_sink(CmdVelCommand(0, 80, "OBSTACLE"))
        self._cancel_goal_best_effort(handle)
        self._publish_scan_context(None)
        if self._obstacle_sink is not None:
            self._obstacle_sink("OBSTACLE")

    def _fail(self, reason: str) -> None:
        with self._lock:
            if self._patrol_failure_reported:
                return
            self._patrol_failure_reported = True
            if not self._first_goal_event.is_set():
                self._first_goal_failure = reason
                self._first_goal_pending = False
                self._first_goal_event.set()
            timer = self._cancel_scan_dwell_locked()
            handle = self._invalidate_goal_locked()
            self._route = None
            self._current_sequence = None
            self._paused = False
            self._cmd_vel_hold_reason = reason
        if timer is not None:
            timer.cancel()
        self._motion_sink(CmdVelCommand(0, 80, reason))
        self._cancel_goal_best_effort(handle)
        self._publish_scan_context(None)
        if self._failure_sink is not None:
            self._failure_sink(reason)

    def _resolve_goal_yaw_deg(self, route: Any, sequence: int) -> float:
        """Preserve explicit yaw; otherwise follow route geometry/current pose."""

        waypoint = route.waypoints[sequence - 1]
        if waypoint.yaw_deg is not None:
            return float(waypoint.yaw_deg)
        if sequence < len(route.waypoints):
            neighbor = route.waypoints[sequence]
            return math.degrees(
                math.atan2(neighbor.y - waypoint.y, neighbor.x - waypoint.x)
            )
        if sequence > 1:
            neighbor = route.waypoints[sequence - 2]
            return math.degrees(
                math.atan2(waypoint.y - neighbor.y, waypoint.x - neighbor.x)
            )
        if self._heading_source is not None:
            heading = self._heading_source()
            if heading is not None and math.isfinite(float(heading)):
                return float(heading)
        raise ValueError("no route direction or current map heading")

    # The bridge used to publish waypoint 1 to /initialpose on every START_PATROL
    # ("_publish_initial_pose"). Removed: localization belongs to AMCL seeded once
    # at startup with the dock pose; the route must not overwrite it. The publisher
    # below is kept wired for operator-driven re-localization tooling only.

    def _publish_scan_context(self, waypoint: Any | None) -> None:
        if self._scan_context_sink is None:
            return
        try:
            self._scan_context_sink(waypoint)
        except Exception as exc:
            LOGGER.warning(
                "SCAN context update failed: %s", type(exc).__name__
            )

    def _spin(self) -> None:
        try:
            while (
                not self._stop_event.is_set()
                and self._rclpy is not None
                and self._rclpy.ok()
            ):
                self._executor.spin_once(timeout_sec=0.1)
                reason = self._health_failure_reason(check_thread=False)
                if reason is not None:
                    self._fail(reason)
        except Exception as exc:
            LOGGER.error(
                "Nav2 bridge thread failed: type=%s",
                type(exc).__name__,
            )
            if self._active_patrol_can_fail():
                self._fail(
                    f"NAV2_BRIDGE_THREAD_ERROR:{type(exc).__name__}"
                )
        finally:
            if (
                not self._stop_event.is_set()
                and self._active_patrol_can_fail()
            ):
                self._fail("NAV2_BRIDGE_THREAD_STOPPED")

    def _active_patrol_can_fail(self) -> bool:
        with self._lock:
            return (
                self._route is not None
                and not self._paused
                and not self._patrol_failure_reported
            )

    def _cleanup_ros(self) -> None:
        executor = self._executor
        node = self._node
        self._subscription = None
        self._initial_pose_publisher = None
        self._action_client = None
        self._executor = None
        self._node = None
        self._initial_pose_type = None
        if node is not None:
            if executor is not None:
                executor.remove_node(node)
            node.destroy_node()
        if executor is not None:
            executor.shutdown()
        rclpy = self._rclpy
        self._rclpy = None
        if self._owns_rclpy_context and rclpy is not None and rclpy.ok():
            rclpy.shutdown()
        self._owns_rclpy_context = False
