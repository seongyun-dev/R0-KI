"""Atomic local persistence for AI detections awaiting Robot enrichment/REST."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .contracts import DetectionEvent


class DetectionOutbox:
    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def enqueue(self, event: DetectionEvent) -> Path:
        destination = self.directory / f"{event.event_id}.json"
        payload = event.to_dict()
        payload["deliveryState"] = "PENDING_CONTEXT"

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{event.event_id}.", suffix=".tmp", dir=self.directory
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
        return destination
