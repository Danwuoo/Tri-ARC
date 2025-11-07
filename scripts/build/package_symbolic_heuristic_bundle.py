#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def load_manifest(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sha256": path.read_text(encoding="utf-8").strip()}


def build_bundle(weights: Path, checksum: Path, output: Path, *, label: str) -> Path:
    weights = weights.resolve()
    checksum = checksum.resolve()
    if not weights.exists():
        raise FileNotFoundError(f"Weights file not found: {weights}")
    if not checksum.exists():
        raise FileNotFoundError(f"Checksum file not found: {checksum}")

    metadata = {
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "weights": weights.name,
        "checksum_manifest": checksum.name,
        "checksum": None,
    }
    manifest_payload = load_manifest(checksum)
    metadata["checksum"] = manifest_payload.get("sha256")
    metadata["payload"] = manifest_payload

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(weights, arcname=weights.name)
        archive.write(checksum, arcname=checksum.name)
        archive.writestr("manifest.json", json.dumps(metadata, indent=2) + os.linesep)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package symbolic heuristic weights into a portable bundle.")
    parser.add_argument("--weights", type=Path, default=Path("models/symbolic/heuristic.pt"), help="TorchScript weights path.")
    parser.add_argument("--checksum", type=Path, default=Path("models/symbolic/heuristic.sha256"), help="Checksum manifest path.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/heuristics/symbolic_heuristic_bundle.zip"),
        help="Destination zip archive path.",
    )
    parser.add_argument("--label", type=str, default="symbolic-heuristic", help="Bundle label recorded in manifest.json.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bundle = build_bundle(args.weights, args.checksum, args.output, label=args.label)
    print(f"[bundle] wrote {bundle} containing {args.weights.name} and {args.checksum.name}")


if __name__ == "__main__":
    main()
