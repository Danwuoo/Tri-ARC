#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arc import data as arc_data
from arc import logging_utils
from arc.config import DEFAULT_CONFIG_PATH, load_config
from arc.core import ModuleRegistry


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
    parser.add_argument("--enable-modules", default=None, help="Comma-separated module names to force enable.")
    parser.add_argument("--disable-modules", default=None, help="Comma-separated module names to force disable.")
    parser.add_argument(
        "--mock-modules",
        default=None,
        help="Comma-separated module names to instantiate using their configured mock implementations.",
    )
    parser.add_argument(
        "--module-budget",
        action="append",
        default=[],
        metavar="NAME=SECONDS",
        help="Override module execution budgets (seconds). May be specified multiple times.",
    )
    return parser.parse_args()


def ensure_observability_dirs(log_root: Path) -> None:
    for sub in ("smt", "llm"):
        (log_root / sub).mkdir(parents=True, exist_ok=True)


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [token.strip() for token in value.split(",") if token.strip()]


def _collect_overrides(args: argparse.Namespace) -> Dict[str, Set[str]]:
    enable = set(_parse_csv(args.enable_modules))
    disable = set(_parse_csv(args.disable_modules))
    mocks = set(_parse_csv(args.mock_modules))

    env_enable = _parse_csv(os.environ.get("TRI_ARC_ENABLE_MODULES"))
    env_disable = _parse_csv(os.environ.get("TRI_ARC_DISABLE_MODULES"))
    env_mocks = _parse_csv(os.environ.get("TRI_ARC_MOCK_MODULES"))

    enable.update(env_enable)
    disable.update(env_disable)
    mocks.update(env_mocks)

    # Remove duplicates across enable/disable to avoid surprises.
    for name in list(enable):
        if name in disable:
            enable.discard(name)
    return {"enable": enable, "disable": disable, "mocks": mocks}


def _apply_budget_overrides(config: Dict[str, Any], overrides: Iterable[str], logger: Any) -> None:
    if not overrides:
        return
    modules_cfg = config.setdefault("modules", {})
    for item in overrides:
        if "=" not in item:
            logger.warning("Skipping invalid --module-budget override '%s' (expected name=value).", item)
            continue
        name, raw_value = item.split("=", 1)
        name = name.strip()
        raw_value = raw_value.strip()
        try:
            value = float(raw_value)
        except ValueError:
            logger.warning("Skipping module budget override for %s; '%s' is not numeric.", name, raw_value)
            continue
        module_entry = modules_cfg.setdefault(name, {})
        module_entry["budget_seconds"] = value


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
    module_overrides = _collect_overrides(args)
    _apply_budget_overrides(config, args.module_budget, logger)

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

    metrics_sink = lambda payload: logging_utils.append_metric(metrics_file, payload)
    registry = ModuleRegistry(
        config,
        run_id=f"eval-{now_iso}",
        shared_cache={},
        metrics_sink=metrics_sink,
        logger=logger.getChild("modules"),
        force_enable=module_overrides["enable"],
        force_disable=module_overrides["disable"],
        use_mocks=module_overrides["mocks"],
    )
    registry.bootstrap()

    round_trip_summary: Dict[str, Any] = {
        "timestamp": now_iso,
        "split": args.split,
        "task_id": "unknown",
        "max_tasks": args.max_tasks,
        "status": "success",
        "train_example_shapes": [],
        "eval_example_shapes": [],
        "modules": {},
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

        task_payload = {
            "task_id": sample_task.get("task_id", "sample_task"),
            "train_examples": [
                {"input": item.get("input"), "output": item.get("output")}
                for item in sample_task.get("train", [])
            ],
            "metadata": {"source_split": args.split},
        }

        for name, module in registry.active_modules().items():
            try:
                prepared = module.prepare_task(task_payload)
                result = module.solve(prepared)
                round_trip_summary["modules"][name] = {
                    "status": result.status.value,
                    "summary": result.summary,
                }
                metrics_sink(
                    {
                        "event": "module_result",
                        "module": name,
                        "status": result.status.value,
                        "task_id": result.task_id,
                        "timestamp": now_iso,
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Module %s failed sample solve: %s", name, exc)
                round_trip_summary["modules"][name] = {"status": "error", "error": repr(exc)}

    except Exception as exc:
        logger.exception("Failed ARC round-trip: %s", exc)
        round_trip_summary["status"] = "error"
        round_trip_summary["error"] = repr(exc)

    registry.shutdown()
    logging_utils.append_metric(metrics_file, round_trip_summary)
    logger.info("Tri-ARC evaluation complete with status=%s", round_trip_summary["status"])
    return 0 if round_trip_summary["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
