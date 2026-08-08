from __future__ import annotations

import unittest
from types import SimpleNamespace

from integration.mapping_motion_sink import MappingMotionSink


class FakeMission:
    def __init__(self) -> None:
        self.started: list[tuple[int, int]] = []
        self.stops = 0
        self.stop_error: Exception | None = None

    def start_patrol(self, *, speed: int, steering_deg: int) -> None:
        self.started.append((speed, steering_deg))

    def stop_patrol(self) -> None:
        self.stops += 1
        if self.stop_error is not None:
            raise self.stop_error


def command(speed: int, steering: int = 80, reason: str | None = None):
    return SimpleNamespace(speed_pwm=speed, steering_deg=steering, stop_reason=reason)


class MappingMotionSinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mission = FakeMission()
        self.runtime = SimpleNamespace(mission=self.mission)
        self.mapping = SimpleNamespace(motion_active=True)
        self.reasons: list[str] = []
        self.sink = MappingMotionSink(
            self.runtime,
            lambda: self.mapping,
            stop_reporter=self.reasons.append,
        )

    def test_drives_only_while_the_mapping_session_is_active(self) -> None:
        self.sink(command(46, 70))
        self.assertEqual(self.mission.started, [(46, 70)])
        self.assertTrue(self.sink.driving)

        # Session ends mid-drive: the very next command must stop the chassis.
        self.mapping.motion_active = False
        self.sink(command(46, 70))
        self.assertEqual(self.mission.started, [(46, 70)])
        self.assertEqual(self.mission.stops, 1)
        self.assertFalse(self.sink.driving)
        self.assertEqual(self.reasons, ["MAPPING_NOT_DRIVING"])

    def test_no_mapping_runtime_never_moves(self) -> None:
        sink = MappingMotionSink(self.runtime, lambda: None)
        sink(command(51, 120))
        self.assertEqual(self.mission.started, [])
        self.assertEqual(self.mission.stops, 1)

    def test_zero_speed_stops_and_keeps_the_nav2_reason(self) -> None:
        self.sink(command(46))
        self.sink(command(0, reason="OBSTACLE"))
        self.assertEqual(self.mission.stops, 1)
        self.assertEqual(self.reasons, ["OBSTACLE"])
        self.assertFalse(self.sink.driving)

    def test_failed_stop_is_reported_and_reraised(self) -> None:
        self.mission.stop_error = RuntimeError("serial down")
        with self.assertRaises(RuntimeError):
            self.sink(command(0))
        self.assertEqual(self.reasons, ["MAPPING_NAV2_STOP_STOP_FAILED"])
        self.assertFalse(self.sink.driving)

    def test_repeated_stops_report_once(self) -> None:
        self.mapping.motion_active = False
        self.sink(command(46))
        self.sink(command(46))
        self.assertEqual(self.reasons, [])
        # Only the first stop reaches the serial link; the smoother's ramp-down
        # messages must not re-send it. See MappingMotionSink._stop.
        self.assertEqual(self.mission.stops, 1)

    def test_a_failed_stop_is_retried_on_the_next_command(self) -> None:
        self.mapping.motion_active = False
        self.mission.stop_error = RuntimeError("serial down")
        with self.assertRaises(RuntimeError):
            self.sink(command(46))
        self.mission.stop_error = None
        self.sink(command(46))
        self.assertEqual(self.mission.stops, 2)

    def test_driving_again_rearms_the_stop(self) -> None:
        self.sink(command(46))
        self.mapping.motion_active = False
        self.sink(command(46))
        self.mapping.motion_active = True
        self.sink(command(46))
        self.mapping.motion_active = False
        self.sink(command(46))
        self.assertEqual(self.mission.stops, 2)
        self.assertEqual(self.reasons, ["MAPPING_NOT_DRIVING", "MAPPING_NOT_DRIVING"])


if __name__ == "__main__":
    unittest.main()
