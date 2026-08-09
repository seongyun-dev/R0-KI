"""리셋 이후의 지도만 통과시키는 신선도 검사.

스캔 게이트를 걷어낸 뒤 이전 지도 겹침(직사각형 방이 별모양이 되던 문제)을
막는 것은 두 가지다: 매핑 START 마다의 ``reset_slam()`` 과 여기서 검증하는
``fresh_map_ready``. 리셋이 성공해도 옛 지도가 한 장 더 도착하면 그것을
새 지도로 착각할 수 있고, 그러면 다음 세션이 이전 그래프 위에서 시작한다.

ROS 전송 계층은 여기서 다루지 않는다 -- 그쪽은 여전히 무커버리지다.
"""

from __future__ import annotations

import contextlib
import io
import math
import unittest

from integration.slam_session_control import (
    FreshMapTracker,
    RosSlamSessionControl,
)


class FreshMapReadyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1000.0
        self.tracker = FreshMapTracker(clock=lambda: self.now)

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def test_map_built_after_the_reset_scan_is_fresh(self) -> None:
        marker = self.tracker.marker()
        self.advance(0.1)
        self.tracker.note_scan(stamp_ns=2_000)
        self.advance(0.1)
        self.tracker.note_map(stamp_ns=2_500)

        self.assertTrue(self.tracker.fresh_map_ready(marker))

    def test_no_scan_after_the_marker_is_not_fresh(self) -> None:
        """리셋 뒤 스캔이 한 장도 없으면 어떤 지도도 새것이 아니다."""

        self.tracker.note_scan(stamp_ns=1_000)
        marker = self.tracker.marker()
        self.advance(0.1)
        self.tracker.note_map(stamp_ns=1_500)

        self.assertFalse(self.tracker.fresh_map_ready(marker))

    def test_map_that_predates_the_reset_scan_is_not_fresh(self) -> None:
        """리셋 직후 도착한 옛 지도를 새것으로 세면 겹침이 돌아온다."""

        marker = self.tracker.marker()
        self.advance(0.1)
        self.tracker.note_map(stamp_ns=900)  # 리셋 전에 만들어진 지도
        self.advance(0.1)
        self.tracker.note_scan(stamp_ns=2_000)

        self.assertFalse(self.tracker.fresh_map_ready(marker))

    def test_map_stamped_before_the_scan_is_not_fresh(self) -> None:
        """도착 순서가 맞아도 스캔보다 이른 스탬프면 그 스캔의 산물이 아니다."""

        marker = self.tracker.marker()
        self.advance(0.1)
        self.tracker.note_scan(stamp_ns=2_000)
        self.advance(0.1)
        self.tracker.note_map(stamp_ns=1_500)

        self.assertFalse(self.tracker.fresh_map_ready(marker))

    def test_marker_taken_before_reset_would_pass_a_stale_map(self) -> None:
        """마커를 리셋 앞에서 잡으면 옛 지도가 새것으로 통과한다.

        이것이 mapping_runtime 이 ``reset_slam()`` **뒤에** 마커를 잡는 이유다.
        리셋이 진행되는 동안 (a) 스캔 한 장과 (b) 옛 그래프로 만들어진 지도
        한 장이 이 순서로 도착하면 세 가드를 전부 통과한다 -- 지도가 겹치지는
        않지만 "새 지도가 생겼다"는 확인이 무의미해진다.
        """

        early = self.tracker.marker()  # 리셋 전에 잡은 마커
        self.advance(0.05)
        self.tracker.note_scan(stamp_ns=2_000)  # 리셋 진행 중 도착
        self.advance(0.05)
        self.tracker.note_map(stamp_ns=2_100)  # 아직 옛 그래프의 산물

        self.assertTrue(
            self.tracker.fresh_map_ready(early),
            "리셋 앞 마커는 옛 지도를 걸러내지 못한다 -- 그래서 뒤에서 잡는다",
        )

        late = self.tracker.marker()  # 리셋이 반환한 뒤 잡은 마커
        self.assertFalse(
            self.tracker.fresh_map_ready(late),
            "리셋 뒤 마커는 그 이후 산물만 통과시켜야 한다",
        )

    def test_marker_moves_with_each_session(self) -> None:
        """두 번째 매핑이 첫 번째의 지도를 자기 것으로 세면 안 된다."""

        first = self.tracker.marker()
        self.advance(0.1)
        self.tracker.note_scan(stamp_ns=2_000)
        self.advance(0.1)
        self.tracker.note_map(stamp_ns=2_500)
        self.assertTrue(self.tracker.fresh_map_ready(first))

        second = self.tracker.marker()

        self.assertFalse(
            self.tracker.fresh_map_ready(second),
            "새 세션은 자기 리셋 이후의 지도를 따로 받아야 한다",
        )


class _Stamp:
    def __init__(self, ns: int) -> None:
        self.sec = ns // 1_000_000_000
        self.nanosec = ns % 1_000_000_000


class _Transform:
    """TF 메시지의 최소 형태. ``header.stamp`` 만 있으면 된다."""

    def __init__(self, ns: int) -> None:
        self.header = type("H", (), {"stamp": _Stamp(ns)})()


class _Clock:
    def __init__(self, ns: int) -> None:
        self._ns = ns

    def now(self):
        return type("T", (), {"nanoseconds": self._ns})()


class TransformFreshnessTest(unittest.TestCase):
    """신선도 판정이 실제로 판정하는가.

    2026-08-09 실기: 이 함수가 **상수 False** 였다. 호출부가 이미 푼 Time 을
    넘기는데 _stamp_ns 는 메시지를 기대해서 항상 0 이 나왔고, 그래서
    wait_for_fresh_map / wait_for_localization_ready / current_map_pose 가
    전부 죽었다. START_MAPPING 이 30초를 태우고 FRESH_MAP_NOT_READY 로
    거부됐다(08:32:27, 08:33:17, 08:37:55).

    **테스트가 하나도 없어서 522개를 통과하고 현장까지 갔다.** 그래서
    여기서는 실물 메서드를 부른다 -- 스텁하면 같은 사고가 또 난다.
    """

    def control(self, *, now_ns: int) -> RosSlamSessionControl:
        control = RosSlamSessionControl(transform_max_age_sec=2.0)
        control._node = type("N", (), {"get_clock": lambda self: _Clock(now_ns)})()
        return control

    def test_recent_transform_is_fresh(self) -> None:
        now = 1_000_000_000_000
        control = self.control(now_ns=now)

        self.assertTrue(control._transform_is_fresh(_Transform(now - 500_000_000)))

    def test_slam_publishes_slightly_into_the_future(self) -> None:
        """slam 은 스탬프에 transform_timeout_ 를 더한다. 실측 -0.10초."""

        now = 1_000_000_000_000
        control = self.control(now_ns=now)

        self.assertTrue(control._transform_is_fresh(_Transform(now + 120_000_000)))

    def test_old_transform_is_stale(self) -> None:
        now = 1_000_000_000_000
        control = self.control(now_ns=now)

        self.assertFalse(control._transform_is_fresh(_Transform(now - 5_000_000_000)))

    def test_far_future_transform_is_stale(self) -> None:
        """얼어붙은 TF 가 미래 스탬프를 달면 상한만으로는 영원히 통과한다."""

        now = 1_000_000_000_000
        control = self.control(now_ns=now)

        self.assertFalse(control._transform_is_fresh(_Transform(now + 60_000_000_000)))

    def test_missing_stamp_is_stale(self) -> None:
        control = self.control(now_ns=1_000_000_000_000)

        self.assertFalse(control._transform_is_fresh(_Transform(0)))


def _pose_message(x: float, y: float, yaw_deg: float, covariance: object) -> object:
    """PoseWithCovarianceStamped 의 최소 형태."""

    yaw = math.radians(yaw_deg)
    pose = type("P", (), {})()
    pose.position = type("Pt", (), {"x": x, "y": y, "z": 0.0})()
    pose.orientation = type(
        "Q",
        (),
        {"x": 0.0, "y": 0.0, "z": math.sin(yaw / 2.0), "w": math.cos(yaw / 2.0)},
    )()
    inner = type("PC", (), {})()
    inner.pose = pose
    inner.covariance = covariance
    message = type("M", (), {})()
    message.pose = inner
    return message


class LocalizationPoseObservationTest(unittest.TestCase):
    """/pose 관측이 실제로 관측하는가.

    이 토픽 한 건이 "slam 이 스캔을 처리했다"는 유일한 직접 증거다. 그래서
    스텁이 아니라 실물 핸들러를 부른다 -- _transform_is_fresh 가 상수 False
    인 채로 522개 테스트를 통과하고 현장까지 간 이유가 스텁이었다.
    """

    def observe(self, control, message) -> str:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            control._on_localization_pose(message)
        return buffer.getvalue()

    def test_pose_and_covariance_are_reported(self) -> None:
        control = RosSlamSessionControl()
        covariance = [0.0] * 36
        covariance[0] = 0.0123
        covariance[7] = 0.0456
        covariance[35] = 0.0789

        line = self.observe(control, _pose_message(1.644, -0.368, 90.0, covariance))

        self.assertIn("x=1.644", line)
        self.assertIn("y=-0.368", line)
        self.assertIn("yawDeg=90.0", line)
        self.assertIn("covXX=0.0123", line)
        self.assertIn("covYY=0.0456", line)
        self.assertIn("covYaw=0.0789", line)

    def test_first_pose_has_no_previous_interval(self) -> None:
        control = RosSlamSessionControl()

        line = self.observe(control, _pose_message(0.0, 0.0, 0.0, [0.0] * 36))

        self.assertIn("sinceLastSec=-", line)

    def test_interval_since_the_previous_pose_is_reported(self) -> None:
        """정지 중 침묵과 주행 중 연속 발행을 구분할 유일한 값이다."""

        now = 100.0
        control = RosSlamSessionControl(clock=lambda: now)
        self.observe(control, _pose_message(0.0, 0.0, 0.0, [0.0] * 36))
        now = 100.4

        line = self.observe(control, _pose_message(0.1, 0.0, 0.0, [0.0] * 36))

        self.assertIn("sinceLastSec=0.40", line)

    def test_missing_covariance_does_not_raise(self) -> None:
        """콜백에서 예외가 나가면 executor spin 이 죽고 구독 전체를 잃는다."""

        control = RosSlamSessionControl()

        line = self.observe(control, _pose_message(0.0, 0.0, 0.0, None))

        self.assertIn("covXX=nan", line)

    def test_message_without_a_pose_is_ignored(self) -> None:
        control = RosSlamSessionControl()

        self.assertEqual(self.observe(control, type("M", (), {"pose": None})()), "")


class YawFromQuaternionTest(unittest.TestCase):
    """current_map_pose 와 /pose 관측이 같은 변환을 쓴다."""

    def test_known_angles(self) -> None:
        for degrees in (0.0, 45.0, 90.0, -90.0, 179.0):
            with self.subTest(degrees=degrees):
                yaw = math.radians(degrees)
                rotation = type(
                    "Q",
                    (),
                    {
                        "x": 0.0,
                        "y": 0.0,
                        "z": math.sin(yaw / 2.0),
                        "w": math.cos(yaw / 2.0),
                    },
                )()

                self.assertAlmostEqual(
                    math.degrees(RosSlamSessionControl._yaw_from_quaternion(rotation)),
                    degrees,
                    places=6,
                )


if __name__ == "__main__":
    unittest.main()
