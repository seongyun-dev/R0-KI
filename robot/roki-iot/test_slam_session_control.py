"""리셋 이후의 지도만 통과시키는 신선도 검사.

스캔 게이트를 걷어낸 뒤 이전 지도 겹침(직사각형 방이 별모양이 되던 문제)을
막는 것은 두 가지다: 매핑 START 마다의 ``reset_slam()`` 과 여기서 검증하는
``fresh_map_ready``. 리셋이 성공해도 옛 지도가 한 장 더 도착하면 그것을
새 지도로 착각할 수 있고, 그러면 다음 세션이 이전 그래프 위에서 시작한다.

ROS 전송 계층은 여기서 다루지 않는다 -- 그쪽은 여전히 무커버리지다.
"""

from __future__ import annotations

import unittest

from integration.slam_session_control import FreshMapTracker


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


if __name__ == "__main__":
    unittest.main()
