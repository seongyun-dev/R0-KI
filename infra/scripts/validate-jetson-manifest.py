#!/usr/bin/env python3
"""Dependency-free validation for the stable Jetson manifest contract."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


RELEASE_PATTERN = re.compile(r"^jetson-v\d+\.\d+\.\d+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_FIELDS = {
    "schema_version",
    "release",
    "robot_commit",
    "ai_commit",
    "model_version",
    "jetpack",
    "architecture",
    "artifact_url",
    "artifact_size_bytes",
    "sha256",
    "published_at",
}


def fail(message: str) -> None:
    raise ValueError(message)


def validate(manifest: object) -> None:
    if not isinstance(manifest, dict):
        fail("manifest must be a JSON object")

    missing = REQUIRED_FIELDS - manifest.keys()
    extra = manifest.keys() - REQUIRED_FIELDS
    if missing:
        fail(f"missing fields: {', '.join(sorted(missing))}")
    if extra:
        fail(f"unknown fields: {', '.join(sorted(extra))}")

    if manifest["schema_version"] != 1:
        fail("schema_version must be 1")
    if not isinstance(manifest["release"], str) or not RELEASE_PATTERN.fullmatch(
        manifest["release"]
    ):
        fail("release must match jetson-vX.Y.Z")

    for field in ("robot_commit", "ai_commit"):
        value = manifest[field]
        if not isinstance(value, str) or not COMMIT_PATTERN.fullmatch(value):
            fail(f"{field} must be a 40-character lowercase commit SHA")

    model_version = manifest["model_version"]
    if not isinstance(model_version, str) or not 1 <= len(model_version) <= 128:
        fail("model_version must contain 1 to 128 characters")
    if manifest["jetpack"] != "6.2":
        fail("jetpack must be 6.2")
    if manifest["architecture"] != "aarch64":
        fail("architecture must be aarch64")

    artifact_url = manifest["artifact_url"]
    if not isinstance(artifact_url, str) or urlparse(artifact_url).scheme != "https":
        fail("artifact_url must use HTTPS")
    artifact_size = manifest["artifact_size_bytes"]
    if isinstance(artifact_size, bool) or not isinstance(artifact_size, int) or artifact_size < 1:
        fail("artifact_size_bytes must be a positive integer")
    checksum = manifest["sha256"]
    if not isinstance(checksum, str) or not SHA256_PATTERN.fullmatch(checksum):
        fail("sha256 must be 64 lowercase hexadecimal characters")

    published_at = manifest["published_at"]
    if not isinstance(published_at, str):
        fail("published_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"published_at is invalid: {exc}")
    if parsed.tzinfo is None:
        fail("published_at must include a timezone")


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: validate-jetson-manifest.py <manifest.json> [schema.json]", file=sys.stderr)
        return 2

    manifest_path = Path(sys.argv[1])
    if len(sys.argv) == 3:
        schema = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail("unexpected JSON Schema version")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate(manifest)
    print(f"Jetson manifest validated: {manifest['release']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"manifest validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
