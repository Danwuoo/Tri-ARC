#!/usr/bin/env python3
"""
Stage 3 evaluation harness entrypoint for Tri-ARC.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tri_arc.data import ARCAGI2Dataset
from tri_arc.evaluation import EvaluationHarness, EvaluationSettings
from tri_arc.logging_utils import setup_logging


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Tri-ARC evaluation harness.")
    parser.add_argument("--split", default="evaluation", help="Dataset split to evaluate.")
    parser.add_argument("--limit", type=int, help="Optional cap on number of tasks.")
    parser.add_argument("--seed", type=int, help="Optional override for the evaluation seed.")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle tasks within the split deterministically.")
    parser.add_argument("--config", type=Path, default=ROOT_DIR / "docs" / "CONFIG_DEFAULTS.yaml", help="Path to YAML config.")
    parser.add_argument("--metrics-path", type=Path, help="Override metrics output path.")
    parser.add_argument("--pass2-path", type=Path, help="Override pass@2 JSON path.")
    parser.add_argument("--summary-path", type=Path, help="Override summary report path.")
    parser.add_argument("--smoke-sample", type=int, default=10, help="Number of tasks for the synthetic smoke split.")
    parser.add_argument("--max-hours", type=float, help="Budget hint for schedulers (unused in Stage 3).")
    return parser.parse_args()


def _resolve_path(candidate: Path) -> Path:
    return candidate if candidate.is_absolute() else ROOT_DIR / candidate


def _load_config(path: Path) -> Dict[str, Any]:
    config_path = _resolve_path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def main() -> int:
    args = _parse_args()
    config = _load_config(args.config)

    global_cfg = config.get("global", {})
    logging_cfg = config.get("logging", {})

    seed = args.seed if args.seed is not None else int(global_cfg.get("seed", 1337))

    data_root = _resolve_path(Path(global_cfg.get("data_root", "data/arcagi2")))
    log_root = _resolve_path(Path(global_cfg.get("log_root", "logs")))
    log_root.mkdir(parents=True, exist_ok=True)

    runtime_log = Path(logging_cfg.get("runtime_log", "runtime.log"))
    log_level = str(logging_cfg.get("level", "INFO"))
    logger = setup_logging(log_level, log_root / runtime_log)
    logger.info("Initialising evaluation harness (split=%s, seed=%s)", args.split, seed)

    dataset = ARCAGI2Dataset(data_root)

    metrics_path = _resolve_path(args.metrics_path or Path(logging_cfg.get("metrics_file", "metrics.jsonl")))
    pass2_path = _resolve_path(args.pass2_path or Path("outputs/pass2.json"))
    summary_path = _resolve_path(args.summary_path or Path("reports/eval_summary.md"))

    settings = EvaluationSettings(
        split=args.split,
        seed=seed,
        shuffle=args.shuffle,
        limit=args.limit,
        smoke_sample=args.smoke_sample,
        metrics_path=metrics_path,
        pass2_path=pass2_path,
        summary_path=summary_path,
    )

    harness = EvaluationHarness(dataset, settings)
    result = harness.run()

    logger.info(
        "Evaluation finished: tasks=%d pass@1=%d (%.2f%%) pass@2=%d (%.2f%%) duration=%.2fs",
        result.total_tasks,
        result.pass_at_1,
        result.pass_at_1_rate * 100,
        result.pass_at_2,
        result.pass_at_2_rate * 100,
        result.duration_s,
    )
    logger.info("Outputs written to %s", pass2_path)
    logger.info("Summary report available at %s", summary_path)
    logger.info("Metrics log written to %s", metrics_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
