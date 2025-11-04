#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def compute_file_checksum(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_directory_manifest(data_dir: Path) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for file_path in sorted(data_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel_path = file_path.relative_to(data_dir)
        checksum = compute_file_checksum(file_path)
        entries.append(
            {
                "path": str(rel_path).replace("\\", "/"),
                "size_bytes": file_path.stat().st_size,
                "sha256": checksum,
            }
        )
    return entries


def package_data(data_dir: Path, output_path: Path) -> None:
    import tarfile

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as archive:
        archive.add(data_dir, arcname=data_dir.name)


def write_manifest(manifest_path: Path, payload: Dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Package ARC datasets into an offline bundle.")
    parser.add_argument("--data-root", type=Path, default=Path("data/arcagi2"))
    parser.add_argument("--output", type=Path, default=Path("dist/data_bundle.tar.gz"))
    parser.add_argument("--manifest", type=Path, default=Path("dist/data_bundle_checksums.json"))
    args = parser.parse_args()

    if not args.data_root.exists():
        raise FileNotFoundError(f"Data root {args.data_root} not found")

    directory_manifest = collect_directory_manifest(args.data_root)

    package_data(args.data_root, args.output)

    bundle_checksum = compute_file_checksum(args.output)
    manifest_payload = {
        "bundle": {
            "path": str(args.output),
            "sha256": bundle_checksum,
        },
        "files": directory_manifest,
    }
    write_manifest(args.manifest, manifest_payload)
    print(json.dumps({"bundle": str(args.output), "manifest": str(args.manifest), "files_hashed": len(directory_manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
