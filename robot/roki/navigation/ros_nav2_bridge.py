"""ROS 2 Nav2 action and ``cmd_vel`` bridge for the Ackermann robot.

This component never opens the ESP32 serial port.  It translates Nav2 output
and delegates the resulting bounded target to the one RobotRuntime owner.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any, Callable

from navigation.cmd_vel_adapter import (
    AckermannCommandSettings,
    CmdVelCommand,
    CmdVelToEsp32Adapter,
)


MotionSink = Callable[[CmdVelCommand], None]
FailureSink = Callable[[str], None]


@dataclass(frozen=True)
class RosNav2BridgeSettings:
    ackermann: AckermannCommandSettings
    cmd_vel_topic: str = "/cmd_vel"
    navigate_action: str = "/navigate_to_pose"
    map_frame: str = "map"

    def __post_init__(self) -> None:
        for name, value in (
            ("cmd_vel_topic", self.cmd_vel_topic),
            ("navigate_action", self.navigate_action),
            ("map_frame", self.map_frame),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")


class RosNav2Bridge:
    """Own the Nav2 ROS node while RobotRuntime remains the serial owner."""

    def __init__(
        self,
        *,
        settings: RosNav2BridgeSettings,
        motion_sink: MotionSink,
        failure_sink: FailureSink | None = None,
    ) -> None:
        self._settings = settings
        self._adapter = CmdVelToEsp32Adapter(settings.ackermann)
        self._motion_sink = motion_sink
        self._failure_sink = failure_sink
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._route: Any = None
        self._current_sequence: int | None = None
        self._paused = False
        self._goal_handle: Any = None
        self._node: Any = None
        self._executor: Any = None
        self._action_client: Any = None
        self._subscription: Any = None
        self._rclpy: Any = None
        self._navigate_type: Any = None
        self._pose_type: Any = None
        self._owns_rclpy_context = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        try:
            import rclpy
            from geometry_msgs.msg import PoseStamped, Twist
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
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._spin,
                name="ros-nav2-bridge",
                daemon=True,
            )
            self._thread.start()
        except Exception:
            self._cleanup_ros()
            raise

    def stop(self) -> None:
        self.stop_patrol()
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._cleanup_ros()

    def is_ready(self) -> tuple[bool, str]:
        if self._thread is None or not self._thread.is_alive():
            return False, "NAV2_BRIDGE_NOT_RUNNING"
        if self._action_client is None or not self._action_client.server_is_ready():
            return False, "NAV2_ACTION_SERVER_NOT_READY"
        return True, "READY"

    def start_patrol(self, *, route: Any, first_event: Any) -> None:
        del first_event
        ready, reason = self.is_ready()
        if not ready:
            raise RuntimeError(reason)
        with self._lock:
            self._route = route
            self._paused = False
            self._current_sequence = 1
        self._send_sequence(1)

    def stop_patrol(self) -> None:
        with self._lock:
            handle = self._goal_handle
            self._goal_handle = None
            self._route = None
            self._current_sequence = None
            self._paused = False
        if handle is not None:
            handle.cancel_goal_async()
        self._motion_sink(CmdVelCommand(0, 80, "NAV2_PATROL_STOPPED"))

    def pause_patrol(self) -> None:
        with self._lock:
            self._paused = True
            handle = self._goal_handle
        if handle is not None:
            handle.cancel_goal_async()
        self._motion_sink(CmdVelCommand(0, 80, "OBSTACLE"))

    def resume_patrol(self) -> None:
        with self._lock:
            sequence = self._current_sequence
            self._paused = False
        if sequence is not None:
            self._send_sequence(sequence)

    def on_navigation_event(self, event: Any) -> None:
        event_type = getattr(event.mission_event.event_type, "value", "")
        waypoint = getattr(event.mission_event, "waypoint", None)
        if event_type == "DESTINATION_REACHED":
            return
        if event_type != "WAYPOINT_REACHED" or waypoint is None:
            return
        next_sequence = int(waypoint.sequence) + 1
        with self._lock:
            route = self._route
            paused = self._paused
            if route is None or next_sequence > len(route.waypoints):
                return
            self._current_sequence = next_sequence
        if not paused:
            self._send_sequence(next_sequence)

    def record_cmd_vel(
        self, linear_x_mps: float, angular_z_radps: float
    ) -> CmdVelCommand:
        """Pure test boundary shared with the ROS callback."""

        command = self._adapter.convert(linear_x_mps, angular_z_radps)
        self._motion_sink(command)
        return command

    def _on_cmd_vel(self, message: Any) -> None:
        try:
            self.record_cmd_vel(float(message.linear.x), float(message.angular.z))
        except (TypeError, ValueError) as exc:
            self._fail(f"NAV2_CMD_VEL_INVALID:{exc}")

    def _send_sequence(self, sequence: int) -> None:
        with self._lock:
            if self._paused or self._route is None:
                return
            waypoint = self._route.waypoints[sequence - 1]
        assert self._navigate_type is not None
        assert self._pose_type is not None
        assert self._node is not None
        goal = self._navigate_type.Goal()
        pose = self._pose_type()
        pose.header.frame_id = self._settings.map_frame
        pose.header.stamp = self._node.get_clock().now().to_msg()
        pose.pose.position.x = float(waypoint.x)
        pose.pose.position.y = float(waypoint.y)
        yaw = math.radians(float(waypoint.yaw_deg))
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        goal.pose = pose
        future = self._action_client.send_goal_async(goal)
        future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future: Any) -> None:
        try:
            handle = future.result()
            if handle is None or not handle.accepted:
                self._fail("NAV2_GOAL_REJECTED")
                return
            with self._lock:
                self._goal_handle = handle
            result_future = handle.get_result_async()
            result_future.add_done_callback(self._on_goal_result)
        except Exception as exc:
            self._fail(f"NAV2_GOAL_ERROR:{type(exc).__name__}")

    def _on_goal_result(self, future: Any) -> None:
        try:
            wrapped = future.result()
            status = int(getattr(wrapped, "status", -1))
            # action_msgs/GoalStatus: SUCCEEDED == 4, CANCELED == 5.
            if status not in (4, 5):  # canceled while paused/stopping is safe
                self._fail(f"NAV2_GOAL_STATUS_{status}")
        except Exception as exc:
            self._fail(f"NAV2_RESULT_ERROR:{type(exc).__name__}")

    def _fail(self, reason: str) -> None:
        self._motion_sink(CmdVelCommand(0, 80, reason))
        if self._failure_sink is not None:
            self._failure_sink(reason)

    def _spin(self) -> None:
        while (
            not self._stop_event.is_set()
            and self._rclpy is not None
            and self._rclpy.ok()
        ):
            self._executor.spin_once(timeout_sec=0.1)

    def _cleanup_ros(self) -> None:
        executor = self._executor
        node = self._node
        self._subscription = None
        self._action_client = None
        self._executor = None
        self._node = None
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
