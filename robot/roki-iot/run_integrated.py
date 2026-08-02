#!/usr/bin/env python3
"""Production composition root for Robot MQTT, navigation, AI and telemetry."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
ROBOT_ROOT = PROJECT_ROOT.parent
FINAL_RUNTIME_ROOT = ROBOT_ROOT / "roki"
ROBOT_SRC_ROOT = ROBOT_ROOT / "src"

for path in (str(ROBOT_SRC_ROOT), str(FINAL_RUNTIME_ROOT), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _build_final_components() -> tuple[Any, Any, Any]:
    """Build the sole ESP32 owner and read-only ROS sensor bridges."""

    final_root = str(FINAL_RUNTIME_ROOT)
    original_sys_path = list(sys.path)
    sys.path = [final_root, *(path for path in original_sys_path if path != final_root)]
    try:
        from scripts.run_runtime import (
            build_ros_lidar_health_bridge,
            build_ros_tf_pose_bridge,
            build_runtime,
        )

        runtime = build_runtime()
        pose_bridge = build_ros_tf_pose_bridge(runtime.state_store)
        lidar_health_bridge = build_ros_lidar_health_bridge(runtime.state_store)
    finally:
        sys.path = original_sys_path

    # roki-iot also has a legacy ``state`` package. Keep the already-created
    # final objects but let subsequent imports resolve the adapter package.
    for module_name in tuple(sys.modules):
        if module_name == "state" or module_name.startswith("state."):
            del sys.modules[module_name]
    return runtime, pose_bridge, lidar_health_bridge


def _selected_route_path(route_path: str | Path | None = None) -> Path:
    return Path(
        route_path
        or os.getenv(
            "ROKI_ROUTE_FILE",
            "/var/lib/aiot/config/route.local.yaml",
        )
    )


def _build_navigation_service(
    route_path: str | Path | None = None,
    *,
    encoder_limited: bool,
) -> Any:
    selected_path = _selected_route_path(route_path)
    if not selected_path.is_file():
        raise RuntimeError(f"waypoint route file is missing: {selected_path}")
    from navigation.encoder_waypoint import (
        EncoderWaypointSettings,
        validate_straight_encoder_route,
    )
    from navigation.route import load_route
    from navigation.service import WaypointNavigationService

    route = load_route(selected_path)
    if encoder_limited:
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


def _navigation_mode(settings: Any) -> str:
    mode = settings.navigation_mode
    if mode != "auto":
        return mode
    calibrated = bool(os.getenv("ROKI_WHEELBASE_M")) and bool(
        os.getenv("ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG")
    )
    nav2_available = importlib.util.find_spec("nav2_msgs") is not None
    return "nav2" if calibrated and nav2_available else "encoder_limited"


def _build_nav2_driver(service_holder: dict[str, Any]) -> Any:
    from navigation.cmd_vel_adapter import AckermannCommandSettings
    from navigation.ros_nav2_bridge import RosNav2Bridge, RosNav2BridgeSettings

    wheelbase = os.getenv("ROKI_WHEELBASE_M")
    maximum_angle = os.getenv("ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG")
    if not wheelbase or not maximum_angle:
        raise RuntimeError(
            "Nav2 mode requires ROKI_WHEELBASE_M and "
            "ROKI_MAXIMUM_ROAD_WHEEL_ANGLE_DEG"
        )
    settings = RosNav2BridgeSettings(
        ackermann=AckermannCommandSettings(
            wheelbase_m=float(wheelbase),
            maximum_road_wheel_angle_deg=float(maximum_angle),
            maximum_linear_speed_mps=float(
                os.getenv("ROKI_MAXIMUM_LINEAR_SPEED_MPS", "0.4")
            ),
            minimum_drive_pwm=int(os.getenv("PATROL_DRIVE_SPEED_PWM", "45")),
            maximum_drive_pwm=int(os.getenv("ROKI_MAXIMUM_DRIVE_PWM", "51")),
            steering_left_deg=60,
            steering_center_deg=80,
            steering_right_deg=100,
        ),
        cmd_vel_topic=os.getenv("ROKI_CMD_VEL_TOPIC", "/cmd_vel"),
        navigate_action=os.getenv("ROKI_NAVIGATE_ACTION", "/navigate_to_pose"),
        map_frame=os.getenv("ROKI_MAP_FRAME", "map"),
    )
    return RosNav2Bridge(
        settings=settings,
        motion_sink=lambda command: service_holder["service"].apply_motion_command(
            command
        ),
        failure_sink=lambda reason: service_holder["service"].fail_patrol(reason),
    )


def create_integrated_application(
    *,
    final_runtime: Any | None = None,
    pose_bridge: Any | None = None,
    lidar_health_bridge: Any | None = None,
    start_serial_runtime: bool = True,
    navigation_service: Any | None = None,
    navigation_mode: str = "encoder_limited",
    operational_ai: bool = False,
    ai_controller: Any | None = None,
    event_worker: Any | None = None,
    deployment_guard: Any | None = None,
) -> Any:
    """Compose all production components around exactly one RobotRuntime."""

    if final_runtime is None:
        runtime, default_pose_bridge, default_lidar_bridge = _build_final_components()
        pose_bridge = pose_bridge or default_pose_bridge
        lidar_health_bridge = lidar_health_bridge or default_lidar_bridge
    else:
        runtime = final_runtime

    from aiot_robot.deployment_guard import PatrolDeploymentGuard
    from aiot_robot.event_delivery import DetectionRecorder, EventDeliveryWorker
    from aiot_robot.outbox import DetectionOutbox
    from config.settings import load_settings
    from integration.runtime_state_backend_adapter import FinalRuntimeService
    from mqtt.client import MqttClient
    from mqtt.command_handler import PatrolCommandHandler
    from mqtt.publisher import RokiPublisherApplication
    from pipeline.patrol_pipeline import PatrolPipelineRunner

    settings = load_settings()
    state_store = runtime.state_store
    service_holder: dict[str, Any] = {}
    navigation_driver = (
        _build_nav2_driver(service_holder) if navigation_mode == "nav2" else None
    )
    runtime_service = FinalRuntimeService(
        runtime,
        patrol_drive_speed_pwm=settings.patrol_drive_speed_pwm,
        patrol_steering_degrees=settings.patrol_steering_degrees,
        navigation_service=navigation_service,
        navigation_start_x_m=float(os.getenv("ROKI_ROUTE_START_X_M", "1.0")),
        navigation_start_y_m=float(os.getenv("ROKI_ROUTE_START_Y_M", "2.5")),
        navigation_maximum_travel_m=float(
            os.getenv("ROKI_ROUTE_MAXIMUM_TRAVEL_M", "0.70")
        ),
        encoder_fallback_enabled=settings.encoder_fallback_enabled,
        navigation_driver=navigation_driver,
        deployment_guard=deployment_guard
        or PatrolDeploymentGuard(
            os.getenv(
                "AIOT_PATROL_DEPLOY_LOCK_FILE",
                "/var/lib/aiot/state/patrol-deploy.lock",
            )
        ),
    )
    service_holder["service"] = runtime_service

    runtime_components: list[Any] = []
    readiness_checks: list[Any] = []
    if operational_ai:
        from aiot_robot.runtime_ai import RosAiCoordinator

        outbox = DetectionOutbox(
            os.getenv("AIOT_EVENT_OUTBOX_DIR", "/var/lib/aiot/outbox")
        )
        recorder = DetectionRecorder(outbox, state_store)
        ai_controller = ai_controller or RosAiCoordinator(recorder, state_store)
        event_worker = event_worker or EventDeliveryWorker(
            outbox,
            token_file=settings.service_token_file,
        )
        runtime_components.extend((ai_controller, event_worker))
        readiness_checks.append(event_worker.readiness_for_new_patrol)
    elif ai_controller is not None:
        runtime_components.append(ai_controller)
    if event_worker is not None and event_worker not in runtime_components:
        runtime_components.append(event_worker)
        readiness_checks.append(event_worker.readiness_for_new_patrol)

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
        pipeline_enabled=False,
        ai_controller=ai_controller,
        readiness_checks=readiness_checks,
    )
    application = RokiPublisherApplication(
        settings=settings,
        serial_reader=runtime_service,
        state_store=state_store,
        mqtt_client=mqtt_client,
        command_handler=command_handler,
        pipeline_runner=pipeline_runner,
        pose_source=pose_bridge,
        lidar_health_source=lidar_health_bridge,
        runtime_components=tuple(runtime_components),
        start_serial_reader=start_serial_runtime,
    )
    command_handler.set_flush_telemetry(application.publish_now)
    runtime_service.set_destination_listener(command_handler.on_destination_reached)
    return application


def preflight(route_path: str | Path | None = None) -> dict[str, Any]:
    """Validate configuration without MQTT, ROS nodes or serial access."""

    from config.settings import load_settings

    settings = load_settings()
    mode = _navigation_mode(settings)
    navigation = _build_navigation_service(
        route_path,
        encoder_limited=mode == "encoder_limited",
    )
    if mode == "nav2":
        holder: dict[str, Any] = {"service": None}
        _build_nav2_driver(holder)
    return {
        "robotKey": settings.robot_key,
        "navigationMode": mode,
        "routeId": navigation.route.route_id,
        "waypoints": len(navigation.route.waypoints),
        "aiRequired": settings.ai_required_for_patrol,
        "lidarRequired": settings.lidar_required_for_patrol,
        "serialAccessed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pose-only",
        action="store_true",
        help="start telemetry without opening the ESP32 serial port",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate config and route without opening MQTT, ROS or serial",
    )
    parser.add_argument("--route", default=None)
    args = parser.parse_args(argv)
    if args.check:
        import json

        print(json.dumps(preflight(args.route), sort_keys=True))
        return 0

    from config.settings import load_settings

    settings = load_settings()
    mode = _navigation_mode(settings)
    navigation = _build_navigation_service(
        args.route,
        encoder_limited=mode == "encoder_limited",
    )
    application = create_integrated_application(
        start_serial_runtime=not args.pose_only,
        navigation_service=navigation,
        navigation_mode=mode,
        operational_ai=True,
    )

    def stop_handler(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    try:
        application.start()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.getLogger(__name__).exception("Integrated Robot runtime failed")
        return 1
    finally:
        application.stop()


if __name__ == "__main__":
    raise SystemExit(main())
