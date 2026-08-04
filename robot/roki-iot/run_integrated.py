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

    return runtime, pose_bridge, lidar_health_bridge


def _selected_route_path(route_path: str | Path | None = None) -> Path:
    return Path(
        route_path
        or os.getenv(
            "ROKI_ROUTE_FILE",
            "/var/lib/aiot/config/route.local.yaml",
        )
    )


def _validate_import_namespaces() -> None:
    """Ensure final-runtime and backend-compatibility packages coexist."""

    final_root = str(FINAL_RUNTIME_ROOT)
    original_sys_path = list(sys.path)
    preserved_state_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "state" or name.startswith("state.")
    }
    for name in preserved_state_modules:
        del sys.modules[name]
    sys.path = [final_root, *(path for path in original_sys_path if path != final_root)]
    try:
        from state.robot_state import RobotStateStore as FinalRobotStateStore
        from backend_state.robot_state_store import (
            RobotStateStore as BackendRobotStateStore,
        )
        from mqtt.client import MqttClient as FinalMqttClient
        from backend_mqtt.client import MqttClient as BackendMqttClient
        from integration.runtime_state_backend_adapter import FinalRuntimeService

        if (
            FinalRobotStateStore is BackendRobotStateStore
            or FinalMqttClient is BackendMqttClient
            or FinalRuntimeService is None
        ):
            raise RuntimeError("runtime import namespaces are not isolated")
    finally:
        sys.path = original_sys_path
        for name in tuple(sys.modules):
            if name == "state" or name.startswith("state."):
                del sys.modules[name]
        sys.modules.update(preserved_state_modules)


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


def _build_manual_demo_components(runtime: Any) -> tuple[Any, Any]:
    """Build the temporary TTY demo without creating another Serial owner."""

    from control.manual_drive_controller import (
        ManualDriveController,
        ManualDriveSettings,
    )
    from integration.manual_keyboard_input import ManualKeyboardInput

    settings = ManualDriveSettings(
        forward_target_pwm=int(os.getenv("ROKI_MANUAL_FORWARD_PWM", "45")),
        reverse_target_pwm=int(os.getenv("ROKI_MANUAL_REVERSE_PWM", "40")),
        drive_pulse_sec=float(os.getenv("ROKI_MANUAL_DRIVE_PULSE_SEC", "0.2")),
        steering_center_deg=int(os.getenv("ROKI_MANUAL_STEERING_CENTER_DEG", "80")),
        steering_min_deg=int(os.getenv("ROKI_MANUAL_STEERING_MIN_DEG", "70")),
        steering_max_deg=int(os.getenv("ROKI_MANUAL_STEERING_MAX_DEG", "90")),
        steering_step_deg=int(os.getenv("ROKI_MANUAL_STEERING_STEP_DEG", "2")),
        steering_pulse_sec=float(
            os.getenv("ROKI_MANUAL_STEERING_PULSE_SEC", "0.5")
        ),
    )
    controller = ManualDriveController(
        runtime=runtime,
        state_store=runtime.state_store,
        settings=settings,
    )
    return controller, ManualKeyboardInput(
        controller,
        loop_interval_sec=float(
            os.getenv("ROKI_MANUAL_KEYBOARD_LOOP_SEC", "0.02")
        ),
    )


def _environment_enabled(name: str, default: bool = True) -> bool:
    value = os.getenv(name, "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_mapping_runtime(
    runtime: Any,
    runtime_service: Any,
    state_store: Any,
    settings: Any,
) -> Any:
    """Build a dormant gamepad mapper; the device opens only on START_MAPPING."""

    from aiot_robot.mapping_artifacts import MapExportSettings, SlamMapExporter
    from control.manual_drive_controller import (
        ManualDriveController,
        ManualDriveSettings,
    )
    from integration.linux_gamepad_input import GamepadSettings, LinuxGamepadInput
    from integration.mapping_runtime import (
        ManualMappingRuntime,
        MappingRuntimeSettings,
    )

    drive_controller = ManualDriveController(
        runtime=runtime,
        state_store=state_store,
        settings=ManualDriveSettings(
            forward_target_pwm=int(os.getenv("ROKI_MAPPING_FORWARD_PWM", "45")),
            reverse_target_pwm=int(os.getenv("ROKI_MAPPING_REVERSE_PWM", "45")),
            drive_pulse_sec=float(os.getenv("ROKI_MAPPING_DRIVE_PULSE_SEC", "0.2")),
            steering_center_deg=int(
                os.getenv("ROKI_MAPPING_STEERING_CENTER_DEG", "80")
            ),
            steering_min_deg=int(os.getenv("ROKI_MAPPING_STEERING_MIN_DEG", "60")),
            steering_max_deg=int(os.getenv("ROKI_MAPPING_STEERING_MAX_DEG", "100")),
            steering_step_deg=int(os.getenv("ROKI_MAPPING_STEERING_STEP_DEG", "2")),
            steering_pulse_sec=float(
                os.getenv("ROKI_MAPPING_STEERING_PULSE_SEC", "0.2")
            ),
            # LiDAR obstacles are map input in this explicit manual mode. The
            # operator and deadman switch own motion; runtime hardware safety
            # and ESP32 watchdog remain enforced below this controller.
            require_clear_path=False,
        ),
    )
    gamepad_settings = GamepadSettings(
        device_path=os.getenv("ROKI_MAPPING_GAMEPAD_DEVICE", "/dev/input/js0"),
        steering_axis=int(os.getenv("ROKI_MAPPING_GAMEPAD_STEERING_AXIS", "0")),
        throttle_axis=int(os.getenv("ROKI_MAPPING_GAMEPAD_THROTTLE_AXIS", "1")),
        deadman_button=int(os.getenv("ROKI_MAPPING_GAMEPAD_DEADMAN_BUTTON", "4")),
        stop_button=int(os.getenv("ROKI_MAPPING_GAMEPAD_STOP_BUTTON", "1")),
        finish_button_a=int(os.getenv("ROKI_MAPPING_GAMEPAD_FINISH_BUTTON_A", "6")),
        finish_button_b=int(os.getenv("ROKI_MAPPING_GAMEPAD_FINISH_BUTTON_B", "7")),
        deadzone=float(os.getenv("ROKI_MAPPING_GAMEPAD_DEADZONE", "0.35")),
        finish_hold_sec=float(os.getenv("ROKI_MAPPING_FINISH_HOLD_SEC", "2.0")),
        loop_interval_sec=float(os.getenv("ROKI_MAPPING_GAMEPAD_LOOP_SEC", "0.05")),
        reconnect_interval_sec=float(
            os.getenv("ROKI_MAPPING_GAMEPAD_RECONNECT_SEC", "1.0")
        ),
        input_lease_sec=float(
            os.getenv("ROKI_MAPPING_GAMEPAD_INPUT_LEASE_SEC", "0.25")
        ),
    )
    holder: dict[str, Any] = {}
    gamepad_input = LinuxGamepadInput(
        drive_controller,
        settings=gamepad_settings,
        finish_callback=lambda: holder["mapping"].finish(),
    )
    mapping_runtime = ManualMappingRuntime(
        runtime_service=runtime_service,
        state_store=state_store,
        drive_controller=drive_controller,
        gamepad_input=gamepad_input,
        map_exporter=SlamMapExporter(
            MapExportSettings(
                Path(os.getenv("AIOT_MAPPING_OUTPUT_DIR", "/var/lib/aiot/maps")),
                timeout_seconds=float(
                    os.getenv("AIOT_MAPPING_EXPORT_TIMEOUT_SEC", "30")
                ),
                serialize_pose_graph=_environment_enabled(
                    "AIOT_MAPPING_SERIALIZE_POSE_GRAPH", True
                ),
            )
        ),
        settings=MappingRuntimeSettings(
            backend_base_url=os.getenv(
                "AIOT_BACKEND_BASE_URL", "https://i15e103.p.ssafy.io"
            ),
            backend_token_file=Path(settings.service_token_file),
            backend_timeout_sec=float(os.getenv("AIOT_BACKEND_TIMEOUT_SEC", "10")),
            upload_retry_initial_sec=float(
                os.getenv("AIOT_MAPPING_UPLOAD_RETRY_INITIAL_SEC", "2")
            ),
            upload_retry_max_sec=float(
                os.getenv("AIOT_MAPPING_UPLOAD_RETRY_MAX_SEC", "30")
            ),
        ),
    )
    holder["mapping"] = mapping_runtime
    return mapping_runtime


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
    manual_demo: bool = False,
    manual_controller: Any | None = None,
    keyboard_input: Any | None = None,
    mapping_runtime: Any | None = None,
    allow_legacy_direct_patrol: bool = True,
) -> Any:
    """Compose all production components around exactly one RobotRuntime."""

    build_default_runtime = final_runtime is None
    if final_runtime is None:
        runtime, default_pose_bridge, default_lidar_bridge = _build_final_components()
        pose_bridge = pose_bridge or default_pose_bridge
        lidar_health_bridge = lidar_health_bridge or default_lidar_bridge
    else:
        runtime = final_runtime

    from aiot_robot.deployment_guard import PatrolDeploymentGuard
    from aiot_robot.event_delivery import DetectionRecorder, EventDeliveryWorker
    from aiot_robot.outbox import DetectionOutbox
    from backend_config.settings import load_settings
    from integration.runtime_state_backend_adapter import FinalRuntimeService
    from backend_mqtt.client import MqttClient
    from backend_mqtt.command_handler import PatrolCommandHandler
    from backend_mqtt.publisher import RokiPublisherApplication
    from pipeline.patrol_pipeline import PatrolPipelineRunner

    settings = load_settings()
    state_store = runtime.state_store
    manual_enabled = (
        manual_demo
        or manual_controller is not None
        or keyboard_input is not None
    )
    if manual_demo and manual_controller is None and keyboard_input is None:
        manual_controller, keyboard_input = _build_manual_demo_components(runtime)
    service_holder: dict[str, Any] = {}
    navigation_driver = (
        _build_nav2_driver(service_holder)
        if (
            navigation_mode == "nav2"
            and not manual_enabled
            and navigation_service is not None
        )
        else None
    )
    runtime_service = FinalRuntimeService(
        runtime,
        patrol_drive_speed_pwm=settings.patrol_drive_speed_pwm,
        patrol_steering_degrees=settings.patrol_steering_degrees,
        navigation_service=None if manual_enabled else navigation_service,
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
        manual_controller=manual_controller,
        keyboard_input=keyboard_input,
        allow_legacy_direct_patrol=allow_legacy_direct_patrol,
    )
    service_holder["service"] = runtime_service
    if mapping_runtime is None and build_default_runtime and _environment_enabled(
        "AIOT_MAPPING_GAMEPAD_ENABLED", True
    ):
        mapping_runtime = _build_mapping_runtime(
            runtime,
            runtime_service,
            state_store,
            settings,
        )

    runtime_components: list[Any] = []
    readiness_checks: list[Any] = []
    if operational_ai:
        from aiot_robot.runtime_ai import RosAiCoordinator

        outbox = DetectionOutbox(
            os.getenv("AIOT_EVENT_OUTBOX_DIR", "/var/lib/aiot/outbox")
        )
        recorder = DetectionRecorder(
            outbox,
            state_store,
            vehicle_range_source=lidar_health_bridge,
            camera_yaw_deg=float(os.getenv("AIOT_VEHICLE_CAMERA_YAW_DEG", "0")),
        )
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
        mapping_runtime=mapping_runtime,
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

    from backend_config.settings import load_settings

    _validate_import_namespaces()
    settings = load_settings()
    mode = _navigation_mode(settings)
    selected_route = _selected_route_path(route_path)
    mapping_available = _environment_enabled("AIOT_MAPPING_GAMEPAD_ENABLED", True)
    navigation = None
    if selected_route.is_file():
        navigation = _build_navigation_service(
            selected_route,
            encoder_limited=mode == "encoder_limited",
        )
    elif not mapping_available:
        raise RuntimeError(f"waypoint route file is missing: {selected_route}")
    if mode == "nav2" and navigation is not None:
        holder: dict[str, Any] = {"service": None}
        _build_nav2_driver(holder)
    return {
        "robotKey": settings.robot_key,
        "navigationMode": mode,
        "routeConfigured": navigation is not None,
        "routeId": navigation.route.route_id if navigation is not None else None,
        "waypoints": len(navigation.route.waypoints) if navigation is not None else 0,
        "mappingAvailable": mapping_available,
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
    parser.add_argument(
        "--manual-keyboard",
        action="store_true",
        help=(
            "temporary foreground demo: MQTT START enables AI, then "
            "W/A/S/D controls short motion pulses"
        ),
    )
    parser.add_argument("--route", default=None)
    args = parser.parse_args(argv)
    if args.manual_keyboard and args.pose_only:
        parser.error("--manual-keyboard cannot be combined with --pose-only")
    if args.manual_keyboard and args.check:
        parser.error("--manual-keyboard cannot be combined with --check")
    if args.manual_keyboard and not sys.stdin.isatty():
        parser.error("--manual-keyboard requires a foreground TTY")
    if args.check:
        import json

        print(json.dumps(preflight(args.route), sort_keys=True))
        return 0

    from backend_config.settings import load_settings

    settings = load_settings()
    mode = "manual" if args.manual_keyboard else _navigation_mode(settings)
    navigation = None
    if not args.manual_keyboard:
        selected_route = _selected_route_path(args.route)
        if selected_route.is_file():
            navigation = _build_navigation_service(
                selected_route,
                encoder_limited=mode == "encoder_limited",
            )
        elif not _environment_enabled("AIOT_MAPPING_GAMEPAD_ENABLED", True):
            raise RuntimeError(f"waypoint route file is missing: {selected_route}")
        else:
            logging.getLogger(__name__).warning(
                "Patrol route is missing; mapping remains available but "
                "START_PATROL will be rejected: %s",
                selected_route,
            )
    application = create_integrated_application(
        start_serial_runtime=not args.pose_only,
        navigation_service=navigation,
        navigation_mode=mode,
        operational_ai=True,
        manual_demo=args.manual_keyboard,
        allow_legacy_direct_patrol=False,
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
