from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from arc.core import ModuleContext, ModuleTaskContext
from arc.config import load_config
from arc.symbolic import SymbolicModule


def iter_task_files(directory: Path) -> Iterable[Path]:
    for path in sorted(directory.glob("*.json")):
        if path.is_file():
            yield path


def load_task(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    train_examples = payload.get("train", [])
    task_id = path.stem
    return {
        "task_id": task_id,
        "train_examples": [{"input": item["input"], "output": item["output"]} for item in train_examples],
        "metadata": {"source": str(path.parent.name)},
    }


def run_benchmark(
    *,
    input_dir: Path,
    limit: Optional[int],
    config_path: Optional[Path],
    output_path: Optional[Path],
) -> Path:
    config = load_config(config_path)
    module = SymbolicModule(config=config)
    logger = logging.getLogger("arc.symbolic.bench")
    logger.setLevel(logging.INFO)
    shared_cache: Dict[str, Any] = {}
    run_id = f"symbolic-bench-{time.strftime('%Y%m%d-%H%M%S')}"
    context = ModuleContext(
        module_name=SymbolicModule.module_name,
        config=config,
        shared_cache=shared_cache,
        run_id=run_id,
        logger=logger,
        metrics_sink=None,
    )
    module.initialize(context)

    tasks = list(iter_task_files(input_dir))
    if limit is not None:
        tasks = tasks[:limit]
    if not tasks:
        raise RuntimeError(f"No JSON tasks found under {input_dir}")

    records: List[Dict[str, object]] = []
    success = 0
    total_elapsed = 0.0

    print(f"[bench] Running symbolic solver on {len(tasks)} tasks from {input_dir}...")

    for index, path in enumerate(tasks, start=1):
        task = load_task(path)
        start = time.perf_counter()
        prepared: ModuleTaskContext = module.prepare_task(task)
        result = module.solve(prepared)
        elapsed = time.perf_counter() - start
        total_elapsed += elapsed
        status = result.status.value
        if status == "success" and any(candidate["verification_passed"] for candidate in result.candidates):
            success += 1
        summary = result.summary
        record = {
            "task_id": task["task_id"],  # type: ignore[index]
            "status": status,
            "elapsed_s": summary.get("elapsed_s", elapsed),
            "expansions": summary.get("expansions", 0),
            "nodes": summary.get("nodes", 0),
            "solutions": summary.get("solutions", 0),
        }
        records.append(record)
        print(
            f"[bench] ({index}/{len(tasks)}) task={record['task_id']} "
            f"status={record['status']} elapsed={record['elapsed_s']:.2f}s "
            f"solutions={record['solutions']}"
        )

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = output_path or Path("reports") / f"symbolic_benchmark_{timestamp}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        handle.write("# Symbolic Solver Benchmark\n\n")
        handle.write(f"- Input directory: `{input_dir}`\n")
        handle.write(f"- Tasks run: {len(records)}\n")
        handle.write(f"- Successful solves: {success}\n")
        handle.write(f"- Average elapsed: {total_elapsed / len(records):.2f} s\n\n")
        handle.write("| Task | Status | Elapsed (s) | Expansions | Nodes | Solutions |\n")
        handle.write("|------|--------|-------------|------------|-------|-----------|\n")
        for record in records:
            handle.write(
                f"| {record['task_id']} | {record['status']} | {record['elapsed_s']:.2f} | "
                f"{record['expansions']} | {record['nodes']} | {record['solutions']} |\n"
        )

    print(f"[bench] Report written to {report_path}")
    module.shutdown()
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the symbolic solver over a directory of ARC tasks.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/arcagi2/train"), help="Directory containing ARC JSON tasks.")
    parser.add_argument("--limit", type=int, help="Limit the number of tasks to evaluate.")
    parser.add_argument("--config", type=Path, help="Path to configuration YAML (defaults to docs/CONFIG_DEFAULTS.yaml).")
    parser.add_argument("--output", type=Path, help="Destination path for the markdown report.")
    args = parser.parse_args()

    run_benchmark(
        input_dir=args.input_dir,
        limit=args.limit,
        config_path=args.config,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
