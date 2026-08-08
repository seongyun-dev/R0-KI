"""Save a live SLAM Toolbox map and prepare the backend preview artifact."""

from __future__ import annotations

import binascii
import math
import shutil
import struct
import subprocess
import tempfile
import zlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml


class MapExportError(RuntimeError):
    """The live ROS map could not be saved or validated."""


@dataclass(frozen=True)
class MapArtifact:
    directory: Path
    yaml_path: Path
    pgm_path: Path
    png_path: Path
    resolution: float
    origin_x: float
    origin_y: float
    origin_yaw: float


@dataclass(frozen=True)
class MapExportSettings:
    output_directory: Path
    timeout_seconds: float = 30.0
    serialize_pose_graph: bool = True
    require_zero_origin_yaw: bool = True
    # SLAM Toolbox sizes the grid to every ray endpoint, so a small room ends up
    # as a tiny island inside a mostly-unknown canvas, and a single-channel
    # LiDAR leaves isolated hits behind. Refining the saved grid keeps the same
    # PGM/YAML contract while making the map match the space that was mapped.
    refine_saved_grid: bool = True
    crop_margin_cells: int = 4
    unknown_island_max_cells: int = 8

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("map export timeout must be positive")
        if self.crop_margin_cells < 0:
            raise ValueError("crop margin must not be negative")
        if self.unknown_island_max_cells < 0:
            raise ValueError("unknown island limit must not be negative")


CommandRunner = Callable[[Sequence[str], float], Any]


def _run_command(
    command: Sequence[str], timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class SlamMapExporter:
    """Use the installed Nav2 map saver without owning any ROS node."""

    def __init__(
        self,
        settings: MapExportSettings,
        *,
        runner: CommandRunner = _run_command,
        ros2_command: str = "ros2",
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._ros2_command = ros2_command

    def readiness(self) -> tuple[bool, str]:
        if shutil.which(self._ros2_command) is None:
            return False, "ROS2_COMMAND_NOT_FOUND"
        try:
            self._settings.output_directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=self._settings.output_directory,
                prefix=".mapping-write-check-",
            ):
                pass
        except OSError:
            return False, "MAP_OUTPUT_NOT_WRITABLE"
        try:
            result = self._runner(
                (
                    self._ros2_command,
                    "service",
                    "list",
                    "-t",
                    "--no-daemon",
                ),
                min(self._settings.timeout_seconds, 5.0),
            )
        except (OSError, subprocess.SubprocessError):
            return False, "SLAM_TOOLBOX_NOT_READY"
        service_graph = str(getattr(result, "stdout", ""))
        expected_service = (
            "/slam_toolbox/serialize_map "
            "[slam_toolbox/srv/SerializePoseGraph]"
        )
        if expected_service not in service_graph:
            return False, "SLAM_TOOLBOX_NOT_READY"
        return True, "READY"

    def export(self, mapping_session_id: int) -> MapArtifact:
        if isinstance(mapping_session_id, bool) or mapping_session_id <= 0:
            raise ValueError("mapping_session_id must be a positive integer")
        self._settings.output_directory.mkdir(parents=True, exist_ok=True)
        directory = Path(
            tempfile.mkdtemp(
                prefix=f"mapping-{mapping_session_id}-",
                dir=self._settings.output_directory,
            )
        )
        prefix = directory / "map"
        # Nav2's CLI otherwise uses a 2-second internal default. The Jetson's
        # transient-local /map sample took slightly longer during field audit,
        # even though the outer process timeout was 30 seconds.
        saver_timeout = max(2.0, self._settings.timeout_seconds * 0.8)
        try:
            self._runner(
                (
                    self._ros2_command,
                    "run",
                    "nav2_map_server",
                    "map_saver_cli",
                    "-f",
                    str(prefix),
                    "--ros-args",
                    "-p",
                    # Nav2 declares this parameter as double.  ``:g`` turns
                    # an integral float such as 24.0 into ``24``, which ROS
                    # then rejects as an integer override.
                    f"save_map_timeout:={saver_timeout}",
                ),
                self._settings.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise MapExportError("ROS map_saver_cli failed") from exc

        yaml_path = prefix.with_suffix(".yaml")
        pgm_path = prefix.with_suffix(".pgm")
        if not yaml_path.is_file() or not pgm_path.is_file():
            raise MapExportError("map saver did not create map.yaml and map.pgm")
        _normalize_map_thresholds(yaml_path)
        if self._settings.refine_saved_grid:
            # Must run before the PNG is rendered and before the metadata is
            # read: the backend derives width/height from the uploaded PNG, and
            # the returned artifact must carry the post-crop origin.
            refine_saved_map(pgm_path, yaml_path, self._settings)
        metadata = _load_metadata(yaml_path)
        origin_x, origin_y, origin_yaw = metadata["origin"]
        if self._settings.require_zero_origin_yaw and not math.isclose(
            origin_yaw, 0.0, abs_tol=1e-6
        ):
            raise MapExportError(
                "frontend coordinate conversion requires map origin yaw 0"
            )
        png_path = directory / "map.png"
        convert_pgm_to_png(pgm_path, png_path)
        if self._settings.serialize_pose_graph:
            self._serialize_pose_graph(directory / "posegraph")
        return MapArtifact(
            directory=directory,
            yaml_path=yaml_path,
            pgm_path=pgm_path,
            png_path=png_path,
            resolution=metadata["resolution"],
            origin_x=origin_x,
            origin_y=origin_y,
            origin_yaw=origin_yaw,
        )

    def _serialize_pose_graph(self, prefix: Path) -> None:
        try:
            self._runner(
                (
                    self._ros2_command,
                    "service",
                    "call",
                    "/slam_toolbox/serialize_map",
                    "slam_toolbox/srv/SerializePoseGraph",
                    f"{{filename: '{prefix}'}}",
                ),
                self._settings.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # The backend needs only PNG + YAML metadata. Preserve the usable
            # map even when optional pose-graph serialization is unavailable.
            print(
                "[MAPPING] pose graph serialization skipped "
                f"type={type(exc).__name__}"
            )


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MapExportError("map YAML is unreadable") from exc
    if not isinstance(raw, Mapping):
        raise MapExportError("map YAML root must be an object")
    resolution = _finite(raw.get("resolution"), "resolution")
    if resolution <= 0:
        raise MapExportError("map resolution must be positive")
    origin = raw.get("origin")
    if not isinstance(origin, list) or len(origin) != 3:
        raise MapExportError("map origin must contain x, y and yaw")
    return {
        "resolution": resolution,
        "origin": tuple(
            _finite(value, f"origin[{index}]") for index, value in enumerate(origin)
        ),
    }


def _normalize_map_thresholds(path: Path) -> None:
    """Keep canonical ROS unknown pixels unknown during Nav2 patrol.

    ``map_saver_cli`` commonly writes ``free_thresh: 0.25``. For a trinary
    PGM, the canonical unknown shade (205/255) has occupancy about 0.196 and
    would therefore be classified as FREE. The runtime correctly rejects that
    unsafe map, so normalize saved maps before hashing, upload and activation.
    """

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MapExportError("map YAML is unreadable") from exc
    if not isinstance(raw, Mapping):
        raise MapExportError("map YAML root must be an object")
    normalized = dict(raw)
    normalized["mode"] = "trinary"
    normalized["occupied_thresh"] = 0.65
    normalized["free_thresh"] = 0.15
    temporary = path.with_name(f".{path.name}.thresholds.tmp")
    try:
        temporary.write_text(
            yaml.safe_dump(normalized, sort_keys=False),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        raise MapExportError("map thresholds could not be normalized") from exc
    finally:
        temporary.unlink(missing_ok=True)


_OCCUPIED, _FREE, _UNKNOWN = 0, 1, 2
# Canonical ROS trinary shades, written only for cells this pass changes.
_SHADE = {_OCCUPIED: 0, _FREE: 254, _UNKNOWN: 205}
_NEIGHBOURS_8 = (
    (-1, -1), (0, -1), (1, -1),
    (-1, 0), (1, 0),
    (-1, 1), (0, 1), (1, 1),
)


def _read_pgm_grid(path: Path) -> tuple[int, int, int, bytearray]:
    try:
        raw = path.read_bytes()
        magic, cursor = _pgm_token(raw, 0)
        width_raw, cursor = _pgm_token(raw, cursor)
        height_raw, cursor = _pgm_token(raw, cursor)
        maximum_raw, cursor = _pgm_token(raw, cursor)
        width, height, maximum = (
            int(width_raw), int(height_raw), int(maximum_raw)
        )
    except (OSError, ValueError) as exc:
        raise MapExportError("saved map PGM header is invalid") from exc
    if magic != b"P5":
        raise MapExportError("saved map PGM must be binary P5")
    if width <= 0 or height <= 0 or not 1 <= maximum <= 255:
        raise MapExportError("saved map PGM dimensions are invalid")
    if cursor >= len(raw) or raw[cursor] not in b" \t\r\n":
        raise MapExportError("saved map PGM raster separator is missing")
    cursor += 2 if raw[cursor : cursor + 2] == b"\r\n" else 1
    pixels = bytearray(raw[cursor : cursor + width * height])
    if len(pixels) != width * height:
        raise MapExportError("saved map PGM raster is incomplete")
    return width, height, maximum, pixels


def _classify(
    pixels: bytearray, maximum: int, occupied_thresh: float, free_thresh: float
) -> bytearray:
    classes = bytearray(len(pixels))
    for index, value in enumerate(pixels):
        occupancy = (maximum - value) / float(maximum)
        if occupancy > occupied_thresh:
            classes[index] = _OCCUPIED
        elif occupancy < free_thresh:
            classes[index] = _FREE
        else:
            classes[index] = _UNKNOWN
    return classes


def _drop_occupied_speckle(
    width: int, height: int, classes: bytearray
) -> list[tuple[int, int]]:
    """Remove hits with at most one occupied neighbour.

    A real wall segment always has two or more occupied neighbours, so this
    clears single-scan LiDAR noise and people who walked past during mapping
    without eroding genuine structure.
    """

    changed: list[tuple[int, int]] = []
    for row in range(height):
        for column in range(width):
            index = row * width + column
            if classes[index] != _OCCUPIED:
                continue
            occupied = free = 0
            for dx, dy in _NEIGHBOURS_8:
                nx, ny = column + dx, row + dy
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                neighbour = classes[ny * width + nx]
                if neighbour == _OCCUPIED:
                    occupied += 1
                elif neighbour == _FREE:
                    free += 1
            if occupied <= 1:
                changed.append((index, _FREE if free >= 3 else _UNKNOWN))
    for index, value in changed:
        classes[index] = value
    return changed


def _fill_unknown_islands(
    width: int, height: int, classes: bytearray, max_cells: int
) -> int:
    """Close small unobserved holes that sit inside observed free space.

    Only holes bounded purely by free cells are filled: a hole touching a wall
    may be genuinely unobserved space behind that wall, and one touching the
    canvas border belongs to the unmapped outside.
    """

    if max_cells <= 0:
        return 0
    visited = bytearray(width * height)
    filled = 0
    for row in range(height):
        for column in range(width):
            start = row * width + column
            if classes[start] != _UNKNOWN or visited[start]:
                continue
            visited[start] = 1
            queue = deque(((column, row),))
            component = [start]
            touches_border = False
            free_neighbours = occupied_neighbours = 0
            while queue:
                cx, cy = queue.popleft()
                if cx in (0, width - 1) or cy in (0, height - 1):
                    touches_border = True
                for dx, dy in _NEIGHBOURS_8:
                    nx, ny = cx + dx, cy + dy
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        touches_border = True
                        continue
                    neighbour_index = ny * width + nx
                    neighbour = classes[neighbour_index]
                    if neighbour == _FREE:
                        free_neighbours += 1
                    elif neighbour == _OCCUPIED:
                        occupied_neighbours += 1
                    elif not visited[neighbour_index]:
                        visited[neighbour_index] = 1
                        queue.append((nx, ny))
                        component.append(neighbour_index)
            if touches_border or len(component) > max_cells:
                continue
            if free_neighbours == 0 or occupied_neighbours > 0:
                continue
            for index in component:
                classes[index] = _FREE
            filled += len(component)
    return filled


def _observed_bounds(
    width: int, height: int, classes: bytearray, margin: int
) -> tuple[int, int, int, int] | None:
    columns = [index % width for index, value in enumerate(classes)
               if value != _UNKNOWN]
    if not columns:
        return None
    rows = [index // width for index, value in enumerate(classes)
            if value != _UNKNOWN]
    first_column = max(0, min(columns) - margin)
    last_column = min(width - 1, max(columns) + margin)
    first_row = max(0, min(rows) - margin)
    last_row = min(height - 1, max(rows) + margin)
    if last_column <= first_column or last_row <= first_row:
        return None
    return first_column, last_column, first_row, last_row


def _write_pgm(path: Path, width: int, height: int, pixels: bytes) -> None:
    temporary = path.with_name(f".{path.name}.refine.tmp")
    try:
        header = b"P5\n%d %d\n255\n" % (width, height)
        temporary.write_bytes(header + pixels)
        temporary.replace(path)
    except OSError as exc:
        raise MapExportError("refined map PGM could not be written") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _shift_map_origin(path: Path, delta_x: float, delta_y: float) -> None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MapExportError("map YAML is unreadable") from exc
    if not isinstance(raw, Mapping):
        raise MapExportError("map YAML root must be an object")
    origin = raw.get("origin")
    if not isinstance(origin, list) or len(origin) != 3:
        raise MapExportError("map origin must contain x, y and yaw")
    updated = dict(raw)
    updated["origin"] = [
        round(_finite(origin[0], "origin[0]") + delta_x, 6),
        round(_finite(origin[1], "origin[1]") + delta_y, 6),
        _finite(origin[2], "origin[2]"),
    ]
    temporary = path.with_name(f".{path.name}.origin.tmp")
    try:
        temporary.write_text(
            yaml.safe_dump(updated, sort_keys=False), encoding="utf-8"
        )
        temporary.replace(path)
    except OSError as exc:
        raise MapExportError("map origin could not be updated") from exc
    finally:
        temporary.unlink(missing_ok=True)


def refine_saved_map(
    pgm_path: Path, yaml_path: Path, settings: MapExportSettings
) -> None:
    """Despeckle the saved grid and crop it to the space that was mapped.

    The PGM stays binary P5 with the canonical trinary shades and the YAML keeps
    every key, so hashing, upload, activation and the frontend's
    origin/resolution coordinate conversion all keep working unchanged. Cropping
    shifts ``origin`` by exactly the removed offset, which leaves every world
    coordinate -- and therefore every stored waypoint and zone -- where it was.

    The stored map is localization evidence for AMCL; obstacle avoidance runs
    off the live LiDAR costmap, so clearing isolated hits does not weaken the
    obstacle interlock.
    """

    metadata = _load_metadata(yaml_path)
    resolution = metadata["resolution"]
    thresholds = _load_thresholds(yaml_path)
    width, height, maximum, pixels = _read_pgm_grid(pgm_path)
    classes = _classify(pixels, maximum, *thresholds)

    speckle = _drop_occupied_speckle(width, height, classes)
    for index, value in speckle:
        pixels[index] = _SHADE[value]
    filled = _fill_unknown_islands(
        width, height, classes, settings.unknown_island_max_cells
    )
    if filled:
        for index, value in enumerate(classes):
            if value == _FREE and pixels[index] == _SHADE[_UNKNOWN]:
                pixels[index] = _SHADE[_FREE]

    bounds = _observed_bounds(width, height, classes, settings.crop_margin_cells)
    if bounds is None:
        # Nothing observed, or the observed span is degenerate: keep the canvas
        # rather than emitting a map the runtime cannot localize against.
        _write_pgm(pgm_path, width, height, bytes(pixels))
        print(
            "[MAPPING] map refined speckle=%d holes=%d crop=skipped"
            % (len(speckle), filled)
        )
        return

    first_column, last_column, first_row, last_row = bounds
    new_width = last_column - first_column + 1
    new_height = last_row - first_row + 1
    cropped = bytearray(new_width * new_height)
    for row in range(new_height):
        source = (first_row + row) * width + first_column
        cropped[row * new_width : (row + 1) * new_width] = pixels[
            source : source + new_width
        ]
    _write_pgm(pgm_path, new_width, new_height, bytes(cropped))
    # PGM row 0 is the top row while the map origin is the bottom-left corner,
    # so the vertical shift is measured from the bottom-most retained row.
    _shift_map_origin(
        yaml_path,
        first_column * resolution,
        (height - 1 - last_row) * resolution,
    )
    print(
        "[MAPPING] map refined speckle=%d holes=%d crop=%dx%d->%dx%d"
        % (len(speckle), filled, width, height, new_width, new_height)
    )


def _load_thresholds(path: Path) -> tuple[float, float]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MapExportError("map YAML is unreadable") from exc
    if not isinstance(raw, Mapping):
        raise MapExportError("map YAML root must be an object")
    occupied = _finite(raw.get("occupied_thresh", 0.65), "occupied_thresh")
    free = _finite(raw.get("free_thresh", 0.15), "free_thresh")
    if not 0.0 <= free < occupied <= 1.0:
        raise MapExportError("map thresholds must satisfy 0 <= free < occupied <= 1")
    return occupied, free


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MapExportError(f"map {field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MapExportError(f"map {field} must be finite")
    return result


def convert_pgm_to_png(source: Path, destination: Path) -> None:
    """Convert P2/P5 occupancy PGM to an 8-bit grayscale PNG using stdlib."""

    try:
        raw = source.read_bytes()
        magic, cursor = _pgm_token(raw, 0)
        width_raw, cursor = _pgm_token(raw, cursor)
        height_raw, cursor = _pgm_token(raw, cursor)
        maximum_raw, cursor = _pgm_token(raw, cursor)
        width = int(width_raw)
        height = int(height_raw)
        maximum = int(maximum_raw)
    except (OSError, ValueError) as exc:
        raise MapExportError("invalid PGM header") from exc
    if magic not in {b"P2", b"P5"} or width <= 0 or height <= 0:
        raise MapExportError("unsupported PGM image")
    if not 1 <= maximum <= 255:
        raise MapExportError("PGM max value must be between 1 and 255")
    expected = width * height
    if magic == b"P5":
        if cursor >= len(raw) or raw[cursor] not in b" \t\r\n":
            raise MapExportError("PGM binary raster separator is missing")
        if raw[cursor : cursor + 2] == b"\r\n":
            cursor += 2
        else:
            cursor += 1
        pixels = raw[cursor : cursor + expected]
        if len(pixels) != expected:
            raise MapExportError("PGM raster is incomplete")
    else:
        values: list[int] = []
        while len(values) < expected:
            token, cursor = _pgm_token(raw, cursor)
            if not token:
                break
            try:
                values.append(int(token))
            except ValueError as exc:
                raise MapExportError("PGM ASCII raster is invalid") from exc
        if len(values) != expected:
            raise MapExportError("PGM raster is incomplete")
        if any(value < 0 or value > maximum for value in values):
            raise MapExportError("PGM pixel is outside max value")
        pixels = bytes(values)
    if maximum != 255:
        pixels = bytes(round(value * 255 / maximum) for value in pixels)
    scanlines = b"".join(
        b"\x00" + pixels[row * width : (row + 1) * width]
        for row in range(height)
    )
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(
        _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0),
        )
    )
    png.extend(_png_chunk(b"IDAT", zlib.compress(scanlines, level=6)))
    png.extend(_png_chunk(b"IEND", b""))
    try:
        destination.write_bytes(bytes(png))
    except OSError as exc:
        raise MapExportError("PNG preview could not be written") from exc


def _pgm_token(raw: bytes, cursor: int) -> tuple[bytes, int]:
    length = len(raw)
    while cursor < length:
        if raw[cursor] in b" \t\r\n":
            cursor += 1
            continue
        if raw[cursor] == ord("#"):
            newline = raw.find(b"\n", cursor)
            cursor = length if newline < 0 else newline + 1
            continue
        break
    start = cursor
    while cursor < length and raw[cursor] not in b" \t\r\n#":
        cursor += 1
    return raw[start:cursor], cursor


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", checksum)
    )
