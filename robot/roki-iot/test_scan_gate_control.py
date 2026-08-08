"""기동 시 IDLE 게이트 개방.

이 파일이 덮는 것은 ``_open_for_idle`` 하나다. 게이트 전송 계층 전체는
ROS 없이는 못 돌리므로 여기서 다루지 않는다 -- 그쪽은 여전히 무커버리지다.
"""

from __future__ import annotations

import unittest

from integration.scan_gate_control import RosScanGateControl


class IdleOpenControl(RosScanGateControl):
    """ROS 없이 기동 개방만 돌린다. 전송은 전부 기록으로 대체한다."""

    def __init__(self, *, transform_ready: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.calls: list[str] = []
        self.open_error: Exception | None = None
        self._transform_ready = transform_ready
        self.wait_deadlines: list[float] = []

    def open(self) -> None:
        self.calls.append("open")
        if self.open_error is not None:
            raise self.open_error

    def close(self) -> None:
        self.calls.append("close")

    def _wait_for_transform(self, deadline: float) -> bool:
        self.calls.append("wait")
        self.wait_deadlines.append(deadline)
        return self._transform_ready


class OpenForIdleTest(unittest.TestCase):
    def test_idle_leaves_the_gate_open(self) -> None:
        """열었다 닫으면 map->odom 스탬프가 얼어붙어 pose 가 죽는다.

        2026-08-09 02:45 실기: 게이트를 닫자 slam 의 TF 발행이 마지막 스캔
        시각으로 고정됐고, 지도 좌표 pose 조회가 extrapolation 오류로
        영구 실패했다. Nav2 는 최신값 조회라 멀쩡해 보여서 진단이 어려웠다.
        pose 가 없으면 백엔드가 명령을 로봇까지 보내지 않는다.
        """

        control = IdleOpenControl()

        control._open_for_idle()

        self.assertEqual(control.calls, ["open", "wait"])
        self.assertNotIn("close", control.calls, "닫으면 스탬프가 얼어붙는다")

    def test_idle_stays_open_even_if_the_map_frame_is_slow(self) -> None:
        """프레임이 늦게 와도 열어둔 채로 둔다. 닫으면 영영 안 온다."""

        control = IdleOpenControl(transform_ready=False)

        control._open_for_idle()

        self.assertEqual(control.calls, ["open", "wait"])

    def test_open_failure_does_not_stop_startup(self) -> None:
        """기동 개방은 최적화지 기동 조건이 아니다.

        못 열어도 첫 매핑이 열면서 같은 일이 일어난다. 여기서 예외를 올리면
        게이트 서비스가 늦게 뜨는 것만으로 런타임 기동이 실패한다.
        """

        control = IdleOpenControl()
        control.open_error = RuntimeError("gate service unavailable")

        control._open_for_idle()  # 예외가 새어나오면 실패

        self.assertEqual(control.calls, ["open"], "못 열었으면 기다릴 것도 없다")

    def test_wait_window_is_bounded(self) -> None:
        """기동이 게이트 대기 때문에 무한정 늘어나면 안 된다."""

        now = 1000.0
        control = IdleOpenControl(
            transform_ready=False,
            prime_timeout_sec=10.0,
            clock=lambda: now,
        )

        control._open_for_idle()

        self.assertEqual(control.wait_deadlines, [now + 10.0])


if __name__ == "__main__":
    unittest.main()
