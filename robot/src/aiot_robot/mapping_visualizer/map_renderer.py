"""Pure map/scan/pose rendering with no ROS or runtime dependencies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class GridMap:
    width: int
    height: int
    resolution: float
    origin: Pose2D
    values: Sequence[int]

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("map dimensions must be positive")
        if self.resolution <= 0:
            raise ValueError("map resolution must be positive")
        if len(self.values) != self.width * self.height:
            raise ValueError("map data length does not match dimensions")


@dataclass(frozen=True)
class ScanPoints:
    points: Sequence[tuple[float, float]]


class MappingRenderer:
    """Render OccupancyGrid coordinates into a bounded square dashboard frame."""

    UNKNOWN_GRAY = 128
    FREE_GRAY = 245
    OCCUPIED_GRAY = 0

    def __init__(
        self,
        *,
        size_px: int = 800,
        margin_px: int = 30,
        maximum_path_points: int = 1000,
        path_minimum_distance_m: float = 0.05,
    ) -> None:
        if size_px <= 0:
            raise ValueError("render size must be positive")
        if margin_px < 0 or margin_px * 2 >= size_px:
            raise ValueError("render margin is invalid")
        if maximum_path_points <= 0:
            raise ValueError("maximum path points must be positive")
        if path_minimum_distance_m <= 0:
            raise ValueError("path minimum distance must be positive")
        self.size_px = size_px
        self.margin_px = margin_px
        self.maximum_path_points = maximum_path_points
        self.path_minimum_distance_m = path_minimum_distance_m

    def occupancy_image(self, grid: GridMap) -> np.ndarray:
        values = np.asarray(grid.values, dtype=np.int16).reshape(
            grid.height,
            grid.width,
        )
        grayscale = np.full(values.shape, self.UNKNOWN_GRAY, dtype=np.uint8)
        known = values >= 0
        clipped = np.clip(values, 0, 100)
        grayscale[known] = np.rint(
            self.FREE_GRAY
            - clipped[known]
            * (self.FREE_GRAY - self.OCCUPIED_GRAY)
            / 100.0
        ).astype(np.uint8)
        # OccupancyGrid row zero is the lower map edge; image row zero is top.
        return np.flipud(grayscale)

    def world_to_grid_pixel(
        self,
        grid: GridMap,
        x: float,
        y: float,
    ) -> tuple[float, float] | None:
        dx = x - grid.origin.x
        dy = y - grid.origin.y
        cosine = math.cos(grid.origin.yaw)
        sine = math.sin(grid.origin.yaw)
        local_x = cosine * dx + sine * dy
        local_y = -sine * dx + cosine * dy
        pixel_x = local_x / grid.resolution
        pixel_y = grid.height - 1 - local_y / grid.resolution
        if not (0 <= pixel_x < grid.width and 0 <= pixel_y < grid.height):
            return None
        return pixel_x, pixel_y

    def append_path(
        self,
        path: list[Pose2D],
        pose: Pose2D,
    ) -> None:
        if path:
            distance = math.hypot(pose.x - path[-1].x, pose.y - path[-1].y)
            if distance < self.path_minimum_distance_m:
                return
        path.append(pose)
        if len(path) > self.maximum_path_points:
            del path[: len(path) - self.maximum_path_points]

    def render(
        self,
        grid: GridMap,
        *,
        scan: ScanPoints | None = None,
        robot_pose: Pose2D | None = None,
        path: Sequence[Pose2D] = (),
    ) -> np.ndarray:
        canvas = np.full((self.size_px, self.size_px, 3), 32, dtype=np.uint8)
        usable = self.size_px - self.margin_px * 2
        scale = min(usable / grid.width, usable / grid.height)
        render_width = max(1, int(round(grid.width * scale)))
        render_height = max(1, int(round(grid.height * scale)))
        offset_x = (self.size_px - render_width) // 2
        offset_y = (self.size_px - render_height) // 2
        map_bgr = cv2.cvtColor(self.occupancy_image(grid), cv2.COLOR_GRAY2BGR)
        resized = cv2.resize(
            map_bgr,
            (render_width, render_height),
            interpolation=cv2.INTER_NEAREST,
        )
        canvas[offset_y : offset_y + render_height, offset_x : offset_x + render_width] = resized

        def project(x: float, y: float) -> tuple[int, int] | None:
            point = self.world_to_grid_pixel(grid, x, y)
            if point is None:
                return None
            return (
                int(round(offset_x + point[0] * scale)),
                int(round(offset_y + point[1] * scale)),
            )

        projected_path = [
            point
            for pose in path
            if (point := project(pose.x, pose.y)) is not None
        ]
        if len(projected_path) >= 2:
            cv2.polylines(
                canvas,
                [np.asarray(projected_path, dtype=np.int32)],
                False,
                (70, 180, 240),
                2,
                cv2.LINE_AA,
            )

        if scan is not None:
            for x, y in scan.points:
                point = project(x, y)
                if point is not None:
                    cv2.circle(canvas, point, 1, (230, 190, 40), -1)

        if robot_pose is not None:
            center = project(robot_pose.x, robot_pose.y)
            if center is not None:
                arrow_length = 18
                local_heading = robot_pose.yaw - grid.origin.yaw
                endpoint = (
                    int(round(center[0] + math.cos(local_heading) * arrow_length)),
                    int(round(center[1] - math.sin(local_heading) * arrow_length)),
                )
                cv2.circle(canvas, center, 7, (60, 70, 230), -1, cv2.LINE_AA)
                cv2.arrowedLine(
                    canvas,
                    center,
                    endpoint,
                    (20, 20, 180),
                    3,
                    cv2.LINE_AA,
                    tipLength=0.35,
                )
        return canvas

    def inactive_frame(self) -> np.ndarray:
        canvas = np.full((self.size_px, self.size_px, 3), 40, dtype=np.uint8)
        text = "Mapping is not active"
        size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        origin = ((self.size_px - size[0]) // 2, self.size_px // 2)
        cv2.putText(
            canvas,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (210, 210, 210),
            2,
            cv2.LINE_AA,
        )
        return canvas


def transform_scan_points(
    ranges: Iterable[float],
    *,
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    scan_to_map: Pose2D,
) -> ScanPoints:
    """Convert valid LaserScan ranges through the supplied TF result."""

    cosine = math.cos(scan_to_map.yaw)
    sine = math.sin(scan_to_map.yaw)
    points: list[tuple[float, float]] = []
    for index, distance in enumerate(ranges):
        if not math.isfinite(distance) or not range_min <= distance <= range_max:
            continue
        angle = angle_min + index * angle_increment
        local_x = distance * math.cos(angle)
        local_y = distance * math.sin(angle)
        points.append(
            (
                scan_to_map.x + cosine * local_x - sine * local_y,
                scan_to_map.y + sine * local_x + cosine * local_y,
            )
        )
    return ScanPoints(points)
