from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiot_robot.mapping_artifacts import MapArtifact
from integration.map_activation import (
    CurrentMapActivator,
    MapActivationError,
    MapActivationSettings,
)
from navigation.map_metadata import load_map_metadata, map_bundle_sha256


class CurrentMapActivatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / "source"
        source.mkdir()
        yaml_path = source / "map.yaml"
        pgm_path = source / "map.pgm"
        png_path = source / "map.png"
        yaml_path.write_text(
            "image: map.pgm\n"
            "mode: trinary\n"
            "resolution: 0.05\n"
            "origin: [-1.0, -2.0, 0.0]\n"
            "negate: 0\n"
            "occupied_thresh: 0.65\n"
            "free_thresh: 0.25\n",
            encoding="utf-8",
        )
        pgm_path.write_bytes(b"P5\n2 2\n255\n\xff\x00\xcd\xff")
        png_path.write_bytes(b"preview")
        self.artifact = MapArtifact(
            source,
            yaml_path,
            pgm_path,
            png_path,
            0.05,
            -1.0,
            -2.0,
            0.0,
        )
        self.settings = MapActivationSettings(
            self.root / "maps",
            self.root / "config" / "current-map.env",
            self.root / "state" / "map-activation.pending",
        )
        self.activator = CurrentMapActivator(self.settings)

    def test_installs_versioned_bundle_and_atomically_selects_patrol_map(self) -> None:
        activated = self.activator.activate(
            self.artifact,
            map_id=7,
            map_version=3,
        )

        self.assertTrue(activated.yaml_path.is_file())
        self.assertTrue((activated.yaml_path.parent / "map.pgm").is_file())
        metadata = load_map_metadata(activated.yaml_path)
        self.assertEqual(activated.bundle_sha256, map_bundle_sha256(metadata))
        environment = self.settings.environment_file.read_text(encoding="utf-8")
        self.assertIn('AIOT_ROS_MODE="patrol"', environment)
        self.assertIn('ROKI_MAP_ID="7"', environment)
        self.assertIn('ROKI_MAP_VERSION="3"', environment)
        self.assertIn(
            f'ROKI_MAP_SHA256="{activated.bundle_sha256}"',
            environment,
        )
        request = json.loads(
            self.settings.restart_request_file.read_text(encoding="utf-8")
        )
        self.assertEqual(request["mapId"], 7)
        self.assertEqual(request["mapVersion"], 3)
        self.assertEqual(request["mapYaml"], str(activated.yaml_path))

    def test_same_backend_version_and_content_is_idempotent(self) -> None:
        first = self.activator.activate(self.artifact, map_id="7", map_version="3")
        second = self.activator.activate(self.artifact, map_id=7, map_version=3)

        self.assertEqual(first, second)
        self.assertEqual(
            [path for path in self.settings.maps_directory.iterdir() if path.is_dir()],
            [first.yaml_path.parent],
        )

    def test_invalid_bundle_preserves_previously_selected_map(self) -> None:
        self.settings.environment_file.parent.mkdir(parents=True)
        self.settings.environment_file.write_text(
            'ROKI_MAP_YAML="/previous/map.yaml"\n',
            encoding="utf-8",
        )
        self.artifact.yaml_path.write_text(
            "image: another.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n",
            encoding="utf-8",
        )

        with self.assertRaises(MapActivationError):
            self.activator.activate(self.artifact, map_id=7, map_version=4)

        self.assertEqual(
            self.settings.environment_file.read_text(encoding="utf-8"),
            'ROKI_MAP_YAML="/previous/map.yaml"\n',
        )
        self.assertFalse(self.settings.restart_request_file.exists())


if __name__ == "__main__":
    unittest.main()
