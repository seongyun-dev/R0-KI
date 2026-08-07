from __future__ import annotations

import unittest

from integration.localization_mode import (
    LOCALIZE_AT_POSE,
    DockPose,
    LocalizationModeController,
)


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


class LocalizationModeControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = RecordingTransport()
        self.messages: list[str] = []
        self.controller = LocalizationModeController(
            self.transport, report=self.messages.append
        )

    def test_entering_mapping_disables_localization(self) -> None:
        ready, reason = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        self.assertEqual(self.transport.calls, [("set_localization_mode", False)])
        self.assertEqual(self.controller.mode, "mapping")

    def test_patrol_switches_mode_before_loading_the_graph(self) -> None:
        """순서가 뒤집히면 매핑 모드로 그래프를 읽어 원본을 덮어쓸 수 있다."""

        self.controller.enter_patrol("/maps/session/posegraph", DockPose(1.0, 2.0, 0.5))

        self.assertEqual(
            self.transport.calls,
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
        self.assertEqual(len(self.transport.calls), 1)

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
        self.assertEqual(len(self.transport.calls), 2)

    def test_reassert_replays_patrol_with_the_same_graph(self) -> None:
        """생애주기 복구가 파라미터를 되돌릴 때 모드도 다시 밀어넣어야 한다."""

        self.controller.enter_patrol("/maps/session/posegraph", DockPose(0.0, 0.0, 1.57))
        self.transport.calls.clear()

        ready, _ = self.controller.reassert()

        self.assertTrue(ready)
        self.assertEqual(
            self.transport.calls,
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

    def test_reassert_replays_mapping(self) -> None:
        self.controller.enter_mapping()
        self.transport.calls.clear()

        ready, _ = self.controller.reassert()

        self.assertTrue(ready)
        self.assertEqual(self.transport.calls, [("set_localization_mode", False)])

    def test_reassert_before_any_mode_is_a_no_op(self) -> None:
        ready, reason = self.controller.reassert()

        self.assertFalse(ready)
        self.assertEqual(reason, "NO_MODE_TO_REASSERT")
        self.assertEqual(self.transport.calls, [])

    def test_transitions_are_reported(self) -> None:
        self.controller.enter_mapping()
        self.controller.enter_patrol("/maps/session/posegraph")

        self.assertIn("[LOCALIZATION] mode=mapping", self.messages)
        self.assertIn(
            "[LOCALIZATION] mode=patrol posegraph=/maps/session/posegraph",
            self.messages,
        )


if __name__ == "__main__":
    unittest.main()
