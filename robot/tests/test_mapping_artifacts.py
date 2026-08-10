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
    refine_saved_map,
)

OCCUPIED, FREE, UNKNOWN = 0, 254, 205


def _write_grid(
    directory: Path,
    width: int,
    height: int,
    cells: dict[tuple[int, int], int],
    origin: tuple[float, float, float] = (-1.0, -2.0, 0.0),
    resolution: float = 0.05,
) -> tuple[Path, Path]:
    """Write a synthetic trinary map. ``cells`` maps (column, row) -> shade."""

    pixels = bytearray([UNKNOWN]) * (width * height)
    for (column, row), shade in cells.items():
        pixels[row * width + column] = shade
    pgm = directory / "map.pgm"
    pgm.write_bytes(b"P5\n%d %d\n255\n" % (width, height) + bytes(pixels))
    yaml_path = directory / "map.yaml"
    yaml_path.write_text(
        "image: map.pgm\nmode: trinary\nresolution: %s\n"
        "origin: [%s, %s, %s]\nnegate: 0\n"
        "occupied_thresh: 0.65\nfree_thresh: 0.15\n"
        % (resolution, origin[0], origin[1], origin[2]),
        encoding="utf-8",
    )
    return pgm, yaml_path


def _read_grid(pgm: Path) -> tuple[int, int, bytes]:
    raw = pgm.read_bytes()
    header, _, rest = raw.partition(b"255\n")
    width, height = (int(part) for part in header.split()[1:3])
    return width, height, rest


def _hollow_room(
    first: int, last: int, hole: tuple[int, int] | None = None
) -> dict[tuple[int, int], int]:
    cells: dict[tuple[int, int], int] = {}
    for column in range(first, last + 1):
        for row in range(first, last + 1):
            edge = column in (first, last) or row in (first, last)
            cells[(column, row)] = OCCUPIED if edge else FREE
    if hole is not None:
        cells[hole] = UNKNOWN
    return cells


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

    def test_crop_shifts_origin_so_world_coordinates_are_unchanged(self) -> None:
        pgm, yaml_path = _write_grid(self.root, 20, 20, _hollow_room(5, 10))
        settings = MapExportSettings(self.root, crop_margin_cells=0)

        refine_saved_map(pgm, yaml_path, settings)

        width, height, pixels = _read_grid(pgm)
        self.assertEqual((width, height), (6, 6))
        text = yaml_path.read_text(encoding="utf-8")
        # origin_x += 5 cells, origin_y += (20 - 1 - 10) cells, at 0.05 m/cell
        self.assertIn("- -0.75", text)
        self.assertIn("- -1.55", text)
        # the room's bottom-left wall cell keeps its world position
        self.assertEqual(pixels[5 * 6 + 0], OCCUPIED)
        old_world = (-1.0 + 5 * 0.05, -2.0 + (20 - 1 - 10) * 0.05)
        new_world = (-0.75 + 0 * 0.05, -1.55 + (6 - 1 - 5) * 0.05)
        self.assertAlmostEqual(old_world[0], new_world[0], places=6)
        self.assertAlmostEqual(old_world[1], new_world[1], places=6)

    def test_isolated_hits_are_dropped_but_wall_segments_survive(self) -> None:
        cells = _hollow_room(5, 10)
        cells[(16, 16)] = OCCUPIED  # lone speckle in unknown space
        pgm, yaml_path = _write_grid(self.root, 20, 20, cells)

        refine_saved_map(
            pgm, yaml_path, MapExportSettings(self.root, crop_margin_cells=0)
        )

        width, height, pixels = _read_grid(pgm)
        # cropping to the room proves the speckle was removed before bounding:
        # otherwise the observed area would still reach column/row 16.
        self.assertEqual((width, height), (6, 6))
        walls = sum(1 for value in pixels if value == OCCUPIED)
        self.assertEqual(walls, 20)  # the full 6x6 hollow border, intact

    def test_small_hole_in_free_space_is_filled_but_not_next_to_a_wall(
        self,
    ) -> None:
        for hole, expected in (((7, 7), FREE), ((6, 6), UNKNOWN)):
            with self.subTest(hole=hole):
                root = Path(tempfile.mkdtemp(dir=self.root))
                pgm, yaml_path = _write_grid(
                    root, 20, 20, _hollow_room(5, 10, hole=hole)
                )

                refine_saved_map(
                    pgm, yaml_path, MapExportSettings(root, crop_margin_cells=0)
                )

                width, _height, pixels = _read_grid(pgm)
                local = (hole[0] - 5, hole[1] - 5)
                self.assertEqual(pixels[local[1] * width + local[0]], expected)

    def test_all_unknown_map_keeps_its_canvas_and_origin(self) -> None:
        pgm, yaml_path = _write_grid(self.root, 8, 8, {})

        refine_saved_map(pgm, yaml_path, MapExportSettings(self.root))

        width, height, _pixels = _read_grid(pgm)
        self.assertEqual((width, height), (8, 8))
        text = yaml_path.read_text(encoding="utf-8")
        self.assertIn("-1.0", text)
        self.assertIn("-2.0", text)

    def test_refinement_can_be_disabled_without_touching_the_map(self) -> None:
        def runner(command, _timeout):
            command = tuple(command)
            if "map_saver_cli" in command:
                prefix = Path(command[command.index("-f") + 1])
                cells = _hollow_room(5, 10)
                cells[(16, 16)] = OCCUPIED
                _write_grid(prefix.parent, 20, 20, cells)

        exporter = SlamMapExporter(
            MapExportSettings(
                self.root,
                serialize_pose_graph=False,
                refine_saved_grid=False,
            ),
            runner=runner,
        )
        artifact = exporter.export(9)

        width, height, pixels = _read_grid(artifact.pgm_path)
        self.assertEqual((width, height), (20, 20))
        self.assertEqual(pixels[16 * 20 + 16], OCCUPIED)  # speckle preserved
        self.assertAlmostEqual(artifact.origin_x, -1.0, places=6)
        self.assertAlmostEqual(artifact.origin_y, -2.0, places=6)

    def test_export_png_matches_the_cropped_grid_the_backend_measures(
        self,
    ) -> None:
        def runner(command, _timeout):
            command = tuple(command)
            if "map_saver_cli" in command:
                prefix = Path(command[command.index("-f") + 1])
                cells = _hollow_room(5, 10)
                cells[(16, 16)] = OCCUPIED
                _write_grid(prefix.parent, 20, 20, cells)

        exporter = SlamMapExporter(
            MapExportSettings(
                self.root, serialize_pose_graph=False, crop_margin_cells=0
            ),
            runner=runner,
        )
        artifact = exporter.export(7)

        png = artifact.png_path.read_bytes()
        # The backend reads width/height straight off this PNG, so it must carry
        # the cropped size rather than the original SLAM canvas.
        self.assertEqual(struct.unpack(">II", png[16:24]), (6, 6))
        self.assertAlmostEqual(artifact.origin_x, -0.75, places=6)
        self.assertAlmostEqual(artifact.origin_y, -1.55, places=6)

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
            [
                (
                    "ros2",
                    "service",
                    "list",
                    "-t",
                    "--no-daemon",
                    "--spin-time",
                    "2.0",
                )
            ],
        )

    def test_readiness_retries_one_partial_discovery_within_deadline(self) -> None:
        calls: list[tuple[tuple[str, ...], float]] = []

        def runner(command, timeout):
            calls.append((tuple(command), timeout))
            if len(calls) == 1:
                return SimpleNamespace(stdout="")
            return SimpleNamespace(
                stdout=(
                    "/slam_toolbox/serialize_map "
                    "[slam_toolbox/srv/SerializePoseGraph]\n"
                )
            )

        exporter = SlamMapExporter(MapExportSettings(self.root), runner=runner)
        with patch("aiot_robot.mapping_artifacts.shutil.which", return_value="ros2"):
            self.assertEqual(exporter.readiness(), (True, "READY"))

        self.assertEqual(len(calls), 2)
        self.assertGreater(calls[0][1], calls[1][1])
        self.assertLessEqual(calls[0][1], 8.0)

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
