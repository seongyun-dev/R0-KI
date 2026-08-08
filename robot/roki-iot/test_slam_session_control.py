from __future__ import annotations

import unittest
from types import SimpleNamespace

from integration.localization_mode import ServiceCallFailed
from integration.slam_session_control import (
    FreshMapTracker,
    RosSlamSessionControl,
)


class FakeReset:
    class Request:
        def __init__(self) -> None:
            self.pause_new_measurements = True

    class Response:
        RESULT_SUCCESS = 0


class FreshMapTrackerTest(unittest.TestCase):
    def test_marker_separates_old_observations_from_a_new_session(self) -> None:
        tracker = FreshMapTracker()
        tracker.note_scan(100, arrival=1.0)
        tracker.note_map(100, arrival=1.1)
        marker = tracker.marker()

        self.assertFalse(tracker.fresh_map_ready(marker))

        tracker.note_scan(200, arrival=2.0)
        tracker.note_map(200, arrival=2.1)
        self.assertTrue(tracker.fresh_map_ready(marker))

    def test_map_arriving_before_the_first_new_scan_is_not_fresh(self) -> None:
        tracker = FreshMapTracker()
        marker = tracker.marker()

        tracker.note_map(200, arrival=1.0)
        tracker.note_scan(200, arrival=2.0)

        self.assertFalse(tracker.fresh_map_ready(marker))

    def test_map_with_an_older_ros_stamp_is_not_fresh(self) -> None:
        tracker = FreshMapTracker()
        marker = tracker.marker()
        tracker.note_scan(300, arrival=1.0)
        tracker.note_map(299, arrival=1.1)

        self.assertFalse(tracker.fresh_map_ready(marker))

        tracker.note_map(300, arrival=1.2)
        self.assertTrue(tracker.fresh_map_ready(marker))

    def test_zero_scan_stamp_falls_back_to_arrival_order(self) -> None:
        tracker = FreshMapTracker()
        marker = tracker.marker()
        tracker.note_scan(0, arrival=1.0)
        tracker.note_map(0, arrival=1.1)

        self.assertTrue(tracker.fresh_map_ready(marker))


class RosSlamSessionControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.control = RosSlamSessionControl()
        self.control._reset_type = FakeReset
        self.control._reset_client = object()

    def test_reset_resumes_measurements_and_accepts_success(self) -> None:
        captured = []

        def invoke(client, request, description):
            captured.append((client, request, description))
            return SimpleNamespace(result=FakeReset.Response.RESULT_SUCCESS)

        self.control._invoke = invoke

        self.control.reset_slam()

        self.assertEqual(len(captured), 1)
        self.assertFalse(captured[0][1].pause_new_measurements)
        self.assertEqual(captured[0][2], "/slam_toolbox/reset")

    def test_reset_rejects_non_success_result(self) -> None:
        self.control._invoke = lambda *_: SimpleNamespace(result=7)

        with self.assertRaises(ServiceCallFailed):
            self.control.reset_slam()

    def test_fresh_map_wait_times_out_without_new_observations(self) -> None:
        marker = self.control.marker()

        self.assertFalse(self.control.wait_for_fresh_map(marker, timeout_sec=0))

    def test_fresh_map_wait_requires_transform_after_new_scan_and_map(self) -> None:
        marker = self.control.marker()
        with self.control._condition:
            self.control._tracker.note_scan(100, arrival=1.0)
            self.control._tracker.note_map(100, arrival=1.1)
        self.control._wait_for_transform = lambda deadline: True

        self.assertTrue(self.control.wait_for_fresh_map(marker, timeout_sec=1))

    def test_localization_wait_requires_a_new_scan(self) -> None:
        marker = self.control.marker()
        self.assertFalse(
            self.control.wait_for_localization_ready(marker, timeout_sec=0)
        )

        with self.control._condition:
            self.control._tracker.note_scan(100, arrival=1.0)
        self.control._wait_for_transform = lambda deadline: True
        self.assertTrue(
            self.control.wait_for_localization_ready(marker, timeout_sec=1)
        )

    def test_stamp_ns_reads_a_ros_header(self) -> None:
        message = SimpleNamespace(
            header=SimpleNamespace(stamp=SimpleNamespace(sec=12, nanosec=34))
        )

        self.assertEqual(self.control._stamp_ns(message), 12_000_000_034)

    def test_transform_freshness_uses_the_transform_header_stamp(self) -> None:
        now_ns = 20_000_000_000
        self.control._node = SimpleNamespace(
            get_clock=lambda: SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=now_ns)
            )
        )
        transform = SimpleNamespace(
            header=SimpleNamespace(
                stamp=SimpleNamespace(sec=19, nanosec=500_000_000)
            )
        )

        self.assertTrue(self.control._transform_is_fresh(transform))


if __name__ == "__main__":
    unittest.main()
