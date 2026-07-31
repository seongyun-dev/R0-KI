"""Exact HTTP transport for the current backend Robot event endpoints."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4


class BackendError(RuntimeError):
    """Backend transport or API contract failure without exposing credentials."""


UrlOpen = Callable[..., Any]


@dataclass(frozen=True)
class BackendConfig:
    base_url: str
    access_token: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("AIOT_BACKEND_BASE_URL must be an absolute HTTPS URL")
        if not self.access_token:
            raise ValueError("AIOT_BACKEND_ACCESS_TOKEN is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    @classmethod
    def from_environment(cls) -> "BackendConfig":
        return cls(
            base_url=os.environ["AIOT_BACKEND_BASE_URL"],
            access_token=os.environ["AIOT_BACKEND_ACCESS_TOKEN"],
            timeout_seconds=float(os.getenv("AIOT_BACKEND_TIMEOUT_SEC", "10")),
        )


class RobotBackendClient:
    """Low-level client; mission code remains responsible for pose/event mapping."""

    def __init__(
        self, config: BackendConfig, *, urlopen: UrlOpen = urllib.request.urlopen
    ) -> None:
        self._config = config
        self._urlopen = urlopen

    def create_event(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._post_json("/api/robot/events", payload)

    def create_events_batch(self, events: list[Mapping[str, Any]]) -> Mapping[str, Any]:
        if not events:
            raise ValueError("events must not be empty")
        return self._post_json("/api/robot/events/batch", {"events": events})

    def check_vehicles(self, vehicles: list[Mapping[str, Any]]) -> Mapping[str, Any]:
        if not vehicles:
            raise ValueError("vehicles must not be empty")
        return self._post_json("/api/robot/vehicle-checks", {"vehicles": vehicles})

    def upload_evidence(
        self,
        event_id: int,
        file_path: str | os.PathLike[str],
        *,
        media_type: str = "IMAGE",
        captured_at: str | None = None,
    ) -> Mapping[str, Any]:
        if event_id < 1:
            raise ValueError("event_id must be positive")
        path = Path(file_path)
        if not path.is_file():
            raise ValueError(f"evidence file does not exist: {path}")

        boundary = f"aiot-{uuid4().hex}"
        fields = [("mediaType", media_type)]
        if captured_at is not None:
            fields.append(("capturedAt", captured_at))
        body = bytearray()
        for name, value in fields:
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{path.name}"\r\n'
            ).encode("utf-8")
        )
        body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return self._request(
            f"/api/events/{event_id}/evidence",
            bytes(body),
            f"multipart/form-data; boundary={boundary}",
        )

    def _post_json(
        self, endpoint: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        return self._request(endpoint, body, "application/json")

    def _request(
        self, endpoint: str, body: bytes, content_type: str
    ) -> Mapping[str, Any]:
        url = f"{self._config.base_url.rstrip('/')}{endpoint}"
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._config.access_token}",
                "Content-Type": content_type,
            },
        )
        try:
            with self._urlopen(
                request, timeout=self._config.timeout_seconds
            ) as response:
                response_body = response.read(1024 * 1024)
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", "replace")
            raise BackendError(f"backend HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"backend connection failed: {exc.reason}") from exc

        try:
            decoded = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackendError("backend returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise BackendError("backend response must be a JSON object")
        if decoded.get("success") is not True:
            raise BackendError(
                f"backend rejected request: {decoded.get('code', 'UNKNOWN')}"
            )
        return decoded
