#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arc import data as arc_data
from arc import logging_utils
from arc.config import DEFAULT_CONFIG_PATH, load_config


def set_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tri-ARC evaluation entrypoint.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to the config YAML.")
    parser.add_argument("--split", choices=["train", "evaluation", "smoke"], default="smoke")
    parser.add_argument("--max_tasks", type=int, default=1)
    parser.add_argument("--log-level", default=None, help="Override logging level (e.g., DEBUG).")
    parser.add_argument("--metrics-file", type=Path, default=None, help="Optional override for metrics file.")
    return parser.parse_args()


def ensure_observability_dirs(log_root: Path) -> None:
    for sub in ("smt", "llm"):
        (log_root / sub).mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    config = load_config(args.config)

    seed = int(config.get("global", {}).get("seed", 0))
    set_seed(seed)

    log_root = Path(config.get("global", {}).get("log_root", "logs"))
    ensure_observability_dirs(log_root)

    logging_cfg = config.get("logging", {})
    level = args.log_level or logging_cfg.get("level", "INFO")
    runtime_log_name = logging_cfg.get("runtime_log", "runtime.log")
    metrics_file = args.metrics_file or Path(logging_cfg.get("metrics_file", "metrics.jsonl"))
    if not metrics_file.is_absolute():
        metrics_file = log_root / metrics_file

    log_path = logging_utils.configure_logging(log_root, runtime_log_name, level=level)

    logger = __import__("logging").getLogger("tri_arc.run_eval")
    logger.info("Tri-ARC evaluation starting")
    logger.info("Runtime log: %s", log_path)
    logger.info("Metrics file: %s", metrics_file)
    logger.info("Device map: %s", json.dumps(config.get("global", {}).get("device_map", {})))

    data_root = Path(config.get("global", {}).get("data_root", "data/arcagi2"))

    sample_task = arc_data.load_sample_task(data_root)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    if sample_task is None:
        logger.warning("No ARC sample found under %s; skipping round-trip.", data_root)
        metrics_payload = {
            "timestamp": now_iso,
            "split": args.split,
            "status": "no_data",
        }
        logging_utils.append_metric(metrics_file, metrics_payload)
        return 0

    round_trip_summary: Dict[str, Any] = {
        "timestamp": now_iso,
        "split": args.split,
        "task_id": "unknown",
        "max_tasks": args.max_tasks,
        "status": "success",
        "train_example_shapes": [],
        "eval_example_shapes": [],
    }

    try:
        # ARC JSON has "train" and "test" keys.
        for example in sample_task.get("train", []):
            grid = example.get("input")
            if grid:
                round_trip_summary["train_example_shapes"].append([len(grid), len(grid[0])])
        for idx, example in enumerate(sample_task.get("test", [])):
            grid = example.get("input")
            if grid:
                round_trip_summary["eval_example_shapes"].append([len(grid), len(grid[0])])
                logger.info("Round-trip %d: mirrored input grid of shape %s", idx, round_trip_summary["eval_example_shapes"][-1])
    except Exception as exc:
        logger.exception("Failed ARC round-trip: %s", exc)
        round_trip_summary["status"] = "error"
        round_trip_summary["error"] = repr(exc)

    logging_utils.append_metric(metrics_file, round_trip_summary)
    logger.info("Tri-ARC evaluation complete with status=%s", round_trip_summary["status"])
    return 0 if round_trip_summary["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
