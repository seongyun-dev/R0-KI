"""Linux advisory lock preventing patrol and OTA activation from overlapping."""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO


class PatrolDeploymentGuard:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._stream: IO[str] | None = None

    def acquire(self) -> tuple[bool, str]:
        if self._stream is not None:
            return True, "READY"
        try:
            import fcntl

            stream = self._path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                stream.close()
                return False, "OTA_ACTIVATION_IN_PROGRESS"
            stream.seek(0)
            stream.truncate()
            stream.write(f"patrol-owner-pid={os.getpid()}\n")
            stream.flush()
            self._stream = stream
            return True, "READY"
        except (ImportError, OSError):
            return False, "PATROL_DEPLOY_GUARD_UNAVAILABLE"

    def release(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
