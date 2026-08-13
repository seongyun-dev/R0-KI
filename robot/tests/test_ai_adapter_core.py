import unittest

from aiot_robot.ai_adapter_core import (
    DemoVehiclePlatePolicy,
    build_detection_message,
    collapse_recycling_events_for_frame,
    demo_vehicle_plate_collector,
    detection_context_from_pipeline_payload,
    preserve_pipeline_detection_context,
)
from aiot_robot.contracts import DetectionEvent
import json


class AiAdapterCoreTest(unittest.TestCase):
    @staticmethod
    def _licence(track_id=7, bbox=None, confidence=0.8):
        return {
            "class_name": "licence",
            "track_id": track_id,
            "bbox": bbox or [10, 20, 110, 60],
            "confidence": confidence,
            "camera": "A",
        }

    def test_demo_plate_waits_for_stable_track_and_falls_back_after_ocr_failure(self):
        policy = DemoVehiclePlatePolicy("254러1559", stable_frames=3)
        detection = self._licence()

        self.assertEqual(policy.observe([detection], [], camera="A"), [])
        self.assertEqual(policy.observe([detection], [], camera="A"), [])
        records = policy.observe([detection], [], camera="A")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["plate"], "254러1559")
        self.assertEqual(records[0]["_demoOcrPlate"], "UNAVAILABLE")
        self.assertEqual(records[0]["_demoSource"], "OCR_FALLBACK")

    def test_demo_plate_overrides_successful_ocr_without_changing_context(self):
        policy = DemoVehiclePlatePolicy("254러1559", stable_frames=3)
        detection = self._licence(bbox=[30, 40, 130, 80])
        actual = {
            "track_id": 7,
            "plate": "254러1558",
            "confidence": 0.91,
            "bbox": [30, 40, 130, 80],
            "camera": "A",
        }

        policy.observe([detection], [actual], camera="A")
        policy.observe([detection], [], camera="A")
        records = policy.observe([detection], [], camera="A")

        self.assertEqual(records[0]["plate"], "254러1559")
        self.assertEqual(records[0]["_demoOcrPlate"], "254러1558")
        self.assertEqual(records[0]["_demoSource"], "OCR_OVERRIDE")
        self.assertEqual(records[0]["track_id"], 7)
        self.assertEqual(records[0]["bbox"], [30, 40, 130, 80])
        self.assertEqual(records[0]["camera"], "A")

    def test_demo_plate_requires_consecutive_frames(self):
        policy = DemoVehiclePlatePolicy("254러1559", stable_frames=3)
        detection = self._licence()

        policy.observe([detection], [], camera="A")
        policy.observe([], [], camera="A")
        policy.observe([detection], [], camera="A")
        policy.observe([detection], [], camera="A")

        self.assertEqual(policy.all_records(), [])

    def test_demo_plate_emits_each_track_only_once(self):
        policy = DemoVehiclePlatePolicy("254러1559", stable_frames=2)
        detection = self._licence()

        policy.observe([detection], [], camera="A")
        first = policy.observe([detection], [], camera="A")
        repeated = policy.observe([detection], [], camera="A")

        self.assertEqual(len(first), 1)
        self.assertEqual(repeated, [])
        self.assertEqual(len(policy.all_records()), 1)

    def test_demo_plate_keeps_position_fields_outside_plate_policy(self):
        context = {
            "x": -1.25,
            "y": 3.75,
            "bbox": [10, 20, 110, 60],
            "frameWidth": 640,
        }
        policy = DemoVehiclePlatePolicy("254러1559", stable_frames=2)
        detection = self._licence(bbox=context["bbox"])

        policy.observe([detection], [], camera="A")
        record = policy.observe([detection], [], camera="A")[0]

        self.assertEqual(record["bbox"], context["bbox"])
        self.assertEqual((context["x"], context["y"]), (-1.25, 3.75))
        self.assertEqual(context["frameWidth"], 640)

    def test_demo_off_returns_exact_original_collector_class(self):
        class ExistingCollector:
            pass

        self.assertIs(demo_vehicle_plate_collector(ExistingCollector, None), ExistingCollector)
        self.assertIs(demo_vehicle_plate_collector(ExistingCollector, ""), ExistingCollector)

    def test_demo_collector_calls_ocr_on_every_frame_before_fallback(self):
        class ExistingCollector:
            def __init__(self):
                self.calls = 0

            def update(self, detections, frame, frame_idx, camera=None):
                del detections, frame, frame_idx, camera
                self.calls += 1
                return []

            def all_plates(self):
                return []

        Collector = demo_vehicle_plate_collector(ExistingCollector, "254러1559")
        collector = Collector()
        detection = self._licence()

        self.assertEqual(collector.update([detection], None, 1, camera="A"), [])
        self.assertEqual(collector.update([detection], None, 2, camera="A"), [])
        result = collector.update([detection], None, 3, camera="A")

        self.assertEqual(collector._delegate.calls, 3)
        self.assertEqual(result[0]["plate"], "254러1559")
        self.assertEqual(len(collector.all_plates()), 1)

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
