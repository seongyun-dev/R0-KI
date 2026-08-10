"""최초 장비 상태 게이트.

ESP32 가 hardwareStatus 를 한 번도 보고하지 않았는데 status 를 발행하면
백엔드가 기본값 DISCONNECTED 를 실제 보고로 착각한다. 배터리는 null 일 수
있고 모듈이 정말 DISCONNECTED 일 수도 있어서 payload 값으로는 구별되지 않는다.

이 게이트는 실기에서 돌고 있었는데 git 에 없었고(fa643c2 에서 회수), 회수
시점까지 **검증하는 테스트가 하나도 없었다.**
"""

from __future__ import annotations

import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend_mqtt.publisher import RokiPublisherApplication
from backend_state.robot_state_store import RobotStateStore


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        status_publish_interval_seconds=5.0,
        pose_publish_interval_seconds=1.0,
        schema_version=1,
        robot_key="ROKI-01",
        status_topic="hanbakwi/v1/robots/ROKI-01/status",
        pose_topic="hanbakwi/v1/robots/ROKI-01/pose",
    )


def _application(store) -> tuple[RokiPublisherApplication, Mock]:
    client = Mock()
    application = RokiPublisherApplication(
        settings=_settings(),
        serial_reader=Mock(),
        state_store=store,
        mqtt_client=client,
        command_handler=Mock(),
        pipeline_runner=Mock(),
    )
    return application, client


def _hardware(battery: float = 80.0) -> SimpleNamespace:
    return SimpleNamespace(
        battery=battery,
        motor="NORMAL",
        line_sensor="NORMAL",
    )


class PublisherHardwareGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = RobotStateStore()
        self.application, self.client = _application(self.store)

    def test_nothing_is_published_before_the_first_hardware_report(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.application._publish_status_if_needed(100.0)

        self.client.publish.assert_not_called()

    def test_status_is_published_once_hardware_arrives(self) -> None:
        self.store.update_hardware(_hardware())

        self.application._publish_status_if_needed(100.0)

        self.client.publish.assert_called_once()

    def test_force_does_not_bypass_the_gate(self) -> None:
        """force 는 주기를 건너뛰라는 뜻이지 가짜를 보내라는 뜻이 아니다."""

        with contextlib.redirect_stdout(io.StringIO()):
            self.application._publish_status_if_needed(100.0, force=True)

        self.client.publish.assert_not_called()

    def test_the_wait_log_is_printed_once_not_every_cycle(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.application._publish_status_if_needed(100.0)
            self.application._publish_status_if_needed(200.0)

        self.assertEqual(buffer.getvalue().count("최초 장비 상태 수신 대기"), 1)


class _ResetStore:
    """세대 리셋 직후의 저장소.

    ``get_publishable_status`` 는 None 을 주는데 ``get_status`` 는 초기화된
    값을 계속 돌려준다. 판정과 읽기가 나뉘어 있으면 이 값이 발행된다.

    ``Mock(spec=...)`` 를 쓰지 않는 이유: publisher 는 인터페이스 조회를
    ``type(store)`` 에서 한다. 인스턴스에서 조회하면 아무 속성이나 만들어내는
    ``Mock`` 저장소를 쓰는 기존 테스트들이 전부 게이트를 통과해버린다.
    ``Mock(spec=X)`` 의 타입은 ``Mock`` 이라 클래스 조회에 걸리지 않는다.
    """

    def __init__(self) -> None:
        self.get_status_calls = 0

    def get_publishable_status(self):
        return None

    def get_status(self):
        self.get_status_calls += 1
        return SimpleNamespace(
            battery=None,
            state="IDLE",
            motor="DISCONNECTED",
            camera="DISCONNECTED",
            lidar="DISCONNECTED",
            line_sensor="DISCONNECTED",
            obstacle=SimpleNamespace(
                status="CLEAR", direction="NONE", reason_message=None
            ),
        )

    def mark_status_published(self) -> None:
        pass


class AtomicReadTest(unittest.TestCase):
    """판정과 읽기가 한 번의 호출이어야 한다.

    나눠 부르면 그 사이에 reset_connection() 이 끼어들 수 있다: 판정은 참인데
    읽은 값은 초기화된 DISCONNECTED 라서, 게이트가 막으려던 payload 가 그대로
    나간다. 좁은 창이지만 시리얼 재연결마다 열린다.
    """

    def test_get_status_is_not_consulted_when_the_atomic_reader_exists(self) -> None:
        store = _ResetStore()
        application, client = _application(store)

        with contextlib.redirect_stdout(io.StringIO()):
            application._publish_status_if_needed(100.0)

        self.assertEqual(store.get_status_calls, 0)
        client.publish.assert_not_called()

    def test_a_generation_reset_between_the_two_calls_cannot_leak(self) -> None:
        store = _ResetStore()
        application, client = _application(store)

        with contextlib.redirect_stdout(io.StringIO()):
            application._publish_status_if_needed(100.0, force=True)

        client.publish.assert_not_called()


class StoreContractTest(unittest.TestCase):
    def test_publishable_status_is_none_until_hardware_is_reported(self) -> None:
        store = RobotStateStore()

        self.assertIsNone(store.get_publishable_status())

        store.update_hardware(_hardware())

        self.assertIsNotNone(store.get_publishable_status())

    def test_runtime_store_reopens_the_gate_on_reconnect(self) -> None:
        """운영 경로의 저장소는 시리얼 세대가 바뀌면 다시 막아야 한다.

        run.sh -> run_integrated.py 가 쓰는 것은 이쪽이다. backend_state 쪽
        저장소에는 reset 경로가 없어서 같은 검사를 할 수 없다 -- 지금은
        레거시 create_application() 만 쓰므로 남겨둔다.
        """

        from serial_comm.protocol import (
            HardwareStatus,
            LineSensorStatus,
            MotorStatus,
        )
        from state.robot_state import RobotStateStore as RuntimeStateStore

        store = RuntimeStateStore()
        self.assertIsNone(store.get_publishable_status())

        store.update_hardware_status(
            HardwareStatus(
                battery_percent=80.0,
                motor=MotorStatus.NORMAL,
                line_sensor=LineSensorStatus.NORMAL,
            )
        )
        self.assertIsNotNone(store.get_publishable_status())

        store.reset_connection()

        self.assertIsNone(store.get_publishable_status())


class MissingInterfaceTest(unittest.TestCase):
    """게이트가 사라졌다는 사실이 조용히 묻히지 않아야 한다."""

    def test_a_store_without_the_reader_is_reported_once(self) -> None:
        store = Mock(spec=["get_status", "get_pose", "mark_status_published"])
        store.get_status.return_value = SimpleNamespace(
            battery=80.0,
            state="IDLE",
            motor="NORMAL",
            camera="NORMAL",
            lidar="NORMAL",
            line_sensor="NORMAL",
            obstacle=SimpleNamespace(
                status="CLEAR", direction="NONE", reason_message=None
            ),
        )
        application, client = _application(store)

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            application._publish_status_if_needed(100.0)
            application._publish_status_if_needed(200.0)

        self.assertEqual(
            buffer.getvalue().count("최초 장비 상태 게이트가 비활성"), 1
        )
        self.assertEqual(client.publish.call_count, 2)


if __name__ == "__main__":
    unittest.main()
