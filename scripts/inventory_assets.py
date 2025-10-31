#!/usr/bin/env python3
"""
Inventory helper for offline assets (wheels, model weights, datasets).

Generates a structured summary that can be attached to environment readiness logs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
WHEEL_ROOT = ROOT_DIR / "vendor" / "wheels"
MODEL_ROOT = ROOT_DIR / "model"
DATA_ROOT = ROOT_DIR / "data"
ARC_DATA_ROOT = ROOT_DIR / "ARC-AGI-2-data"

try:
    from self_test import check_model_inventory, check_wheel_inventory, parse_requirements  # type: ignore
except ImportError:  # pragma: no cover - only if script relocated
    raise SystemExit("Importing helper functions from self_test.py failed.")


def bytes_to_human(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024 or unit == "TB":
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"


def wheel_stats() -> Dict[str, object]:
    if not WHEEL_ROOT.exists():
        return {"wheel_root": str(WHEEL_ROOT), "status": "missing"}

    wheels = sorted(WHEEL_ROOT.glob("*.whl"))
    total_size = sum(path.stat().st_size for path in wheels)
    return {
        "wheel_root": str(WHEEL_ROOT),
        "status": "present",
        "count": len(wheels),
        "size_bytes": total_size,
        "size_human": bytes_to_human(total_size),
        "files": [path.name for path in wheels],
    }


def model_stats() -> Dict[str, object]:
    if not MODEL_ROOT.exists():
        return {"model_root": str(MODEL_ROOT), "status": "missing"}
    files = sorted(MODEL_ROOT.glob("**/*"))
    total_size = sum(path.stat().st_size for path in files if path.is_file())
    return {
        "model_root": str(MODEL_ROOT),
        "status": "present",
        "count": len(files),
        "size_bytes": total_size,
        "size_human": bytes_to_human(total_size),
        "files": [str(path.relative_to(MODEL_ROOT)) for path in files if path.is_file()],
    }


def dataset_stats() -> Dict[str, object]:
    datasets: List[Tuple[str, Path]] = [
        ("arcagi2", DATA_ROOT / "arcagi2"),
        ("arc_forge", DATA_ROOT / "arc_forge"),
        ("kaggle_bundle", ARC_DATA_ROOT),
    ]
    entries = []
    for name, path in datasets:
        if not path.exists():
            entries.append({"name": name, "status": "missing", "path": str(path)})
            continue
        files = sorted(path.glob("**/*"))
        size = sum(p.stat().st_size for p in files if p.is_file())
        entries.append(
            {
                "name": name,
                "status": "present",
                "path": str(path),
                "count": len(files),
                "size_bytes": size,
                "size_human": bytes_to_human(size),
            }
        )
    return {"datasets": entries}


def generate_report() -> Dict[str, object]:
    requirements = parse_requirements(ROOT_DIR / "requirements.txt")
    wheel_check = check_wheel_inventory(requirements)
    model_check = check_model_inventory()
    report = {
        "wheel_inventory": wheel_check,
        "model_inventory": model_check,
        "wheel_stats": wheel_stats(),
        "model_stats": model_stats(),
        "dataset_stats": dataset_stats(),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate offline asset inventory.")
    parser.add_argument("--json", type=Path, help="Path to write JSON output.")
    args = parser.parse_args()

    report = generate_report()
    print(json.dumps(report, indent=2))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[inventory] JSON written to {args.json}")

    wheel_status = report["wheel_inventory"]["status"]
    model_status = report["model_inventory"]["status"]
    return 0 if wheel_status == "ok" and model_status in {"ok", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
