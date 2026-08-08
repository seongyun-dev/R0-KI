from __future__ import annotations

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
        )
        # 실제 os.environ 을 쓰지 않는다. 전역 환경을 건드리는 테스트는 다른
        # 테스트로 새어나가 순서 의존 실패를 만든다.
        self.environment: dict[str, str] = {
            "ROKI_MAP_YAML": "/var/lib/aiot/maps/active/map-7-v2-old/map.yaml",
            "ROKI_MAP_ID": "7",
            "ROKI_MAP_VERSION": "2",
            "ROKI_MAP_SHA256": "0" * 64,
        }
        self.activator = CurrentMapActivator(
            self.settings, environment=self.environment
        )

    def test_activation_updates_the_process_environment(self) -> None:
        """활성화하면 프로세스 환경이 새 지도를 가리켜야 한다.

        A안(무재시작 모드 전환) 이전에는 모드를 바꿀 때 서비스를 재시작해서
        os.environ 이 env 파일에서 새로 로드됐다. 그래서 "os.environ 은 현재
        활성 지도를 반영한다" 는 불변식이 정의상 성립했고, ROKI_MAP_* 을
        os.getenv 로 읽는 코드가 전부 옳았다.

        재시작을 없애면서 그 불변식만 깨졌고, 2026-08-08 실기에서 세 자리가
        같은 이유로 순찰을 거부했다 -- 부팅 시점 v38 을 든 프로세스가 방금
        만든 v39 의 route/metadata/sha256 과 비교했다.

        이 테스트는 호출부를 세지 않는다. 불변식 자체를 지킨다 -- 그래야
        나중에 생기는 넷째 호출부도 자동으로 옳다.
        """

        activated = self.activator.activate(self.artifact, map_id=7, map_version=3)

        self.assertEqual(self.environment["ROKI_MAP_VERSION"], "3")
        self.assertEqual(self.environment["ROKI_MAP_ID"], "7")
        self.assertEqual(
            self.environment["ROKI_MAP_YAML"], str(activated.yaml_path.resolve())
        )
        self.assertEqual(self.environment["ROKI_MAP_SHA256"], activated.bundle_sha256)

    def test_failed_activation_does_not_touch_the_environment(self) -> None:
        """실패한 활성화가 환경을 오염시키면, 프로세스가 없는 지도를 활성으로 믿는다."""

        before = dict(self.environment)

        with self.assertRaises(MapActivationError):
            self.activator.activate(self.artifact, map_id=0, map_version=3)

        self.assertEqual(self.environment, before)

    def test_environment_and_env_file_agree_after_activation(self) -> None:
        """진실이 둘이면 언젠가 어긋난다. 파일과 프로세스 환경이 같아야 한다."""

        self.activator.activate(self.artifact, map_id=7, map_version=3)

        written = {}
        for line in self.settings.environment_file.read_text(
            encoding="utf-8"
        ).splitlines():
            name, separator, raw = line.partition("=")
            if separator:
                written[name.strip()] = raw.strip().strip('"')
        for name in (
            "ROKI_MAP_YAML",
            "ROKI_MAP_ID",
            "ROKI_MAP_VERSION",
            "ROKI_MAP_SHA256",
        ):
            self.assertEqual(written[name], self.environment[name], name)

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
        self.assertIn('ROKI_MAP_ID="7"', environment)
        self.assertIn('ROKI_MAP_VERSION="3"', environment)
        self.assertIn(
            f'ROKI_MAP_SHA256="{activated.bundle_sha256}"',
            environment,
        )
        # 활성화는 더 이상 모드를 정하지 않는다. 예전에는 여기에
        # AIOT_ROS_MODE="patrol" 을 적고 마커 파일로 서비스를 재시작해 전환했다.
        # 그 재시작이 진행 중이던 세션을 고아로 만들고 시리얼을 다시 열게 했다.
        # 지금은 slam_toolbox 서비스 호출로 전환하므로, 이 파일에 남는 것은
        # "활성 지도가 무엇인가"라는 사실뿐이다.
        self.assertNotIn("AIOT_ROS_MODE", environment)

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


if __name__ == "__main__":
    unittest.main()
