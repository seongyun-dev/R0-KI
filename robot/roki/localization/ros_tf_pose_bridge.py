"""ROS TF ``map -> base_link``를 Final Runtime의 Map Pose로 전달한다."""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from localization.pose import PoseSource
from localization.ros_pose_source_adapter import RosPoseSourceAdapter


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RosTfPoseBridgeSettings:
    map_frame: str
    base_frame: str
    map_pose_timeout_sec: float
    tf_poll_interval_sec: float
    max_future_transform_sec: float = 0.75

    def __post_init__(self) -> None:
        if not self.map_frame.strip():
            raise ValueError("localization.map_frame must not be empty")
        if not self.base_frame.strip():
            raise ValueError("localization.base_frame must not be empty")
        if self.map_pose_timeout_sec <= 0:
            raise ValueError(
                "localization.map_pose_timeout_sec must be positive"
            )
        if self.tf_poll_interval_sec <= 0:
            raise ValueError(
                "localization.tf_poll_interval_sec must be positive"
            )
        if (
            not math.isfinite(self.max_future_transform_sec)
            or self.max_future_transform_sec < 0
        ):
            raise ValueError(
                "localization.max_future_transform_sec must be non-negative"
            )


class RosTfPoseBridge:
    """TF 조회와 Pose Store 갱신만 담당하는 lifecycle component."""

    def __init__(
        self,
        *,
        state_store: Any,
        settings: RosTfPoseBridgeSettings,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._state_store = state_store
        self._settings = settings
        self._monotonic_clock = monotonic_clock
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._node: Any = None
        self._buffer: Any = None
        self._listener: Any = None
        self._executor: Any = None
        self._rclpy: Any = None
        self._owns_rclpy_context = False
        self._lookup_failure_logged = False

    @property
    def state_store(self) -> Any:
        """DI 검증용 읽기 전용 Store 참조."""

        return self._state_store

    def start(self) -> None:
        if self.is_running():
            return

        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from tf2_ros import Buffer, TransformListener
        except ImportError as exc:
            raise RuntimeError(
                "ROS TF Pose Bridge requires rclpy and tf2_ros"
            ) from exc

        self._rclpy = rclpy
        self._owns_rclpy_context = not rclpy.ok()
        if self._owns_rclpy_context:
            rclpy.init(args=None)

        try:
            self._node = rclpy.create_node("roki_map_pose_bridge")
            self._buffer = Buffer()
            self._listener = TransformListener(
                self._buffer,
                self._node,
                spin_thread=False,
            )
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="ros-tf-pose-bridge",
                daemon=True,
            )
            self._thread.start()
        except Exception:
            self._cleanup_ros()
            raise

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(2.0, self._settings.tf_poll_interval_sec * 2))
        self._thread = None
        self._cleanup_ros()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def lookup_and_update(
        self,
        lookup: Callable[[], Any],
        *,
        ros_now_sec: float,
        received_at: float | None = None,
    ) -> bool:
        """조회 실패를 Store 갱신 없이 처리한다."""

        try:
            transform = lookup()
        except Exception as exc:
            if not self._lookup_failure_logged:
                LOGGER.warning("map -> base_link TF unavailable: %s", exc)
                self._lookup_failure_logged = True
            return False

        updated = self.ingest_transform(
            transform,
            ros_now_sec=ros_now_sec,
            received_at=received_at,
        )
        if updated:
            self._lookup_failure_logged = False
        return updated

    def ingest_transform(
        self,
        transform: Any,
        *,
        ros_now_sec: float,
        received_at: float | None = None,
    ) -> bool:
        """TransformStamped를 검증하고 fresh한 Map Pose만 저장한다."""

        try:
            if transform.header.frame_id != self._settings.map_frame:
                return False
            if transform.child_frame_id != self._settings.base_frame:
                return False

            stamp = transform.header.stamp
            transform_time = float(stamp.sec) + float(stamp.nanosec) / 1e9
            age = float(ros_now_sec) - transform_time
            if (
                not math.isfinite(age)
                or age < -self._settings.max_future_transform_sec
                or age > self._settings.map_pose_timeout_sec
            ):
                return False

            translation = transform.transform.translation
            rotation = transform.transform.rotation
            quaternion = (
                float(rotation.x),
                float(rotation.y),
                float(rotation.z),
                float(rotation.w),
            )
            values = (
                float(translation.x),
                float(translation.y),
                *quaternion,
            )
            if not all(math.isfinite(value) for value in values):
                return False

            norm = math.sqrt(sum(value * value for value in quaternion))
            if norm <= 1e-12:
                return False
            qx, qy, qz, qw = (value / norm for value in quaternion)
            yaw = math.atan2(
                2.0 * (qw * qz + qx * qy),
                1.0 - 2.0 * (qy * qy + qz * qz),
            )
            pose = RosPoseSourceAdapter.from_map_to_base_link(
                x_m=float(translation.x),
                y_m=float(translation.y),
                heading_rad=yaw,
                timestamp=(
                    self._monotonic_clock()
                    if received_at is None
                    else float(received_at)
                ),
                source=PoseSource.SLAM_MAP,
            )
            if not pose.valid:
                return False
            self._state_store.update_map_pose(pose)
            return True
        except (AttributeError, TypeError, ValueError, OverflowError):
            return False

    def _run(self) -> None:
        assert self._rclpy is not None
        assert self._node is not None
        assert self._buffer is not None

        next_lookup = 0.0
        while not self._stop_event.is_set() and self._rclpy.ok():
            self._executor.spin_once(
                timeout_sec=min(0.05, self._settings.tf_poll_interval_sec),
            )
            now = self._monotonic_clock()
            if now < next_lookup:
                continue
            next_lookup = now + self._settings.tf_poll_interval_sec
            ros_now_sec = self._node.get_clock().now().nanoseconds / 1e9
            self.lookup_and_update(
                self._lookup_current_transform,
                ros_now_sec=ros_now_sec,
                received_at=now,
            )

    def _lookup_current_transform(self) -> Any:
        from rclpy.time import Time

        return self._buffer.lookup_transform(
            self._settings.map_frame,
            self._settings.base_frame,
            Time(),
        )

    def _cleanup_ros(self) -> None:
        self._listener = None
        executor = self._executor
        self._executor = None
        node = self._node
        self._node = None
        self._buffer = None
        if node is not None:
            if executor is not None:
                executor.remove_node(node)
            node.destroy_node()
        if executor is not None:
            executor.shutdown()
        rclpy = self._rclpy
        self._rclpy = None
        if (
            self._owns_rclpy_context
            and rclpy is not None
            and rclpy.ok()
        ):
            rclpy.shutdown()
        self._owns_rclpy_context = False
