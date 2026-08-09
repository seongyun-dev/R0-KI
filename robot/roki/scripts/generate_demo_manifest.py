#!/usr/bin/env python3
"""Generate the non-secret identity values that bind a demo map and route."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROKI_ROOT = Path(__file__).resolve().parents[1]
if str(ROKI_ROOT) not in sys.path:
    sys.path.insert(0, str(ROKI_ROOT))

from navigation.map_metadata import file_sha256, load_map_metadata, map_bundle_sha256
from navigation.route import load_route


def build_manifest(map_path: str | Path, route_path: str | Path) -> dict[str, str]:
    metadata = load_map_metadata(map_path)
    route = load_route(route_path)
    return {
        "ROKI_MAP_ID": route.map_id,
        "ROKI_MAP_VERSION": str(route.map_version),
        "ROKI_MAP_SHA256": map_bundle_sha256(metadata),
        "ROKI_ROUTE_SHA256": file_sha256(route_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True, dest="map_path")
    parser.add_argument("--route", required=True, dest="route_path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    manifest = build_manifest(args.map_path, args.route_path)
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        for name, value in manifest.items():
            print(f"{name}={json.dumps(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
