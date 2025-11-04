#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
from pathlib import Path


CHECKS = [
    ("python", ["python", "--version"]),
    ("pip", ["python", "-m", "pip", "--version"]),
    ("torch", ["python", "-c", "import torch; print(torch.__version__)"]),
    ("z3", ["z3", "--version"]),
    ("gpu", ["python", "scripts/check_gpu.py", "--json"]),
]


def run_command(label: str, command: list[str]) -> dict[str, str]:
    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True)
        status = "ok"
    except subprocess.CalledProcessError as exc:
        output = exc.output
        status = "error"
    return {"check": label, "command": " ".join(command), "status": status, "output": output.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Tri-ARC self-test harness.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "checks": [run_command(label, cmd) for label, cmd in CHECKS],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
