#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional


def _load_candidates(tasks_dir: Path) -> Iterable[Dict[str, float]]:
    for path in sorted(tasks_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        modules = payload.get("modules", {})
        symbolic = modules.get("symbolic")
        if not symbolic:
            continue
        for candidate in symbolic.get("candidates", []):
            heuristics = candidate.get("metadata", {}).get("heuristics")
            if heuristics:
                yield heuristics


def summarise_components(dirs: List[Path]) -> Dict[str, Dict[str, float]]:
    series: Dict[str, List[float]] = defaultdict(list)
    for tasks_dir in dirs:
        for record in _load_candidates(tasks_dir):
            score = record.get("score")
            if score is not None:
                series["score"].append(float(score))
            for name, value in (record.get("components") or {}).items():
                try:
                    series[name].append(float(value))
                except (TypeError, ValueError):
                    continue
    summary: Dict[str, Dict[str, float]] = {}
    for name, values in series.items():
        if not values:
            continue
        summary[name] = {
            "count": len(values),
            "mean": mean(values),
            "min": min(values),
            "max": max(values),
        }
    return summary


def _format_row(name: str, stats: Dict[str, float]) -> str:
    return f"{name:15} {int(stats['count']):6d}  {stats['mean']:0.6f}  {stats['min']:0.6f}  {stats['max']:0.6f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare heuristic component weights across solver outputs.")
    parser.add_argument(
        "--tasks-dir",
        action="append",
        type=Path,
        required=True,
        help="Directory containing task JSON summaries (e.g. reports/eval_runs/smoke/<run>/tasks).",
    )
    args = parser.parse_args()
    dirs = [path.resolve() for path in args.tasks_dir]
    summary = summarise_components(dirs)
    if not summary:
        print("No heuristic metadata found under:", ", ".join(str(path) for path in dirs))
        return
    header = "Component       Count    Mean       Min        Max"
    print(header)
    print("-" * len(header))
    for name in sorted(summary):
        print(_format_row(name, summary[name]))


if __name__ == "__main__":
    main()
