from __future__ import annotations

import unittest
from types import SimpleNamespace

from aiot_robot.runtime_ai import RosAiCoordinator


class FakeBridge:
    def __init__(self, *, apply_result: bool = True) -> None:
        self.disabled: list[str] = []
        self.enabled: list[int] = []
        self.apply_result = apply_result
        self.destroyed = False
        self.gate = SimpleNamespace(
            decision=lambda: SimpleNamespace(allowed=True, reason="AI_READY")
        )

    def safe_disable(self, reason: str) -> int:
        self.disabled.append(reason)
        return 0

    def set_detection_enabled(
        self,
        enabled: bool,
        patrol_id: int,
        _reason: str,
    ) -> int:
        if enabled:
            self.enabled.append(patrol_id)
        return 4

    def wait_for_detection_state(self, *_args, **_kwargs) -> bool:
        return self.apply_result

    def detection_applied(self, patrol_id: int) -> bool:
        return self.apply_result and self.enabled[-1:] == [patrol_id]

    def destroy_node(self) -> None:
        self.destroyed = True


class FakeRclpy:
    def __init__(self) -> None:
        self.running = False

    def ok(self) -> bool:
        return self.running

    def init(self, *, args=None) -> None:
        del args
        self.running = True

    def shutdown(self) -> None:
        self.running = False


class FakeExecutor:
    def __init__(self) -> None:
        self.node = None

    def add_node(self, node) -> None:
        self.node = node

    def remove_node(self, node) -> None:
        if self.node is node:
            self.node = None

    def shutdown(self) -> None:
        return None

    def spin_once(self, *, timeout_sec: float) -> None:
        del timeout_sec


class RosAiCoordinatorTest(unittest.TestCase):
    def test_start_publishes_explicit_disable_before_spin(self) -> None:
        bridge = FakeBridge()
        rclpy = FakeRclpy()
        coordinator = RosAiCoordinator(
            lambda _event: None,
            SimpleNamespace(update_camera_status=lambda _status: None),
            bridge_factory=lambda *_args, **_kwargs: bridge,
        )
        coordinator._load_ros_runtime = lambda: (rclpy, FakeExecutor)
        coordinator._spin = lambda: None

        coordinator.start()
        self.assertEqual(bridge.disabled, ["ROBOT_RUNTIME_STARTED"])
        coordinator.stop()
        self.assertTrue(bridge.destroyed)

    def test_enable_waits_for_matching_applied_status(self) -> None:
        bridge = FakeBridge(apply_result=True)
        coordinator = RosAiCoordinator(
            None,
            None,
            control_apply_timeout_seconds=0.1,
        )
        coordinator._bridge = bridge

        coordinator.enable(17)

        self.assertEqual(bridge.enabled, [17])
        self.assertTrue(coordinator.detection_applied(17))

    def test_unconfirmed_enable_fails_closed(self) -> None:
        bridge = FakeBridge(apply_result=False)
        coordinator = RosAiCoordinator(
            None,
            None,
            control_apply_timeout_seconds=0.1,
        )
        coordinator._bridge = bridge

        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            coordinator.enable(17)

        self.assertEqual(bridge.disabled, ["AI_ENABLE_NOT_APPLIED"])


if __name__ == "__main__":
    unittest.main()
