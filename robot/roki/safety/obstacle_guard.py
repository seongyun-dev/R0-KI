"""LiDAR 전방 sector의 장애물 상태를 계산하는 순수 정책."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from state.robot_state import ObstacleState


STOP_REASON_MESSAGE = "전방에 장애물이 있습니다."


@dataclass(frozen=True)
class ObstacleDetectorSettings:
    """front_angle_deg는 정면으로부터 좌우 최대 각도다."""

    front_angle_deg: float
    stop_distance_m: float
    clear_distance_m: float
    center_angle_deg: float = 0.0

    def __post_init__(self) -> None:
        if not 0 < self.front_angle_deg <= 180:
            raise ValueError("obstacle.front_angle_deg must be in (0, 180]")
        if not math.isfinite(self.center_angle_deg):
            raise ValueError("obstacle.center_angle_deg must be finite")
        if self.stop_distance_m <= 0:
            raise ValueError("obstacle.stop_distance_m must be positive")
        if self.clear_distance_m <= self.stop_distance_m:
            raise ValueError(
                "obstacle.clear_distance_m must exceed stop_distance_m"
            )


@dataclass(frozen=True)
class ObstacleDetection:
    obstacle: ObstacleState
    front_distance_m: float | None
    stop_distance_m: float


class FrontObstacleDetector:
    """유효한 전방 최소거리와 hysteresis로 보고 상태만 계산한다."""

    def __init__(self, settings: ObstacleDetectorSettings) -> None:
        self._settings = settings
        self._status = "CLEAR"

    def evaluate_scan(
        self,
        *,
        ranges: Sequence[float],
        angle_min_rad: float,
        angle_increment_rad: float,
        range_min_m: float,
        range_max_m: float,
    ) -> ObstacleDetection:
        front_distance = self._minimum_front_distance(
            ranges=ranges,
            angle_min_rad=angle_min_rad,
            angle_increment_rad=angle_increment_rad,
            range_min_m=range_min_m,
            range_max_m=range_max_m,
        )
        if front_distance is not None:
            if front_distance <= self._settings.stop_distance_m:
                self._status = "STOP"
            elif front_distance >= self._settings.clear_distance_m:
                self._status = "CLEAR"

        obstacle = (
            ObstacleState("STOP", "FRONT", STOP_REASON_MESSAGE)
            if self._status == "STOP"
            else ObstacleState("CLEAR", "NONE", None)
        )
        return ObstacleDetection(
            obstacle=obstacle,
            front_distance_m=front_distance,
            stop_distance_m=self._settings.stop_distance_m,
        )

    def _minimum_front_distance(
        self,
        *,
        ranges: Sequence[float],
        angle_min_rad: float,
        angle_increment_rad: float,
        range_min_m: float,
        range_max_m: float,
    ) -> float | None:
        sector_limit = math.radians(self._settings.front_angle_deg)
        sector_center = math.radians(self._settings.center_angle_deg)
        valid: list[float] = []
        for index, raw_distance in enumerate(ranges):
            distance = float(raw_distance)
            angle = angle_min_rad + index * angle_increment_rad
            angle_delta = angle - sector_center
            normalized_angle = math.atan2(
                math.sin(angle_delta),
                math.cos(angle_delta),
            )
            if abs(normalized_angle) > sector_limit:
                continue
            if not math.isfinite(distance) or distance <= 0:
                continue
            if distance < range_min_m or distance > range_max_m:
                continue
            valid.append(distance)
        return min(valid) if valid else None
