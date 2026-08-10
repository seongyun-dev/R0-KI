"""Lifecycle-isolated ROS subscribers and loopback MJPEG mapping service."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from aiot_robot.mjpeg_stream import MjpegStreamServer

from .map_renderer import GridMap, MappingRenderer, Pose2D, transform_scan_points


@dataclass(frozen=True)
class MappingVisualizerSettings:
    bind: str = "127.0.0.1"
    port: int = 8091
    output_size_px: int = 800
    maximum_fps: float = 4.0
    jpeg_quality: int = 75
    inactive_fps: float = 1.0
    map_topic: str = "/map"
    scan_topic: str = "/scan"
    map_frame: str = "map"
    robot_frame: str = "base_link"

    def __post_init__(self) -> None:
        if self.bind != "127.0.0.1":
            raise ValueError("mapping MJPEG must bind to loopback")
        if not 1 <= self.port <= 65535:
            raise ValueError("mapping MJPEG port is invalid")
        if self.output_size_px <= 0:
            raise ValueError("mapping output size must be positive")
        if not 0 < self.maximum_fps <= 4:
            raise ValueError("mapping FPS must be between 0 and 4")
        if not 70 <= self.jpeg_quality <= 85:
            raise ValueError("mapping JPEG quality must be between 70 and 85")
        if not 0 < self.inactive_fps <= 1:
            raise ValueError("inactive FPS must be between 0 and 1")


class MappingVisualizer:
    """Read ROS data and render only; never owns mapping, Serial or motion."""

    def __init__(
        self,
        *,
        mapping_active: Callable[[], bool],
        settings: MappingVisualizerSettings = MappingVisualizerSettings(),
        server_factory: Callable[..., MjpegStreamServer] = MjpegStreamServer,
    ) -> None:
        if not callable(mapping_active):
            raise ValueError("mapping_active callback is required")
        self._mapping_active = mapping_active
        self._settings = settings
        self._renderer = MappingRenderer(size_px=settings.output_size_px)
        self._server_factory = server_factory
        self._server: MjpegStreamServer | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._map: GridMap | None = None
        self._scan: Any | None = None
        self._path: list[Pose2D] = []
        self._context: Any | None = None
        self._node: Any | None = None
        self._executor: Any | None = None
        self._ros_thread: threading.Thread | None = None
        self._render_thread: threading.Thread | None = None
        self._tf_buffer: Any | None = None
        self._tf_listener: Any | None = None
        self._server_started = False

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None:
            raise RuntimeError("mapping MJPEG server is not started")
        return self._server.address

    def start(self) -> None:
        if self._ros_thread is not None:
            return
        try:
            self._start_ros()
            self._server = self._server_factory(
                self._settings.bind,
                self._settings.port,
                quality=self._settings.jpeg_quality,
                max_fps=self._settings.maximum_fps,
                max_frame_age_seconds=max(
                    2.0,
                    2.0 / self._settings.inactive_fps,
                ),
            )
            self._server.start()
            self._server_started = True
            self._stop.clear()
            self._ros_thread = threading.Thread(
                target=self._spin_ros,
                name="mapping-visualizer-ros",
                daemon=True,
            )
            self._render_thread = threading.Thread(
                target=self._render_loop,
                name="mapping-visualizer-render",
                daemon=True,
            )
            self._ros_thread.start()
            self._render_thread.start()
            host, port = self.address
            print(f"[MAPPING_VIEW] listening http://{host}:{port}/stream.mjpg")
        except Exception as exc:
            self._stop.set()
            self._cleanup_ros()
            if self._server_started and self._server is not None:
                self._server.stop()
                self._server_started = False
            self._server = None
            print(f"[MAPPING_VIEW] disabled type={type(exc).__name__}")

    def stop(self) -> None:
        self._stop.set()
        executor = self._executor
        if executor is not None:
            executor.shutdown(timeout_sec=1.0)
        for thread in (self._render_thread, self._ros_thread):
            if thread is not None:
                thread.join(timeout=2.0)
        self._render_thread = None
        self._ros_thread = None
        self._cleanup_ros()
        if self._server_started and self._server is not None:
            self._server.stop()
            self._server_started = False
        self._server = None

    def _cleanup_ros(self) -> None:
        node = self._node
        if node is not None:
            node.destroy_node()
        context = self._context
        if context is not None and context.ok():
            context.shutdown()
        self._node = None
        self._context = None
        self._executor = None
        self._tf_buffer = None
        self._tf_listener = None

    def _start_ros(self) -> None:
        import rclpy
        from nav_msgs.msg import OccupancyGrid
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import LaserScan
        from tf2_ros import Buffer, TransformListener

        context = Context()
        rclpy.init(context=context)
        node = Node("roki_mapping_visualizer", context=context)
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        node.create_subscription(
            OccupancyGrid,
            self._settings.map_topic,
            self._on_map,
            map_qos,
        )
        node.create_subscription(
            LaserScan,
            self._settings.scan_topic,
            self._on_scan,
            qos_profile_sensor_data,
        )
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(
            self._tf_buffer,
            node,
            spin_thread=False,
        )
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        self._context = context
        self._node = node
        self._executor = executor

    def _spin_ros(self) -> None:
        try:
            self._executor.spin()
        except Exception as exc:
            if not self._stop.is_set():
                print(f"[MAPPING_VIEW] ROS stopped type={type(exc).__name__}")

    def _on_map(self, message: Any) -> None:
        origin = message.info.origin
        grid = GridMap(
            width=int(message.info.width),
            height=int(message.info.height),
            resolution=float(message.info.resolution),
            origin=Pose2D(
                float(origin.position.x),
                float(origin.position.y),
                _quaternion_yaw(origin.orientation),
            ),
            values=tuple(message.data),
        )
        with self._lock:
            self._map = grid

    def _on_scan(self, message: Any) -> None:
        with self._lock:
            self._scan = message

    def _render_loop(self) -> None:
        active_before = False
        next_inactive_at = 0.0
        active_interval = 1.0 / self._settings.maximum_fps
        inactive_interval = 1.0 / self._settings.inactive_fps
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                active = bool(self._mapping_active())
                if active and not active_before:
                    self._path.clear()
                if not active:
                    if active_before:
                        self._path.clear()
                    if started >= next_inactive_at:
                        assert self._server is not None
                        self._server.publisher.publish(
                            self._renderer.inactive_frame(),
                            _cv2(),
                        )
                        next_inactive_at = started + inactive_interval
                else:
                    self._render_active_frame()
                active_before = active
            except Exception as exc:
                print(f"[MAPPING_VIEW] frame skipped type={type(exc).__name__}")
            interval = active_interval if active_before else min(active_interval, 0.25)
            self._stop.wait(max(0.0, interval - (time.monotonic() - started)))

    def _render_active_frame(self) -> None:
        with self._lock:
            grid = self._map
            scan = self._scan
        if grid is None:
            return
        robot_pose = self._lookup_pose(self._settings.robot_frame)
        if robot_pose is not None:
            self._renderer.append_path(self._path, robot_pose)
        scan_points = None
        if scan is not None:
            scan_pose = self._lookup_pose(str(scan.header.frame_id))
            if scan_pose is not None:
                scan_points = transform_scan_points(
                    scan.ranges,
                    angle_min=float(scan.angle_min),
                    angle_increment=float(scan.angle_increment),
                    range_min=float(scan.range_min),
                    range_max=float(scan.range_max),
                    scan_to_map=scan_pose,
                )
        frame = self._renderer.render(
            grid,
            scan=scan_points,
            robot_pose=robot_pose,
            path=self._path,
        )
        assert self._server is not None
        self._server.publisher.publish(frame, _cv2())

    def _lookup_pose(self, child_frame: str) -> Pose2D | None:
        from rclpy.time import Time

        try:
            transform = self._tf_buffer.lookup_transform(
                self._settings.map_frame,
                child_frame,
                Time(),
            )
        except Exception:
            return None
        translation = transform.transform.translation
        return Pose2D(
            float(translation.x),
            float(translation.y),
            _quaternion_yaw(transform.transform.rotation),
        )


def _quaternion_yaw(quaternion: Any) -> float:
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z),
    )


def _cv2() -> Any:
    import cv2

    return cv2
