"""Durable Robot-owned delivery of AI detections to backend REST APIs."""

from __future__ import annotations

import math
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .backend_client import BackendConfig, RobotBackendClient
from .contracts import DetectionEvent
from .detection_localization import bbox_center_bearing_deg, project_detection
from .outbox import DetectionOutbox
from .vehicle_localization import project_front_vehicle


BackendFactory = Callable[[], RobotBackendClient]
DEFAULT_MIN_DETECTION_CONFIDENCE = 0.5
_DIRECTIONAL_ENVIRONMENT_EVENT_TYPES = frozenset(
    {"TRASH_DETECTED", "RECYCLING_AREA_FULL", "EMERGENCY"}
)


class DetectionRecorder:
    """Attach the Robot-owned map pose before an AI event reaches disk."""

    def __init__(
        self,
        outbox: DetectionOutbox,
        state_store: Any,
        *,
        vehicle_range_source: Any | None = None,
        camera_yaw_deg: float = 0.0,
        camera_horizontal_fov_deg: float | None = None,
        lidar_forward_center_angle_deg: float | None = None,
        minimum_confidence: float | None = None,
        emergency_stop_sink: Callable[[Any], None] | None = None,
    ) -> None:
        self._outbox = outbox
        self._state_store = state_store
        self._vehicle_range_source = vehicle_range_source
        self._camera_yaw_deg = float(camera_yaw_deg)
        self._camera_horizontal_fov_deg = float(
            os.getenv("AIOT_DETECTION_CAMERA_HORIZONTAL_FOV_DEG", "48")
            if camera_horizontal_fov_deg is None
            else camera_horizontal_fov_deg
        )
        self._lidar_forward_center_angle_deg = float(
            os.getenv(
                "AIOT_LIDAR_FORWARD_CENTER_ANGLE_DEG",
                os.getenv("AIOT_VEHICLE_LIDAR_CENTER_ANGLE_DEG", "0"),
            )
            if lidar_forward_center_angle_deg is None
            else lidar_forward_center_angle_deg
        )
        if (
            not math.isfinite(self._camera_horizontal_fov_deg)
            or not 0.0 < self._camera_horizontal_fov_deg < 180.0
        ):
            raise ValueError("camera horizontal FOV must be between 0 and 180")
        if not math.isfinite(self._lidar_forward_center_angle_deg):
            raise ValueError("LiDAR forward center angle must be finite")
        self._minimum_confidence = (
            float(os.getenv("AIOT_MIN_DETECTION_CONFIDENCE", "0.5"))
            if minimum_confidence is None
            else float(minimum_confidence)
        )
        if (
            not math.isfinite(self._minimum_confidence)
            or not 0.0 <= self._minimum_confidence <= 1.0
        ):
            raise ValueError("minimum detection confidence must be between 0 and 1")
        self._emergency_stop_sink = emergency_stop_sink
        self._scan_context_lock = threading.Lock()
        self._scan_context: dict[str, Any] | None = None
        self._recycling_lock = threading.Lock()
        self._recycling_patrol_ids: set[int] = set()

    def set_scan_context(self, waypoint: Any | None) -> None:
        """Receive the current SCAN hook from the navigation runtime."""

        context = None
        if waypoint is not None:
            context = {
                "sequence": int(getattr(waypoint, "sequence")),
                "name": str(getattr(waypoint, "name", "SCAN")),
                "zoneId": getattr(waypoint, "zone_id", None),
            }
        with self._scan_context_lock:
            self._scan_context = context

    def __call__(self, event: DetectionEvent) -> None:
        if event.confidence < self._minimum_confidence:
            print(
                "[EVENT] detection dropped below confidence threshold "
                f"eventId={event.event_id} confidence={event.confidence:.3f} "
                f"threshold={self._minimum_confidence:.3f}"
            )
            return
        if event.event_type == "RECYCLING_AREA_FULL" and event.patrol_id is not None:
            with self._recycling_lock:
                if event.patrol_id in self._recycling_patrol_ids:
                    print(
                        "[EVENT] recycling-area duplicate suppressed "
                        f"eventId={event.event_id} patrolId={event.patrol_id}"
                    )
                    return
        if event.event_type == "EMERGENCY" and callable(
            self._emergency_stop_sink
        ):
            try:
                # Use the same accepted detection threshold as alert delivery.
                # Stop before pose/outbox persistence so a storage failure cannot
                # leave the chassis moving.
                self._emergency_stop_sink(event)
            except Exception as exc:
                print(
                    "[EVENT] emergency stop callback failed "
                    f"eventId={event.event_id} type={type(exc).__name__}"
                )
        pose = self._state_store.get_pose()
        if pose is None:
            print(f"[EVENT] detection dropped without map pose eventId={event.event_id}")
            return
        x = float(pose.x)
        y = float(pose.y)
        context = {"x": x, "y": y, "heading": float(pose.heading)}
        with self._scan_context_lock:
            scan_context = (
                dict(self._scan_context)
                if self._scan_context is not None
                else None
            )
        if scan_context is not None:
            context["scan"] = scan_context
        if event.event_type == "VEHICLE_DETECTED":
            get_range = getattr(
                self._vehicle_range_source,
                "get_front_range",
                None,
            )
            range_m = get_range() if callable(get_range) else None
            if range_m is None:
                print(
                    "[EVENT] vehicle detection dropped without fresh LiDAR range "
                    f"eventId={event.event_id}"
                )
                return
            try:
                vehicle = project_front_vehicle(
                    pose,
                    float(range_m),
                    camera_yaw_deg=self._camera_yaw_deg,
                )
            except (TypeError, ValueError):
                print(
                    "[EVENT] vehicle detection dropped with invalid LiDAR range "
                    f"eventId={event.event_id}"
                )
                return
            context.update(
                {"x": vehicle.x, "y": vehicle.y, "rangeM": vehicle.range_m}
            )
            zone_id = scan_context.get("zoneId") if scan_context else None
            print(
                "[VEHICLE_LOCALIZATION] "
                f"robot=({x:.3f},{y:.3f}) heading={float(pose.heading):.2f} "
                f"frontRange={vehicle.range_m:.3f} "
                f"estimatedVehicle=({vehicle.x:.3f},{vehicle.y:.3f}) "
                f"zone={zone_id or 'UNAVAILABLE'}"
            )
        elif event.event_type in _DIRECTIONAL_ENVIRONMENT_EVENT_TYPES:
            localized = self._localize_environment_detection(event, pose)
            if localized is not None:
                context.update(
                    {
                        "x": localized.x,
                        "y": localized.y,
                        "rangeM": localized.range_m,
                        "bearingDeg": localized.bearing_deg,
                        "locationMethod": "BBOX_LIDAR",
                    }
                )
                print(
                    "[ENVIRONMENT_LOCALIZATION] "
                    f"eventType={event.event_type} "
                    f"robot=({x:.3f},{y:.3f}) "
                    f"bearingDeg={localized.bearing_deg:.2f} "
                    f"range={localized.range_m:.3f} "
                    f"estimated=({localized.x:.3f},{localized.y:.3f})"
                )
            else:
                # Preserve the previous behavior rather than losing a report
                # when a low floor object is below the 2D LiDAR scan plane.
                context["locationMethod"] = "ROBOT_OBSERVATION_POSE"
                print(
                    "[ENVIRONMENT_LOCALIZATION] fallback to observation pose "
                    f"eventType={event.event_type} eventId={event.event_id}"
                )
        recycling_reserved = False
        if event.event_type == "RECYCLING_AREA_FULL" and event.patrol_id is not None:
            with self._recycling_lock:
                if event.patrol_id in self._recycling_patrol_ids:
                    return
                self._recycling_patrol_ids.add(event.patrol_id)
                recycling_reserved = True
        try:
            self._outbox.enqueue(event, context=context)
        except BaseException:
            if recycling_reserved:
                with self._recycling_lock:
                    self._recycling_patrol_ids.discard(event.patrol_id)
            raise

    def _localize_environment_detection(
        self,
        event: DetectionEvent,
        pose: Any,
    ) -> Any | None:
        get_range = getattr(self._vehicle_range_source, "get_range_at_angle", None)
        if not callable(get_range):
            return None
        frame_width = event.attributes.get("frameWidth")
        if frame_width is None:
            return None
        try:
            bearing_deg = bbox_center_bearing_deg(
                event.bbox,
                float(frame_width),
                camera_horizontal_fov_deg=self._camera_horizontal_fov_deg,
                camera_yaw_deg=self._camera_yaw_deg,
            )
            range_m = get_range(
                self._lidar_forward_center_angle_deg + bearing_deg
            )
            if range_m is None:
                return None
            return project_detection(
                pose,
                float(range_m),
                bearing_deg=bearing_deg,
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return None


class EventDeliveryWorker:
    """Retry-safe outbox worker; an event is never recreated after eventId."""

    def __init__(
        self,
        outbox: DetectionOutbox,
        *,
        backend_factory: BackendFactory | None = None,
        poll_interval_seconds: float = 1.0,
        token_file: str | os.PathLike[str] | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._outbox = outbox
        self._backend_factory = backend_factory or self._client_from_environment
        self._poll_interval_seconds = poll_interval_seconds
        self._token_file = Path(
            token_file
            or os.getenv(
                "AIOT_BACKEND_TOKEN_FILE",
                "/var/lib/aiot/secrets/robot-service-token",
            )
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="backend-event-delivery",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self._poll_interval_seconds * 2))
        self._thread = None

    def readiness_for_new_patrol(self) -> tuple[bool, str]:
        if self._outbox.pending_count() > 0:
            return False, "EVENT_OUTBOX_NOT_DRAINED"
        try:
            self._backend_factory()
        except Exception:
            return False, "BACKEND_DELIVERY_NOT_CONFIGURED"
        return True, "READY"

    def process_available(self, maximum: int = 100) -> int:
        processed = 0
        for path in self._outbox.pending_paths()[:maximum]:
            if self._process(path):
                processed += 1
        return processed

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.process_available()
            except Exception as exc:
                print(f"[EVENT] worker error type={type(exc).__name__}")
            self._stop_event.wait(self._poll_interval_seconds)

    def _process(self, path: Path) -> bool:
        try:
            payload = self._outbox.read(path)
            context = payload.get("context")
            if not isinstance(context, dict):
                return False
            client = self._backend_factory()
            event_id = payload.get("backendEventId")
            if event_id is None:
                event_id = self._create_backend_event(client, payload, context)
                if event_id is None:
                    self._complete_delivery(path, payload)
                    return True
                payload["backendEventId"] = int(event_id)
                payload["deliveryState"] = "PENDING_EVIDENCE"
                payload["attempts"] = int(payload.get("attempts", 0)) + 1
                payload.pop("lastError", None)
                self._outbox.update(path, payload)

            evidence = Path(str(payload["evidencePath"]))
            client.upload_evidence(
                int(event_id), evidence, captured_at=str(payload["observedAt"])
            )
            self._complete_delivery(path, payload)
            return True
        except Exception as exc:
            try:
                payload = self._outbox.read(path)
                payload["attempts"] = int(payload.get("attempts", 0)) + 1
                payload["lastError"] = type(exc).__name__
                self._outbox.update(path, payload)
            except Exception:
                pass
            return False

    def _complete_delivery(self, path: Path, payload: Mapping[str, Any]) -> None:
        self._outbox.complete(path)
        if os.getenv("AIOT_DELETE_DELIVERED_EVIDENCE", "true").lower() not in {
            "true",
            "1",
            "yes",
            "on",
        }:
            return
        try:
            evidence_root = Path("/var/lib/aiot/evidence").resolve()
            evidence = Path(str(payload["evidencePath"]))
            resolved = evidence.resolve()
            if evidence.is_symlink() or not resolved.is_relative_to(evidence_root):
                return
            evidence.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[EVENT] evidence cleanup failed type={type(exc).__name__}")

    @staticmethod
    def _create_backend_event(
        client: RobotBackendClient,
        payload: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> int | None:
        attributes = payload.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        plate = attributes.get("plateText") or attributes.get("licensePlate")
        if payload.get("eventType") == "VEHICLE_DETECTED" and not (
            isinstance(plate, str) and plate.strip()
        ):
            return None
        confidence = float(payload.get("confidence", 0.0))
        details = (
            f"{payload['eventType']}, confidence={confidence:.2f}, "
            f"camera={payload['cameraId']}, trackId={payload['trackId']}"
        )
        scan = context.get("scan")
        if isinstance(scan, Mapping):
            details += (
                f", scanSequence={scan.get('sequence')}, "
                f"scanZoneId={scan.get('zoneId')}"
            )
        location_method = context.get("locationMethod")
        if isinstance(location_method, str) and location_method:
            details += f", locationMethod={location_method}"
        if context.get("rangeM") is not None:
            details += f", rangeM={float(context['rangeM']):.2f}"
        detection_count = attributes.get("detectionCount")
        if isinstance(detection_count, int) and detection_count > 0:
            details += f", detectedCount={detection_count}"
        if isinstance(plate, str) and plate.strip():
            response = client.check_vehicles(
                [
                    {
                        "tempId": str(payload["eventId"]),
                        "x": float(context["x"]),
                        "y": float(context["y"]),
                        "licensePlate": plate.strip(),
                        "eventDetails": details,
                        "occurredAt": str(payload["observedAt"]),
                    }
                ]
            )
            data = response.get("data")
            violations = data.get("violations", []) if isinstance(data, dict) else []
            for violation in violations:
                if str(violation.get("tempId")) == str(payload["eventId"]):
                    return int(violation["eventId"])
            return None

        event_type = str(payload["eventType"])
        risk_level = str(attributes.get("riskLevel") or "NORMAL").upper()
        if risk_level not in {"LOW", "NORMAL", "EMERGENCY"}:
            risk_level = "NORMAL"
        response = client.create_event(
            {
                "eventType": event_type,
                "eventTitle": str(attributes.get("eventTitle") or event_type),
                "eventDetails": details,
                "occurredAt": str(payload["observedAt"]),
                "x": float(context["x"]),
                "y": float(context["y"]),
                "riskLevel": risk_level,
            }
        )
        data = response.get("data")
        if not isinstance(data, dict) or data.get("eventId") is None:
            raise RuntimeError("backend event response has no eventId")
        return int(data["eventId"])

    def _client_from_environment(self) -> RobotBackendClient:
        token = os.getenv("AIOT_BACKEND_ACCESS_TOKEN", "").strip()
        if not token:
            try:
                token = self._token_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise RuntimeError("backend token is unavailable") from exc
        config = BackendConfig(
            base_url=os.environ["AIOT_BACKEND_BASE_URL"],
            access_token=token,
            timeout_seconds=float(os.getenv("AIOT_BACKEND_TIMEOUT_SEC", "10")),
        )
        return RobotBackendClient(config)
