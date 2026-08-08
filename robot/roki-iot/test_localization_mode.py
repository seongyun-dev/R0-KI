from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from integration.localization_mode import (
    LOCALIZE_AT_POSE,
    DockPose,
    LocalizationModeController,
    ServiceCallFailed,
    posegraph_files_present,
    wait_for_response,
)


class FakeFuture:
    """호출 N 번째에 완료되는 future. 대기 루프를 시간 없이 검증한다."""

    def __init__(self, *, done_after=0, result=None, exception=None):
        self._remaining = done_after
        self._result = result
        self._exception = exception
        self.cancelled = False

    def done(self):
        if self._remaining <= 0:
            return True
        self._remaining -= 1
        return False

    def cancel(self):
        self.cancelled = True

    def exception(self):
        return self._exception

    def result(self):
        return self._result


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RecordingTransport:
    """호출 순서를 그대로 남긴다. 순서가 이 모듈의 핵심 계약이라서."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail_on: set[str] = set()

    def set_localization_mode(self, localization: bool) -> None:
        self.calls.append(("set_localization_mode", localization))
        if "set" in self.fail_on:
            raise RuntimeError("service unavailable")

    def deserialize_map(self, filename, match_type, initial_pose) -> None:
        self.calls.append(("deserialize_map", filename, match_type, initial_pose))
        if "deserialize" in self.fail_on:
            raise RuntimeError("file missing")

    def set_node_parameters(self, node_name, values) -> None:
        self.calls.append(("set_node_parameters", node_name, dict(values)))
        if "parameters" in self.fail_on:
            raise RuntimeError("parameter rejected")

    def injected(self) -> dict:
        """주입된 Nav2 파라미터를 노드별로 모은다."""

        return {
            call[1]: call[2] for call in self.calls if call[0] == "set_node_parameters"
        }

    def mode_calls(self) -> list:
        """slam_toolbox 모드 전환만 남긴다. 파라미터 주입은 세지 않는다."""

        return [call for call in self.calls if call[0] == "set_localization_mode"]


class LocalizationModeControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = RecordingTransport()
        self.messages: list[str] = []
        self.missing: set[str] = set()
        self.controller = LocalizationModeController(
            self.transport,
            posegraph_exists=lambda path: path not in self.missing,
            report=self.messages.append,
        )

    def test_entering_mapping_disables_localization(self) -> None:
        ready, reason = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        self.assertEqual(
            self.transport.calls[0], ("set_localization_mode", False)
        )
        self.assertEqual(self.controller.mode, "mapping")

    def test_patrol_switches_mode_before_loading_the_graph(self) -> None:
        """순서가 뒤집히면 매핑 모드로 그래프를 읽어 원본을 덮어쓸 수 있다."""

        self.controller.enter_patrol("/maps/session/posegraph", DockPose(1.0, 2.0, 0.5))

        self.assertEqual(
            self.transport.calls[:2],
            [
                ("set_localization_mode", True),
                (
                    "deserialize_map",
                    "/maps/session/posegraph",
                    LOCALIZE_AT_POSE,
                    DockPose(1.0, 2.0, 0.5),
                ),
            ],
        )

    def test_patrol_injects_the_patrol_nav2_profile(self) -> None:
        """MODE_PROFILES["patrol"] 이 정의만 되고 적용되지 않았던 회귀를 막는다.

        2026-08-08 실기: 순찰 자리에 매핑 값(REEDS_SHEPP / 1.3 / 3.15)이
        그대로 올라가 있어 순찰이 후진하고 아무 방향으로나 도착 판정을 했다.
        """

        ready, reason = self.controller.enter_patrol("/maps/session/posegraph")

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        injected = self.transport.injected()
        self.assertEqual(
            injected["/planner_server"]["GridBased.motion_model_for_search"],
            "DUBIN",
        )
        self.assertEqual(injected["/planner_server"]["GridBased.reverse_penalty"], 2.1)
        self.assertIs(
            injected["/planner_server"]["GridBased.cache_obstacle_heuristic"], True
        )
        self.assertEqual(
            injected["/controller_server"]["general_goal_checker.yaw_goal_tolerance"],
            0.35,
        )

    def test_mapping_restores_the_mapping_nav2_profile(self) -> None:
        """순찰 뒤 매핑은 DUBIN 을 물려받으면 안 된다. 회전반경이 못 버틴다."""

        self.controller.enter_patrol("/maps/session/posegraph")
        self.transport.calls.clear()

        self.controller.enter_mapping()

        injected = self.transport.injected()
        self.assertEqual(
            injected["/planner_server"]["GridBased.motion_model_for_search"],
            "REEDS_SHEPP",
        )

    def test_patrol_refuses_when_the_profile_cannot_be_injected(self) -> None:
        """주입이 실패한 순찰을 READY 로 알리면 그 순찰은 후진한다."""

        self.transport.fail_on.add("parameters")

        ready, reason = self.controller.enter_patrol("/maps/session/posegraph")

        self.assertFalse(ready)
        self.assertEqual(reason, "MODE_PROFILE_APPLY_FAILED")
        self.assertIsNone(self.controller.mode)

    def test_mapping_survives_a_profile_injection_failure(self) -> None:
        """렌더된 파일이 이미 매핑 값이다. 여기서 실패로 처리하면 매핑이 못 뜬다."""

        self.transport.fail_on.add("parameters")

        ready, reason = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        self.assertEqual(self.controller.mode, "mapping")

    def test_patrol_defaults_to_the_dock_origin(self) -> None:
        self.controller.enter_patrol("/maps/session/posegraph")

        _, _, _, pose = self.transport.calls[1]
        self.assertEqual(pose, DockPose(0.0, 0.0, 0.0))

    def test_repeated_mapping_entry_does_not_re_send(self) -> None:
        """매핑 재진입마다 버퍼를 비우면 진행 중인 세션이 끊긴다."""

        self.controller.enter_mapping()
        ready, reason = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(reason, "ALREADY_MAPPING")
        self.assertEqual(len(self.transport.mode_calls()), 1)

    def test_absent_posegraph_files_stop_the_switch(self) -> None:
        """DeserializePoseGraph 는 빈 응답이라 실패를 알려주지 않는다.

        2026-08-07 실기: 없는 경로를 주면 노드는 "Failed to open requested
        file" 을 찍는데 서비스는 정상 응답한다. 여기서 막지 않으면 지도 없이
        순찰이 시작된다.
        """

        self.missing.add("/maps/gone/posegraph")

        ready, reason = self.controller.enter_patrol("/maps/gone/posegraph")

        self.assertFalse(ready)
        self.assertEqual(reason, "POSEGRAPH_MISSING")
        self.assertEqual(self.transport.calls, [], "모드를 바꾸기 전에 걸러야 한다")
        self.assertIsNone(self.controller.mode)

    def test_missing_posegraph_path_never_touches_the_service(self) -> None:
        ready, reason = self.controller.enter_patrol("")

        self.assertFalse(ready)
        self.assertEqual(reason, "POSEGRAPH_PATH_MISSING")
        self.assertEqual(self.transport.calls, [])

    def test_failed_mode_switch_leaves_the_mode_unknown(self) -> None:
        """실패를 성공으로 기억하면 다음 요청이 조용히 무시된다."""

        self.transport.fail_on.add("set")
        ready, reason = self.controller.enter_mapping()

        self.assertFalse(ready)
        self.assertEqual(reason, "SET_MAPPING_MODE_FAILED")
        self.assertIsNone(self.controller.mode)

    def test_graph_load_failure_is_reported_and_not_recorded_as_patrol(self) -> None:
        """모드는 바뀌었는데 지도가 없는 상태를 순찰 가능으로 보면 안 된다."""

        self.transport.fail_on.add("deserialize")
        ready, reason = self.controller.enter_patrol("/maps/missing/posegraph")

        self.assertFalse(ready)
        self.assertEqual(reason, "POSEGRAPH_LOAD_FAILED")
        self.assertIsNone(self.controller.mode)

    def test_failure_then_retry_re_sends_the_request(self) -> None:
        self.transport.fail_on.add("set")
        self.controller.enter_mapping()
        self.transport.fail_on.clear()

        ready, _ = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(len(self.transport.mode_calls()), 2)

    def test_reassert_replays_patrol_with_the_same_graph(self) -> None:
        """생애주기 복구가 파라미터를 되돌릴 때 모드도 다시 밀어넣어야 한다."""

        self.controller.enter_patrol("/maps/session/posegraph", DockPose(0.0, 0.0, 1.57))
        self.transport.calls.clear()

        ready, _ = self.controller.reassert()

        self.assertTrue(ready)
        self.assertEqual(
            self.transport.calls[:2],
            [
                ("set_localization_mode", True),
                (
                    "deserialize_map",
                    "/maps/session/posegraph",
                    LOCALIZE_AT_POSE,
                    DockPose(0.0, 0.0, 1.57),
                ),
            ],
        )
        # 복구가 되돌린 것이 바로 이 값들이다. 다시 밀어넣지 않으면 reassert 가
        # 하려던 일의 절반만 한 것이 된다.
        self.assertEqual(
            self.transport.injected()["/planner_server"][
                "GridBased.motion_model_for_search"
            ],
            "DUBIN",
        )

    def test_reassert_replays_mapping(self) -> None:
        self.controller.enter_mapping()
        self.transport.calls.clear()

        ready, _ = self.controller.reassert()

        self.assertTrue(ready)
        self.assertEqual(self.transport.mode_calls(), [("set_localization_mode", False)])
        self.assertEqual(
            self.transport.injected()["/planner_server"][
                "GridBased.motion_model_for_search"
            ],
            "REEDS_SHEPP",
        )

    def test_reassert_before_any_mode_is_a_no_op(self) -> None:
        ready, reason = self.controller.reassert()

        self.assertFalse(ready)
        self.assertEqual(reason, "NO_MODE_TO_REASSERT")
        self.assertEqual(self.transport.calls, [])

    def test_lifecycle_recovery_is_recorded_not_repaired(self) -> None:
        """복구 빈도를 재기 전에는 자동 재적용을 하지 않는다.

        순찰 중 복구만 위험하다 -- 렌더 기준선이 매핑이라 복구가 순찰
        파라미터를 매핑으로 되돌린다. 그 경고가 로그에 남아야 한다.
        """

        self.controller.enter_patrol("/maps/session/posegraph")
        self.transport.calls.clear()

        self.controller.note_lifecycle_recovery("bond lost")

        self.assertEqual(self.transport.calls, [], "관찰만 하고 고치지 않는다")
        message = self.messages[-1]
        self.assertIn("lifecycle recovery observed", message)
        self.assertIn("mode=patrol", message)
        self.assertIn("순찰 프로필", message)

    def test_lifecycle_recovery_during_mapping_is_harmless(self) -> None:
        self.controller.enter_mapping()

        self.controller.note_lifecycle_recovery()

        self.assertIn("mode=mapping", self.messages[-1])
        self.assertNotIn("순찰 프로필", self.messages[-1])

    def test_dock_pose_seeds_the_graph_load(self) -> None:
        """도킹 표시를 옮기면 그 좌표를 줘야 스캔 매칭이 수렴한다."""

        controller = LocalizationModeController(
            self.transport,
            dock_pose=DockPose(1.5, -0.5, 0.7),
            posegraph_exists=lambda _: True,
        )

        controller.enter_patrol("/maps/session/posegraph")

        self.assertEqual(self.transport.calls[1][3], DockPose(1.5, -0.5, 0.7))

    def test_transitions_are_reported(self) -> None:
        self.controller.enter_mapping()
        self.controller.enter_patrol("/maps/session/posegraph")

        self.assertIn("[LOCALIZATION] mode=mapping", self.messages)
        self.assertIn(
            "[LOCALIZATION] mode=patrol posegraph=/maps/session/posegraph",
            self.messages,
        )


class PosegraphFilesPresentTest(unittest.TestCase):
    """직렬화는 확장자 없는 경로에서 .posegraph 와 .data 두 개를 만든다."""

    def _base(self, directory, *suffixes):
        base = Path(directory) / "posegraph"
        for suffix in suffixes:
            base.with_suffix(suffix).write_bytes(b"x")
        return str(base)

    def test_both_files_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = self._base(directory, ".posegraph", ".data")
            self.assertTrue(posegraph_files_present(base))

    def test_data_file_alone_is_not_enough(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = self._base(directory, ".data")
            self.assertFalse(posegraph_files_present(base))

    def test_posegraph_file_alone_is_not_enough(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = self._base(directory, ".posegraph")
            self.assertFalse(posegraph_files_present(base))

    def test_nothing_there(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(posegraph_files_present(str(Path(directory) / "none")))


class WaitForResponseTest(unittest.TestCase):
    """실행기가 다른 스레드에서 채우는 future 를 기다리는 로직."""

    def _wait(self, future, timeout_sec=5.0, clock=None):
        clock = clock or FakeClock()
        return wait_for_response(
            future,
            timeout_sec=timeout_sec,
            description="/svc",
            clock=clock,
            sleep=lambda _: clock.advance(0.02),
        )

    def test_returns_the_response_once_done(self) -> None:
        response = SimpleNamespace(success=True, message="")

        self.assertIs(self._wait(FakeFuture(result=response)), response)

    def test_polls_until_the_executor_completes_it(self) -> None:
        future = FakeFuture(done_after=3, result=SimpleNamespace(success=True))

        self._wait(future)

        self.assertFalse(future.cancelled)

    def test_timeout_cancels_so_a_late_reply_cannot_land_later(self) -> None:
        clock = FakeClock()
        future = FakeFuture(done_after=10_000)

        with self.assertRaises(ServiceCallFailed):
            self._wait(future, timeout_sec=0.1, clock=clock)

        self.assertTrue(future.cancelled)

    def test_service_exception_is_surfaced(self) -> None:
        future = FakeFuture(exception=ValueError("boom"))

        with self.assertRaisesRegex(ServiceCallFailed, "ValueError"):
            self._wait(future)

    def test_success_false_is_a_failure_not_a_pass(self) -> None:
        """SetBool 이 success=False 를 주면 전환이 안 된 것이다."""

        future = FakeFuture(result=SimpleNamespace(success=False, message="busy"))

        with self.assertRaisesRegex(ServiceCallFailed, "busy"):
            self._wait(future)

    def test_empty_response_counts_as_success(self) -> None:
        """DeserializePoseGraph 응답에는 success 필드가 없다."""

        response = SimpleNamespace()

        self.assertIs(self._wait(FakeFuture(result=response)), response)

    def test_none_response_is_a_failure(self) -> None:
        with self.assertRaises(ServiceCallFailed):
            self._wait(FakeFuture(result=None))


if __name__ == "__main__":
    unittest.main()
