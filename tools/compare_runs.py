#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Tuple

from arc.evaluation import calculate_deltas, collect_run_metrics

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two evaluation runs and emit a delta report.")
    parser.add_argument("run_a", type=Path, help="Path to baseline run directory or summary.json")
    parser.add_argument("run_b", type=Path, help="Path to candidate run directory or summary.json")
    parser.add_argument("--output", type=Path, help="Destination markdown report (defaults to reports/eval_compare_<timestamp>.md).")
    return parser.parse_args()


def load_run(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Path]:
    if path.is_dir():
        run_dir = path
        summary_path = run_dir / "summary.json"
    else:
        summary_path = path
        run_dir = summary_path.parent
    if not summary_path.exists():
        raise FileNotFoundError(f"Summary file not found at {summary_path}")
    with summary_path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    metrics = collect_run_metrics(run_dir / "tasks")
    return summary, metrics, run_dir


def build_entry(run_id: str, summary: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    completed = int(summary.get("tasks_completed", 0))
    failed = int(summary.get("tasks_failed", 0))
    total = max(1, completed + failed)
    pass_rate = completed / total if total else 0.0
    return {
        "run_id": run_id,
        "tasks_total": summary.get("tasks_total", total),
        "tasks_completed": completed,
        "tasks_failed": failed,
        "elapsed_s": summary.get("elapsed_s", 0.0),
        "fallback_count": metrics.get("fallback_count", 0),
        "latency_mean": metrics.get("arbitration_latency_ms", {}).get("mean", 0.0),
        "pass_rate": pass_rate,
        "module_stats": metrics.get("module_stats", {}),
        "commit": summary.get("run_state", {}).get("commit_hash", "unknown"),
    }


def format_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    formatted = dict(entry)
    module_stats = formatted.get("module_stats", {})
    formatted["module_stats"] = {
        name: {
            "success": value.get("success", 0),
            "attempts": value.get("attempts", 0),
            "success_rate": value.get("success_rate", 0.0),
            "avg_elapsed_s": value.get("avg_elapsed_s", 0.0),
        }
        for name, value in module_stats.items()
    }
    return formatted


def write_report(
    output_path: Path,
    *,
    run_a_id: str,
    run_b_id: str,
    entry_a: Dict[str, Any],
    entry_b: Dict[str, Any],
    deltas: Dict[str, Any],
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Evaluation Comparison ({run_b_id} vs {run_a_id})",
        "",
        "## Overview",
        "",
        f"- Baseline run: `{run_a_id}`",
        f"- Candidate run: `{run_b_id}`",
        f"- Pass rate change: {deltas['pass_rate']:+.2%}",
        f"- Completed tasks change: {deltas['tasks_completed']:+d}",
        f"- Failed tasks change: {deltas['tasks_failed']:+d}",
        f"- Fallback delta: {deltas['fallback_count']:+d}",
        f"- Mean latency delta: {deltas['latency_mean']:+.2f} ms",
        "",
        "## Run Metrics",
        "",
        "| Metric | Baseline | Candidate |",
        "|--------|----------|-----------|",
        f"| Pass rate | {entry_a['pass_rate']:.2%} | {entry_b['pass_rate']:.2%} |",
        f"| Tasks completed | {entry_a['tasks_completed']} | {entry_b['tasks_completed']} |",
        f"| Tasks failed | {entry_a['tasks_failed']} | {entry_b['tasks_failed']} |",
        f"| Fallback count | {entry_a.get('fallback_count', 0)} | {entry_b.get('fallback_count', 0)} |",
        f"| Mean latency (ms) | {entry_a.get('latency_mean', 0.0):.2f} | {entry_b.get('latency_mean', 0.0):.2f} |",
        f"| Elapsed seconds | {entry_a.get('elapsed_s', 0.0):.2f} | {entry_b.get('elapsed_s', 0.0):.2f} |",
        "",
        "## Module Success Delta",
        "",
        "| Module | Baseline Success Rate | Candidate Success Rate | Δ Success Rate |",
        "|--------|-----------------------|------------------------|----------------|",
    ]

    module_keys = sorted(set(entry_a["module_stats"].keys()) | set(entry_b["module_stats"].keys()))
    module_deltas = deltas["modules"]
    for module in module_keys:
        base_stats = entry_a["module_stats"].get(module, {})
        cand_stats = entry_b["module_stats"].get(module, {})
        lines.append(
            f"| {module} | {base_stats.get('success_rate', 0.0):.2%} | {cand_stats.get('success_rate', 0.0):.2%} | "
            f"{module_deltas.get(module, {}).get('success_rate_delta', 0.0):+.2%} |"
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    args = parse_args()
    summary_a, metrics_a, run_dir_a = load_run(args.run_a)
    summary_b, metrics_b, run_dir_b = load_run(args.run_b)
    run_a_id = Path(run_dir_a).name
    run_b_id = Path(run_dir_b).name
    entry_a = format_entry(build_entry(run_a_id, summary_a, metrics_a))
    entry_b = format_entry(build_entry(run_b_id, summary_b, metrics_b))
    deltas = calculate_deltas(entry_b, entry_a)

    if args.output:
        output_path = args.output
    else:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = REPORTS_DIR / f"eval_compare_{timestamp}.md"

    write_report(output_path, run_a_id=run_a_id, run_b_id=run_b_id, entry_a=entry_a, entry_b=entry_b, deltas=deltas)
    print(f"[compare] Report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

