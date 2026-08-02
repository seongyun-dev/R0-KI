#!/usr/bin/env python3
"""Final Serial Runtime과 기존 MQTT Publisher의 통합 진입점."""

from __future__ import annotations

import sys
import signal
import os
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


def _build_navigation_service(route_path: str | Path | None = None) -> Any:
    """Load the local route and build a hardware-independent waypoint mission."""

    selected_path = Path(
        route_path
        or os.getenv(
            "ROKI_ROUTE_FILE",
            str(FINAL_RUNTIME_ROOT / "config" / "route.local.yaml"),
        )
    )
    if not selected_path.is_file():
        raise RuntimeError(
            "waypoint route file is missing; refusing fixed straight patrol: "
            f"{selected_path}"
        )
    final_root = str(FINAL_RUNTIME_ROOT)
    if final_root not in sys.path:
        sys.path.insert(0, final_root)
    from navigation.encoder_waypoint import (
        EncoderWaypointSettings,
        validate_straight_encoder_route,
    )
    from navigation.route import load_route
    from navigation.service import WaypointNavigationService

    route = load_route(selected_path)
    validate_straight_encoder_route(
        route,
        EncoderWaypointSettings(
            start_x_m=float(os.getenv("ROKI_ROUTE_START_X_M", "0.0")),
            start_y_m=float(os.getenv("ROKI_ROUTE_START_Y_M", "0.0")),
            maximum_travel_m=float(
                os.getenv("ROKI_ROUTE_MAXIMUM_TRAVEL_M", "0.70")
            ),
        ),
    )
    return WaypointNavigationService(route)


def create_integrated_application(
    *,
    final_runtime: Any | None = None,
    navigation_service: Any | None = None,
) -> Any:
    """Final Runtime과 기존 Publisher가 사용할 객체를 조립한다."""

    runtime = final_runtime or _build_final_runtime()

    from config.settings import load_settings
    from integration.encoder_waypoint_runtime_service import (
        EncoderWaypointRuntimeService,
    )
    from integration.runtime_state_backend_adapter import (
        RuntimeStateBackendAdapter,
        WaypointStateBackendAdapter,
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
    if navigation_service is not None:
        WaypointStateBackendAdapter(
            navigation_service,
            backend_state_store,
        ).connect()

    runtime_service = EncoderWaypointRuntimeService(
        runtime,
        patrol_drive_speed_pwm=settings.patrol_drive_speed_pwm,
        patrol_steering_degrees=settings.patrol_steering_degrees,
        navigation_service=navigation_service,
        navigation_start_x_m=float(
            os.getenv("ROKI_ROUTE_START_X_M", "0.0")
        ),
        navigation_start_y_m=float(
            os.getenv("ROKI_ROUTE_START_Y_M", "0.0")
        ),
        navigation_maximum_travel_m=float(
            os.getenv("ROKI_ROUTE_MAXIMUM_TRAVEL_M", "0.70")
        ),
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
    application = create_integrated_application(
        navigation_service=_build_navigation_service()
    )

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
