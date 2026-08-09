from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigation.map_metadata import load_map_metadata, validate_route_bounds
from navigation.route import load_route
from scripts.generate_dummy_map import generate_dummy_map


class GenerateDummyMapTest(unittest.TestCase):
    def test_generated_map_and_route_are_mutually_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path, image_path, route_path = generate_dummy_map(directory)
            self.assertTrue(image_path.is_file())
            metadata = load_map_metadata(map_path)
            route = load_route(route_path)
            validate_route_bounds(route, metadata)
            self.assertEqual(metadata.resolution_m, 0.05)
            self.assertEqual((metadata.width_m, metadata.height_m), (8.0, 5.0))
            self.assertEqual(route.waypoints[-1].name, "DESTINATION")

    def test_refuses_overwrite_and_invalid_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generate_dummy_map(directory)
            with self.assertRaises(FileExistsError):
                generate_dummy_map(directory)
            with self.assertRaises(ValueError):
                generate_dummy_map(Path(directory) / "small", width_m=1.0)


if __name__ == "__main__":
    unittest.main()
