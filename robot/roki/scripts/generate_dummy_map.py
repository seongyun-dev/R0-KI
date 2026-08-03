#!/usr/bin/env python3
"""Generate a deterministic rectangular ROS occupancy map and straight route."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def generate_dummy_map(
    output_dir: str | Path,
    *,
    width_m: float = 8.0,
    height_m: float = 5.0,
    resolution_m: float = 0.05,
    overwrite: bool = False,
) -> tuple[Path, Path, Path]:
    if width_m < 2.0 or height_m < 2.0:
        raise ValueError("dummy map dimensions must be at least 2 metres")
    if not 0.01 <= resolution_m <= 0.5:
        raise ValueError("resolution_m must be 0.01..0.5")
    width_px = round(width_m / resolution_m)
    height_px = round(height_m / resolution_m)
    if width_px < 10 or height_px < 10:
        raise ValueError("dummy map requires at least 10 pixels per axis")

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    image_path = target / "map.pgm"
    map_path = target / "map.yaml"
    route_path = target / "route.yaml"
    for path in (image_path, map_path, route_path):
        if path.exists() and not overwrite:
            raise FileExistsError(f"refusing to overwrite {path}")

    # ROS map convention: black=occupied and white=free when negate is zero.
    wall_px = max(1, round(0.10 / resolution_m))
    pixels = bytearray(width_px * height_px)
    for row in range(height_px):
        for column in range(width_px):
            wall = (
                row < wall_px
                or row >= height_px - wall_px
                or column < wall_px
                or column >= width_px - wall_px
            )
            pixels[row * width_px + column] = 0 if wall else 254
    image_path.write_bytes(
        f"P5\n{width_px} {height_px}\n255\n".encode("ascii") + pixels
    )

    map_data = {
        "image": "map.pgm",
        "mode": "trinary",
        "resolution": resolution_m,
        "origin": [0.0, 0.0, 0.0],
        "negate": 0,
        "occupied_thresh": 0.65,
        "free_thresh": 0.25,
    }
    map_path.write_text(
        yaml.safe_dump(map_data, sort_keys=False),
        encoding="utf-8",
    )

    centre_y = round(height_m / 2.0, 3)
    route_data = {
        "schema_version": 1,
        "map_id": "dummy-rectangle",
        "map_version": 1,
        "route_id": "dummy-straight-v1",
        "frame_id": "map",
        "waypoints": [
            _waypoint(1, "CHECKPOINT_1", width_m * 0.25, centre_y, "PASS", 0.30),
            _waypoint(2, "SCAN_POINT", width_m * 0.50, centre_y, "SCAN", 0.30),
            _waypoint(
                3,
                "DESTINATION",
                width_m * 0.75,
                centre_y,
                "DESTINATION",
                0.20,
            ),
        ],
    }
    route_path.write_text(
        yaml.safe_dump(route_data, sort_keys=False),
        encoding="utf-8",
    )
    return map_path, image_path, route_path


def _waypoint(
    sequence: int,
    name: str,
    x: float,
    y: float,
    action: str,
    radius: float,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "name": name,
        "x": round(x, 3),
        "y": round(y, 3),
        "yaw_deg": 0.0,
        "acceptance_radius_m": radius,
        "action": action,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width-m", type=float, default=8.0)
    parser.add_argument("--height-m", type=float, default=5.0)
    parser.add_argument("--resolution-m", type=float, default=0.05)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    generated = generate_dummy_map(
        args.output_dir,
        width_m=args.width_m,
        height_m=args.height_m,
        resolution_m=args.resolution_m,
        overwrite=args.overwrite,
    )
    for path in generated:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
