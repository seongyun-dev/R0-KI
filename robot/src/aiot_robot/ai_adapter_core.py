"""ROS-independent conversion from the existing AI REST payload to v1 events."""

from __future__ import annotations

import re
import math
from typing import Any, Mapping, Sequence


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
}


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
