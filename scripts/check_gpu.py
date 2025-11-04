#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GPUReport:
    cuda_available: bool
    cuda_version: Optional[str]
    torch_version: Optional[str]
    gpu_count: int
    devices: List[Dict[str, Any]]
    nvidia_smi: Optional[str]


def collect_nvidia_smi() -> Optional[str]:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        output = subprocess.check_output(["nvidia-smi"], text=True, stderr=subprocess.STDOUT)
        return output.strip()
    except subprocess.CalledProcessError:
        return None


def collect_devices() -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    try:
        import torch

        if torch.cuda.is_available():
            for idx in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(idx)
                devices.append(
                    {
                        "index": idx,
                        "name": props.name,
                        "total_memory_mb": props.total_memory // (1024 * 1024),
                        "multi_processor_count": props.multi_processor_count,
                    }
                )
    except Exception as exc:  # pragma: no cover
        devices.append({"error": f"torch inspection failed: {exc!r}"})
    return devices


def build_report() -> GPUReport:
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        cuda_version = torch.version.cuda
        torch_version = torch.__version__
        gpu_count = torch.cuda.device_count() if cuda_available else 0
    except Exception as exc:  # pragma: no cover
        cuda_available = False
        cuda_version = None
        torch_version = None
        gpu_count = 0
        return GPUReport(
            cuda_available=cuda_available,
            cuda_version=cuda_version,
            torch_version=torch_version,
            gpu_count=gpu_count,
            devices=[{"error": f"torch not available: {exc!r}"}],
            nvidia_smi=collect_nvidia_smi(),
        )

    return GPUReport(
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        torch_version=torch_version,
        gpu_count=gpu_count,
        devices=collect_devices(),
        nvidia_smi=collect_nvidia_smi(),
    )


def write_report(report: GPUReport, output: Optional[Path], json_mode: bool) -> None:
    if json_mode:
        payload = json.dumps(asdict(report), indent=2, sort_keys=True)
    else:
        lines = [
            "# GPU Compatibility Report",
            "",
            f"- CUDA available: {'yes' if report.cuda_available else 'no'}",
            f"- CUDA version: {report.cuda_version or 'unknown'}",
            f"- Torch version: {report.torch_version or 'unknown'}",
            f"- GPU count: {report.gpu_count}",
            "",
            "## Devices",
        ]
        if report.devices:
            for device in report.devices:
                if "error" in device:
                    lines.append(f"- error: {device['error']}")
                else:
                    lines.append(
                        f"- index {device['index']}: {device['name']} "
                        f"({device['total_memory_mb']} MiB, SMs={device['multi_processor_count']})"
                    )
        else:
            lines.append("- none detected")
        if report.nvidia_smi:
            lines.extend(["", "## nvidia-smi", "```", report.nvidia_smi, "```"])
        payload = "\n".join(lines) + "\n"

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate GPU availability for Tri-ARC.")
    parser.add_argument("--output", type=Path, help="Optional file path to write the report.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    report = build_report()
    write_report(report, args.output, args.json)
    if not report.cuda_available:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
