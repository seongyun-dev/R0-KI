"""Exact HTTP transport for the current backend Robot event endpoints."""

from __future__ import annotations

import errno
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4


class BackendError(RuntimeError):
    """Backend transport or API contract failure without exposing credentials."""


class BackendTransportError(BackendError):
    """The request could not reach Backend; a configured local route may be used."""


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

    def get_navigation_config(
        self, *, timeout_seconds: float | None = None
    ) -> Mapping[str, Any]:
        """Fetch the Robot-token-scoped map, zones and ordered route."""

        return self._get_json(
            "/api/robot/navigation-config",
            timeout_seconds=timeout_seconds,
        )

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

    def upload_map(
        self,
        mapping_session_id: int,
        command_id: str,
        map_image: str | os.PathLike[str],
        *,
        resolution: float,
        origin_x: float,
        origin_y: float,
        origin_yaw: float,
    ) -> Mapping[str, Any]:
        """Upload the exact PNG + ROS metadata contract owned by Backend."""

        if isinstance(mapping_session_id, bool) or mapping_session_id < 1:
            raise ValueError("mapping_session_id must be positive")
        if not command_id:
            raise ValueError("command_id is required")
        path = Path(map_image)
        if not path.is_file() or path.suffix.lower() != ".png":
            raise ValueError("map_image must be an existing PNG file")
        if resolution <= 0:
            raise ValueError("resolution must be positive")
        boundary = f"aiot-map-{uuid4().hex}"
        body = self._multipart_body(
            boundary=boundary,
            fields=(
                ("commandId", command_id),
                ("resolution", format(resolution, ".10g")),
                ("originX", format(origin_x, ".10g")),
                ("originY", format(origin_y, ".10g")),
                ("originYaw", format(origin_yaw, ".10g")),
            ),
            file_field="mapImage",
            file_path=path,
            file_content_type="image/png",
        )
        return self._request(
            f"/api/map/mapping-sessions/{mapping_session_id}/map",
            body,
            f"multipart/form-data; boundary={boundary}",
        )

    def _post_json(
        self, endpoint: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        return self._request(endpoint, body, "application/json")

    def _get_json(
        self,
        endpoint: str,
        *,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        return self._request_json(
            endpoint,
            method="GET",
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _multipart_body(
        *,
        boundary: str,
        fields: tuple[tuple[str, str], ...],
        file_field: str,
        file_path: Path,
        file_content_type: str,
    ) -> bytes:
        body = bytearray()
        for name, value in fields:
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
            body.extend(value.encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f"Content-Type: {file_content_type}\r\n\r\n".encode())
        body.extend(file_path.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return bytes(body)

    def _request(
        self, endpoint: str, body: bytes, content_type: str
    ) -> Mapping[str, Any]:
        return self._request_json(
            endpoint,
            method="POST",
            body=body,
            content_type=content_type,
        )

    def _request_json(
        self,
        endpoint: str,
        *,
        method: str,
        body: bytes | None = None,
        content_type: str | None = None,
        timeout_seconds: float | None = None,
    ) -> Mapping[str, Any]:
        url = f"{self._config.base_url.rstrip('/')}{endpoint}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._config.access_token}",
        }
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers=headers,
        )
        request_timeout = self._config.timeout_seconds
        if timeout_seconds is not None:
            if timeout_seconds <= 0:
                raise ValueError("timeout_seconds must be positive")
            request_timeout = min(request_timeout, float(timeout_seconds))
        try:
            with self._urlopen(
                request, timeout=request_timeout
            ) as response:
                response_body = response.read(1024 * 1024)
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", "replace")
            raise BackendError(f"backend HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if _is_genuine_transport_failure(exc):
                raise BackendTransportError("backend connection failed") from exc
            raise BackendError("backend secure connection failed") from exc
        except OSError as exc:
            if _is_genuine_transport_failure(exc):
                raise BackendTransportError("backend connection failed") from exc
            raise BackendError("backend secure connection failed") from exc

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


_TRANSPORT_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "ECONNREFUSED", None),
        getattr(errno, "ECONNRESET", None),
        getattr(errno, "ENETDOWN", None),
        getattr(errno, "ENETUNREACH", None),
        getattr(errno, "EHOSTDOWN", None),
        getattr(errno, "EHOSTUNREACH", None),
        getattr(errno, "ETIMEDOUT", None),
        # Winsock values used by CPython on Windows.
        10051,
        10060,
        10061,
        10064,
        10065,
        11001,
    )
    if value is not None
)


def _is_genuine_transport_failure(error: BaseException) -> bool:
    """Classify outages without treating TLS trust/handshake failures as fallback."""

    chain = tuple(_exception_chain(error))
    # SSL errors may wrap socket/OSError causes. Trust and handshake failures
    # always win over an underlying transport-looking errno.
    if any(isinstance(item, ssl.SSLError) for item in chain):
        return False
    for item in chain:
        if isinstance(item, (TimeoutError, socket.gaierror, ConnectionRefusedError)):
            return True
        if isinstance(item, OSError) and item.errno in _TRANSPORT_ERRNOS:
            return True
    return False


def _exception_chain(error: BaseException):
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        if isinstance(current, urllib.error.URLError) and isinstance(
            current.reason, BaseException
        ):
            pending.append(current.reason)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
