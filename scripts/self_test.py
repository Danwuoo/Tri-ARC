#!/usr/bin/env python3
"""
Offline environment validation script for Tri-ARC.

The checks cover:
- Python version compatibility
- PyTorch + CUDA visibility
- Z3 solver availability
- Vendor wheel inventory completeness
- Model weight inventory
- Optional GPU diagnostics via nvidia-smi

Outputs a human-readable summary and, optionally, a Markdown report file.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"
WHEEL_ROOT = ROOT_DIR / "vendor" / "wheels"
MODEL_ROOT = ROOT_DIR / "model"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Tri-ARC environment self tests.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write a Markdown report summarising the checks.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to write the raw JSON payload for downstream automation.",
    )
    return parser.parse_args()


def check_python_version() -> Dict[str, object]:
    required = (3, 11)
    version_tuple = tuple(int(x) for x in sys.version.split()[0].split(".")[:2])
    ok = version_tuple >= required
    return {
        "name": "python",
        "status": "ok" if ok else "fail",
        "details": {
            "required": ">=3.11",
            "current": sys.version,
        },
        "message": "Python version OK" if ok else "Python >=3.11 required.",
    }


def check_torch_cuda() -> Dict[str, object]:
    try:
        import torch
    except Exception as exc:  # pragma: no cover - only triggered on missing torch
        return {
            "name": "torch",
            "status": "fail",
            "details": {"error": f"PyTorch import failed: {exc!r}"},
            "message": "PyTorch is not installed or incompatible.",
        }

    cuda_available = torch.cuda.is_available()
    device_count = torch.cuda.device_count() if cuda_available else 0
    devices = []
    for idx in range(device_count):
        props = torch.cuda.get_device_properties(idx)
        devices.append(
            {
                "id": idx,
                "name": props.name,
                "total_memory_GB": round(props.total_memory / 1024**3, 2),
                "compute_capability": f"{props.major}.{props.minor}",
            }
        )

    status = "ok" if cuda_available and device_count >= 1 else "warn"
    message = (
        f"{device_count} CUDA device(s) detected."
        if status == "ok"
        else "PyTorch installed but CUDA GPU not detected."
    )
    return {
        "name": "torch",
        "status": status,
        "details": {
            "version": torch.__version__,
            "cuda_available": cuda_available,
            "device_count": device_count,
            "devices": devices,
        },
        "message": message,
    }


def check_nvidia_smi() -> Dict[str, object]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {
            "name": "nvidia_smi",
            "status": "warn",
            "details": {"available": False},
            "message": "`nvidia-smi` not available on PATH.",
        }
    try:
        result = subprocess.run(
            [smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - runtime-specific
        return {
            "name": "nvidia_smi",
            "status": "fail",
            "details": {"returncode": exc.returncode, "stderr": exc.stderr},
            "message": "`nvidia-smi` command failed.",
        }

    gpus = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        name, memory, driver = [part.strip() for part in line.split(",")]
        gpus.append({"name": name, "memory": memory, "driver": driver})

    status = "ok" if gpus else "warn"
    message = "Found GPU(s) via nvidia-smi." if gpus else "nvidia-smi returned no devices."
    return {
        "name": "nvidia_smi",
        "status": status,
        "details": {"gpus": gpus},
        "message": message,
    }


def check_z3() -> Dict[str, object]:
    try:
        from z3 import Int, Solver
    except Exception as exc:  # pragma: no cover - only triggered on missing z3
        return {
            "name": "z3",
            "status": "fail",
            "details": {"error": f"Z3 import failed: {exc!r}"},
            "message": "Z3 solver missing.",
        }
    try:
        x, y = Int("x"), Int("y")
        solver = Solver()
        solver.add(x + y == 10, x > 0, y > 0)
        assert solver.check() == 1
        model = solver.model()
        witness = {"x": model[x].as_long(), "y": model[y].as_long()}
    except Exception as exc:  # pragma: no cover - runtime-specific
        return {
            "name": "z3",
            "status": "fail",
            "details": {"error": f"Z3 solver check failed: {exc!r}"},
            "message": "Z3 solver not functioning correctly.",
        }
    return {
        "name": "z3",
        "status": "ok",
        "details": {"witness": witness},
        "message": "Z3 import and basic solve succeeded.",
    }


def parse_requirements(file_path: Path) -> List[Tuple[str, Optional[str]]]:
    requirements: List[Tuple[str, Optional[str]]] = []
    if not file_path.exists():
        return requirements
    for raw in file_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            name, version = line.split("==", 1)
            requirements.append((name.strip(), version.strip()))
        else:
            requirements.append((line, None))
    return requirements


def normalize_pkg_name(name: str) -> str:
    return name.lower().replace("-", "_")


def check_wheel_inventory(requirements: Sequence[Tuple[str, Optional[str]]]) -> Dict[str, object]:
    if not WHEEL_ROOT.exists():
        return {
            "name": "wheel_inventory",
            "status": "warn",
            "details": {"missing_packages": [name for name, _ in requirements]},
            "message": "Wheel cache directory vendor/wheels not found.",
        }

    wheel_files = [path.name for path in WHEEL_ROOT.glob("*.whl")]
    available = {normalize_pkg_name(name.split("-")[0]): name for name in wheel_files}
    missing = []
    for name, version in requirements:
        package_key = normalize_pkg_name(name)
        candidates = [wf for wf in wheel_files if normalize_pkg_name(wf).startswith(package_key)]
        if not candidates:
            missing.append(f"{name}=={version}" if version else name)

    status = "ok" if not missing else "warn"
    return {
        "name": "wheel_inventory",
        "status": status,
        "details": {
            "wheel_root": str(WHEEL_ROOT),
            "total_wheels": len(wheel_files),
            "missing_packages": missing,
        },
        "message": "Wheel cache complete." if status == "ok" else "Wheel cache missing packages.",
    }


def check_model_inventory() -> Dict[str, object]:
    if not MODEL_ROOT.exists():
        return {
            "name": "model_inventory",
            "status": "warn",
            "details": {"message": "model/ directory not found."},
            "message": "Model weights directory missing.",
        }
    files = list(MODEL_ROOT.glob("**/*"))
    safetensors = [f for f in files if f.suffix == ".safetensors"]
    index = [f for f in files if f.name.endswith(".json")]
    status = "ok" if safetensors and index else "warn"
    return {
        "name": "model_inventory",
        "status": status,
        "details": {
            "safetensors": [f.name for f in safetensors],
            "index_files": [f.name for f in index],
            "total_files": len(files),
        },
        "message": "Model weights detected." if status == "ok" else "Model weights incomplete.",
    }


def summarize_checks(checks: Sequence[Dict[str, object]]) -> Dict[str, object]:
    higher = {"fail": 3, "warn": 2, "ok": 1}
    worst = max(checks, key=lambda c: higher.get(c["status"], 0))
    overall_status = worst["status"]
    return {
        "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
        "overall_status": overall_status,
        "checks": list(checks),
    }


def format_markdown(report: Dict[str, object]) -> str:
    lines = [
        "# Tri-ARC Environment Self-Test",
        "",
        f"- Timestamp: {report['timestamp']}",
        f"- Overall status: **{report['overall_status'].upper()}**",
        "",
        "## Checks",
    ]
    for check in report["checks"]:
        lines.append(f"### {check['name']}")
        lines.append(f"- Status: **{check['status'].upper()}**")
        lines.append(f"- Message: {check['message']}")
        if check.get("details"):
            lines.append("```json")
            lines.append(json.dumps(check["details"], indent=2, sort_keys=True))
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    requirements = parse_requirements(REQUIREMENTS_FILE)
    checks = [
        check_python_version(),
        check_torch_cuda(),
        check_nvidia_smi(),
        check_z3(),
        check_wheel_inventory(requirements),
        check_model_inventory(),
    ]
    report = summarize_checks(checks)

    print(f"[SELF-TEST] Overall status: {report['overall_status'].upper()}")
    for check in report["checks"]:
        print(f"- {check['name']}: {check['status']} ({check['message']})")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(format_markdown(report), encoding="utf-8")
        print(f"[SELF-TEST] Markdown report written to {args.output}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[SELF-TEST] JSON report written to {args.json}")

    return 0 if report["overall_status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
