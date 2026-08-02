#!/usr/bin/env python3
"""Final Serial Runtime과 기존 MQTT Publisher의 단일 실행 진입점.

통합 운용에서는 legacy ``python3 -m mqtt.publisher``를 함께 실행하지 않는다.
이 모듈만 Final RobotRuntime의 Serial 연결과 공용 Store를 사용한다.
"""

from __future__ import annotations

import argparse
import os
import sys
import signal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
FINAL_RUNTIME_ROOT = PROJECT_ROOT.parent / "roki"


def _build_final_components() -> tuple[Any, Any, Any]:
    """Final Runtime과 같은 Store를 쓰는 ROS bridges를 생성한다."""

    final_root = str(FINAL_RUNTIME_ROOT)
    original_sys_path = list(sys.path)
    sys.path = [
        final_root,
        *(path for path in original_sys_path if path != final_root),
    ]
    try:
        from scripts.run_runtime import (
            build_ros_lidar_health_bridge,
            build_ros_tf_pose_bridge,
            build_runtime,
        )

        runtime = build_runtime()
        pose_bridge = build_ros_tf_pose_bridge(runtime.state_store)
        lidar_health_bridge = build_ros_lidar_health_bridge(
            runtime.state_store
        )
    finally:
        sys.path = original_sys_path

    # Final Runtime 객체는 필요한 클래스 참조를 이미 보유한다.
    # 이후 legacy `state` package를 로드할 수 있도록 이름만 비운다.
    for module_name in tuple(sys.modules):
        if module_name == "state" or module_name.startswith("state."):
            del sys.modules[module_name]
    return runtime, pose_bridge, lidar_health_bridge


def _build_final_runtime() -> Any:
    """기존 내부 호출 호환용 Final Runtime 생성 함수."""

    runtime, _pose_bridge, _lidar_health_bridge = _build_final_components()
    return runtime


def _build_navigation_service(route_path: str | Path | None = None) -> Any:
    """Load and bound the temporary straight encoder waypoint route."""

    selected_path = Path(
        route_path
        or os.getenv(
            "ROKI_ROUTE_FILE",
            str(FINAL_RUNTIME_ROOT / "config" / "route.local.yaml"),
        )
    )
    if not selected_path.is_file():
        raise RuntimeError(
            "waypoint route file is missing; refusing encoder patrol: "
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
            start_x_m=float(os.getenv("ROKI_ROUTE_START_X_M", "1.0")),
            start_y_m=float(os.getenv("ROKI_ROUTE_START_Y_M", "2.5")),
            maximum_travel_m=float(
                os.getenv("ROKI_ROUTE_MAXIMUM_TRAVEL_M", "0.70")
            ),
        ),
    )
    return WaypointNavigationService(route)


def create_integrated_application(
    *,
    final_runtime: Any | None = None,
    pose_bridge: Any | None = None,
    lidar_health_bridge: Any | None = None,
    start_serial_runtime: bool = True,
    navigation_service: Any | None = None,
) -> Any:
    """Final Runtime의 단일 Store를 기존 Publisher에 직접 주입한다."""

    if final_runtime is None:
        runtime, default_pose_bridge, default_lidar_bridge = (
            _build_final_components()
        )
        if pose_bridge is None:
            pose_bridge = default_pose_bridge
        if lidar_health_bridge is None:
            lidar_health_bridge = default_lidar_bridge
    else:
        runtime = final_runtime

    from config.settings import load_settings
    from integration.runtime_state_backend_adapter import (
        FinalRuntimeService,
    )
    from mqtt.client import MqttClient
    from mqtt.command_handler import PatrolCommandHandler
    from mqtt.publisher import RokiPublisherApplication
    from pipeline.patrol_pipeline import PatrolPipelineRunner

    settings = load_settings()
    state_store = runtime.state_store

    runtime_service = FinalRuntimeService(
        runtime,
        patrol_drive_speed_pwm=settings.patrol_drive_speed_pwm,
        patrol_steering_degrees=settings.patrol_steering_degrees,
        navigation_service=navigation_service,
        navigation_start_x_m=float(
            os.getenv("ROKI_ROUTE_START_X_M", "1.0")
        ),
        navigation_start_y_m=float(
            os.getenv("ROKI_ROUTE_START_Y_M", "2.5")
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
        state_store=state_store,
        pipeline_runner=pipeline_runner,
        pipeline_enabled=settings.pipeline_enabled,
    )
    return RokiPublisherApplication(
        settings=settings,
        serial_reader=runtime_service,
        state_store=state_store,
        mqtt_client=mqtt_client,
        command_handler=command_handler,
        pipeline_runner=pipeline_runner,
        pose_source=pose_bridge,
        lidar_health_source=lidar_health_bridge,
        start_serial_reader=start_serial_runtime,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pose-only",
        action="store_true",
        help="ESP32 Serial Runtime 없이 TF Map Pose와 MQTT만 검증합니다",
    )
    args = parser.parse_args()
    application = create_integrated_application(
        start_serial_runtime=not args.pose_only,
        navigation_service=(
            None if args.pose_only else _build_navigation_service()
        ),
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
