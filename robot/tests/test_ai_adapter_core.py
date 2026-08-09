import unittest

from aiot_robot.ai_adapter_core import build_detection_message
from aiot_robot.contracts import DetectionEvent
import json


class AiAdapterCoreTest(unittest.TestCase):
    def test_unsupported_backend_event_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported backend eventType"):
            build_detection_message(
                {"eventType": "UNKNOWN"},
                evidence_path="/var/lib/aiot/evidence/e1.jpg",
                patrol_id=9,
                event_id="e1",
                observed_at_fallback="2026-08-03T00:00:01Z",
            )

    def test_existing_pipeline_event_becomes_ros_contract(self) -> None:
        message = build_detection_message(
            {
                "eventType": "TRASH_DETECTED",
                "eventTitle": "trash",
                "eventDetails": "TRASH, confidence=0.93, camera=A, trackId=42",
                "occurredAt": "2026-08-03T00:00:00Z",
                "riskLevel": "NORMAL",
            },
            evidence_path="/var/lib/aiot/evidence/e1.jpg",
            patrol_id=9,
            event_id="e1",
            observed_at_fallback="2026-08-03T00:00:01Z",
        )
        event = DetectionEvent.from_json(json.dumps(message))
        self.assertEqual(event.event_type, "TRASH_DETECTED")
        self.assertEqual(event.camera_id, "A")
        self.assertEqual(event.track_id, "42")
        self.assertEqual(event.confidence, 0.93)

    def test_vehicle_is_neutral_and_keeps_plate_for_backend_decision(self) -> None:
        message = build_detection_message(
            {
                "tempId": "v1",
                "licensePlate": "12가3456",
                "eventDetails": "LICENSE_PLATE, confidence=0.88",
                "occurredAt": "2026-08-03T00:00:00Z",
            },
            evidence_path="/var/lib/aiot/evidence/v1.jpg",
            patrol_id=9,
            event_id="v1-event",
            observed_at_fallback="2026-08-03T00:00:01Z",
            vehicle=True,
        )
        self.assertEqual(message["eventType"], "VEHICLE_DETECTED")
        self.assertEqual(message["attributes"]["plateText"], "12가3456")


if __name__ == "__main__":
    unittest.main()
