"""Atomically promote a freshly mapped occupancy bundle for Nav2 patrol."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import yaml

from aiot_robot.mapping_artifacts import MapArtifact


class MapActivationError(RuntimeError):
    """A new map could not be made the persistent current patrol map."""


@dataclass(frozen=True)
class MapActivationSettings:
    maps_directory: Path
    environment_file: Path


@dataclass(frozen=True)
class ActivatedMap:
    map_id: int
    map_version: int
    yaml_path: Path
    bundle_sha256: str


class CurrentMapActivator:
    """Install an immutable map bundle and atomically switch its environment."""

    def __init__(
        self,
        settings: MapActivationSettings,
        *,
        environment: MutableMapping[str, str] | None = None,
    ) -> None:
        self._settings = settings
        # 활성화는 env 파일과 프로세스 환경을 함께 갱신한다.
        #
        # A안(무재시작 모드 전환) 이전에는 모드를 바꿀 때 서비스를 재시작했고,
        # 그래서 프로세스의 os.environ 이 항상 env 파일에서 새로 로드됐다.
        # "os.environ 은 현재 활성 지도를 반영한다" 는 불변식이 정의상 성립했고,
        # ROKI_MAP_* 을 os.getenv 로 읽는 코드는 전부 옳았다.
        #
        # 재시작을 없애면서 그 불변식만 조용히 깨졌다. 2026-08-08 실기에서
        # 그 대가를 세 자리에서 확인했다 -- 부팅 시점 v38 을 든 프로세스가
        # 방금 만든 v39 의 route/metadata 와 비교해 순찰을 거부했다
        # (NAVIGATION_MAP_MISMATCH, NAVIGATION_MAP_METADATA_MISMATCH,
        #  그리고 _build_navigation_service_from_route 의 sha256 대조).
        #
        # 호출부를 하나씩 파일에서 다시 읽게 고치는 것은 자리 수를 세는 일이고
        # 넷째 자리를 막지 못한다. 여기서 불변식을 복원하면 os.getenv 가 다시
        # 옳은 코드가 된다.
        #
        # 매핑은 os.environ 이지만 주입 가능하게 둔다: 테스트가 전역 환경을
        # 오염시키지 않아야 하고, 그 오염은 순서 의존 실패로 되돌아온다.
        self._environment = os.environ if environment is None else environment

    def activate(
        self,
        artifact: MapArtifact,
        *,
        map_id: Any,
        map_version: Any,
    ) -> ActivatedMap:
        normalized_map_id = _positive_integer(map_id, "mapId")
        normalized_map_version = _positive_integer(map_version, "mapVersion")
        image_name = _validated_image_name(artifact)
        source_hash = _bundle_sha256(artifact.yaml_path, artifact.pgm_path)

        maps_directory = self._settings.maps_directory
        maps_directory.mkdir(parents=True, exist_ok=True)
        final_directory = maps_directory / (
            f"map-{normalized_map_id}-v{normalized_map_version}-{source_hash[:12]}"
        )
        staging_directory = Path(
            tempfile.mkdtemp(prefix=".map-activation-", dir=maps_directory)
        )
        try:
            staged_yaml = staging_directory / artifact.yaml_path.name
            staged_image = staging_directory / image_name
            shutil.copyfile(artifact.yaml_path, staged_yaml)
            shutil.copyfile(artifact.pgm_path, staged_image)
            # 포즈그래프도 함께 옮긴다. 이미지가 프론트용이라면 그래프는
            # 위치추정용이고, 둘 다 있어야 이 지도로 순찰할 수 있다. 세션
            # 디렉터리에만 두면 그 디렉터리를 치우는 순간 순찰이 불가능해지는데,
            # DeserializePoseGraph 는 빈 응답이라 그 사실조차 알려주지 않는다.
            for suffix in (".posegraph", ".data"):
                source = artifact.directory / f"posegraph{suffix}"
                if source.is_file():
                    shutil.copyfile(source, staging_directory / source.name)
            if _bundle_sha256(staged_yaml, staged_image) != source_hash:
                raise MapActivationError("copied map bundle hash does not match source")

            if final_directory.exists():
                installed_yaml = final_directory / artifact.yaml_path.name
                installed_image = final_directory / image_name
                if (
                    not installed_yaml.is_file()
                    or not installed_image.is_file()
                    or _bundle_sha256(installed_yaml, installed_image) != source_hash
                ):
                    raise MapActivationError("existing map version has different content")
            else:
                os.replace(staging_directory, final_directory)

            active_yaml = final_directory / artifact.yaml_path.name
            # AIOT_ROS_MODE 를 쓰지 않는다. 예전에는 이 파일에 "patrol" 을 적고
            # restart_request_file 로 서비스를 재시작해 모드를 바꿨다. 두 운행이
            # 서로 다른 노드 집합을 쓰던 시절의 구조다. 지금은 slam_toolbox 가
            # 두 역할을 다 하므로 전환이 서비스 호출이고, 재시작이 필요 없다.
            # 여기 남은 값들은 "지금 활성 지도가 무엇인가"라는 사실뿐이다.
            environment = {
                "ROKI_MAP_YAML": str(active_yaml.resolve()),
                "ROKI_MAP_ID": str(normalized_map_id),
                "ROKI_MAP_VERSION": str(normalized_map_version),
                "ROKI_MAP_SHA256": source_hash,
            }
            _atomic_write_text(
                self._settings.environment_file,
                "".join(
                    f"{name}={json.dumps(value)}\n"
                    for name, value in environment.items()
                ),
            )
            # 파일을 쓴 뒤에만 갱신한다. env 가 파일을 앞지르면, 활성화가
            # 실패한 지도를 프로세스가 이미 활성으로 믿는 상태가 생긴다.
            self._environment.update(environment)
            return ActivatedMap(
                normalized_map_id,
                normalized_map_version,
                active_yaml,
                source_hash,
            )
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise MapActivationError("map activation filesystem failure") from exc
        finally:
            if staging_directory.exists():
                shutil.rmtree(staging_directory, ignore_errors=True)


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise MapActivationError(f"{field} must be a positive integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MapActivationError(f"{field} must be a positive integer") from exc
    if normalized <= 0 or str(normalized) != str(value).strip():
        raise MapActivationError(f"{field} must be a positive integer")
    return normalized


def _validated_image_name(artifact: MapArtifact) -> str:
    if not artifact.yaml_path.is_file() or not artifact.pgm_path.is_file():
        raise MapActivationError("map YAML and PGM must exist")
    try:
        raw = yaml.safe_load(artifact.yaml_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MapActivationError("map YAML is unreadable") from exc
    if not isinstance(raw, Mapping):
        raise MapActivationError("map YAML root must be an object")
    image = raw.get("image")
    if not isinstance(image, str) or not image.strip():
        raise MapActivationError("map YAML image is missing")
    relative_image = Path(image)
    if relative_image.is_absolute() or relative_image.name != image:
        raise MapActivationError("map YAML image must be a local file name")
    if (artifact.yaml_path.parent / relative_image).resolve() != artifact.pgm_path.resolve():
        raise MapActivationError("map YAML does not reference the exported PGM")
    return relative_image.name


def _bundle_sha256(yaml_path: Path, image_path: Path) -> str:
    digest = hashlib.sha256(b"ROKI_MAP_BUNDLE_V1\0")
    for path in (yaml_path, image_path):
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
