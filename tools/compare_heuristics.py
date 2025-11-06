from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

sys.path.append(str(Path(__file__).resolve().parents[1]))

from arc.config import load_config
from arc.symbolic.solver import SymbolicSolver


def iter_task_files(directory: Path) -> Iterable[Path]:
    for path in sorted(directory.glob("*.json")):
        if path.is_file():
            yield path


def load_task(path: Path) -> Dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    train_examples = payload.get("train", []) or payload.get("train_examples", [])
    return {
        "task_id": path.stem,
        "train_examples": [{"input": item["input"], "output": item["output"]} for item in train_examples],
    }


@dataclass
class ModeResult:
    mode: str
    records: List[Dict[str, object]]

    @property
    def success_count(self) -> int:
        return sum(1 for record in self.records if record["status"] == "success")

    @property
    def average_elapsed(self) -> float:
        if not self.records:
            return 0.0
        return statistics.mean(record["elapsed_s"] for record in self.records)

    @property
    def tasks(self) -> int:
        return len(self.records)


def run_mode(
    *,
    mode_name: str,
    config_path: Optional[Path],
    config_overrides: Optional[Mapping[str, object]],
    task_paths: Iterable[Path],
) -> ModeResult:
    config = load_config(path=config_path, overrides=config_overrides)
    solver = SymbolicSolver(config=config)
    records: List[Dict[str, object]] = []
    for path in task_paths:
        task = load_task(path)
        start = time.perf_counter()
        result = solver.solve(task)
        elapsed = time.perf_counter() - start
        records.append(
            {
                "task_id": task["task_id"],  # type: ignore[index]
                "status": result.status,
                "elapsed_s": elapsed,
                "solutions": len([c for c in result.candidates if c.verification_passed]),
                "expansions": result.summary.get("expansions", 0),
                "nodes": result.summary.get("nodes", 0),
            }
        )
    solver.enumerator.shutdown()
    solver.heuristic.shutdown()
    return ModeResult(mode=mode_name, records=records)


def render_report(results: List[ModeResult], baseline: ModeResult, output_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = output_path or Path("reports") / f"heuristic_comparison_{timestamp}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("# Heuristic Comparison Report\n\n")
        handle.write(f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        handle.write(f"- Tasks evaluated: {baseline.tasks}\n")
        handle.write(f"- Baseline mode: `{baseline.mode}`\n\n")

        handle.write("| Mode | Successes | Avg Elapsed (s) | Delta Success | Delta Avg Elapsed |\n")
        handle.write("|------|-----------|-----------------|---------------|-------------------|\n")
        for result in results:
            delta_success = result.success_count - baseline.success_count
            delta_elapsed = result.average_elapsed - baseline.average_elapsed
            handle.write(
                f"| {result.mode} | {result.success_count} | {result.average_elapsed:.2f} | "
                f"{delta_success:+d} | {delta_elapsed:+.2f} |\n"
            )

        handle.write("\n## Per-task Details\n\n")
        handle.write("| Task | Mode | Status | Elapsed (s) | Solutions | Expansions | Nodes |\n")
        handle.write("|------|------|--------|-------------|-----------|------------|-------|\n")
        for result in results:
            for record in result.records:
                handle.write(
                    f"| {record['task_id']} | {result.mode} | {record['status']} | "
                    f"{record['elapsed_s']:.2f} | {record['solutions']} | {record['expansions']} | {record['nodes']} |\n"
                )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare symbolic solver heuristics across multiple modes.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/arcagi2/smoke"), help="Directory containing ARC JSON tasks.")
    parser.add_argument("--limit", type=int, help="Optional limit on the number of tasks to run.")
    parser.add_argument("--config", type=Path, help="Path to a custom config YAML.")
    parser.add_argument("--output", type=Path, help="Destination markdown report path.")
    parser.add_argument("--seed", type=int, default=1337, help="Override the symbolic solver seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_paths = list(iter_task_files(args.input_dir))
    if args.limit is not None:
        task_paths = task_paths[: args.limit]
    if not task_paths:
        raise RuntimeError(f"No ARC task JSON files found under {args.input_dir}")

    config_path = args.config

    mode_overrides: List[Tuple[str, Dict[str, object]]] = [
        ("blended", {"symbolic": {"seed": args.seed, "device": "cpu"}}),
        (
            "rule_only",
            {
                "symbolic": {
                    "seed": args.seed,
                    "device": "cpu",
                    "heuristics": {
                        "rule_based": {"enabled": True, "weight": 1.0},
                        "neural": {"enabled": False},
                    },
                }
            },
        ),
        (
            "neural_only",
            {
                "symbolic": {
                    "seed": args.seed,
                    "device": "cpu",
                    "heuristics": {
                        "rule_based": {"enabled": False},
                        "neural": {"enabled": True, "weight": 1.0},
                    },
                }
            },
        ),
    ]

    results: List[ModeResult] = []
    for mode_name, overrides in mode_overrides:
        result = run_mode(
            mode_name=mode_name,
            config_path=config_path,
            config_overrides=overrides,
            task_paths=task_paths,
        )
        results.append(result)

    baseline = results[0]
    output_path = render_report(results, baseline, args.output or Path())
    print(f"[compare] Report written to {output_path}")


if __name__ == "__main__":
    main()
