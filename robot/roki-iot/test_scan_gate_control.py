"""기동 시 map 프레임 프라이밍.

이 파일이 덮는 것은 ``_prime_map_frame`` 하나다. 게이트 전송 계층 전체는
ROS 없이는 못 돌리므로 여기서 다루지 않는다 -- 그쪽은 여전히 무커버리지다.
"""

from __future__ import annotations

import unittest

from integration.scan_gate_control import RosScanGateControl


class PrimingControl(RosScanGateControl):
    """ROS 없이 프라이밍만 돌린다. 전송은 전부 기록으로 대체한다."""

    def __init__(self, *, transform_ready: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.calls: list[str] = []
        self.open_error: Exception | None = None
        self.close_error: Exception | None = None
        self._transform_ready = transform_ready
        self.wait_deadlines: list[float] = []

    def open(self) -> None:
        self.calls.append("open")
        if self.open_error is not None:
            raise self.open_error

    def close(self) -> None:
        self.calls.append("close")
        if self.close_error is not None:
            raise self.close_error

    def _wait_for_transform(self, deadline: float) -> bool:
        self.calls.append("wait")
        self.wait_deadlines.append(deadline)
        return self._transform_ready


class PrimeMapFrameTest(unittest.TestCase):
    def test_prime_opens_waits_then_closes(self) -> None:
        """Nav2 는 map 프레임 없이는 활성화를 끝내지 못한다.

        Costmap2DROS::on_activate 가 2Hz 로 무한 대기하고 실패 반환이 없다.
        스캔 한 장이면 slam 이 map->odom 을 내기 시작하고, 그 발행은
        게이트를 닫아도 유지된다(scan_header 를 reset 이 안 지운다).
        """

        control = PrimingControl()

        control._prime_map_frame()

        self.assertEqual(control.calls, ["open", "wait", "close"])

    def test_prime_closes_even_when_the_transform_never_arrives(self) -> None:
        """열어놓고 못 닫으면 IDLE 불변식이 깨진 채 남는다."""

        control = PrimingControl(transform_ready=False)

        control._prime_map_frame()

        self.assertEqual(control.calls, ["open", "wait", "close"])

    def test_prime_failure_does_not_stop_startup(self) -> None:
        """프라이밍은 최적화지 기동 조건이 아니다.

        못 해도 첫 매핑이 게이트를 열면서 같은 일이 일어난다. 여기서 예외를
        올리면 게이트를 못 여는 상황이 곧 런타임 기동 실패가 된다.
        """

        control = PrimingControl()
        control.open_error = RuntimeError("gate service unavailable")

        control._prime_map_frame()  # 예외가 새어나오면 실패

        self.assertEqual(control.calls, ["open"], "열지 못했으면 닫을 것도 없다")

    def test_close_failure_is_raised(self) -> None:
        """닫기 실패만은 삼키지 않는다 -- 게이트가 열린 채 남는다."""

        control = PrimingControl()
        control.close_error = RuntimeError("gate service unavailable")

        with self.assertRaises(RuntimeError):
            control._prime_map_frame()

        self.assertEqual(control.calls, ["open", "wait", "close"])

    def test_prime_window_is_bounded(self) -> None:
        """기동이 프라이밍 때문에 무한정 늘어나면 안 된다."""

        now = 1000.0
        control = PrimingControl(
            transform_ready=False,
            prime_timeout_sec=10.0,
            clock=lambda: now,
        )

        control._prime_map_frame()

        self.assertEqual(control.wait_deadlines, [now + 10.0])


if __name__ == "__main__":
    unittest.main()
