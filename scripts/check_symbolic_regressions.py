from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


DEFAULT_TARGET = Path("tests/symbolic/test_regression.py")


def run_regressions(target: Path, extra_args: List[str]) -> int:
    if not target.exists():
        raise SystemExit(f"Regression target {target} does not exist.")

    forwarded: List[str] = list(extra_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    cmd = [sys.executable, "-m", "pytest", str(target), "-m", "symbolic_regression"]
    if forwarded:
        cmd.extend(forwarded)

    print(f"[symbolic] Running {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the symbolic regression gating suite under pytest.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--tests",
        type=Path,
        default=DEFAULT_TARGET,
        help="Override the regression test path.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to pytest (prefix with -- to stop parser processing).",
    )
    args = parser.parse_args()

    exit_code = run_regressions(args.tests, args.pytest_args)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
