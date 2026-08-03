"""Durable Robot-owned delivery of AI detections to backend REST APIs."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .backend_client import BackendConfig, RobotBackendClient
from .contracts import DetectionEvent
from .outbox import DetectionOutbox


BackendFactory = Callable[[], RobotBackendClient]


class DetectionRecorder:
    """Attach the Robot-owned map pose before an AI event reaches disk."""

    def __init__(self, outbox: DetectionOutbox, state_store: Any) -> None:
        self._outbox = outbox
        self._state_store = state_store

    def __call__(self, event: DetectionEvent) -> None:
        pose = self._state_store.get_pose()
        if pose is None:
            print(f"[EVENT] detection dropped without map pose eventId={event.event_id}")
            return
        context = {
            "x": float(pose.x),
            "y": float(pose.y),
            "heading": float(pose.heading),
        }
        self._outbox.enqueue(event, context=context)


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
