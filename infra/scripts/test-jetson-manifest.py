#!/usr/bin/env python3
"""Unit tests for the Jetson IoT stable manifest contract."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate-jetson-manifest.py")
SPEC = importlib.util.spec_from_file_location("validate_jetson_manifest", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "component": "iot",
        "release": "iot-v1.2.3",
        "iot_commit": "a" * 40,
        "required_ai_contract_version": 1,
        "jetpack": "6.2",
        "architecture": "aarch64",
        "artifact_url": (
            "https://lab.ssafy.com/api/v4/projects/1/packages/"
            "generic/aiot-iot/iot-v1.2.3/aiot-iot-v1.2.3.tar.gz"
        ),
        "artifact_size_bytes": 1024,
        "sha256": "b" * 64,
        "published_at": "2026-07-31T00:00:00Z",
    }


class ManifestTest(unittest.TestCase):
    def test_valid_iot_manifest(self) -> None:
        MODULE.validate(valid_manifest())

    def test_rejects_integrated_legacy_manifest(self) -> None:
        manifest = valid_manifest()
        manifest["ai_commit"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            MODULE.validate(manifest)

    def test_rejects_legacy_tag(self) -> None:
        manifest = valid_manifest()
        manifest["release"] = "jetson-v1.2.3"
        with self.assertRaisesRegex(ValueError, "iot-vX.Y.Z"):
            MODULE.validate(manifest)

    def test_rejects_boolean_contract_version(self) -> None:
        manifest = valid_manifest()
        manifest["required_ai_contract_version"] = True
        with self.assertRaisesRegex(ValueError, "positive integer"):
            MODULE.validate(manifest)


if __name__ == "__main__":
    unittest.main()
