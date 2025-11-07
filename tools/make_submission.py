#!/usr/bin/env python3
"""
Convert arbitrator outputs (outputs/pass2.json) into Kaggle submission format.

Each evaluation task must yield exactly two attempts per output grid.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Sequence


def _load_pass2(path: Path) -> Dict[str, List[List[List[List[int]]]]]:
    if not path.exists():
        raise FileNotFoundError(f"pass2 file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"pass2 payload must be an object, got {type(data).__name__}")
    return data


def _load_task_ids(args: argparse.Namespace) -> List[str]:
    if args.tasks_file:
        source = Path(args.tasks_file)
        if not source.exists():
            raise FileNotFoundError(f"tasks file not found: {source}")
        return [line.strip() for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]

    if args.tasks_dir:
        source = Path(args.tasks_dir)
    else:
        default_file = Path("data/arcagi2/evaluation.txt")
        if default_file.exists():
            return [line.strip() for line in default_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        source = Path("data/arcagi2/evaluation")

    if not source.exists():
        raise FileNotFoundError(f"tasks directory not found: {source}")
    return sorted(path.stem for path in source.glob("*.json"))


def _grid_or_blank(candidates: Sequence[Sequence], candidate_idx: int, output_idx: int) -> List[List[int]]:
    if candidate_idx < len(candidates):
        outputs = candidates[candidate_idx] or []
        if output_idx < len(outputs):
            grid = outputs[output_idx]
            if isinstance(grid, list) and grid:
                return grid
    return [[0]]


def _build_submission(
    pass2: Dict[str, List[List[List[List[int]]]]],
    task_ids: Sequence[str],
    allow_missing: bool,
) -> Dict[str, List[Dict[str, List[List[int]]]]]:
    submission: Dict[str, List[Dict[str, List[List[int]]]]] = {}
    missing: List[str] = []
    for task_id in task_ids:
        candidates = pass2.get(task_id)
        if not candidates:
            missing.append(task_id)
            continue
        num_outputs = max((len(candidate) for candidate in candidates if candidate), default=0)
        if num_outputs == 0:
            missing.append(task_id)
            continue
        rows: List[Dict[str, List[List[int]]]] = []
        for index in range(num_outputs):
            attempt_1 = _grid_or_blank(candidates, 0, index)
            attempt_2 = _grid_or_blank(candidates, 1, index)
            rows.append({"attempt_1": attempt_1, "attempt_2": attempt_2})
        submission[task_id] = rows

    if missing and not allow_missing:
        raise RuntimeError(
            f"Missing predictions for {len(missing)} task(s): "
            + ", ".join(sorted(missing)),
        )

    if missing and allow_missing:
        for task_id in missing:
            submission[task_id] = [{"attempt_1": [[0]], "attempt_2": [[0]]}]

    return submission


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Kaggle submission.json from pass2.json")
    parser.add_argument("--pass2", type=Path, default=Path("outputs/pass2.json"), help="Path to pass2.json")
    parser.add_argument(
        "--tasks-file",
        type=Path,
        help="Optional file containing task_ids (one per line). Defaults to data/arcagi2/evaluation.txt when present.",
    )
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        help="Optional directory containing task JSON files (used when --tasks-file is unset).",
    )
    parser.add_argument("--output", type=Path, default=Path("submission.json"), help="Destination submission.json path.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Fill missing task_ids with 1x1 zero grids instead of raising an error.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    pass2 = _load_pass2(args.pass2)
    task_ids = _load_task_ids(args)
    submission = _build_submission(pass2, task_ids, allow_missing=args.allow_missing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(submission, indent=2), encoding="utf-8")
    print(f"Wrote submission for {len(submission)} tasks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
