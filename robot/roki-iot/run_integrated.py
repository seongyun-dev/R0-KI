#!/usr/bin/env python3
"""Production composition root for Robot MQTT, navigation, AI and telemetry."""

from __future__ import annotations

import argparse
import hmac
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
    if encoder_limited:
        raise RuntimeError(
            "DEMO_NAV2_REQUIRED: encoder_limited is a straight-line diagnostic "
            "mode and cannot run the fixed-map demo patrol"
        )
    selected_path = _selected_route_path(route_path)
    if not selected_path.is_file():
        raise RuntimeError(f"waypoint route file is missing: {selected_path}")
    from navigation.map_metadata import (
        file_sha256,
        load_map_metadata,
        load_occupancy_grid,
        map_bundle_sha256,
        validate_map_quality,
        validate_point_clearance,
        validate_point_bounds,
        validate_route_clearance,
        validate_route_bounds,
    )
    from navigation.route import RouteValidationError, load_route
    from navigation.service import WaypointNavigationService
    from aiot_robot.ros_config import nav2_xy_goal_tolerance

    route = load_route(selected_path)
    xy_goal_tolerance_m = nav2_xy_goal_tolerance(os.environ)
    for waypoint in route.waypoints:
        if waypoint.acceptance_radius_m < xy_goal_tolerance_m:
            raise RouteValidationError(
                f"waypoint {waypoint.sequence} acceptance_radius_m "
                f"{waypoint.acceptance_radius_m:.3f} is below Nav2 "
                f"xy_goal_tolerance {xy_goal_tolerance_m:.3f}; Nav2 could "
                "stop before the mission advances"
            )
    raw_map_path = os.getenv("ROKI_MAP_YAML", "").strip()
    map_path = Path(raw_map_path)
    if not raw_map_path or not map_path.is_absolute() or not map_path.is_file():
        raise RuntimeError(
            "NAV2_MAP_MISSING: ROKI_MAP_YAML must be a readable absolute map YAML"
        )
    metadata = load_map_metadata(map_path)
    expected_map_id = _required_environment("ROKI_MAP_ID")
    expected_map_version = _required_positive_integer("ROKI_MAP_VERSION")
    if route.map_id != expected_map_id:
        raise RouteValidationError(
            f"route map_id {route.map_id!r} does not match ROKI_MAP_ID"
        )
    if route.map_version != expected_map_version:
        raise RouteValidationError(
            "route map_version does not match ROKI_MAP_VERSION"
        )
    expected_map_sha256 = _required_sha256("ROKI_MAP_SHA256")
    expected_route_sha256 = _required_sha256("ROKI_ROUTE_SHA256")
    if not hmac.compare_digest(map_bundle_sha256(metadata), expected_map_sha256):
        raise RouteValidationError("map YAML/image SHA256 does not match deployment")
    if not hmac.compare_digest(file_sha256(selected_path), expected_route_sha256):
        raise RouteValidationError("route SHA256 does not match deployment")

    validate_route_bounds(route, metadata)
    grid = load_occupancy_grid(metadata)
    validate_map_quality(
        grid,
        minimum_known_coverage_ratio=_coverage_ratio(
            "ROKI_MAP_MIN_KNOWN_COVERAGE_RATIO", "0.10"
        ),
        minimum_free_coverage_ratio=_coverage_ratio(
            "ROKI_MAP_MIN_FREE_COVERAGE_RATIO", "0.10"
        ),
    )
    robot_radius_m = float(_required_environment("ROKI_ROBOT_RADIUS_M"))
    validate_route_clearance(
        route,
        grid,
        robot_radius_m=robot_radius_m,
    )
    dock_x = float(_required_environment("ROKI_INITIAL_POSE_X_M"))
    dock_y = float(_required_environment("ROKI_INITIAL_POSE_Y_M"))
    validate_point_bounds(
        dock_x,
        dock_y,
        metadata,
        label="fixed dock initial pose",
    )
    validate_point_clearance(
        dock_x,
        dock_y,
        grid,
        robot_radius_m=robot_radius_m,
        label="fixed dock initial pose",
    )
    return WaypointNavigationService(route)


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"DEMO_CONFIG_MISSING: {name} must be set")
    return value


def _required_positive_integer(name: str) -> int:
    raw = _required_environment(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be positive")
    return value


def _required_sha256(name: str) -> str:
    value = _required_environment(name).lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be a SHA256 hex digest")
    return value


def _coverage_ratio(name: str, default: str) -> float:
    raw = os.getenv(name, default).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be numeric") from exc
    if not 0.0 <= value <= 1.0:
        raise RuntimeError(f"DEMO_CONFIG_INVALID: {name} must be within 0.0..1.0")
    return value


def _navigation_mode(settings: Any) -> str:
    mode = settings.navigation_mode
    if mode != "nav2":
        raise RuntimeError(
            "DEMO_NAV2_REQUIRED: set ROKI_NAVIGATION_MODE=nav2; automatic "
            "encoder_limited fallback is disabled for the fixed-map demo"
        )
    from aiot_robot.ros_config import build_nav2_values

    try:
        build_nav2_values(os.environ)
    except ValueError as exc:
        raise RuntimeError(f"NAV2_FIELD_CONFIG_INVALID: {exc}") from exc
    if importlib.util.find_spec("nav2_msgs") is None:
        raise RuntimeError("NAV2_PACKAGE_MISSING: nav2_msgs is not installed")
    return "nav2"


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
        scan_dwell_sec=float(os.getenv("ROKI_SCAN_DWELL_SECONDS", "3.0")),
        cmd_vel_timeout_sec=float(
            os.getenv("ROKI_NAV2_CMD_VEL_TIMEOUT_SECONDS", "0.5")
        ),
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


def _mapping_mode_requested() -> bool:
    return (
        _environment_enabled("AIOT_MAPPING_GAMEPAD_ENABLED", True)
        and os.getenv("AIOT_ROS_MODE", "").strip().lower() == "mapping"
    )


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
            os.getenv("ROKI_MAPPING_GAMEPAD_INPUT_LEASE_SEC", "1.0")
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
    if not manual_enabled and navigation_service is not None and navigation_mode != "nav2":
        raise RuntimeError(
            "DEMO_NAV2_REQUIRED: fixed-map navigation cannot use encoder progress"
        )
    if not manual_enabled and navigation_mode == "nav2" and navigation_service is None:
        raise RuntimeError("NAV2_ROUTE_REQUIRED: validated navigation service is missing")
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
    if mapping_runtime is not None:
        runtime_service.set_mapping_runtime(mapping_runtime)

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
    if mapping_runtime is not None:
        mapping_runtime.set_failure_listener(command_handler.on_runtime_failure)
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
    runtime_service.set_fault_listener(command_handler.on_runtime_failure)
    return application


def preflight(route_path: str | Path | None = None) -> dict[str, Any]:
    """Validate configuration without MQTT, ROS nodes or serial access."""

    from backend_config.settings import load_settings

    _validate_import_namespaces()
    settings = load_settings()
    selected_route = _selected_route_path(route_path)
    mapping_available = _environment_enabled("AIOT_MAPPING_GAMEPAD_ENABLED", True)
    mapping_requested = _mapping_mode_requested()
    navigation = None
    if mapping_requested:
        mode = "mapping"
    elif selected_route.is_file():
        mode = _navigation_mode(settings)
        navigation = _build_navigation_service(
            selected_route,
            encoder_limited=mode == "encoder_limited",
        )
    elif mapping_available:
        mode = "mapping"
    else:
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
        "mapValidated": navigation is not None,
        "mappingAvailable": mapping_available,
        "mappingModeRequested": mapping_requested,
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
    mode = "manual" if args.manual_keyboard else "mapping"
    navigation = None
    if not args.manual_keyboard:
        selected_route = _selected_route_path(args.route)
        if _mapping_mode_requested():
            logging.getLogger(__name__).info(
                "Explicit ROS mapping mode selected; patrol route validation is deferred"
            )
        elif selected_route.is_file():
            mode = _navigation_mode(settings)
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
