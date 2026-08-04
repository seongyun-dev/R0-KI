"""Backend-owned ordered navigation config for one fixed-map Robot."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from aiot_robot.backend_client import BackendTransportError
from navigation.route import Route, RouteValidationError, parse_route


class NavigationConfigError(RuntimeError):
    """Fail-closed reason that is safe to expose in command logs and ACKs."""

    def __init__(
        self,
        reason: str,
        *,
        local_fallback_allowed: bool = False,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        # Only an actual network/transport outage may opt into the explicitly
        # configured local route. Contract, identity and map-safety failures
        # must always remain fail-closed.
        self.local_fallback_allowed = bool(local_fallback_allowed)


BackendFactory = Callable[[], Any]
NavigationFactory = Callable[[Route], Any]
MapMetadataValidator = Callable[[Mapping[str, Any]], None]


@dataclass(frozen=True)
class NavigationConfigIdentity:
    map_id: str
    map_version: int


class BackendNavigationConfigProvider:
    """Fetch, validate and convert Backend JSON into the existing Route model."""

    def __init__(
        self,
        *,
        backend_factory: BackendFactory,
        navigation_factory: NavigationFactory,
        identity: NavigationConfigIdentity,
        default_acceptance_radius_m: float = 0.30,
        wall_clock: Callable[[], datetime] | None = None,
        map_metadata_validator: MapMetadataValidator | None = None,
    ) -> None:
        if not identity.map_id.strip() or identity.map_version <= 0:
            raise ValueError("a positive fixed-map identity is required")
        if not 0.20 <= default_acceptance_radius_m <= 1.0:
            raise ValueError("default acceptance radius must be within 0.20..1.0")
        self._backend_factory = backend_factory
        self._navigation_factory = navigation_factory
        self._identity = identity
        self._default_acceptance_radius_m = float(default_acceptance_radius_m)
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._map_metadata_validator = map_metadata_validator

    def load_navigation(self, *, deadline: datetime | None = None) -> Any:
        request_timeout = self._request_timeout(deadline)
        try:
            backend = self._backend_factory()
        except Exception as exc:
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID") from exc
        try:
            response = backend.get_navigation_config(
                timeout_seconds=request_timeout
            )
        except BackendTransportError as exc:
            raise NavigationConfigError(
                "NAVIGATION_CONFIG_UNAVAILABLE",
                local_fallback_allowed=True,
            ) from exc
        except Exception as exc:
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID") from exc

        try:
            route = self._parse_response(response)
        except NavigationConfigError:
            raise
        except (KeyError, TypeError, ValueError, RouteValidationError) as exc:
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID") from exc
        try:
            return self._navigation_factory(route)
        except Exception as exc:
            # This factory performs the local map bundle/hash/occupancy/
            # clearance validation. A stale local bundle is not a transport
            # outage and must never activate a fallback route.
            raise NavigationConfigError("NAVIGATION_ROUTE_UNSAFE") from exc

    def _request_timeout(self, deadline: datetime | None) -> float | None:
        if deadline is None:
            return None
        now = self._wall_clock()
        if now.tzinfo is None or deadline.tzinfo is None:
            raise NavigationConfigError("NAVIGATION_DEADLINE_INVALID")
        remaining = (deadline - now).total_seconds()
        # Reserve a small budget for response validation and the mandatory
        # second expiry check immediately before AI/motion activation.
        if remaining <= 0.05:
            raise NavigationConfigError("NAVIGATION_COMMAND_EXPIRED")
        return remaining - 0.05

    def _parse_response(self, response: Any) -> Route:
        if not isinstance(response, Mapping) or response.get("success") is not True:
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID")
        data = response.get("data")
        if not isinstance(data, Mapping) or data.get("schemaVersion") != 1:
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID")
        map_config = data.get("map")
        if not isinstance(map_config, Mapping):
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID")

        map_id = _identifier(map_config.get("mapId"), "map.mapId")
        map_version = _positive_integer(
            map_config.get("mapVersion"), "map.mapVersion"
        )
        if (
            map_id != self._identity.map_id
            or map_version != self._identity.map_version
        ):
            raise NavigationConfigError("NAVIGATION_MAP_MISMATCH")
        _validate_map_metadata(map_config)
        if self._map_metadata_validator is not None:
            self._map_metadata_validator(map_config)

        raw_zones = data.get("zones")
        if not isinstance(raw_zones, list):
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID")
        zone_names: dict[int, str] = {}
        for index, zone in enumerate(raw_zones, start=1):
            if not isinstance(zone, Mapping):
                raise ValueError(f"zone {index} must be an object")
            zone_id = _positive_integer(zone.get("zoneId"), f"zone {index} zoneId")
            name = str(zone.get("name") or f"ZONE_{zone_id}").strip()
            zone_names[zone_id] = name or f"ZONE_{zone_id}"

        raw_waypoints = data.get("waypoints")
        if not isinstance(raw_waypoints, list) or not raw_waypoints:
            raise NavigationConfigError("NAVIGATION_CONFIG_INVALID")
        waypoints: list[dict[str, Any]] = []
        for index, waypoint in enumerate(raw_waypoints, start=1):
            if not isinstance(waypoint, Mapping):
                raise ValueError(f"waypoint {index} must be an object")
            sequence = _positive_integer(
                waypoint.get("sequence"), f"waypoint {index} sequence"
            )
            zone_id = _optional_positive_integer(
                waypoint.get("zoneId"), f"waypoint {index} zoneId"
            )
            if zone_id is not None and zone_id not in zone_names:
                raise ValueError(f"waypoint {index} references an unknown zone")
            action = str(waypoint.get("action") or "").strip().upper()
            name = zone_names.get(zone_id, f"{action or 'WAYPOINT'}_{sequence}")
            raw_yaw = waypoint.get("yaw")
            yaw_deg = (
                None
                if raw_yaw is None
                else math.degrees(
                    _finite_number(raw_yaw, f"waypoint {index} yaw")
                )
            )
            acceptance_radius_m = _optional_finite_number(
                waypoint.get("acceptanceRadius"),
                f"waypoint {index} acceptanceRadius",
                default=self._default_acceptance_radius_m,
            )
            if not 0.20 <= acceptance_radius_m <= 1.0:
                raise ValueError(
                    f"waypoint {index} acceptanceRadius must be within 0.20..1.0"
                )
            waypoints.append(
                {
                    "sequence": sequence,
                    "name": name,
                    "x": _finite_number(waypoint.get("x"), f"waypoint {index} x"),
                    "y": _finite_number(waypoint.get("y"), f"waypoint {index} y"),
                    # Backend/ROS contracts use radians; the existing local
                    # Route model and Nav2 adapter intentionally use degrees.
                    "yaw_deg": yaw_deg,
                    "acceptance_radius_m": acceptance_radius_m,
                    "action": action,
                    "zone_id": zone_id,
                }
            )

        return parse_route(
            {
                "schema_version": 1,
                "map_id": map_id,
                "map_version": map_version,
                "route_id": f"backend-map-{map_id}-v{map_version}",
                "frame_id": "map",
                "waypoints": waypoints,
            }
        )


def _validate_map_metadata(value: Mapping[str, Any]) -> None:
    resolution = _finite_number(value.get("resolution"), "map.resolution")
    if resolution <= 0:
        raise ValueError("map.resolution must be positive")
    _finite_number(value.get("originX"), "map.originX")
    _finite_number(value.get("originY"), "map.originY")
    _finite_number(value.get("originYaw"), "map.originYaw")
    _positive_integer(value.get("width"), "map.width")
    _positive_integer(value.get("height"), "map.height")


def _identifier(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field} must be an identifier")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field} must be an identifier")
    return normalized


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _optional_positive_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _positive_integer(value, field)


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _optional_finite_number(value: Any, field: str, *, default: float) -> float:
    if value is None:
        return default
    return _finite_number(value, field)
