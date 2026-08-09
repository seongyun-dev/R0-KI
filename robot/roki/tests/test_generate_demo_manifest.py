from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.generate_demo_manifest import build_manifest


class GenerateDemoManifestTest(unittest.TestCase):
    def test_binds_exact_map_bundle_and_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "map.pgm").write_bytes(b"P5\n2 2\n255\n" + bytes([255]) * 4)
            map_path = root / "map.yaml"
            map_path.write_text(
                """image: map.pgm
resolution: 0.05
origin: [0, 0, 0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.196
""",
                encoding="utf-8",
            )
            route_path = root / "route.yaml"
            route_path.write_text(
                """schema_version: 1
map_id: final-demo-map
map_version: 7
route_id: friday-demo
frame_id: map
waypoints:
  - sequence: 1
    name: DESTINATION
    x: 0.05
    y: 0.05
    yaw_deg: 0
    acceptance_radius_m: 0.02
    action: DESTINATION
""",
                encoding="utf-8",
            )

            first = build_manifest(map_path, route_path)
            self.assertEqual(first["ROKI_MAP_ID"], "final-demo-map")
            self.assertEqual(first["ROKI_MAP_VERSION"], "7")
            self.assertEqual(len(first["ROKI_MAP_SHA256"]), 64)
            self.assertEqual(len(first["ROKI_ROUTE_SHA256"]), 64)

            route_path.write_text(
                route_path.read_text(encoding="utf-8") + "\n# changed\n",
                encoding="utf-8",
            )
            second = build_manifest(map_path, route_path)
            self.assertEqual(first["ROKI_MAP_SHA256"], second["ROKI_MAP_SHA256"])
            self.assertNotEqual(
                first["ROKI_ROUTE_SHA256"],
                second["ROKI_ROUTE_SHA256"],
            )


if __name__ == "__main__":
    unittest.main()
