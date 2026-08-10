"""Thread-safe patrol activation gate for the Jetson AI pipeline."""

from __future__ import annotations

import threading


class PatrolActivation:
    """Pause expensive inference while keeping the model warm in memory."""

    def __init__(self) -> None:
        self._enabled = threading.Event()

    @property
    def enabled(self) -> bool:
        return self._enabled.is_set()

    def enable(self) -> None:
        self._enabled.set()

    def disable(self) -> None:
        self._enabled.clear()

    def wait(self, timeout: float) -> bool:
        return self._enabled.wait(timeout=max(0.0, timeout))
