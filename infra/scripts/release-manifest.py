#!/usr/bin/env python3
"""Create, validate and read the production release manifest.

Only Python's standard library is used so this script can run on the EC2 host
and in GitLab CI without installing another package.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}$")
RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9._/:,@+-]*$")
APPLICATION_COMPONENTS = ("frontend", "backend")
EDGE_COMPONENTS = ("ai", "iot")
VALID_INTEGRATION_STATUSES = {"passed", "provisional", "legacy", "pending"}


class ManifestError(ValueError):
    pass


def fail(message: str) -> None:
    raise ManifestError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        fail("manifest root must be an object")
    return value


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ManifestError(f"environment file not found: {path}") from exc
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            fail(f"invalid environment line {number} in {path}")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            fail(f"invalid environment key on line {number}: {key}")
        if "\n" in value or "\r" in value:
            fail(f"multiline environment value is not supported: {key}")
        values[key] = value
    return values


def optional_string(value: Any, field: str, max_length: int) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > max_length:
        fail(f"{field} must be a string of at most {max_length} characters or null")
    return value


def validate_commit(value: Any, field: str) -> str | None:
    value = optional_string(value, field, 64)
    if value is not None and not COMMIT_RE.fullmatch(value):
        fail(f"{field} must be a 7-64 character lowercase hexadecimal commit")
    return value


def validate_application_component(name: str, value: Any) -> None:
    if not isinstance(value, dict):
        fail(f"{name} must be an object")
    expected = {"enabled", "image", "commit", "branch"}
    if name == "backend":
        expected.add("databaseSchema")
    if set(value) != expected:
        fail(f"{name} fields must be exactly: {', '.join(sorted(expected))}")
    if not isinstance(value["enabled"], bool):
        fail(f"{name}.enabled must be a boolean")
    image = optional_string(value["image"], f"{name}.image", 255)
    commit = validate_commit(value["commit"], f"{name}.commit")
    optional_string(value["branch"], f"{name}.branch", 128)
    if value["enabled"]:
        if image is None or not IMAGE_RE.fullmatch(image):
            fail(f"{name}.image is required and must be an immutable image reference")
        if image.endswith(":latest") or ":latest@" in image:
            fail(f"{name}.image must not use latest")
        if commit is None:
            fail(f"{name}.commit is required when the component is enabled")
    elif image is not None or commit is not None:
        fail(f"disabled {name} must have null image and commit")
    if name == "backend":
        optional_string(value["databaseSchema"], "backend.databaseSchema", 128)


def validate_edge_component(name: str, value: Any) -> None:
    if not isinstance(value, dict):
        fail(f"{name} must be an object")
    expected = {"status", "version", "artifact", "checksum"}
    if set(value) != expected:
        fail(f"{name} fields must be exactly: {', '.join(sorted(expected))}")
    if value["status"] not in {"pending", "released"}:
        fail(f"{name}.status must be pending or released")
    version = optional_string(value["version"], f"{name}.version", 128)
    artifact = optional_string(value["artifact"], f"{name}.artifact", 2048)
    checksum = optional_string(value["checksum"], f"{name}.checksum", 64)
    if checksum is not None and not re.fullmatch(r"[0-9a-f]{64}", checksum):
        fail(f"{name}.checksum must be a SHA-256 hexadecimal value")
    if value["status"] == "released" and not all((version, artifact, checksum)):
        fail(f"released {name} requires version, artifact and checksum")
    if value["status"] == "pending" and any((version, artifact, checksum)):
        fail(f"pending {name} must not contain release metadata")


def validate_manifest(manifest: dict[str, Any]) -> None:
    expected = {
        "schemaVersion",
        "releaseId",
        "releasedAt",
        "integrationStatus",
        "deployedComponents",
        "frontend",
        "backend",
        "ai",
        "iot",
        "infra",
        "mqttSchema",
    }
    if set(manifest) != expected:
        fail(f"manifest fields must be exactly: {', '.join(sorted(expected))}")
    if manifest["schemaVersion"] != 1:
        fail("schemaVersion must be 1")
    release_id = manifest["releaseId"]
    if not isinstance(release_id, str) or not RELEASE_ID_RE.fullmatch(release_id):
        fail("releaseId contains unsupported characters")
    released_at = manifest["releasedAt"]
    if not isinstance(released_at, str):
        fail("releasedAt must be an ISO-8601 string")
    try:
        datetime.fromisoformat(released_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestError("releasedAt must be a valid ISO-8601 timestamp") from exc
    if manifest["integrationStatus"] not in VALID_INTEGRATION_STATUSES:
        fail("invalid integrationStatus")
    deployed = manifest["deployedComponents"]
    if not isinstance(deployed, list) or len(set(deployed)) != len(deployed):
        fail("deployedComponents must be a unique array")
    if any(item not in {"frontend", "backend", "ai", "iot", "infra"} for item in deployed):
        fail("deployedComponents contains an unknown component")
    for name in APPLICATION_COMPONENTS:
        validate_application_component(name, manifest[name])
    for name in EDGE_COMPONENTS:
        validate_edge_component(name, manifest[name])
    infra = manifest["infra"]
    if not isinstance(infra, dict) or set(infra) != {"commit", "pipelineId", "jobId"}:
        fail("infra must contain commit, pipelineId and jobId")
    validate_commit(infra["commit"], "infra.commit")
    optional_string(infra["pipelineId"], "infra.pipelineId", 64)
    optional_string(infra["jobId"], "infra.jobId", 64)
    if not isinstance(manifest["mqttSchema"], int) or manifest["mqttSchema"] < 1:
        fail("mqttSchema must be a positive integer")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o640)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def env_bool(values: dict[str, str], key: str) -> bool:
    raw = values.get(key, "false").lower()
    if raw not in {"true", "false"}:
        fail(f"{key} must be true or false")
    return raw == "true"


def component_from_env(values: dict[str, str], name: str) -> dict[str, Any]:
    prefix = name.upper()
    enabled = env_bool(values, f"{prefix}_ENABLED")
    component: dict[str, Any] = {
        "enabled": enabled,
        "image": values.get(f"{prefix}_IMAGE") if enabled else None,
        "commit": values.get(f"{prefix}_COMMIT") if enabled else None,
        "branch": values.get(f"{prefix}_BRANCH") or values.get("DEPLOY_BRANCH") or None,
    }
    if name == "backend":
        component["databaseSchema"] = values.get("DATABASE_SCHEMA") or None
    return component


def pending_edge() -> dict[str, Any]:
    return {"status": "pending", "version": None, "artifact": None, "checksum": None}


def create_manifest(args: argparse.Namespace) -> dict[str, Any]:
    values = parse_env(args.env)
    previous: dict[str, Any] | None = None
    if args.previous and args.previous.exists():
        previous = load_json(args.previous)
        validate_manifest(previous)
    released_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    release_id = args.release_id or (
        f"release-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        f"-{args.pipeline_id or 'local'}-{args.job_id or os.getpid()}"
    )
    deployed = [item for item in args.components.split(",") if item]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "releaseId": release_id,
        "releasedAt": released_at,
        "integrationStatus": args.integration_status,
        "deployedComponents": deployed,
        "frontend": component_from_env(values, "frontend"),
        "backend": component_from_env(values, "backend"),
        "ai": previous["ai"] if previous else pending_edge(),
        "iot": previous["iot"] if previous else pending_edge(),
        "infra": {
            "commit": args.infra_commit or None,
            "pipelineId": args.pipeline_id or None,
            "jobId": args.job_id or None,
        },
        "mqttSchema": previous["mqttSchema"] if previous else args.mqtt_schema,
    }
    validate_manifest(manifest)
    return manifest


def manifest_to_env(manifest: dict[str, Any]) -> str:
    validate_manifest(manifest)
    lines = [
        f"DEPLOY_BRANCH=release/{manifest['releaseId']}",
        f"DEPLOY_COMMIT={manifest['infra']['commit'] or ''}",
    ]
    for name in APPLICATION_COMPONENTS:
        component = manifest[name]
        prefix = name.upper()
        pairs = (
            (f"{prefix}_ENABLED", "true" if component["enabled"] else "false"),
            (f"{prefix}_IMAGE", component["image"] or ""),
            (f"{prefix}_COMMIT", component["commit"] or ""),
            (f"{prefix}_BRANCH", component["branch"] or ""),
        )
        for key, value in pairs:
            if not SAFE_VALUE_RE.fullmatch(value):
                fail(f"unsafe shell environment value in {key}")
            lines.append(f"{key}={value}")
    lines.extend(
        [
            f"DATABASE_SCHEMA={manifest['backend']['databaseSchema'] or ''}",
            "BACKEND_HEALTH_URL=http://127.0.0.1:8080/swagger-ui.html",
            "FRONTEND_HEALTH_URL=http://127.0.0.1:3000/",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate one manifest")
    validate.add_argument("manifest", type=Path)

    write = subparsers.add_parser("write", help="write the current and historical manifests")
    write.add_argument("--env", type=Path, required=True)
    write.add_argument("--output", type=Path, required=True)
    write.add_argument("--history-dir", type=Path, required=True)
    write.add_argument("--previous", type=Path)
    write.add_argument("--release-id")
    write.add_argument("--infra-commit", default=os.environ.get("CI_COMMIT_SHA", ""))
    write.add_argument("--pipeline-id", default=os.environ.get("CI_PIPELINE_ID", ""))
    write.add_argument("--job-id", default=os.environ.get("CI_JOB_ID", ""))
    write.add_argument("--components", default="")
    write.add_argument("--integration-status", choices=sorted(VALID_INTEGRATION_STATUSES), default="pending")
    write.add_argument("--mqtt-schema", type=int, default=1)

    export_env = subparsers.add_parser("export-env", help="render a manifest as current.env")
    export_env.add_argument("manifest", type=Path)
    export_env.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate":
            validate_manifest(load_json(args.manifest))
            print(f"release manifest is valid: {args.manifest}")
        elif args.command == "write":
            manifest = create_manifest(args)
            history_path = args.history_dir / f"{manifest['releaseId']}.json"
            if history_path.exists():
                fail(f"release already exists: {history_path}")
            atomic_write_json(args.output, manifest)
            atomic_write_json(history_path, manifest)
            print(manifest["releaseId"])
        elif args.command == "export-env":
            rendered = manifest_to_env(load_json(args.manifest))
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(prefix=f".{args.output.name}.", dir=args.output.parent)
                temporary_path = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                        stream.write(rendered)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.chmod(temporary_path, 0o640)
                    os.replace(temporary_path, args.output)
                finally:
                    temporary_path.unlink(missing_ok=True)
            else:
                sys.stdout.write(rendered)
        return 0
    except ManifestError as exc:
        print(f"release manifest error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
