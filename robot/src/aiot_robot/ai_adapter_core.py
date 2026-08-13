"""ROS-independent conversion from the existing AI REST payload to v1 events."""

from __future__ import annotations

import re
import math
from typing import Any, Callable, Mapping, Sequence


_DETAIL_PATTERN = re.compile(
    r"confidence=(?P<confidence>\d+(?:\.\d+)?)"
    r"(?:, camera=(?P<camera>[^,]+))?"
    r"(?:, trackId=(?P<track>[^,]+))?"
)
_BACKEND_EVENT_TYPES = frozenset(
    {
        "ILLEGAL_PARKING",
        "UNREGISTERED_VEHICLE",
        "TRASH_DETECTED",
        "RECYCLING_AREA_FULL",
        "EMERGENCY",
    }
)
_PIPELINE_CONTEXT_FIELDS = {
    "_bbox": "bbox",
    "_frameWidth": "frameWidth",
    "_camera": "cameraId",
    "_trackId": "trackId",
    "_detectionCount": "detectionCount",
}
_RECYCLING_CLASS_NAMES = frozenset({"bin_overflow", "bag_outside"})


class DemoVehiclePlatePolicy:
    """Emit one forced plate after a tracked licence persists for three frames."""

    def __init__(self, forced_plate: str, *, stable_frames: int = 3) -> None:
        plate = str(forced_plate).strip()
        if not plate:
            raise ValueError("forced demo plate must not be empty")
        if stable_frames < 2:
            raise ValueError("stable_frames must be at least 2")
        self.forced_plate = plate
        self.stable_frames = int(stable_frames)
        self._streaks: dict[tuple[str, int], int] = {}
        self._latest_ocr: dict[tuple[str, int], dict[str, Any]] = {}
        self._emitted: set[tuple[str, int]] = set()
        self._records: list[dict[str, Any]] = []

    @staticmethod
    def _track_id(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            track_id = int(value)
        except (TypeError, ValueError):
            return None
        return track_id if track_id >= 0 else None

    @staticmethod
    def _confidence(item: Mapping[str, Any]) -> float:
        try:
            value = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) else 0.0

    def observe(
        self,
        detections: Sequence[Mapping[str, Any]],
        ocr_records: Sequence[Mapping[str, Any]],
        *,
        camera: str | None,
    ) -> list[dict[str, Any]]:
        """Return at most one demo vehicle record per camera/track pair."""

        camera_key = str(camera or "")
        for record in ocr_records:
            track_id = self._track_id(record.get("track_id"))
            if track_id is not None:
                self._latest_ocr[(camera_key, track_id)] = dict(record)

        current: dict[tuple[str, int], Mapping[str, Any]] = {}
        for detection in detections:
            if detection.get("class_name") != "licence":
                continue
            track_id = self._track_id(detection.get("track_id"))
            if track_id is None:
                continue
            key = (camera_key, track_id)
            previous = current.get(key)
            if previous is None or self._confidence(detection) > self._confidence(previous):
                current[key] = detection

        for key in list(self._streaks):
            if key[0] == camera_key and key not in current:
                self._streaks.pop(key, None)

        emitted: list[dict[str, Any]] = []
        for key, detection in current.items():
            if key in self._emitted:
                continue
            self._streaks[key] = self._streaks.get(key, 0) + 1
            if self._streaks[key] < self.stable_frames:
                continue

            ocr_record = self._latest_ocr.get(key)
            ocr_plate = str((ocr_record or {}).get("plate") or "").strip()
            bbox = (ocr_record or {}).get("bbox")
            if bbox is None:
                bbox = detection.get("bbox")
            confidence_source = ocr_record if ocr_record is not None else detection
            record = {
                "track_id": key[1],
                "plate": self.forced_plate,
                "confidence": self._confidence(confidence_source),
                "bbox": list(bbox) if bbox is not None else None,
                "camera": camera if camera is not None else detection.get("camera"),
                "_demoOcrPlate": ocr_plate or "UNAVAILABLE",
                "_demoSource": "OCR_OVERRIDE" if ocr_plate else "OCR_FALLBACK",
            }
            emitted.append(record)
            self._records.append(
                {key: value for key, value in record.items() if not key.startswith("_demo")}
            )
            self._emitted.add(key)
            self._streaks.pop(key, None)
        return emitted

    def all_records(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._records]

    def reset(self) -> None:
        """Forget demo-only observations when a different patrol starts."""

        self._streaks.clear()
        self._latest_ocr.clear()
        self._emitted.clear()
        self._records.clear()


def demo_vehicle_plate_collector(
    original_collector: type,
    forced_plate: str | None,
    *,
    patrol_id_provider: Callable[[], int | None] | None = None,
) -> type:
    """Wrap the OCR collector only when the optional demo plate is non-empty."""

    plate = str(forced_plate or "").strip()
    if not plate:
        return original_collector

    class DemoPlateCollector:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._delegate = original_collector(*args, **kwargs)
            self._policy = DemoVehiclePlatePolicy(plate)
            self._patrol_id: int | None = None

        def _reset_for_new_patrol(self) -> None:
            patrol_id = patrol_id_provider() if patrol_id_provider is not None else None
            if patrol_id is None or patrol_id == self._patrol_id:
                return
            self._policy.reset()
            self._patrol_id = patrol_id

        def update(
            self,
            detections: Any,
            frame: Any,
            frame_idx: Any,
            camera: str | None = None,
        ) -> list[dict[str, Any]]:
            # This runs on the inference thread, so policy state cannot race the
            # ROS control callback that changes the active patrol ID.
            self._reset_for_new_patrol()
            ocr_records = self._delegate.update(
                detections, frame, frame_idx, camera=camera
            )
            records = self._policy.observe(detections, ocr_records, camera=camera)
            for record in records:
                print(
                    "[DEMO_VEHICLE] "
                    f"trackId={record['track_id']} stable=true "
                    f"ocrPlate={record.pop('_demoOcrPlate')} "
                    f"finalPlate={record['plate']} "
                    f"source={record.pop('_demoSource')}",
                    flush=True,
                )
            return records

        def all_plates(self) -> list[dict[str, Any]]:
            return self._policy.all_records()

        def __getattr__(self, name: str) -> Any:
            return getattr(self._delegate, name)

    return DemoPlateCollector


def scope_vehicle_dedupe_to_patrol(manager: Any, patrol_id: int | None) -> bool:
    """Clear only vehicle-plate dedupe state when the patrol ID changes.

    The external pipeline keeps one EventManager alive for the AI process. Its
    vehicle key is based on the plate string, so a forced demo plate would
    otherwise be suppressed in every later patrol. Duplicate ENABLE messages
    for the same patrol deliberately do not clear the state again.
    """

    if patrol_id is None:
        return False
    if getattr(manager, "_aiot_vehicle_patrol_id", None) == patrol_id:
        return False

    created = getattr(manager, "created", None)
    if isinstance(created, set):
        created.difference_update(
            key
            for key in tuple(created)
            if isinstance(key, tuple) and key and key[0] == "vehicle_plate"
        )
    manager._aiot_vehicle_patrol_id = patrol_id
    return True


def collapse_recycling_events_for_frame(
    events: Sequence[Mapping[str, Any]],
    detections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Represent one recycling-area scene with one event and one union bbox."""

    recycling_boxes: list[tuple[float, float, float, float]] = []
    for detection in detections:
        if detection.get("class_name") not in _RECYCLING_CLASS_NAMES:
            continue
        bbox = detection.get("bbox")
        if not isinstance(bbox, Sequence) or isinstance(bbox, (str, bytes)):
            continue
        if len(bbox) != 4:
            continue
        try:
            x1, y1, x2, y2 = (float(value) for value in bbox)
        except (TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in (x1, y1, x2, y2)) and (
            x1 >= 0 and y1 >= 0 and x2 > x1 and y2 > y1
        ):
            recycling_boxes.append((x1, y1, x2, y2))

    union_bbox = None
    if recycling_boxes:
        union_bbox = [
            min(box[0] for box in recycling_boxes),
            min(box[1] for box in recycling_boxes),
            max(box[2] for box in recycling_boxes),
            max(box[3] for box in recycling_boxes),
        ]

    collapsed: list[dict[str, Any]] = []
    recycling_added = False
    for event in events:
        copied = dict(event)
        if copied.get("eventType") != "RECYCLING_AREA_FULL":
            collapsed.append(copied)
            continue
        if recycling_added:
            continue
        recycling_added = True
        if union_bbox is not None:
            copied["_bbox"] = union_bbox
            copied["_detectionCount"] = len(recycling_boxes)
            details = str(copied.get("eventDetails") or "")
            copied["eventDetails"] = (
                f"{details}, detectedCount={len(recycling_boxes)}"
                if details
                else f"detectedCount={len(recycling_boxes)}"
            )
        collapsed.append(copied)
    return collapsed


def preserve_pipeline_detection_context(
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep AI-private detection metadata across its legacy REST boundary."""

    enriched = dict(payload)
    for source, destination in _PIPELINE_CONTEXT_FIELDS.items():
        value = event.get(source)
        if value is not None:
            enriched[destination] = value
    return enriched


def detection_context_from_pipeline_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return only the camera metadata accepted by the Robot ROS contract."""

    return {
        "bbox": payload.get("bbox"),
        "frameWidth": payload.get("frameWidth"),
        "cameraId": payload.get("cameraId"),
        "trackId": payload.get("trackId"),
    }


def build_detection_message(
    payload: Mapping[str, Any],
    *,
    evidence_path: str,
    patrol_id: int,
    event_id: str,
    observed_at_fallback: str,
    vehicle: bool = False,
    detection_bbox_xyxy: Sequence[Any] | None = None,
    frame_width: Any | None = None,
    camera_id: Any | None = None,
    track_id: Any | None = None,
) -> dict[str, Any]:
    if patrol_id <= 0:
        raise ValueError("patrol_id must be positive")
    details = str(payload.get("eventDetails") or "")
    match = _DETAIL_PATTERN.search(details)
    confidence = float(match.group("confidence")) if match else 0.0
    confidence = max(0.0, min(1.0, confidence))
    camera = str(camera_id).strip() if camera_id is not None else ""
    camera = camera or (match.group("camera") if match else None) or "unknown"
    track = str(track_id).strip() if track_id is not None else ""
    track = track or (match.group("track") if match else None) or str(
        payload.get("tempId") or event_id
    )
    attributes: dict[str, Any] = {}
    if vehicle:
        attributes["plateText"] = str(payload.get("licensePlate") or "")
    if payload.get("eventTitle") is not None:
        attributes["eventTitle"] = str(payload["eventTitle"])
    if payload.get("riskLevel") is not None:
        attributes["riskLevel"] = str(payload["riskLevel"])
    detection_count = payload.get("detectionCount")
    if detection_count is not None:
        if (
            isinstance(detection_count, bool)
            or not isinstance(detection_count, int)
            or detection_count <= 0
        ):
            raise ValueError("detectionCount must be a positive integer")
        attributes["detectionCount"] = detection_count
    bbox = {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    if detection_bbox_xyxy is not None:
        if len(detection_bbox_xyxy) != 4:
            raise ValueError("detection bbox must contain x1,y1,x2,y2")
        x1, y1, x2, y2 = (float(value) for value in detection_bbox_xyxy)
        if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
            raise ValueError("detection bbox must be finite")
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError("detection bbox is invalid")
        bbox = {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
    if frame_width is not None:
        parsed_frame_width = float(frame_width)
        if not math.isfinite(parsed_frame_width) or parsed_frame_width <= 0:
            raise ValueError("frame width must be positive and finite")
        attributes["frameWidth"] = parsed_frame_width
    event_type = "VEHICLE_DETECTED" if vehicle else str(payload.get("eventType"))
    if not vehicle and event_type not in _BACKEND_EVENT_TYPES:
        raise ValueError(f"unsupported backend eventType: {event_type}")
    return {
        "schemaVersion": 1,
        "eventId": event_id,
        "patrolId": patrol_id,
        "eventType": event_type,
        "cameraId": camera,
        "trackId": track,
        "confidence": confidence,
        "observedAt": str(payload.get("occurredAt") or observed_at_fallback),
        "evidencePath": evidence_path,
        "bbox": bbox,
        "attributes": attributes,
    }
