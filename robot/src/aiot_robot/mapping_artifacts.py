"""Save a live SLAM Toolbox map and prepare the backend preview artifact."""

from __future__ import annotations

import binascii
import math
import shutil
import struct
import subprocess
import tempfile
import zlib
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

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("map export timeout must be positive")


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
                    "type",
                    "/slam_toolbox/serialize_map",
                ),
                min(self._settings.timeout_seconds, 5.0),
            )
        except (OSError, subprocess.SubprocessError):
            return False, "SLAM_TOOLBOX_NOT_READY"
        service_type = str(getattr(result, "stdout", "")).strip()
        if "slam_toolbox/srv/SerializePoseGraph" not in service_type:
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
