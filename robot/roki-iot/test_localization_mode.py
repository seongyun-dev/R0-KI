from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiot_robot.ros_config import MODE_PROFILES
from integration.localization_mode import (
    LOCALIZE_AT_POSE,
    DockPose,
    LocalizationModeController,
    RosLocalizationModeTransport,
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
        self.current_parameters: dict[str, dict[str, object]] = {}
        self.lifecycle_states = {
            node: "active" for node in LocalizationModeController.MAPPING_NAV2_NODES
        }

    def set_localization_mode(self, localization: bool) -> None:
        self.calls.append(("set_localization_mode", localization))
        if "set" in self.fail_on:
            raise RuntimeError("service unavailable")

    def deserialize_map(self, filename, match_type, initial_pose) -> None:
        self.calls.append(("deserialize_map", filename, match_type, initial_pose))
        if "deserialize" in self.fail_on:
            raise RuntimeError("file missing")

    def get_node_parameters(self, node_name, names):
        self.calls.append(("get_node_parameters", node_name, tuple(names)))
        if "get_parameters" in self.fail_on:
            raise RuntimeError("parameter query failed")
        current = self.current_parameters.get(node_name, {})
        return {name: current.get(name) for name in names}

    def get_lifecycle_state(self, node_name):
        self.calls.append(("get_lifecycle_state", node_name))
        if "lifecycle" in self.fail_on:
            raise RuntimeError("lifecycle query failed")
        return self.lifecycle_states.get(node_name, "unknown")

    def verified(self) -> dict:
        """조회된 Nav2 파라미터 이름을 노드별로 모은다.

        쓰기 경로는 일부러 없다. ``set_node_parameters`` 를 흉내내던 가짜가
        여기 있었는데, 그 호출이 실기에서 Nav2 스택을 내리는 것이 확인돼
        전송 경계에서 사라졌다(localization_mode.ModeTransport 참고).
        """

        merged: dict[str, set] = {}
        for call in self.calls:
            if call[0] == "get_node_parameters":
                merged.setdefault(call[1], set()).update(call[2])
        return merged

    def mode_calls(self) -> list:
        """slam_toolbox 모드 전환만 남긴다. 파라미터 조회는 세지 않는다."""

        return [call for call in self.calls if call[0] == "set_localization_mode"]


def seed_boot_profiles(transport: RecordingTransport) -> None:
    """기동 직후의 Nav2 를 흉내낸다 -- 두 운행 값이 동시에 올라가 있다.

    이제 전환은 파라미터를 바꾸는 일이 아니라 BT 가 인스턴스를 고르는 일이다
    (MappingGridBased / PatrolGridBased). 렌더된 파라미터 파일이 둘 다 담고
    있으므로, 한쪽만 올라간 상태를 기본으로 두면 실기에 없는 상황을 테스트가
    정상으로 취급하게 된다.
    """

    merged: dict[str, dict[str, object]] = {}
    for profile in MODE_PROFILES.values():
        for node, values in profile.items():
            merged.setdefault(node, {}).update(values)
    transport.current_parameters = merged


class LocalizationModeControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = RecordingTransport()
        seed_boot_profiles(self.transport)
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

    def test_patrol_verifies_the_patrol_instance_and_writes_nothing(self) -> None:
        """순찰은 PatrolGridBased 를 읽어 대조만 한다. 쓰기는 없다.

        2026-08-08 실기: 여기가 SetParameters 를 하던 시절, /planner_server 가
        23~29초 블록되고 4초 bond heartbeat 를 놓쳐 순찰을 시작하는 순간
        Nav2 스택 전체가 내려갔다. 값 자체는 기동 시 이미 제자리에 있다.
        """

        ready, reason = self.controller.enter_patrol("/maps/session/posegraph")

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        verified = self.transport.verified()
        self.assertEqual(
            verified["/planner_server"],
            set(MODE_PROFILES["patrol"]["/planner_server"]),
        )
        self.assertEqual(
            verified["/controller_server"],
            set(MODE_PROFILES["patrol"]["/controller_server"]),
        )
        self.assertFalse(
            hasattr(self.transport, "set_node_parameters"),
            "전송 경계에 쓰기 경로가 생기면 그 호출이 Nav2 를 내린다",
        )

    def test_mapping_after_patrol_no_longer_inherits_the_patrol_profile(self) -> None:
        """인스턴스가 갈린 뒤로 순찰이 매핑 값을 건드리지 않는다.

        예전에는 두 운행이 GridBased 하나를 공유해서, 순찰이 DUBIN 을 밀어넣고
        나면 이어지는 매핑이 그것을 물려받았다 -- 회전반경 0.34 m 로는 전진
        호만으로 프론티어를 못 돌아 계획이 없었다. 지금은 순찰이 아무것도 쓰지
        않으므로 MappingGridBased 가 그대로 남고, 매핑이 바로 READY 가 된다.
        """

        self.controller.enter_patrol("/maps/session/posegraph")
        self.transport.calls.clear()

        ready, reason = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")

    def test_patrol_refuses_when_the_profile_cannot_be_read(self) -> None:
        """대조를 못 한 순찰을 READY 로 알리면 그 순찰은 후진할 수 있다."""

        self.transport.fail_on.add("get_parameters")

        ready, reason = self.controller.enter_patrol("/maps/session/posegraph")

        self.assertFalse(ready)
        self.assertEqual(reason, "MODE_PROFILE_APPLY_FAILED")
        self.assertIsNone(self.controller.mode)

    def test_mapping_verifies_the_mapping_instance(self) -> None:
        ready, reason = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        self.assertEqual(
            self.transport.verified()["/planner_server"],
            set(MODE_PROFILES["mapping"]["/planner_server"]),
        )

    def test_mapping_refuses_a_changed_profile(self) -> None:
        """값이 어긋났는데 READY 를 주면 아무도 그것을 다시 보지 않는다.

        고칠 방법이 없으므로 fail-close 한다 -- 쓰기 경로가 사라졌고, 되돌리는
        길은 launch 파일을 고쳐 스택을 다시 띄우는 것뿐이다.
        """

        self.transport.current_parameters["/planner_server"][
            "MappingGridBased.reverse_penalty"
        ] = 9.9

        ready, reason = self.controller.enter_mapping()

        self.assertFalse(ready)
        self.assertEqual(reason, "MODE_PROFILE_APPLY_FAILED")

    def test_ensure_patrol_loads_the_graph_when_nobody_did(self) -> None:
        """재부팅 뒤 첫 순찰. 그 부팅에 매핑이 없었으니 인계도 없었다."""

        ready, reason = self.controller.ensure_patrol("/maps/active/posegraph")

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        self.assertEqual(
            [call[1] for call in self.transport.calls if call[0] == "deserialize_map"],
            ["/maps/active/posegraph"],
        )

    def test_ensure_patrol_does_not_reload_the_same_graph(self) -> None:
        """7.2MB 재적재는 START_PATROL 의 TTL 을 그만큼 붙잡는다."""

        self.controller.enter_patrol("/maps/active/posegraph")
        self.transport.calls.clear()

        ready, reason = self.controller.ensure_patrol("/maps/active/posegraph")

        self.assertTrue(ready)
        self.assertEqual(reason, "ALREADY_PATROL")
        self.assertEqual(
            [call for call in self.transport.calls if call[0] == "deserialize_map"], []
        )
        # 그래프는 그대로 두되 프로필은 다시 대조한다. 조회 두 번이면 끝나고,
        # 어긋난 채로 순찰을 시작하는 것보다는 싸다.
        self.assertEqual(
            self.transport.verified()["/planner_server"],
            set(MODE_PROFILES["patrol"]["/planner_server"]),
        )

    def test_ensure_patrol_reloads_when_the_active_map_changed(self) -> None:
        """방금 그린 지도는 이전 그래프와 다른 파일이다."""

        self.controller.enter_patrol("/maps/active/map-1/posegraph")
        self.transport.calls.clear()

        ready, _ = self.controller.ensure_patrol("/maps/active/map-2/posegraph")

        self.assertTrue(ready)
        self.assertEqual(
            [call[1] for call in self.transport.calls if call[0] == "deserialize_map"],
            ["/maps/active/map-2/posegraph"],
        )

    def test_ensure_patrol_reports_a_missing_graph(self) -> None:
        self.missing.add("/maps/active/posegraph")

        ready, reason = self.controller.ensure_patrol("/maps/active/posegraph")

        self.assertFalse(ready)
        self.assertEqual(reason, "POSEGRAPH_MISSING")

    def test_mapping_refuses_when_the_profile_cannot_be_read(self) -> None:
        self.transport.fail_on.add("get_parameters")

        ready, reason = self.controller.enter_mapping()

        self.assertFalse(ready)
        self.assertEqual(reason, "MODE_PROFILE_APPLY_FAILED")
        self.assertIsNone(self.controller.mode)

    def test_mapping_requires_all_navigation_nodes_to_be_active(self) -> None:
        for failed_node in LocalizationModeController.MAPPING_NAV2_NODES:
            with self.subTest(node=failed_node):
                transport = RecordingTransport()
                seed_boot_profiles(transport)
                transport.lifecycle_states[failed_node] = "inactive"
                controller = LocalizationModeController(transport)

                ready, reason = controller.enter_mapping()

                self.assertFalse(ready)
                self.assertEqual(reason, "NAV2_NOT_READY")
                self.assertIsNone(controller.mode)

    def test_mapping_refuses_when_lifecycle_state_cannot_be_read(self) -> None:
        self.transport.fail_on.add("lifecycle")

        ready, reason = self.controller.enter_mapping()

        self.assertFalse(ready)
        self.assertEqual(reason, "NAV2_NOT_READY")
        self.assertIsNone(self.controller.mode)

    def test_mapping_reads_all_required_lifecycle_nodes_before_ready(self) -> None:
        ready, reason = self.controller.enter_mapping()

        self.assertTrue(ready)
        self.assertEqual(reason, "READY")
        self.assertEqual(
            [
                call[1]
                for call in self.transport.calls
                if call[0] == "get_lifecycle_state"
            ],
            list(LocalizationModeController.MAPPING_NAV2_NODES),
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
        """slam_toolbox 가 다시 뜨면 모드와 그래프를 서비스로 되돌려야 한다.

        Nav2 파라미터는 이제 파일에서 스스로 돌아오지만, 위치추정 모드와 적재된
        포즈그래프는 서비스 호출로만 정해지는 런타임 상태라 재적용이 필요하다.
        """

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

    def test_reassert_replays_mapping(self) -> None:
        self.controller.enter_mapping()
        self.transport.calls.clear()

        ready, _ = self.controller.reassert()

        self.assertTrue(ready)
        self.assertEqual(self.transport.mode_calls(), [("set_localization_mode", False)])

    def test_reassert_before_any_mode_is_a_no_op(self) -> None:
        ready, reason = self.controller.reassert()

        self.assertFalse(ready)
        self.assertEqual(reason, "NO_MODE_TO_REASSERT")
        self.assertEqual(self.transport.calls, [])

    def test_lifecycle_recovery_is_recorded_not_repaired(self) -> None:
        """복구 빈도를 재기 전에는 자동 재적용을 하지 않는다.

        예전에는 순찰 중 복구가 순찰 파라미터를 매핑으로 되돌렸다. 두 운행 값이
        각자의 인스턴스로 파라미터 파일에 들어간 뒤로 그 손실은 없어졌으므로
        경고도 사라졌다. 기록만 남긴다 -- 복구는 여전히 bond 끊김의 신호다.
        """

        self.controller.enter_patrol("/maps/session/posegraph")
        self.transport.calls.clear()

        self.controller.note_lifecycle_recovery("bond lost")

        self.assertEqual(self.transport.calls, [], "관찰만 하고 고치지 않는다")
        message = self.messages[-1]
        self.assertIn("lifecycle recovery observed", message)
        self.assertIn("mode=patrol", message)
        self.assertIn("bond lost", message)

    def test_lifecycle_recovery_during_mapping_is_recorded_too(self) -> None:
        self.controller.enter_mapping()

        self.controller.note_lifecycle_recovery()

        self.assertIn("mode=mapping", self.messages[-1])

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


class ParameterValueConversionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = RosLocalizationModeTransport()
        self.transport._parameter_type_ids = SimpleNamespace(
            PARAMETER_BOOL=1,
            PARAMETER_INTEGER=2,
            PARAMETER_DOUBLE=3,
            PARAMETER_STRING=4,
        )

    def test_supported_ros_parameter_values_are_converted(self) -> None:
        values = (
            (SimpleNamespace(type=1, bool_value=True), True),
            (SimpleNamespace(type=2, integer_value=7), 7),
            (SimpleNamespace(type=3, double_value=1.3), 1.3),
            (SimpleNamespace(type=4, string_value="DUBIN"), "DUBIN"),
        )

        for raw, expected in values:
            with self.subTest(expected=expected):
                self.assertEqual(
                    self.transport._parameter_value_to_python("name", raw),
                    expected,
                )

    def test_unset_parameter_is_rejected(self) -> None:
        with self.assertRaises(ServiceCallFailed):
            self.transport._parameter_value_to_python(
                "name", SimpleNamespace(type=0)
            )


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
