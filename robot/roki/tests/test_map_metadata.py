from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigation.map_metadata import load_map_metadata, validate_route_bounds
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
            with self.assertRaisesRegex(RouteValidationError, "outside"):
                validate_route_bounds(make_route(10.0, -1.0), metadata)

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


if __name__ == "__main__":
    unittest.main()
