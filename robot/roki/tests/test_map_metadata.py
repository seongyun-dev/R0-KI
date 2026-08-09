from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigation.map_metadata import (
    load_map_metadata,
    load_occupancy_grid,
    validate_map_quality,
    validate_point_clearance,
    validate_point_bounds,
    validate_route_bounds,
)
from navigation.route import RouteValidationError, parse_route


def make_route(x: float, y: float):
    return parse_route(
        {
            "schema_version": 1,
            "map_id": "map-1",
            "map_version": 1,
            "route_id": "route-1",
            "frame_id": "map",
            "waypoints": [
                {
                    "sequence": 1,
                    "x": x,
                    "y": y,
                    "yaw_deg": 0.0,
                    "acceptance_radius_m": 0.2,
                    "action": "DESTINATION",
                }
            ],
        }
    )


class MapMetadataTest(unittest.TestCase):
    @staticmethod
    def write_map(
        root: Path,
        pixels: bytes,
        *,
        width: int = 20,
        height: int = 20,
    ) -> Path:
        (root / "map.pgm").write_bytes(
            f"P5\n{width} {height}\n255\n".encode("ascii") + pixels
        )
        yaml_path = root / "map.yaml"
        yaml_path.write_text(
            """image: map.pgm
resolution: 0.1
origin: [0.0, 0.0, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""",
            encoding="utf-8",
        )
        return yaml_path

    def test_loads_pgm_and_validates_route_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "map.pgm").write_bytes(b"P5\n# test\n100 50\n255\n")
            yaml_path = root / "map.yaml"
            yaml_path.write_text(
                """image: map.pgm
resolution: 0.05
origin: [-1.0, -2.0, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""",
                encoding="utf-8",
            )
            metadata = load_map_metadata(yaml_path)
            self.assertEqual((metadata.width_px, metadata.height_px), (100, 50))
            self.assertEqual((metadata.width_m, metadata.height_m), (5.0, 2.5))
            validate_route_bounds(make_route(0.0, -1.0), metadata)
            validate_point_bounds(-0.5, -1.5, metadata, label="initial pose")
            with self.assertRaisesRegex(RouteValidationError, "outside"):
                validate_route_bounds(make_route(10.0, -1.0), metadata)
            with self.assertRaisesRegex(RouteValidationError, "initial pose.*outside"):
                validate_point_bounds(10.0, -1.0, metadata, label="initial pose")

    def test_rejects_missing_image_and_invalid_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            yaml_path = root / "map.yaml"
            yaml_path.write_text(
                """image: missing.pgm
resolution: 0.05
origin: [0, 0, 0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RouteValidationError, "missing"):
                load_map_metadata(yaml_path)

    def test_decodes_pgm_and_rejects_low_known_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pixels = bytes([255]) * 12 + bytes([128]) * 388
            metadata = load_map_metadata(self.write_map(root, pixels))
            grid = load_occupancy_grid(metadata)
            self.assertAlmostEqual(grid.known_coverage_ratio, 0.03)
            self.assertAlmostEqual(grid.free_coverage_ratio, 0.03)
            with self.assertRaisesRegex(RouteValidationError, "known coverage"):
                validate_map_quality(
                    grid,
                    minimum_known_coverage_ratio=0.10,
                    minimum_free_coverage_ratio=0.10,
                )

    def test_ros_unknown_gray_is_not_counted_as_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pixels = bytes([254]) * 12 + bytes([205]) * 388
            metadata = load_map_metadata(self.write_map(root, pixels))
            grid = load_occupancy_grid(metadata)

            self.assertAlmostEqual(grid.known_coverage_ratio, 0.03)
            self.assertAlmostEqual(grid.free_coverage_ratio, 0.03)
            self.assertEqual(grid.canonical_unknown_cells, 388)
            with self.assertRaisesRegex(RouteValidationError, "known coverage"):
                validate_map_quality(
                    grid,
                    minimum_known_coverage_ratio=0.10,
                    minimum_free_coverage_ratio=0.10,
                )

            mostly_free = bytes([254]) * 399 + bytes([205])
            metadata = load_map_metadata(self.write_map(root, mostly_free))
            grid = load_occupancy_grid(metadata)
            with self.assertRaisesRegex(
                RouteValidationError,
                "thresholds classify canonical unknown",
            ):
                validate_map_quality(
                    grid,
                    minimum_known_coverage_ratio=0.10,
                    minimum_free_coverage_ratio=0.10,
                )

    def test_requires_free_cells_across_robot_footprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pixels = bytearray([255] * 400)
            # world (1.05, 1.05) is grid (10, 10), image row 9.
            pixels[9 * 20 + 10] = 0
            metadata = load_map_metadata(self.write_map(root, bytes(pixels)))
            grid = load_occupancy_grid(metadata)

            with self.assertRaisesRegex(RouteValidationError, "occupied"):
                validate_point_clearance(
                    1.05,
                    1.05,
                    grid,
                    robot_radius_m=0.15,
                    label="fixed dock",
                )
            validate_point_clearance(
                0.5,
                0.5,
                grid,
                robot_radius_m=0.15,
                label="free waypoint",
            )

    def test_demo_occupancy_decode_fails_closed_for_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = bytearray(b"\x89PNG\r\n\x1a\n" + bytes(16))
            header[16:24] = (20).to_bytes(4, "big") + (20).to_bytes(4, "big")
            (root / "map.png").write_bytes(bytes(header))
            yaml_path = root / "map.yaml"
            yaml_path.write_text(
                """image: map.png
resolution: 0.1
origin: [0.0, 0.0, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""",
                encoding="utf-8",
            )
            metadata = load_map_metadata(yaml_path)
            with self.assertRaisesRegex(RouteValidationError, "P2 or P5 PGM"):
                load_occupancy_grid(metadata)


if __name__ == "__main__":
    unittest.main()
