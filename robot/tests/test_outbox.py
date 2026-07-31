import json
import tempfile
import unittest
from pathlib import Path

from aiot_robot.contracts import DetectionEvent
from aiot_robot.outbox import DetectionOutbox


class DetectionOutboxTest(unittest.TestCase):
    def test_atomic_event_file(self) -> None:
        event = DetectionEvent.from_json(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "eventId": "event-1",
                    "eventType": "ILLEGAL_PARKING",
                    "cameraId": "front",
                    "trackId": "track-42",
                    "confidence": 0.93,
                    "observedAt": "2026-07-31T05:20:03Z",
                    "evidencePath": "/var/lib/aiot/evidence/event-1.jpg",
                    "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                }
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            path = DetectionOutbox(directory).enqueue(event)
            self.assertEqual(path, Path(directory) / "event-1.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["deliveryState"], "PENDING_CONTEXT")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
