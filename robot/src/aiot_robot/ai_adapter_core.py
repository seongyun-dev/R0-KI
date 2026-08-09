"""ROS-independent conversion from the existing AI REST payload to v1 events."""

from __future__ import annotations

import re
from typing import Any, Mapping


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


def build_detection_message(
    payload: Mapping[str, Any],
    *,
    evidence_path: str,
    patrol_id: int,
    event_id: str,
    observed_at_fallback: str,
    vehicle: bool = False,
) -> dict[str, Any]:
    if patrol_id <= 0:
        raise ValueError("patrol_id must be positive")
    details = str(payload.get("eventDetails") or "")
    match = _DETAIL_PATTERN.search(details)
    confidence = float(match.group("confidence")) if match else 0.0
    confidence = max(0.0, min(1.0, confidence))
    camera = (match.group("camera") if match else None) or "unknown"
    track = (match.group("track") if match else None) or str(
        payload.get("tempId") or event_id
    )
    attributes: dict[str, Any] = {}
    if vehicle:
        attributes["plateText"] = str(payload.get("licensePlate") or "")
    if payload.get("eventTitle") is not None:
        attributes["eventTitle"] = str(payload["eventTitle"])
    if payload.get("riskLevel") is not None:
        attributes["riskLevel"] = str(payload["riskLevel"])
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
        "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
        "attributes": attributes,
    }
