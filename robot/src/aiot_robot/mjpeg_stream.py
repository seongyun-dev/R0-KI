"""Small in-memory MJPEG server for the Jetson AI preview.

The server intentionally binds to loopback by default.  A TLS reverse proxy or
an SSH reverse tunnel is responsible for carrying the stream off the robot.
"""

from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlsplit


BOUNDARY = "roki-frame"


class MjpegFrameHub:
    """Keep only the newest encoded frame and wake all connected viewers."""

    def __init__(
        self,
        *,
        max_frame_age_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_frame_age_seconds <= 0:
            raise ValueError("MJPEG max frame age must be positive")
        self._condition = threading.Condition()
        self._frame: bytes | None = None
        self._sequence = 0
        self._published_at: float | None = None
        self._max_frame_age_seconds = max_frame_age_seconds
        self._clock = clock

    def publish(self, frame: bytes) -> int:
        if not frame:
            raise ValueError("MJPEG frame must not be empty")
        with self._condition:
            self._frame = bytes(frame)
            self._sequence += 1
            self._published_at = self._clock()
            self._condition.notify_all()
            return self._sequence

    def wait_for_frame(
        self, after_sequence: int, timeout: float
    ) -> tuple[int, bytes] | None:
        deadline = time.monotonic() + max(timeout, 0.0)
        with self._condition:
            while True:
                now = self._clock()
                if (
                    self._frame is not None
                    and self._sequence > after_sequence
                    and self._published_at is not None
                    and now - self._published_at
                    <= self._max_frame_age_seconds
                ):
                    return self._sequence, self._frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)

    def health(self) -> dict[str, object]:
        with self._condition:
            age = (
                None
                if self._published_at is None
                else max(0.0, self._clock() - self._published_at)
            )
            return {
                "ready": (
                    self._frame is not None
                    and age is not None
                    and age <= self._max_frame_age_seconds
                ),
                "sequence": self._sequence,
                "frameAgeSeconds": None if age is None else round(age, 3),
            }


class MjpegPublisher:
    """Throttle and JPEG-encode annotated OpenCV frames."""

    def __init__(
        self,
        hub: MjpegFrameHub,
        *,
        quality: int = 70,
        max_fps: float = 8.0,
    ) -> None:
        if not 1 <= quality <= 100:
            raise ValueError("MJPEG quality must be between 1 and 100")
        if max_fps <= 0:
            raise ValueError("MJPEG max FPS must be positive")
        self._hub = hub
        self._quality = quality
        self._minimum_interval = 1.0 / max_fps
        self._next_frame_at = 0.0
        self._lock = threading.Lock()

    def publish(self, frame: Any, cv2_module: Any) -> bool:
        now = time.monotonic()
        with self._lock:
            if now < self._next_frame_at:
                return False
            self._next_frame_at = now + self._minimum_interval
        ok, encoded = cv2_module.imencode(
            ".jpg",
            frame,
            [int(cv2_module.IMWRITE_JPEG_QUALITY), self._quality],
        )
        if not ok:
            return False
        self._hub.publish(encoded.tobytes())
        return True


class _MjpegHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class MjpegStreamServer:
    def __init__(
        self,
        bind: str,
        port: int,
        *,
        quality: int = 70,
        max_fps: float = 8.0,
        max_frame_age_seconds: float = 2.0,
    ) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("MJPEG port must be between 0 and 65535")
        self.hub = MjpegFrameHub(
            max_frame_age_seconds=max_frame_age_seconds,
        )
        self.publisher = MjpegPublisher(
            self.hub,
            quality=quality,
            max_fps=max_fps,
        )
        handler = _handler_for(self.hub)
        self._server = _MjpegHttpServer((bind, port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ai-mjpeg-http",
            daemon=True,
        )

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)


def _handler_for(hub: MjpegFrameHub) -> type[BaseHTTPRequestHandler]:
    class MjpegHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            path = urlsplit(self.path).path
            if path == "/health":
                self._serve_health()
                return
            if path == "/stream.mjpg":
                self._serve_stream()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _serve_health(self) -> None:
            body = json.dumps(hub.health(), separators=(",", ":")).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_stream(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                f"multipart/x-mixed-replace; boundary={BOUNDARY}",
            )
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            sequence = 0
            try:
                while True:
                    current = hub.wait_for_frame(sequence, timeout=10.0)
                    if current is None:
                        continue
                    sequence, frame = current
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return MjpegHandler
