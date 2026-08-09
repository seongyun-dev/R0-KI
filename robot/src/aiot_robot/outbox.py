"""Atomic local persistence for AI detections awaiting Robot enrichment/REST."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .contracts import DetectionEvent


class DetectionOutbox:
    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def enqueue(
        self,
        event: DetectionEvent,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Path:
        destination = self.directory / f"{event.event_id}.json"
        payload = event.to_dict()
        payload["deliveryState"] = "PENDING_CONTEXT"
        if context is not None:
            payload["context"] = dict(context)
            payload["deliveryState"] = "PENDING_EVENT"
        payload["attempts"] = 0

        self._atomic_write(destination, payload)
        return destination

    def pending_paths(self) -> tuple[Path, ...]:
        return tuple(sorted(self.directory.glob("*.json")))

    def pending_count(self) -> int:
        return len(self.pending_paths())

    @staticmethod
    def read(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("outbox item must be a JSON object")
        return payload

    def update(self, path: Path, payload: Mapping[str, Any]) -> None:
        if path.parent.resolve() != self.directory.resolve():
            raise ValueError("outbox path is outside the configured directory")
        self._atomic_write(path, dict(payload))

    def complete(self, path: Path) -> None:
        if path.parent.resolve() != self.directory.resolve():
            raise ValueError("outbox path is outside the configured directory")
        path.unlink(missing_ok=True)

    def _atomic_write(self, destination: Path, payload: Mapping[str, Any]) -> None:

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}.", suffix=".tmp", dir=self.directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
