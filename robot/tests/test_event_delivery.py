from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiot_robot.contracts import DetectionEvent
from aiot_robot.event_delivery import DetectionRecorder, EventDeliveryWorker
from aiot_robot.outbox import DetectionOutbox


def detection(
    event_id: str = "event-1",
    *,
    confidence: float = 0.93,
    event_type: str = "TRASH_DETECTED",
    patrol_id: int = 15,
    bbox: dict | None = None,
    attributes: dict | None = None,
) -> DetectionEvent:
    return DetectionEvent.from_json(
        json.dumps(
            {
                "schemaVersion": 1,
                "eventId": event_id,
                "patrolId": patrol_id,
                "eventType": event_type,
                "cameraId": "front",
                "trackId": "track-42",
                "confidence": confidence,
                "observedAt": "2026-08-03T00:00:00Z",
                "evidencePath": f"/var/lib/aiot/evidence/{event_id}.jpg",
                "bbox": bbox or {"x": 0, "y": 0, "width": 1, "height": 1},
                "attributes": attributes or {"riskLevel": "NORMAL"},
            }
        )
    )


class FakeBackend:
    def __init__(self, *, fail_upload_once: bool = False) -> None:
        self.create_calls = 0
        self.upload_calls = 0
        self.fail_upload_once = fail_upload_once

    def create_event(self, payload):
        self.create_calls += 1
        self.payload = payload
        return {"success": True, "data": {"eventId": 77}}

    def check_vehicles(self, vehicles):
        self.vehicles = vehicles
        return {"success": True, "data": {"violations": []}}

    def upload_evidence(self, event_id, path, *, captured_at=None):
        del event_id, path, captured_at
        self.upload_calls += 1
        if self.fail_upload_once and self.upload_calls == 1:
            raise RuntimeError("temporary upload failure")
        return {"success": True}


class EventDeliveryTest(unittest.TestCase):
    def test_emergency_uses_bbox_direction_and_lidar_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=90.0)
            )
            requested_angles = []
            stopped_events = []
            ranges = SimpleNamespace(
                get_range_at_angle=lambda angle: requested_angles.append(angle) or 2.0
            )
            event = detection(
                "emergency-ranged",
                event_type="EMERGENCY",
                bbox={"x": 270, "y": 100, "width": 100, "height": 100},
                attributes={"riskLevel": "EMERGENCY", "frameWidth": 640},
            )

            DetectionRecorder(
                outbox,
                store,
                vehicle_range_source=ranges,
                camera_horizontal_fov_deg=60,
                lidar_forward_center_angle_deg=90,
                emergency_stop_sink=stopped_events.append,
            )(event)
            item = outbox.read(outbox.pending_paths()[0])

            self.assertEqual(stopped_events, [event])
            self.assertEqual(requested_angles, [90.0])
            self.assertAlmostEqual(item["context"]["x"], 1.0, places=6)
            self.assertAlmostEqual(item["context"]["y"], 4.0, places=6)
            self.assertEqual(item["context"]["locationMethod"], "BBOX_LIDAR")

    def test_trash_uses_bbox_direction_and_lidar_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            requested_angles = []
            ranges = SimpleNamespace(
                get_range_at_angle=lambda angle: requested_angles.append(angle) or 2.0
            )
            event = detection(
                "trash-ranged",
                bbox={"x": 270, "y": 100, "width": 100, "height": 100},
                attributes={"riskLevel": "LOW", "frameWidth": 640},
            )

            DetectionRecorder(
                outbox,
                store,
                vehicle_range_source=ranges,
                camera_horizontal_fov_deg=60,
                lidar_forward_center_angle_deg=90,
            )(event)
            item = outbox.read(outbox.pending_paths()[0])

            self.assertEqual(requested_angles, [90.0])
            self.assertAlmostEqual(item["context"]["x"], 3.0, places=6)
            self.assertAlmostEqual(item["context"]["y"], 2.0, places=6)
            self.assertEqual(item["context"]["locationMethod"], "BBOX_LIDAR")

    def test_trash_without_directional_range_keeps_observation_pose(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            ranges = SimpleNamespace(get_range_at_angle=lambda _angle: None)

            DetectionRecorder(
                outbox,
                store,
                vehicle_range_source=ranges,
                camera_horizontal_fov_deg=60,
            )(
                detection(
                    "trash-fallback",
                    bbox={"x": 270, "y": 100, "width": 100, "height": 100},
                    attributes={"riskLevel": "LOW", "frameWidth": 640},
                )
            )
            item = outbox.read(outbox.pending_paths()[0])

            self.assertEqual(item["context"]["x"], 1.0)
            self.assertEqual(item["context"]["y"], 2.0)
            self.assertEqual(
                item["context"]["locationMethod"],
                "ROBOT_OBSERVATION_POSE",
            )

    def test_recycling_area_is_recorded_once_per_patrol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            recorder = DetectionRecorder(outbox, store)

            recorder(
                detection(
                    "recycling-first",
                    event_type="RECYCLING_AREA_FULL",
                    patrol_id=15,
                )
            )
            recorder(
                detection(
                    "recycling-duplicate",
                    event_type="RECYCLING_AREA_FULL",
                    patrol_id=15,
                )
            )
            recorder(
                detection(
                    "recycling-next-patrol",
                    event_type="RECYCLING_AREA_FULL",
                    patrol_id=16,
                )
            )

            self.assertEqual(outbox.pending_count(), 2)
            self.assertEqual(
                {outbox.read(path)["eventId"] for path in outbox.pending_paths()},
                {"recycling-first", "recycling-next-patrol"},
            )

    def test_low_confidence_recycling_does_not_consume_patrol_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            recorder = DetectionRecorder(outbox, store, minimum_confidence=0.5)

            recorder(
                detection(
                    "recycling-low",
                    event_type="RECYCLING_AREA_FULL",
                    patrol_id=15,
                    confidence=0.49,
                )
            )
            recorder(
                detection(
                    "recycling-accepted",
                    event_type="RECYCLING_AREA_FULL",
                    patrol_id=15,
                    confidence=0.8,
                )
            )

            self.assertEqual(outbox.pending_count(), 1)
            self.assertEqual(
                outbox.read(outbox.pending_paths()[0])["eventId"],
                "recycling-accepted",
            )

    def test_recorder_drops_detection_below_confidence_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            recorder = DetectionRecorder(outbox, store, minimum_confidence=0.5)

            recorder(detection("low-confidence", confidence=0.499))
            recorder(detection("threshold-confidence", confidence=0.5))

            self.assertEqual(outbox.pending_count(), 1)
            self.assertEqual(
                outbox.read(outbox.pending_paths()[0])["eventId"],
                "threshold-confidence",
            )

    def test_vehicle_without_plate_is_completed_without_invalid_backend_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            event = detection("vehicle-no-plate")
            payload = event.to_dict()
            payload["eventType"] = "VEHICLE_DETECTED"
            vehicle = DetectionEvent.from_json(json.dumps(payload))
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            ranges = SimpleNamespace(get_front_range=lambda: 1.0)
            DetectionRecorder(
                outbox, store, vehicle_range_source=ranges
            )(vehicle)
            backend = FakeBackend()
            worker = EventDeliveryWorker(outbox, backend_factory=lambda: backend)

            self.assertEqual(worker.process_available(), 1)
            self.assertEqual(outbox.pending_count(), 0)
            self.assertEqual(backend.create_calls, 0)

    def test_vehicle_uses_lidar_range_instead_of_robot_pose(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            payload = detection("vehicle-ranged").to_dict()
            payload["eventType"] = "VEHICLE_DETECTED"
            payload["attributes"] = {"plateText": "12가3456"}
            vehicle = DetectionEvent.from_json(json.dumps(payload))
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=90.0)
            )
            ranges = SimpleNamespace(get_front_range=lambda: 2.0)
            DetectionRecorder(
                outbox, store, vehicle_range_source=ranges
            )(vehicle)
            backend = FakeBackend()
            worker = EventDeliveryWorker(outbox, backend_factory=lambda: backend)

            self.assertEqual(worker.process_available(), 1)
            self.assertAlmostEqual(backend.vehicles[0]["x"], 1.0, places=6)
            self.assertAlmostEqual(backend.vehicles[0]["y"], 4.0, places=6)

    def test_vehicle_without_fresh_lidar_range_is_not_misplaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            payload = detection("vehicle-no-range").to_dict()
            payload["eventType"] = "VEHICLE_DETECTED"
            payload["attributes"] = {"plateText": "12가3456"}
            vehicle = DetectionEvent.from_json(json.dumps(payload))
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            ranges = SimpleNamespace(get_front_range=lambda: None)

            DetectionRecorder(
                outbox, store, vehicle_range_source=ranges
            )(vehicle)

            self.assertEqual(outbox.pending_count(), 0)

    def test_recorder_drops_detection_until_map_pose_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(get_pose=lambda: None)

            DetectionRecorder(outbox, store)(detection())

            self.assertEqual(outbox.pending_count(), 0)

    def test_recorder_enriches_pose_and_worker_delivers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.2, y=2.3, heading=45.0)
            )
            DetectionRecorder(outbox, store)(detection())
            backend = FakeBackend()
            worker = EventDeliveryWorker(outbox, backend_factory=lambda: backend)

            self.assertEqual(worker.process_available(), 1)
            self.assertEqual(outbox.pending_count(), 0)
            self.assertEqual(backend.payload["x"], 1.2)
            self.assertEqual(backend.payload["riskLevel"], "NORMAL")

    def test_recorder_carries_current_scan_waypoint_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.2, y=2.3, heading=45.0)
            )
            recorder = DetectionRecorder(outbox, store)
            recorder.set_scan_context(
                SimpleNamespace(sequence=4, name="주차장 스캔", zone_id=12)
            )
            recorder(detection("scan-context"))
            backend = FakeBackend()
            worker = EventDeliveryWorker(outbox, backend_factory=lambda: backend)

            self.assertEqual(worker.process_available(), 1)
            self.assertIn("scanSequence=4", backend.payload["eventDetails"])
            self.assertIn("scanZoneId=12", backend.payload["eventDetails"])

    def test_evidence_retry_does_not_recreate_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = DetectionOutbox(directory)
            store = SimpleNamespace(
                get_pose=lambda: SimpleNamespace(x=1.0, y=2.0, heading=0.0)
            )
            DetectionRecorder(outbox, store)(detection("retry-1"))
            backend = FakeBackend(fail_upload_once=True)
            worker = EventDeliveryWorker(outbox, backend_factory=lambda: backend)

            self.assertEqual(worker.process_available(), 0)
            item = outbox.read(outbox.pending_paths()[0])
            self.assertEqual(item["backendEventId"], 77)
            self.assertEqual(worker.process_available(), 1)
            self.assertEqual(backend.create_calls, 1)
            self.assertEqual(backend.upload_calls, 2)


if __name__ == "__main__":
    unittest.main()
