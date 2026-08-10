"""ROS adapter around the existing script-style Jetson AI pipeline.

The model and inference code remain untouched.  This wrapper replaces only the
pipeline's REST sink so Robot is the single owner of backend delivery.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from .ai_adapter_core import build_detection_message
from .ai_capture import CaptureSettings, configure_capture
from .mjpeg_stream import MjpegStreamServer
from .patrol_activation import PatrolActivation


class AiAdapterNode(Node):
    def __init__(self, evidence_root: Path) -> None:
        super().__init__("aiot_ai_adapter")
        self._evidence_root = evidence_root
        self._evidence_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._active_patrol_id: int | None = None
        self._state = "STARTING"
        self._camera_ready = False
        self._engine_ready = False
        self._inference_ready = False
        self._error_code: str | None = None
        self._message: str | None = None
        self._patrol_activation = PatrolActivation()

        control_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        status_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        detection_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._status_publisher = self.create_publisher(
            String, os.getenv("AIOT_AI_STATUS_TOPIC", "/ai/status"), status_qos
        )
        self._detection_publisher = self.create_publisher(
            String,
            os.getenv("AIOT_AI_DETECTIONS_TOPIC", "/ai/detections"),
            detection_qos,
        )
        self.create_subscription(
            String,
            os.getenv("AIOT_AI_CONTROL_TOPIC", "/ai/control"),
            self._on_control,
            control_qos,
        )
        self.create_timer(2.0, self.publish_status)
        self.publish_status()

    def mark_engine_ready(self) -> None:
        with self._lock:
            self._engine_ready = True
        self.publish_status()

    def mark_camera_ready(self) -> None:
        with self._lock:
            self._camera_ready = True
        self.publish_status()

    def mark_inference_ready(self) -> None:
        with self._lock:
            self._inference_ready = True
            if self._camera_ready and self._engine_ready:
                self._state = "READY"
                self._error_code = None
                self._message = None
        self.publish_status()

    def mark_error(self, code: str, message: str) -> None:
        with self._lock:
            self._state = "ERROR"
            self._error_code = code[:128]
            self._message = message[:512]
        self.publish_status()

    def mark_stopped(self) -> None:
        self._patrol_activation.disable()
        with self._lock:
            self._state = "STOPPED"
            self._active_patrol_id = None
        self.publish_status()

    def publish_status(self) -> None:
        with self._lock:
            ready = (
                self._state == "READY"
                and self._camera_ready
                and self._engine_ready
                and self._inference_ready
            )
            payload = {
                "schemaVersion": 1,
                "state": self._state,
                "ready": ready,
                "cameraReady": self._camera_ready,
                "engineReady": self._engine_ready,
                "inferenceReady": self._inference_ready,
                "detectionEnabled": self._patrol_activation.enabled,
                "patrolId": self._active_patrol_id,
                "modelVersion": os.getenv("AIOT_AI_MODEL_VERSION") or None,
                "heartbeatAt": _utc_now(),
                "errorCode": self._error_code,
                "message": self._message,
            }
        message = String()
        message.data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self._status_publisher.publish(message)

    def publish_detection(
        self,
        payload: dict[str, Any],
        image_path: str | os.PathLike[str] | None,
        *,
        vehicle: bool = False,
        detection_context: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            patrol_id = self._active_patrol_id
            ready = self._state == "READY"
        if patrol_id is None or not ready or image_path is None:
            return
        source = Path(image_path)
        if not source.is_file():
            return
        event_id = uuid4().hex
        evidence = self._evidence_root / f"{event_id}{source.suffix or '.jpg'}"
        try:
            context = detection_context or {}
            message_payload = build_detection_message(
                payload,
                evidence_path=evidence.as_posix(),
                patrol_id=patrol_id,
                event_id=event_id,
                observed_at_fallback=_utc_now(),
                vehicle=vehicle,
                detection_bbox_xyxy=context.get("bbox"),
                frame_width=context.get("frameWidth"),
                camera_id=context.get("cameraId"),
                track_id=context.get("trackId"),
            )
        except ValueError as exc:
            self.get_logger().warning(f"Dropped unsupported AI event: {exc}")
            return
        if source.resolve() != evidence.resolve():
            shutil.copy2(source, evidence)
        message = String()
        message.data = json.dumps(
            message_payload, ensure_ascii=False, separators=(",", ":")
        )
        self._detection_publisher.publish(message)

    def _on_control(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
                raise ValueError("unsupported control schema")
            command = payload.get("command")
            patrol_id = payload.get("patrolId")
            if command == "ENABLE":
                if (
                    isinstance(patrol_id, bool)
                    or not isinstance(patrol_id, int)
                    or patrol_id <= 0
                ):
                    raise ValueError("ENABLE requires patrolId")
                with self._lock:
                    self._active_patrol_id = patrol_id
                self._patrol_activation.enable()
            elif command == "DISABLE":
                self._patrol_activation.disable()
                with self._lock:
                    self._active_patrol_id = None
            else:
                raise ValueError("unsupported control command")
        except (ValueError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f"Rejected AI control: {exc}")
            return
        self.publish_status()

    @property
    def detection_enabled(self) -> bool:
        return self._patrol_activation.enabled

    def wait_for_detection_enabled(self, timeout: float) -> bool:
        return self._patrol_activation.wait(timeout)


class RosEventSink:
    """Drop-in replacement for the AI pipeline's direct REST client."""

    def __init__(self, node: AiAdapterNode) -> None:
        self._node = node

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def flush_all(self) -> int:
        return 0

    def retry_pending_evidence(self) -> int:
        return 0

    def send_urgent(self, payload: dict[str, Any], image_path: Any) -> None:
        self._node.publish_detection(payload, image_path)

    def enqueue_batch(self, payload: dict[str, Any], image_path: Any) -> None:
        self._node.publish_detection(payload, image_path)

    def enqueue_vehicle(
        self, payload: dict[str, Any], image_path: Any = None
    ) -> None:
        self._node.publish_detection(payload, image_path, vehicle=True)

    def enqueue_vehicle_context(
        self,
        payload: dict[str, Any],
        image_path: Any = None,
        *,
        bbox: Any,
        frame_width: Any,
        camera: Any,
        track_id: Any,
    ) -> None:
        """Publish camera-only metadata without changing the REST payload."""

        self._node.publish_detection(
            payload,
            image_path,
            vehicle=True,
            detection_context={
                "bbox": bbox,
                "frameWidth": frame_width,
                "cameraId": camera,
                "trackId": track_id,
            },
        )

    def create_emergency_event(self, payload: dict[str, Any]) -> None:
        # The ROS contract requires evidence. Events without a frame are skipped.
        del payload
        return None


def _load_pipeline(module_path: Path) -> Any:
    source_dir = module_path.parent
    sys.path.insert(0, str(source_dir))
    specification = importlib.util.spec_from_file_location(
        "aiot_external_pipeline_main", module_path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load AI pipeline: {module_path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def run_pipeline(
    node: AiAdapterNode,
    pipeline_main: Path,
    pipeline_args: list[str],
    capture_settings: CaptureSettings,
    mjpeg_server: MjpegStreamServer | None = None,
    *,
    single_camera: bool = False,
) -> int:
    try:
        module = _load_pipeline(pipeline_main)
        sink = RosEventSink(node)
        module.RestEventClient = lambda: sink

        original_detector = module.DualCamTensorRTBotSortDetector

        class DetectorProxy:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self._delegate = original_detector(*args, **kwargs)
                self._warmup_complete = False
                node.mark_engine_ready()

            def track_pair(self, *args: Any, **kwargs: Any) -> Any:
                if self._warmup_complete:
                    while rclpy.ok() and not node.wait_for_detection_enabled(0.25):
                        pass
                    if not rclpy.ok():
                        raise RuntimeError("AI runtime is stopping")
                if single_camera:
                    track_frame = getattr(self._delegate, "track_frame", None)
                    if not callable(track_frame):
                        raise RuntimeError(
                            "single-camera mode requires detector.track_frame"
                        )
                    if not args:
                        raise RuntimeError("single-camera detector received no frame")
                    result = (track_frame(args[0]), [])
                else:
                    result = self._delegate.track_pair(*args, **kwargs)
                if not self._warmup_complete:
                    self._warmup_complete = True
                    node.mark_inference_ready()
                return result

            def __getattr__(self, name: str) -> Any:
                return getattr(self._delegate, name)

        module.DualCamTensorRTBotSortDetector = DetectorProxy
        if mjpeg_server is not None:
            original_hconcat = module.cv2.hconcat

            def hconcat_with_preview(images: Any) -> Any:
                view = images[0] if single_camera else original_hconcat(images)
                if node.detection_enabled:
                    mjpeg_server.publisher.publish(view, module.cv2)
                return view

            module.cv2.hconcat = hconcat_with_preview
        original_open_capture = module.open_capture
        camera_count = 0

        class PlaceholderCapture:
            """Second batch slot without opening another V4L2 device."""

            def read(self) -> tuple[bool, Any]:
                import numpy as np

                frame = np.zeros(
                    (capture_settings.height, capture_settings.width, 3),
                    dtype=np.uint8,
                )
                return True, frame

            def release(self) -> None:
                return None

        def open_capture(source: Any) -> Any:
            nonlocal camera_count
            camera_count += 1
            if single_camera and camera_count == 2:
                return PlaceholderCapture()
            capture = original_open_capture(source)
            configure_capture(capture, module.cv2, capture_settings)
            if camera_count >= (1 if single_camera else 2):
                node.mark_camera_ready()
            return capture

        module.open_capture = open_capture
        original_argv = sys.argv
        sys.argv = [str(pipeline_main), *pipeline_args]
        try:
            module.main()
        finally:
            sys.argv = original_argv
        node.mark_error("PIPELINE_EXITED", "AI pipeline returned unexpectedly")
        return 1
    except Exception as exc:
        node.mark_error(type(exc).__name__, str(exc))
        node.get_logger().error(f"AI pipeline failed: {type(exc).__name__}: {exc}")
        return 1


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="AIoT ROS adapter for Jetson AI")
    parser.add_argument(
        "--pipeline-main",
        default=os.getenv(
            "AIOT_AI_PIPELINE_MAIN",
            "/home/e103/yolo-pipeline/yolo_pipeline/main.py",
        ),
    )
    parser.add_argument(
        "--evidence-root",
        default=os.getenv("AIOT_AI_EVIDENCE_DIR", "/var/lib/aiot/evidence"),
    )
    parser.add_argument(
        "--capture-width",
        type=int,
        default=int(os.getenv("AIOT_AI_CAPTURE_WIDTH", "640")),
    )
    parser.add_argument(
        "--capture-height",
        type=int,
        default=int(os.getenv("AIOT_AI_CAPTURE_HEIGHT", "480")),
    )
    parser.add_argument(
        "--capture-fps",
        type=float,
        default=float(os.getenv("AIOT_AI_CAPTURE_FPS", "30")),
    )
    parser.add_argument(
        "--capture-fourcc",
        default=os.getenv("AIOT_AI_CAPTURE_FOURCC", "MJPG"),
    )
    parser.add_argument(
        "--capture-buffer-size",
        type=int,
        default=int(os.getenv("AIOT_AI_CAPTURE_BUFFER_SIZE", "1")),
    )
    parser.add_argument(
        "--single-camera",
        action="store_true",
        default=_env_flag("AIOT_AI_SINGLE_CAMERA", default=False),
        help="use one physical camera and the detector's single-frame path",
    )
    parser.add_argument(
        "--mjpeg-bind",
        default=os.getenv("AIOT_AI_MJPEG_BIND", "127.0.0.1"),
    )
    parser.add_argument(
        "--mjpeg-port",
        type=int,
        default=int(os.getenv("AIOT_AI_MJPEG_PORT", "8090")),
    )
    parser.add_argument(
        "--mjpeg-quality",
        type=int,
        default=int(os.getenv("AIOT_AI_MJPEG_QUALITY", "70")),
    )
    parser.add_argument(
        "--mjpeg-max-fps",
        type=float,
        default=float(os.getenv("AIOT_AI_MJPEG_MAX_FPS", "5")),
    )
    parser.add_argument(
        "--mjpeg-frame-max-age-seconds",
        type=float,
        default=float(os.getenv("AIOT_AI_MJPEG_FRAME_MAX_AGE_SEC", "2")),
    )
    return parser.parse_known_args(argv)


def main(argv: list[str] | None = None) -> int:
    args, pipeline_args = parse_args(argv)
    pipeline_main = Path(args.pipeline_main)
    if not pipeline_main.is_file():
        raise FileNotFoundError(f"AI pipeline main.py is missing: {pipeline_main}")

    rclpy.init(args=None)
    node = AiAdapterNode(Path(args.evidence_root))
    capture_settings = CaptureSettings(
        width=args.capture_width,
        height=args.capture_height,
        fps=args.capture_fps,
        fourcc=args.capture_fourcc,
        buffer_size=args.capture_buffer_size,
    )
    mjpeg_server = None
    if _env_flag("AIOT_AI_MJPEG_ENABLED", default=False):
        mjpeg_server = MjpegStreamServer(
            args.mjpeg_bind,
            args.mjpeg_port,
            quality=args.mjpeg_quality,
            max_fps=args.mjpeg_max_fps,
            max_frame_age_seconds=args.mjpeg_frame_max_age_seconds,
        )
        mjpeg_server.start()
        host, port = mjpeg_server.address
        node.get_logger().info(
            f"MJPEG preview listening on http://{host}:{port}/stream.mjpg"
        )
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    result: list[int] = []
    pipeline_thread = threading.Thread(
        target=lambda: result.append(
            run_pipeline(
                node,
                pipeline_main,
                pipeline_args,
                capture_settings,
                mjpeg_server,
                single_camera=args.single_camera,
            )
        ),
        name="ai-model-pipeline",
        daemon=True,
    )
    pipeline_thread.start()
    try:
        while pipeline_thread.is_alive() and rclpy.ok():
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        node.mark_stopped()
    finally:
        pipeline_thread.join(timeout=10.0)
        if mjpeg_server is not None:
            mjpeg_server.stop()
        executor.remove_node(node)
        node.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
    return result[0] if result else 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


if __name__ == "__main__":
    raise SystemExit(main())
