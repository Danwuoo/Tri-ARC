#!/usr/bin/env python3
"""
Standalone GPU diagnostic helper for Tri-ARC.

Prints PyTorch CUDA status and available devices, falling back to informative
messages when CUDA is not available.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys


def torch_report() -> dict:
    try:
        import torch
    except Exception as exc:  # pragma: no cover - triggered when torch missing
        return {"available": False, "error": f"PyTorch import failed: {exc!r}"}

    if not torch.cuda.is_available():
        return {
            "available": False,
            "error": "PyTorch CUDA not available. Check drivers / CUDA toolkit.",
            "version": torch.__version__,
        }

    devices = []
    for idx in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(idx)
        devices.append(
            {
                "id": idx,
                "name": props.name,
                "total_memory_GB": round(props.total_memory / 1024**3, 2),
                "compute_capability": f"{props.major}.{props.minor}",
            }
        )
    return {
        "available": True,
        "version": torch.__version__,
        "device_count": len(devices),
        "devices": devices,
    }


def nvidia_smi_report() -> dict:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"available": False, "error": "`nvidia-smi` not found in PATH."}
    try:
        result = subprocess.run(
            [smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        return {"available": False, "error": f"nvidia-smi failed: rc={exc.returncode}", "stderr": exc.stderr}

    gpus = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        name, memory, driver = [part.strip() for part in line.split(",")]
        gpus.append({"name": name, "memory": memory, "driver": driver})
    return {"available": True, "gpus": gpus}


def main() -> int:
    report = {
        "torch": torch_report(),
        "nvidia_smi": nvidia_smi_report(),
    }
    print(json.dumps(report, indent=2))

    if not report["torch"].get("available"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
