import unittest

from aiot_robot.ai_adapter_core import (
    build_detection_message,
    collapse_recycling_events_for_frame,
    detection_context_from_pipeline_payload,
    preserve_pipeline_detection_context,
)
from aiot_robot.contracts import DetectionEvent
import json


class AiAdapterCoreTest(unittest.TestCase):
    def test_collapses_recycling_scene_into_one_union_bbox(self) -> None:
        events = [
            {
                "eventType": "RECYCLING_AREA_FULL",
                "eventDetails": "BIN_OVERFLOW, confidence=0.90",
                "_bbox": [10, 20, 30, 40],
            },
            {
                "eventType": "RECYCLING_AREA_FULL",
                "eventDetails": "BAG_OUTSIDE, confidence=0.80",
                "_bbox": [100, 80, 150, 160],
            },
            {"eventType": "TRASH_DETECTED", "_bbox": [300, 200, 320, 220]},
        ]
        detections = [
            {"class_name": "bin_overflow", "bbox": [10, 20, 30, 40]},
            {"class_name": "bag_outside", "bbox": [100, 80, 150, 160]},
            {"class_name": "small_trash", "bbox": [300, 200, 320, 220]},
        ]

        collapsed = collapse_recycling_events_for_frame(events, detections)

        self.assertEqual(len(collapsed), 2)
        recycling = collapsed[0]
        self.assertEqual(recycling["_bbox"], [10.0, 20.0, 150.0, 160.0])
        self.assertEqual(recycling["_detectionCount"], 2)
        self.assertIn("detectedCount=2", recycling["eventDetails"])
        self.assertEqual(collapsed[1]["eventType"], "TRASH_DETECTED")

    def test_preserves_legacy_pipeline_detection_context(self) -> None:
        payload = preserve_pipeline_detection_context(
            {
                "_bbox": [10, 20, 110, 220],
                "_frameWidth": 640,
                "_camera": "A",
                "_trackId": 42,
            },
            {"eventType": "TRASH_DETECTED"},
        )

        self.assertEqual(
            detection_context_from_pipeline_payload(payload),
            {
                "bbox": [10, 20, 110, 220],
                "frameWidth": 640,
                "cameraId": "A",
                "trackId": 42,
            },
        )

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

    def test_recycling_count_is_preserved_in_ros_attributes(self) -> None:
        payload = preserve_pipeline_detection_context(
            {"_detectionCount": 3},
            {
                "eventType": "RECYCLING_AREA_FULL",
                "eventDetails": "BIN_OVERFLOW, confidence=0.91",
            },
        )

        message = build_detection_message(
            payload,
            evidence_path="/var/lib/aiot/evidence/recycling.jpg",
            patrol_id=9,
            event_id="recycling-1",
            observed_at_fallback="2026-08-03T00:00:01Z",
        )

        self.assertEqual(message["attributes"]["detectionCount"], 3)

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
