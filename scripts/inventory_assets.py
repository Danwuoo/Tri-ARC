#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List


EXCLUDE_DIRS = {"vendor", "logs", "cache", ".venv", "dist"}


def gather_files(root: Path) -> List[Path]:
    files: List[Path] = []
    root = root.resolve()
    for current_dir, dirnames, filenames in os.walk(root):
        current_path = Path(current_dir)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in EXCLUDE_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            file_path = current_path / filename
            if any(part in EXCLUDE_DIRS for part in file_path.relative_to(root).parts):
                continue
            files.append(file_path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate offline asset inventory for Tri-ARC bundles.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    files = gather_files(args.root.resolve())

    inventory: List[Dict[str, Any]] = []
    for item in files:
        checksum = hashlib.sha256(item.read_bytes()).hexdigest()
        inventory.append(
            {
                "path": str(item.relative_to(args.root.resolve())),
                "size_bytes": item.stat().st_size,
                "sha256": checksum,
            }
        )

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"count": len(inventory), "output": str(args.json)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
