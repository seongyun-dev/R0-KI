from __future__ import annotations

import unittest
from types import SimpleNamespace

from integration.mapping_motion_sink import MappingMotionSink
from mission.mission_controller import MissionController


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

    def test_temporary_zero_preserves_authorization_and_can_resume(self) -> None:
        self.sink(command(46))
        self.sink(command(0, reason="OBSTACLE"))
        self.sink(command(47, 82))

        self.assertEqual(self.mission.started, [(46, 80), (0, 80), (47, 82)])
        self.assertEqual(self.mission.stops, 0)
        self.assertEqual(self.reasons, [])
        self.assertTrue(self.sink.driving)

    def test_frontier_transition_zero_does_not_release_motion(self) -> None:
        self.sink(command(46))
        self.sink(command(0, reason="MAPPING_NAV2_STOP"))

        self.assertEqual(self.mission.started[-1], (0, 80))
        self.assertEqual(self.mission.stops, 0)
        self.assertFalse(self.sink.driving)

    def test_temporary_zero_keeps_the_real_mission_generation(self) -> None:
        mission = MissionController(steering_center_deg=80)
        sink = MappingMotionSink(
            SimpleNamespace(mission=mission),
            lambda: self.mapping,
        )

        sink(command(46, 79))
        generation = mission.snapshot().generation
        sink(command(0, 80, "MAPPING_NAV2_STOP"))
        sink(command(47, 81))

        snapshot = mission.snapshot()
        self.assertTrue(snapshot.patrol_active)
        self.assertEqual(snapshot.generation, generation)
        self.assertEqual(snapshot.command.speed, 47)

    def test_explicit_lifecycle_release_stops_and_keeps_reason(self) -> None:
        self.sink(command(46))
        self.sink.release_motion_authorization("STOP_MAPPING")

        self.assertEqual(self.mission.stops, 1)
        self.assertEqual(self.reasons, ["STOP_MAPPING"])
        self.assertFalse(self.sink.driving)

    def test_failed_explicit_release_is_reported_and_reraised(self) -> None:
        self.sink(command(46))
        self.mission.stop_error = RuntimeError("serial down")
        with self.assertRaises(RuntimeError):
            self.sink.release_motion_authorization("STOP_MAPPING")
        self.assertEqual(self.reasons, ["STOP_MAPPING_STOP_FAILED"])
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
