#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arc.symbolic.interpreter_adapter import InterpreterAdapter
from arc.symbolic.dsl.verify import VerificationSummary, verify_directory


def _format_benchmark(summary: VerificationSummary) -> str:
    lines = [
        "# DSL Benchmark Summary",
        "",
        f"- Date: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        f"- Total cases: {summary.total}",
        f"- Passed: {summary.passed}",
        f"- Failed: {summary.failed}",
        f"- Elapsed: {summary.elapsed_ms:.2f} ms",
        "",
        "## Case Results",
    ]
    for result in summary.results:
        status = "pass" if result.passed else "fail"
        lines.append(f"- `{result.case.name}` - {status} ({result.duration_ms:.2f} ms)")
        if not result.passed:
            lines.append(f"  - details: `{result.details}`")
    return "\n".join(lines) + "\n"


def _write_benchmark(summary: VerificationSummary, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_benchmark(summary), encoding="utf-8")
    return output_path


def run_cli() -> int:
    parser = argparse.ArgumentParser(description="Run DSL verification and micro-benchmarks.")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("fixtures/dsl/spec_examples"),
        help="Directory containing JSON fixtures.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs/verification"),
        help="Directory where verification logs will be stored.",
    )
    parser.add_argument(
        "--benchmark-report",
        type=Path,
        default=None,
        help="Optional markdown report path (e.g. reports/dsl_benchmarks_<date>.md).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case output; useful for scripting.",
    )
    args = parser.parse_args()

    adapter = InterpreterAdapter()
    summary = verify_directory(
        args.fixtures.resolve(),
        interpreter=adapter.interpreter,
        log_dir=args.log_dir.resolve() if args.log_dir else None,
    )

    if not args.quiet:
        print(
            f"[Tri-ARC] Verified {summary.total} cases — passed={summary.passed}, "
            f"failed={summary.failed}, elapsed={summary.elapsed_ms:.2f} ms"
        )
        for result in summary.results:
            status = "pass" if result.passed else "fail"
            print(f"  • {result.case.name}: {status} ({result.duration_ms:.2f} ms)")
            if not result.passed:
                print(f"    details: {result.details}")
    if summary.failed:
        return 1

    if args.benchmark_report:
        report_path = _write_benchmark(summary, args.benchmark_report.resolve())
        if not args.quiet:
            print(f"[Tri-ARC] Wrote benchmark report to {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
