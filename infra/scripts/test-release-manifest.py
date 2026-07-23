#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("release-manifest.py")
SPEC = importlib.util.spec_from_file_location("release_manifest", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseManifestTest(unittest.TestCase):
    def test_write_validate_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / "current.env"
            env_path.write_text(
                "\n".join(
                    [
                        "DEPLOY_BRANCH=front/master",
                        "DEPLOY_COMMIT=0123456789abcdef",
                        "FRONTEND_ENABLED=true",
                        "FRONTEND_IMAGE=aiot-frontend:front-0123456789ab",
                        "FRONTEND_COMMIT=0123456789abcdef",
                        "FRONTEND_BRANCH=front/master",
                        "BACKEND_ENABLED=true",
                        "BACKEND_IMAGE=aiot-backend:back-fedcba987654",
                        "BACKEND_COMMIT=fedcba9876543210",
                        "BACKEND_BRANCH=back/master",
                        "DATABASE_SCHEMA=4",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = Namespace(
                env=env_path,
                previous=None,
                release_id="release-test-1",
                infra_commit="0123456789abcdef",
                pipeline_id="12",
                job_id="34",
                components="frontend",
                integration_status="passed",
                mqtt_schema=1,
            )
            manifest = MODULE.create_manifest(args)
            MODULE.validate_manifest(manifest)
            self.assertEqual(manifest["frontend"]["branch"], "front/master")
            self.assertEqual(manifest["backend"]["commit"], "fedcba9876543210")
            self.assertEqual(manifest["deployedComponents"], ["frontend"])
            exported = MODULE.manifest_to_env(manifest)
            self.assertIn("FRONTEND_IMAGE=aiot-frontend:front-0123456789ab", exported)
            self.assertIn("BACKEND_IMAGE=aiot-backend:back-fedcba987654", exported)

    def test_latest_image_is_rejected(self) -> None:
        manifest = {
            "schemaVersion": 1,
            "releaseId": "release-test-2",
            "releasedAt": "2026-07-23T00:00:00Z",
            "integrationStatus": "passed",
            "deployedComponents": ["frontend"],
            "frontend": {
                "enabled": True,
                "image": "aiot-frontend:latest",
                "commit": "0123456",
                "branch": "front/master",
            },
            "backend": {
                "enabled": False,
                "image": None,
                "commit": None,
                "branch": None,
                "databaseSchema": None,
            },
            "ai": MODULE.pending_edge(),
            "iot": MODULE.pending_edge(),
            "infra": {"commit": "0123456", "pipelineId": None, "jobId": None},
            "mqttSchema": 1,
        }
        with self.assertRaises(MODULE.ManifestError):
            MODULE.validate_manifest(manifest)

    def test_schema_file_is_valid_json(self) -> None:
        schema_path = SCRIPT_PATH.parent.parent / "release" / "release-manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)


if __name__ == "__main__":
    unittest.main()
