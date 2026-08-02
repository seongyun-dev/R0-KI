"""Live readiness gate used by the patrol-start pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .contracts import AiStatus


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    mode: str
    reason: str
    age_seconds: float | None


class AiGate:
    """Tracks status arrival time and exposes an explicit limited-mode decision."""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self._status: AiStatus | None = None
        self._received_at: float | None = None

    @property
    def status(self) -> AiStatus | None:
        return self._status

    def record(self, status: AiStatus, now: float | None = None) -> None:
        self._status = status
        self._received_at = time.monotonic() if now is None else now

    def decision(self, now: float | None = None) -> GateDecision:
        if self._status is None or self._received_at is None:
            return GateDecision(False, "LIMITED", "AI_STATUS_MISSING", None)

        current = time.monotonic() if now is None else now
        age = max(0.0, current - self._received_at)
        if age > self.timeout_seconds:
            return GateDecision(False, "LIMITED", "AI_STATUS_STALE", age)

        if not self._status.ready_for_patrol:
            reason = self._status.error_code or f"AI_{self._status.state}"
            return GateDecision(False, "LIMITED", reason, age)

        return GateDecision(True, "READY", "AI_READY", age)
