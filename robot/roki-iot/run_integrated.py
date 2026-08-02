#!/usr/bin/env python3
"""Final Serial Runtime과 기존 MQTT Publisher의 통합 진입점."""

from __future__ import annotations

import sys
import signal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
FINAL_RUNTIME_ROOT = PROJECT_ROOT.parent / "roki"


def _build_final_runtime() -> Any:
    """모듈명이 겹치는 두 프로젝트를 분리해 Final Runtime을 생성한다."""

    final_root = str(FINAL_RUNTIME_ROOT)
    original_sys_path = list(sys.path)
    sys.path = [
        final_root,
        *(path for path in original_sys_path if path != final_root),
    ]
    try:
        from scripts.run_runtime import build_runtime

        runtime = build_runtime()
    finally:
        sys.path = original_sys_path

    # Final Runtime 객체는 필요한 클래스 참조를 이미 보유한다.
    # 이후 legacy `state` package를 로드할 수 있도록 이름만 비운다.
    for module_name in tuple(sys.modules):
        if module_name == "state" or module_name.startswith("state."):
            del sys.modules[module_name]
    return runtime


def create_integrated_application(
    *,
    final_runtime: Any | None = None,
) -> Any:
    """Final Runtime과 기존 Publisher가 사용할 객체를 조립한다."""

    runtime = final_runtime or _build_final_runtime()

    from config.settings import load_settings
    from integration.runtime_state_backend_adapter import (
        FinalRuntimeService,
        RuntimeStateBackendAdapter,
    )
    from mqtt.client import MqttClient
    from mqtt.command_handler import PatrolCommandHandler
    from mqtt.publisher import RokiPublisherApplication
    from pipeline.patrol_pipeline import PatrolPipelineRunner
    from state.robot_state_store import RobotStateStore

    settings = load_settings()
    backend_state_store = RobotStateStore()
    adapter = RuntimeStateBackendAdapter(
        runtime=runtime,
        backend_state_store=backend_state_store,
    )
    adapter.connect()

    runtime_service = FinalRuntimeService(
        runtime,
        patrol_drive_speed_pwm=settings.patrol_drive_speed_pwm,
        patrol_steering_degrees=settings.patrol_steering_degrees,
    )
    mqtt_client = MqttClient(settings)
    pipeline_runner = PatrolPipelineRunner(
        source_a=settings.pipeline_source_a,
        source_b=settings.pipeline_source_b,
        extra_args=settings.pipeline_extra_args,
        start_grace_seconds=settings.pipeline_start_grace_seconds,
    )
    command_handler = PatrolCommandHandler(
        settings=settings,
        mqtt_client=mqtt_client,
        serial_reader=runtime_service,
        state_store=backend_state_store,
        pipeline_runner=pipeline_runner,
        pipeline_enabled=settings.pipeline_enabled,
    )
    return RokiPublisherApplication(
        settings=settings,
        serial_reader=runtime_service,
        state_store=backend_state_store,
        mqtt_client=mqtt_client,
        command_handler=command_handler,
        pipeline_runner=pipeline_runner,
    )


def main() -> None:
    application = create_integrated_application()

    def stop_handler(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    try:
        application.start()
    except KeyboardInterrupt:
        print("\n[SYSTEM] 프로그램을 종료합니다.")
    except Exception as error:
        print(f"[ERROR] {type(error).__name__}: {error}")
    finally:
        application.stop()


if __name__ == "__main__":
    main()
