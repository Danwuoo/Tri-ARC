from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterable, List

import yaml

from .core import SmokeContext, SmokeResult


def _critical_imports() -> List[str]:
    # Keep aligned with docs/ENV_SETUP.md and requirements.txt highlights.
    return [
        "numpy",
        "torch",
        "torchvision",
        "networkx",
        "hydra",
        "hydra.core.config_store",
        "yaml",
        "z3",
    ]


def _import_module(module: str) -> None:
    components = module.split(".")
    __import__(components[0])
    parent = components[0]
    for comp in components[1:]:
        parent = f"{parent}.{comp}"
        __import__(parent)


def check_python_packages(_: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    missing: List[str] = []
    for module in _critical_imports():
        try:
            _import_module(module)
        except Exception as exc:  # pragma: no cover - environment dependent
            missing.append(f"{module}: {exc}")
    status = "pass" if not missing else "fail"
    details = {"checked": _critical_imports(), "missing": missing}
    return SmokeResult(
        name="python_package_imports",
        status=status,
        duration_s=time.perf_counter() - start,
        details=details,
        error=None if not missing else "Missing critical Python packages.",
    )


def check_cuda(_: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    details: dict = {}
    error = None
    status = "pass"
    try:
        import torch
    except Exception as exc:  # pragma: no cover - environment dependent
        status = "fail"
        error = f"PyTorch import failed: {exc}"
    else:
        if not torch.cuda.is_available():
            status = "fail"
            error = "CUDA not available via torch.cuda.is_available()."
        else:
            device_count = torch.cuda.device_count()
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
            details = {
                "torch_version": torch.__version__,
                "device_count": device_count,
                "devices": devices,
            }
    return SmokeResult(
        name="cuda_visibility",
        status=status,
        duration_s=time.perf_counter() - start,
        details=details,
        error=error,
    )


def check_nvidia_smi(_: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    smi = shutil.which("nvidia-smi")
    if not smi:
        return SmokeResult(
            name="nvidia_smi",
            status="warn",
            duration_s=time.perf_counter() - start,
            details={"available": False},
            error="`nvidia-smi` not available on PATH.",
        )
    try:
        result = subprocess.run(
            [smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - environment dependent
        return SmokeResult(
            name="nvidia_smi",
            status="warn",
            duration_s=time.perf_counter() - start,
            details={"returncode": exc.returncode, "stderr": exc.stderr},
            error="`nvidia-smi` command failed.",
        )
    gpus = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        name, memory, driver = [part.strip() for part in line.split(",")]
        gpus.append({"name": name, "memory": memory, "driver": driver})
    return SmokeResult(
        name="nvidia_smi",
        status="pass",
        duration_s=time.perf_counter() - start,
        details={"available": True, "gpus": gpus},
        error=None,
    )


def check_z3(_: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    try:
        import z3
    except Exception as exc:  # pragma: no cover - environment dependent
        return SmokeResult(
            name="z3_solver",
            status="fail",
            duration_s=time.perf_counter() - start,
            details={},
            error=f"Z3 import failed: {exc}",
        )
    solver = z3.Solver()
    x = z3.Int("x")
    solver.add(x + 2 == 5)
    status = solver.check()
    if status != z3.sat:
        return SmokeResult(
            name="z3_solver",
            status="fail",
            duration_s=time.perf_counter() - start,
            details={"status": str(status)},
            error=f"Unexpected solver status: {status}",
        )
    model = solver.model()
    details = {"model": str(model), "variable": model[x].as_long()}
    return SmokeResult(
        name="z3_solver",
        status="pass",
        duration_s=time.perf_counter() - start,
        details=details,
        error=None,
    )


def check_config_load(context: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    path = context.config_path
    if not path.exists():
        return SmokeResult(
            name="config_defaults",
            status="fail",
            duration_s=time.perf_counter() - start,
            details={"config_path": str(path)},
            error="docs/CONFIG_DEFAULTS.yaml not found.",
        )
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    data_root = config.get("global", {}).get("data_root")
    cache_root = config.get("global", {}).get("cache_root")
    return SmokeResult(
        name="config_defaults",
        status="pass",
        duration_s=time.perf_counter() - start,
        details={"data_root": data_root, "cache_root": cache_root},
        error=None,
    )


def check_dataset(context: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    data_root = context.data_root
    if not data_root.exists():
        return SmokeResult(
            name="dataset_presence",
            status="fail",
            duration_s=time.perf_counter() - start,
            details={"data_root": str(data_root)},
            error="Dataset root missing.",
        )
    training_dir = data_root / "training"
    evaluation_dir = data_root / "evaluation"
    samples = []
    for candidate in (training_dir, evaluation_dir):
        if candidate.exists():
            entries = sorted(candidate.glob("*.json"))
            samples.append(
                {
                    "path": str(candidate),
                    "count": len(entries),
                    "example": str(entries[0]) if entries else None,
                }
            )
    status = "pass" if samples else "fail"
    error = None if samples else "No ARC dataset files found under training/ or evaluation/."
    return SmokeResult(
        name="dataset_presence",
        status=status,
        duration_s=time.perf_counter() - start,
        details={"data_root": str(data_root), "samples": samples},
        error=error,
    )


def check_reports(context: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    reports_dir = context.root_dir / "reports"
    if not reports_dir.exists():
        return SmokeResult(
            name="reports_inventory",
            status="warn",
            duration_s=time.perf_counter() - start,
            details={"reports_dir": str(reports_dir)},
            error="reports/ directory missing; Stage 1 artefacts unavailable.",
        )
    setup_reports = sorted(reports_dir.glob("setup_verification_*.md"))
    inventory_reports = sorted(reports_dir.glob("offline_inventory_*.json"))
    status = "pass" if setup_reports or inventory_reports else "warn"
    details = {
        "reports_dir": str(reports_dir),
        "setup_reports": [report.name for report in setup_reports][-5:],
        "inventory_reports": [report.name for report in inventory_reports][-5:],
    }
    error = None if status == "pass" else "Expected Stage 1 verification reports not found."
    return SmokeResult(
        name="reports_inventory",
        status=status,
        duration_s=time.perf_counter() - start,
        details=details,
        error=error,
    )


def check_wheel_cache(context: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    wheel_roots = context.wheel_roots
    entries = []
    for root in wheel_roots:
        wheels = sorted(root.glob("*.whl"))
        entries.append({"root": str(root), "count": len(wheels)})
    status = "pass" if entries and any(entry["count"] > 0 for entry in entries) else "warn"
    error = None if status == "pass" else "Wheel cache directories missing or empty."
    return SmokeResult(
        name="wheel_cache",
        status=status,
        duration_s=time.perf_counter() - start,
        details={"entries": entries},
        error=error,
    )


def check_logging_setup(context: SmokeContext) -> SmokeResult:
    start = time.perf_counter()
    from tri_arc.logging_utils import setup_logging

    logfile = context.log_dir / "smoke.log"
    logger = setup_logging("INFO", logfile, include_console=False)
    message = "Smoke validation logging probe."
    logger.info(message)
    if not logfile.exists():
        return SmokeResult(
            name="logging_setup",
            status="fail",
            duration_s=time.perf_counter() - start,
            details={"logfile": str(logfile)},
            error="Log file was not created.",
        )
    content = logfile.read_text(encoding="utf-8")
    matched = bool(re.search(re.escape(message), content))
    status = "pass" if matched else "warn"
    error = None if matched else "Log file created but expected message not found."
    return SmokeResult(
        name="logging_setup",
        status=status,
        duration_s=time.perf_counter() - start,
        details={"logfile": str(logfile), "size": os.path.getsize(logfile)},
        error=error,
    )


def default_smoke_tests() -> Iterable:
    return [
        check_python_packages,
        check_cuda,
        check_nvidia_smi,
        check_z3,
        check_config_load,
        check_dataset,
        check_wheel_cache,
        check_reports,
        check_logging_setup,
    ]
