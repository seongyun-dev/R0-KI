"""Versioned JSON contracts exchanged between Robot and AI over ROS 2."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Mapping


SCHEMA_VERSION = 1
_EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_AI_STATES = frozenset({"STARTING", "READY", "DEGRADED", "ERROR", "STOPPED"})


class ContractError(ValueError):
    """Raised when a ROS JSON message does not match the v1 contract."""


def _object_from_json(raw: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ContractError("message must be a JSON object")
    if value.get("schemaVersion") != SCHEMA_VERSION:
        raise ContractError("unsupported schemaVersion")
    return value


def _required_string(data: Mapping[str, Any], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")
    return value


def _required_bool(data: Mapping[str, Any], name: str) -> bool:
    value = data.get(name)
    if not isinstance(value, bool):
        raise ContractError(f"{name} must be a boolean")
    return value


def _optional_string(data: Mapping[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError(f"{name} must be a string or null")
    return value


def _optional_bool(data: Mapping[str, Any], name: str) -> bool | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ContractError(f"{name} must be a boolean or null")
    return value


def _optional_positive_int(data: Mapping[str, Any], name: str) -> int | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(f"{name} must be a positive integer or null")
    return value


def _timestamp(data: Mapping[str, Any], name: str) -> str:
    value = _required_string(data, name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{name} must include a timezone")
    return value


@dataclass(frozen=True)
class AiStatus:
    state: str
    ready: bool
    camera_ready: bool
    engine_ready: bool
    inference_ready: bool
    heartbeat_at: str
    detection_enabled: bool | None = None
    patrol_id: int | None = None
    model_version: str | None = None
    error_code: str | None = None
    message: str | None = None

    @property
    def ready_for_patrol(self) -> bool:
        return (
            self.state == "READY"
            and self.ready
            and self.camera_ready
            and self.engine_ready
            and self.inference_ready
        )

    def detection_applied_for(self, patrol_id: int) -> bool:
        """Return true only when matching detection is usable for patrol."""

        return (
            self.ready_for_patrol
            and self.detection_enabled is True
            and self.patrol_id == patrol_id
        )

    @classmethod
    def from_json(cls, raw: str) -> "AiStatus":
        data = _object_from_json(raw)
        state = _required_string(data, "state").upper()
        if state not in _AI_STATES:
            raise ContractError(f"state must be one of {sorted(_AI_STATES)}")
        return cls(
            state=state,
            ready=_required_bool(data, "ready"),
            camera_ready=_required_bool(data, "cameraReady"),
            engine_ready=_required_bool(data, "engineReady"),
            inference_ready=_required_bool(data, "inferenceReady"),
            heartbeat_at=_timestamp(data, "heartbeatAt"),
            detection_enabled=_optional_bool(data, "detectionEnabled"),
            patrol_id=_optional_positive_int(data, "patrolId"),
            model_version=_optional_string(data, "modelVersion"),
            error_code=_optional_string(data, "errorCode"),
            message=_optional_string(data, "message"),
        )


@dataclass(frozen=True)
class DetectionEvent:
    event_id: str
    event_type: str
    camera_id: str
    track_id: str
    confidence: float
    observed_at: str
    evidence_path: str
    bbox: Mapping[str, float]
    attributes: Mapping[str, Any]
    patrol_id: int | None = None

    @classmethod
    def from_json(cls, raw: str) -> "DetectionEvent":
        data = _object_from_json(raw)
        event_id = _required_string(data, "eventId")
        if not _EVENT_ID_PATTERN.fullmatch(event_id):
            raise ContractError("eventId contains unsupported characters")

        confidence_value = data.get("confidence")
        if isinstance(confidence_value, bool) or not isinstance(
            confidence_value, (int, float)
        ):
            raise ContractError("confidence must be a number")
        confidence = float(confidence_value)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ContractError("confidence must be between 0 and 1")

        patrol_id = data.get("patrolId")
        if patrol_id is not None and (
            isinstance(patrol_id, bool) or not isinstance(patrol_id, int) or patrol_id < 1
        ):
            raise ContractError("patrolId must be a positive integer or null")

        bbox_value = data.get("bbox")
        if not isinstance(bbox_value, dict):
            raise ContractError("bbox must be an object")
        bbox: dict[str, float] = {}
        for key in ("x", "y", "width", "height"):
            coordinate = bbox_value.get(key)
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                raise ContractError(f"bbox.{key} must be a number")
            number = float(coordinate)
            if not math.isfinite(number) or number < 0:
                raise ContractError(f"bbox.{key} must be finite and non-negative")
            bbox[key] = number

        attributes_value = data.get("attributes", {})
        if not isinstance(attributes_value, dict):
            raise ContractError("attributes must be an object")

        evidence_path = _required_string(data, "evidencePath")
        evidence_root = PurePosixPath("/var/lib/aiot/evidence")
        evidence = PurePosixPath(evidence_path)
        if (
            not evidence.is_absolute()
            or evidence == evidence_root
            or not evidence.is_relative_to(evidence_root)
            or ".." in evidence.parts
        ):
            raise ContractError("evidencePath must be below /var/lib/aiot/evidence")

        return cls(
            event_id=event_id,
            patrol_id=patrol_id,
            event_type=_required_string(data, "eventType"),
            camera_id=_required_string(data, "cameraId"),
            track_id=_required_string(data, "trackId"),
            confidence=confidence,
            observed_at=_timestamp(data, "observedAt"),
            evidence_path=evidence_path,
            bbox=bbox,
            attributes=dict(attributes_value),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "eventId": self.event_id,
            "patrolId": self.patrol_id,
            "eventType": self.event_type,
            "cameraId": self.camera_id,
            "trackId": self.track_id,
            "confidence": self.confidence,
            "observedAt": self.observed_at,
            "evidencePath": self.evidence_path,
            "bbox": dict(self.bbox),
            "attributes": dict(self.attributes),
        }


def control_message(
    enabled: bool, patrol_id: int | None, requested_at: str, reason: str
) -> str:
    if patrol_id is not None and patrol_id < 1:
        raise ContractError("patrolId must be positive or null")
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "command": "ENABLE" if enabled else "DISABLE",
        "patrolId": patrol_id,
        "requestedAt": requested_at,
        "reason": reason,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
