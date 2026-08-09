from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiot_robot.mapping_artifacts import (
    MapExportError,
    MapExportSettings,
    SlamMapExporter,
    convert_pgm_to_png,
)


class MappingArtifactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_binary_pgm_is_converted_to_png_with_same_dimensions(self) -> None:
        source = self.root / "map.pgm"
        destination = self.root / "map.png"
        source.write_bytes(b"P5\n# occupancy\n2 2\n255\n" + bytes((0, 127, 205, 255)))

        convert_pgm_to_png(source, destination)

        png = destination.read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (2, 2))

    def test_export_uses_map_saver_and_preserves_backend_metadata(self) -> None:
        commands: list[tuple[str, ...]] = []

        def runner(command, _timeout):
            command = tuple(command)
            commands.append(command)
            if "map_saver_cli" in command:
                prefix = Path(command[command.index("-f") + 1])
                prefix.with_suffix(".pgm").write_bytes(b"P5\n1 1\n255\n\x7f")
                prefix.with_suffix(".yaml").write_text(
                    "image: map.pgm\nresolution: 0.05\norigin: [-1.0, -2.0, 0.0]\n",
                    encoding="utf-8",
                )

        exporter = SlamMapExporter(
            MapExportSettings(self.root, serialize_pose_graph=True),
            runner=runner,
        )
        artifact = exporter.export(12)

        self.assertTrue(artifact.png_path.is_file())
        self.assertEqual(artifact.resolution, 0.05)
        self.assertEqual((artifact.origin_x, artifact.origin_y), (-1.0, -2.0))
        self.assertEqual(len(commands), 2)
        self.assertIn("map_saver_cli", commands[0])
        self.assertIn("save_map_timeout:=24.0", commands[0])
        self.assertIn("/slam_toolbox/serialize_map", commands[1])
        normalized_yaml = artifact.yaml_path.read_text(encoding="utf-8")
        self.assertIn("mode: trinary", normalized_yaml)
        self.assertIn("occupied_thresh: 0.65", normalized_yaml)
        self.assertIn("free_thresh: 0.15", normalized_yaml)

    def test_readiness_requires_live_slam_toolbox_service(self) -> None:
        commands: list[tuple[str, ...]] = []

        def ready_runner(command, _timeout):
            commands.append(tuple(command))
            return SimpleNamespace(
                stdout=(
                    "/slam_toolbox/serialize_map "
                    "[slam_toolbox/srv/SerializePoseGraph]\n"
                )
            )

        exporter = SlamMapExporter(
            MapExportSettings(self.root),
            runner=lambda _command, _timeout: SimpleNamespace(stdout=""),
        )
        with patch("aiot_robot.mapping_artifacts.shutil.which", return_value="ros2"):
            self.assertEqual(
                exporter.readiness(),
                (False, "SLAM_TOOLBOX_NOT_READY"),
            )

        ready_exporter = SlamMapExporter(
            MapExportSettings(self.root),
            runner=ready_runner,
        )
        with patch("aiot_robot.mapping_artifacts.shutil.which", return_value="ros2"):
            self.assertEqual(ready_exporter.readiness(), (True, "READY"))
        self.assertEqual(
            commands,
            [("ros2", "service", "list", "-t", "--no-daemon")],
        )

    def test_nonzero_origin_yaw_is_rejected_for_current_frontend(self) -> None:
        def runner(command, _timeout):
            if "map_saver_cli" not in command:
                return
            prefix = Path(command[command.index("-f") + 1])
            prefix.with_suffix(".pgm").write_bytes(b"P5\n1 1\n255\n\x7f")
            prefix.with_suffix(".yaml").write_text(
                "image: map.pgm\nresolution: 0.05\norigin: [0.0, 0.0, 0.1]\n",
                encoding="utf-8",
            )

        exporter = SlamMapExporter(
            MapExportSettings(self.root),
            runner=runner,
        )
        with self.assertRaisesRegex(MapExportError, "origin yaw 0"):
            exporter.export(1)


if __name__ == "__main__":
    unittest.main()
