from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

from safety.obstacle_guard import (
    FrontObstacleDetector,
    ObstacleDetectorSettings,
)
from sensors.ros_lidar_health_bridge import (
    RosLidarHealthBridge,
    RosLidarHealthSettings,
)
from state.robot_state import ObstacleState, RobotStateStore


class CountingRobotStateStore(RobotStateStore):
    def __init__(self) -> None:
        super().__init__()
        self.obstacle_update_count = 0

    def update_obstacle(self, obstacle: ObstacleState) -> None:
        self.obstacle_update_count += 1
        super().update_obstacle(obstacle)


class RecordingObstacleDetector:
    def __init__(self) -> None:
        self.evaluate_count = 0
        self.reset_count = 0

    def evaluate_scan(self, **_kwargs):
        self.evaluate_count += 1
        return SimpleNamespace(
            obstacle=ObstacleState(
                status="STOP",
                direction="FRONT",
                reason_message="blocked",
            )
        )

    def reset(self) -> None:
        self.reset_count += 1


class RosLidarHealthBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = RobotStateStore()
        self.bridge = RosLidarHealthBridge(
            state_store=self.store,
            settings=RosLidarHealthSettings(
                scan_topic="/scan",
                scan_timeout_sec=1.0,
            ),
            monotonic_clock=lambda: 10.0,
        )

    def test_scan_sets_normal_and_camera_remains_disconnected(self) -> None:
        self.bridge.record_scan(received_at=10.0)

        self.assertEqual(self.bridge.evaluate(now=10.999), "NORMAL")
        status = self.store.get_status()
        self.assertEqual(status.lidar, "NORMAL")
        self.assertEqual(status.camera, "DISCONNECTED")

    def test_scan_timeout_sets_disconnected(self) -> None:
        self.bridge.record_scan(received_at=10.0)

        self.assertEqual(self.bridge.evaluate(now=11.0), "DISCONNECTED")
        self.assertEqual(
            self.store.get_status().lidar,
            "DISCONNECTED",
        )

    def test_no_scan_remains_disconnected(self) -> None:
        self.assertEqual(self.bridge.evaluate(now=10.0), "DISCONNECTED")
        self.assertEqual(
            self.store.get_status().lidar,
            "DISCONNECTED",
        )

    def test_front_range_uses_nearest_samples_and_expires(self) -> None:
        distance = self.bridge.ingest_scan(
            ranges=[9.0, 2.0, 1.5, 1.6, 9.0],
            angle_min_rad=-0.2,
            angle_increment_rad=0.1,
            range_min_m=0.12,
            range_max_m=12.0,
            received_at=10.0,
        )

        self.assertAlmostEqual(distance, 1.6)
        self.assertAlmostEqual(self.bridge.get_front_range(now=10.5), 1.6)
        self.assertIsNone(self.bridge.get_front_range(now=11.0))

    def test_front_range_rejects_invalid_values(self) -> None:
        distance = self.bridge.ingest_scan(
            ranges=[float("nan"), float("inf"), 9.0],
            angle_min_rad=-0.1,
            angle_increment_rad=0.1,
            range_min_m=0.12,
            range_max_m=12.0,
            received_at=10.0,
        )

        self.assertIsNone(distance)
        self.assertIsNone(self.bridge.get_front_range(now=10.5))

    def test_vehicle_range_uses_lidar_frame_center_angle(self) -> None:
        bridge = RosLidarHealthBridge(
            state_store=self.store,
            settings=RosLidarHealthSettings(
                scan_topic="/scan",
                scan_timeout_sec=1.0,
                vehicle_center_angle_deg=90.0,
            ),
            monotonic_clock=lambda: 10.0,
        )

        distance = bridge.ingest_scan(
            ranges=[0.4, 3.0, 1.2],
            angle_min_rad=0.0,
            angle_increment_rad=math.pi / 4,
            range_min_m=0.12,
            range_max_m=12.0,
            received_at=10.0,
        )

        self.assertAlmostEqual(distance, 1.2)

    def test_scan_updates_obstacle_without_touching_motion_or_safety(self) -> None:
        bridge = RosLidarHealthBridge(
            state_store=self.store,
            settings=RosLidarHealthSettings(
                scan_topic="/scan",
                scan_timeout_sec=1.0,
            ),
            obstacle_detector=FrontObstacleDetector(
                ObstacleDetectorSettings(30.0, 0.6, 0.7)
            ),
            obstacle_activity_check=lambda: True,
            monotonic_clock=lambda: 10.0,
        )
        scan = SimpleNamespace(
            ranges=[1.0, 0.4, 1.0],
            angle_min=-0.1,
            angle_increment=0.1,
            range_min=0.12,
            range_max=12.0,
        )

        bridge._on_scan(scan)

        status = self.store.get_status()
        self.assertEqual(status.obstacle.status, "STOP")
        self.assertEqual(status.obstacle.direction, "FRONT")
        self.assertEqual(status.camera, "DISCONNECTED")
        self.assertEqual(status.motor, "DISCONNECTED")
        self.assertEqual(status.line_sensor, "DISCONNECTED")
        self.assertIsNone(self.store.snapshot().safety_decision)

    def _clear_sink_bridge(self, resumes, active=lambda: True):
        """STOP 0.6 / CLEAR 0.7 hysteresis 를 가진 브릿지와 resume 기록기."""

        bridge = RosLidarHealthBridge(
            state_store=self.store,
            settings=RosLidarHealthSettings("/scan", 1.0),
            obstacle_detector=FrontObstacleDetector(
                ObstacleDetectorSettings(30.0, 0.6, 0.7)
            ),
            obstacle_activity_check=active,
            monotonic_clock=lambda: 10.0,
        )
        bridge.set_obstacle_clear_sink(lambda: resumes.append(1))
        return bridge

    @staticmethod
    def _scan(front_range):
        return SimpleNamespace(
            ranges=[1.0, front_range, 1.0],
            angle_min=-0.1,
            angle_increment=0.1,
            range_min=0.12,
            range_max=12.0,
        )

    def test_obstacle_clear_after_stop_requests_resume_once(self) -> None:
        resumes: list[int] = []
        bridge = self._clear_sink_bridge(resumes)

        bridge._on_scan(self._scan(0.4))
        self.assertEqual(self.store.get_status().obstacle.status, "STOP")
        self.assertEqual(resumes, [], "STOP 중에는 재개하지 않는다")

        bridge._on_scan(self._scan(1.5))

        self.assertEqual(self.store.get_status().obstacle.status, "CLEAR")
        self.assertEqual(resumes, [1], "STOP -> CLEAR 전이에서 한 번만 재개")

        bridge._on_scan(self._scan(1.5))
        self.assertEqual(resumes, [1], "CLEAR 유지 중에는 재개를 반복하지 않는다")

    def test_clear_without_prior_stop_never_resumes(self) -> None:
        """정상 주행 중의 CLEAR 스캔이 일시정지를 임의로 풀면 안 된다."""

        resumes: list[int] = []
        bridge = self._clear_sink_bridge(resumes)

        for _ in range(3):
            bridge._on_scan(self._scan(1.5))

        self.assertEqual(resumes, [])

    def test_hysteresis_band_holds_stop_and_does_not_resume(self) -> None:
        """0.6~0.7 사이는 아직 해제가 아니므로 재개하지 않는다."""

        resumes: list[int] = []
        bridge = self._clear_sink_bridge(resumes)

        bridge._on_scan(self._scan(0.4))
        bridge._on_scan(self._scan(0.65))

        self.assertEqual(self.store.get_status().obstacle.status, "STOP")
        self.assertEqual(resumes, [])

    def test_operation_end_drops_the_latch_so_next_run_is_clean(self) -> None:
        """운행 종료로 detection이 꺼지면 다음 운행 첫 CLEAR가 재개를 부르지 않는다."""

        resumes: list[int] = []
        active = {"on": True}
        bridge = self._clear_sink_bridge(resumes, active=lambda: active["on"])

        bridge._on_scan(self._scan(0.4))
        active["on"] = False
        bridge._on_scan(self._scan(1.5))
        active["on"] = True
        bridge._on_scan(self._scan(1.5))

        self.assertEqual(resumes, [])

    def test_resume_failure_does_not_kill_the_scan_callback(self) -> None:
        bridge = self._clear_sink_bridge([])
        bridge.set_obstacle_clear_sink(
            lambda: (_ for _ in ()).throw(RuntimeError("nav2 down"))
        )

        bridge._on_scan(self._scan(0.4))
        bridge._on_scan(self._scan(1.5))

        # 예외가 전파되면 이후 CLEAR 판정 자체가 멈춘다.
        self.assertEqual(self.store.get_status().obstacle.status, "CLEAR")

    def test_inactive_scan_clears_stale_stop_once_without_detection(self) -> None:
        store = CountingRobotStateStore()
        store.update_obstacle(
            ObstacleState("STOP", "FRONT", "blocked")
        )
        store.obstacle_update_count = 0
        detector = RecordingObstacleDetector()
        bridge = RosLidarHealthBridge(
            state_store=store,
            settings=RosLidarHealthSettings("/scan", 1.0),
            obstacle_detector=detector,
            obstacle_activity_check=lambda: False,
            monotonic_clock=lambda: 10.0,
        )
        scan = SimpleNamespace(
            ranges=[1.0, 0.4, 1.0],
            angle_min=-0.1,
            angle_increment=0.1,
            range_min=0.12,
            range_max=12.0,
        )

        bridge._on_scan(scan)
        bridge._on_scan(scan)

        self.assertEqual(detector.evaluate_count, 0)
        self.assertEqual(store.get_status().obstacle, ObstacleState())
        self.assertEqual(store.obstacle_update_count, 1)

    def test_active_scan_detects_then_inactive_transition_resets(self) -> None:
        store = CountingRobotStateStore()
        detector = RecordingObstacleDetector()
        activity = {"active": True}
        bridge = RosLidarHealthBridge(
            state_store=store,
            settings=RosLidarHealthSettings("/scan", 1.0),
            obstacle_detector=detector,
            obstacle_activity_check=lambda: activity["active"],
            monotonic_clock=lambda: 10.0,
        )
        scan = SimpleNamespace(
            ranges=[1.0, 0.4, 1.0],
            angle_min=-0.1,
            angle_increment=0.1,
            range_min=0.12,
            range_max=12.0,
        )

        bridge._on_scan(scan)
        self.assertEqual(detector.evaluate_count, 1)
        self.assertEqual(store.get_status().obstacle.status, "STOP")

        activity["active"] = False
        bridge.evaluate(now=10.0)
        bridge.evaluate(now=10.0)

        self.assertEqual(store.get_status().obstacle, ObstacleState())
        self.assertEqual(detector.reset_count, 1)
        self.assertEqual(store.obstacle_update_count, 2)

    def test_detection_resumes_immediately_when_operation_becomes_active(self) -> None:
        detector = RecordingObstacleDetector()
        activity = {"active": False}
        bridge = RosLidarHealthBridge(
            state_store=self.store,
            settings=RosLidarHealthSettings("/scan", 1.0),
            obstacle_detector=detector,
            obstacle_activity_check=lambda: activity["active"],
            monotonic_clock=lambda: 10.0,
        )
        scan = SimpleNamespace(
            ranges=[1.0, 0.4, 1.0],
            angle_min=-0.1,
            angle_increment=0.1,
            range_min=0.12,
            range_max=12.0,
        )

        bridge._on_scan(scan)
        activity["active"] = True
        bridge._on_scan(scan)

        self.assertEqual(detector.evaluate_count, 1)
        self.assertEqual(self.store.get_status().obstacle.status, "STOP")


if __name__ == "__main__":
    unittest.main()
