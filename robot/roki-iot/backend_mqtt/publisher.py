"""
한바퀴 Jetson MQTT Publisher 실행 모듈.

전체 데이터 흐름:

ESP32
    ↓ USB Serial
ESP32SerialReader
    ↓
RobotStateStore
    ↓
MQTT Payload Builder
    ↓
MqttClient
    ↓
Mosquitto Broker

Inbound:
MQTT command → PatrolCommandHandler
    → ESP32 Serial / YOLO pipeline / command ack

세부 책임:

- 환경설정: config/settings.py
- 상태 저장: state/robot_state_store.py
- Payload 생성: mqtt/payload_builder.py
- MQTT 통신: mqtt/client.py
- 명령 처리: mqtt/command_handler.py
- 파이프라인: pipeline/patrol_pipeline.py
- ESP32 통신: serial_reader.py
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from backend_config.settings import (
    AppSettings,
    load_settings,
)
from backend_mqtt.client import MqttClient
from backend_mqtt.command_handler import PatrolCommandHandler
from backend_mqtt.payload_builder import (
    build_pose_payload,
    build_status_payload,
)
from pipeline.patrol_pipeline import PatrolPipelineRunner
from serial_reader import ESP32SerialReader
from backend_state.robot_state_store import RobotStateStore


class RokiPublisherApplication:
    """
    Serial 수신, MQTT 발행, command 처리를
    관리하는 Jetson 애플리케이션 실행 클래스.
    """

    LOOP_INTERVAL_SECONDS = 0.1

    def __init__(
        self,
        *,
        settings: AppSettings,
        serial_reader: ESP32SerialReader,
        state_store: RobotStateStore,
        mqtt_client: MqttClient,
        command_handler: PatrolCommandHandler,
        pipeline_runner: PatrolPipelineRunner,
        pose_source: Any | None = None,
        lidar_health_source: Any | None = None,
        pose_publish_activity_check: Callable[[], bool] | None = None,
        obstacle_alert_activity_check: Callable[[], bool] | None = None,
        runtime_components: tuple[Any, ...] = (),
        start_serial_reader: bool = True,
    ) -> None:
        self._settings = settings
        self._serial_reader = serial_reader
        self._state_store = state_store
        self._mqtt_client = mqtt_client
        self._command_handler = command_handler
        self._pipeline_runner = pipeline_runner
        self._pose_source = pose_source
        self._lidar_health_source = lidar_health_source
        self._pose_publish_activity_check = (
            pose_publish_activity_check
            if pose_publish_activity_check is not None
            else lambda: True
        )
        self._obstacle_alert_activity_check = (
            obstacle_alert_activity_check
            if obstacle_alert_activity_check is not None
            else lambda: True
        )
        self._runtime_components = runtime_components
        self._started_runtime_components: list[Any] = []
        self._start_serial_reader = start_serial_reader
        self._serial_reader_started = False
        self._pose_source_started = False
        self._lidar_health_source_started = False

        self._last_pose_publish_time = 0.0
        self._last_status_publish_time = 0.0

        self._pose_wait_log_printed = False
        self._hardware_wait_log_printed = False
        self._stop_event = threading.Event()

    def start(self) -> None:
        """
        Serial과 MQTT 연결을 시작하고
        MQTT 발행 루프를 실행한다.
        """

        self._mqtt_client.set_command_handler(
            self._command_handler.handle
        )

        self._stop_event.clear()
        if self._pose_source is not None:
            self._pose_source.start()
            self._pose_source_started = True
        if self._lidar_health_source is not None:
            self._lidar_health_source.start()
            self._lidar_health_source_started = True
        for component in self._runtime_components:
            component.start()
            self._started_runtime_components.append(component)
        if self._start_serial_reader:
            self._serial_reader.start()
            self._serial_reader_started = True
        self._mqtt_client.connect()

        self._print_startup_information()
        self._run_publish_loop()

    def stop(self) -> None:
        """Serial, 파이프라인, MQTT를 안전하게 종료한다."""

        self._stop_event.set()
        stop_commands = getattr(
            self._mqtt_client,
            "stop_command_worker",
            None,
        )
        if callable(stop_commands):
            if not stop_commands(drain=False):
                print("[SYSTEM] MQTT command worker did not stop cleanly")
        try:
            self._command_handler.shutdown()
        except Exception as exc:
            print(f"[SYSTEM] safe shutdown error: {type(exc).__name__}")

        if self._serial_reader_started:
            self._serial_reader.stop()
            self._serial_reader_started = False

        for component in reversed(self._started_runtime_components):
            try:
                component.stop()
            except Exception as exc:
                print(
                    "[SYSTEM] runtime component stop error: "
                    f"{type(exc).__name__}"
                )
        self._started_runtime_components.clear()

        if self._lidar_health_source_started:
            self._lidar_health_source.stop()
            self._lidar_health_source_started = False

        if self._pose_source_started:
            self._pose_source.stop()
            self._pose_source_started = False

        self._mqtt_client.disconnect()

    def _run_publish_loop(self) -> None:
        """
        RobotStateStore 상태를 확인하고
        필요한 MQTT 메시지를 발행한다.
        """

        while not self._stop_event.is_set():
            current_time = time.monotonic()

            if self._serial_reader_started:
                is_running = getattr(self._serial_reader, "is_running", None)
                if callable(is_running) and not is_running():
                    self._state_store.update_robot_state("ERROR")
                    raise RuntimeError("Robot serial runtime stopped unexpectedly")

            self._command_handler.tick()

            self._publish_status_if_needed(
                current_time
            )

            self._publish_pose_if_needed(
                current_time
            )

            self._stop_event.wait(self.LOOP_INTERVAL_SECONDS)

    def _publish_status_if_needed(
        self,
        current_time: float,
        *,
        force: bool = False,
    ) -> None:
        """
        Status는 상태 변경 빈도와 무관하게 정기 주기로만 발행한다.
        """

        periodic_publish_due = (
            current_time
            - self._last_status_publish_time
            >= self._settings
            .status_publish_interval_seconds
        )

        if not force and not periodic_publish_due:
            return

        status = self._state_store.get_status()

        self._hardware_wait_log_printed = False

        payload = build_status_payload(
            schema_version=(
                self._settings.schema_version
            ),
            robot_key=self._settings.robot_key,
            status=status,
            obstacle_alert_enabled=self._obstacle_alert_activity_check(),
        )

        self._mqtt_client.publish(
            topic=self._settings.status_topic,
            payload=payload,
        )

        self._last_status_publish_time = (
            current_time
        )

        self._state_store.mark_status_published()

    def _publish_pose_if_needed(
        self,
        current_time: float,
        *,
        force: bool = False,
    ) -> None:
        """
        실제 Pose가 존재하고 발행 주기가 지난 경우
        Pose를 MQTT로 발행한다.
        """

        if not self._pose_publish_activity_check():
            return

        publish_due = (
            current_time
            - self._last_pose_publish_time
            >= self._settings
            .pose_publish_interval_seconds
        )

        if not force and not publish_due:
            return

        pose = self._state_store.get_pose()

        # Localization 연결 전에는
        # 가짜 좌표를 발행하지 않는다.
        if pose is None:
            self._print_pose_wait_log()
            return

        payload = build_pose_payload(
            schema_version=(
                self._settings.schema_version
            ),
            robot_key=self._settings.robot_key,
            pose=pose,
        )

        self._mqtt_client.publish(
            topic=self._settings.pose_topic,
            payload=payload,
        )

        self._last_pose_publish_time = (
            current_time
        )

        self._pose_wait_log_printed = False

    def publish_now(self) -> None:
        """Best-effort final telemetry while MQTT is still connected."""

        now = time.monotonic()
        self._publish_pose_if_needed(now, force=True)
        self._publish_status_if_needed(now, force=True)

    def _print_startup_information(self) -> None:
        """현재 실행 설정을 터미널에 출력한다."""

        print(
            "[SYSTEM] Status 발행 주기: "
            f"{self._settings.status_publish_interval_seconds}"
            "초"
        )

        print(
            "[SYSTEM] Pose 발행 주기: "
            f"{self._settings.pose_publish_interval_seconds}"
            "초"
        )

        print(
            "[SYSTEM] Status 토픽: "
            f"{self._settings.status_topic}"
        )

        print(
            "[SYSTEM] Pose 토픽: "
            f"{self._settings.pose_topic}"
        )

        print(
            "[SYSTEM] Command 구독 토픽: "
            f"{self._settings.command_topic}"
        )

        print(
            "[SYSTEM] Command ACK 토픽: "
            f"{self._settings.command_response_topic}"
        )

    def _print_pose_wait_log(self) -> None:
        """Pose 대기 로그가 반복되지 않게 출력한다."""

        if self._pose_wait_log_printed:
            return

        print(
            "[WAIT] 실제 Pose 수신 대기 "
            "- 가짜 좌표는 발행하지 않습니다."
        )

        self._pose_wait_log_printed = True

    def _print_hardware_wait_log(self) -> None:
        """ESP32 대기 로그가 반복되지 않게 출력한다."""

        if self._hardware_wait_log_printed:
            return

        print(
            "[WAIT] ESP32 최초 장비 상태 수신 대기"
        )

        self._hardware_wait_log_printed = True


def create_application() -> RokiPublisherApplication:
    """
    실행에 필요한 객체를 생성하고 연결한다.

    SerialReader와 MQTT Publisher가
    동일한 RobotStateStore 객체를 공유한다.
    """

    settings = load_settings()

    state_store = RobotStateStore()

    serial_reader = ESP32SerialReader(
        state_store=state_store,
    )

    mqtt_client = MqttClient(
        settings
    )

    pipeline_runner = PatrolPipelineRunner(
        source_a=settings.pipeline_source_a,
        source_b=settings.pipeline_source_b,
        extra_args=settings.pipeline_extra_args,
        start_grace_seconds=(
            settings.pipeline_start_grace_seconds
        ),
    )

    command_handler = PatrolCommandHandler(
        settings=settings,
        mqtt_client=mqtt_client,
        serial_reader=serial_reader,
        state_store=state_store,
        pipeline_runner=pipeline_runner,
    )

    return RokiPublisherApplication(
        settings=settings,
        serial_reader=serial_reader,
        state_store=state_store,
        mqtt_client=mqtt_client,
        command_handler=command_handler,
        pipeline_runner=pipeline_runner,
    )


def main() -> None:
    """Jetson MQTT Publisher 애플리케이션 진입점."""

    application = create_application()

    try:
        application.start()

    except KeyboardInterrupt:
        print(
            "\n[SYSTEM] 프로그램을 종료합니다."
        )

    except Exception as error:
        print(
            "[ERROR] "
            f"{type(error).__name__}: {error}"
        )

    finally:
        application.stop()


if __name__ == "__main__":
    main()
