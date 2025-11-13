#!/usr/bin/env python3
"""Evaluation runner script for symbolic synthesis enhancements."""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from arc.symbolic.evaluation.baseline import BaselineConfig
from arc.symbolic.evaluation.dataset import DatasetSplit
from arc.symbolic.evaluation.runner import EvaluationConfig, EvaluationRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger("symbolic_evaluation")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run symbolic synthesis evaluation with enhancements"
    )
    
    # Basic configuration
    parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Unique identifier for this run",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/arcagi2"),
        help="Root directory of dataset",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/symbolic_evaluation"),
        help="Output directory for results",
    )
    
    # Dataset configuration
    parser.add_argument(
        "--split",
        type=str,
        choices=["train", "validation", "test", "full"],
        default="validation",
        help="Dataset split to evaluate",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to evaluate",
    )
    parser.add_argument(
        "--task-ids",
        type=str,
        nargs="+",
        default=None,
        help="Specific task IDs to evaluate",
    )
    
    # Baseline configuration
    parser.add_argument(
        "--baseline",
        type=str,
        choices=[
            "full_system",
            "no_pruning",
            "no_witness",
            "no_egraph",
            "no_cegis",
            "no_smt",
            "minimal",
        ],
        default="full_system",
        help="Baseline configuration to use",
    )
    parser.add_argument(
        "--run-ablations",
        action="store_true",
        help="Run all ablation studies",
    )
    
    # Execution configuration
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--timeout-per-task",
        type=float,
        default=150.0,
        help="Timeout per task in seconds",
    )
    
    # Output configuration
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        help="Don't save metrics",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Don't generate dashboard data",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Don't generate report",
    )
    
    args = parser.parse_args()
    
    # Create baseline config
    baseline_map = {
        "full_system": BaselineConfig.full_system,
        "no_pruning": BaselineConfig.no_pruning,
        "no_witness": BaselineConfig.no_witness,
        "no_egraph": BaselineConfig.no_egraph,
        "no_cegis": BaselineConfig.no_cegis,
        "no_smt": BaselineConfig.no_smt,
        "minimal": BaselineConfig.minimal,
    }
    baseline_config = baseline_map[args.baseline]()
    
    # Create evaluation config
    config = EvaluationConfig(
        run_id=args.run_id,
        dataset_root=args.dataset_root,
        output_dir=args.output_dir / args.run_id,
        split=DatasetSplit(args.split),
        max_tasks=args.max_tasks,
        task_ids=args.task_ids,
        baseline_config=baseline_config,
        run_ablations=args.run_ablations,
        seed=args.seed,
        timeout_per_task=args.timeout_per_task,
        save_metrics=not args.no_metrics,
        save_dashboard_data=not args.no_dashboard,
        generate_report=not args.no_report,
    )
    
    # Create runner
    runner = EvaluationRunner(config, logger=LOGGER)
    
    # Run evaluation
    if args.run_ablations:
        LOGGER.info("Running ablation studies")
        results = runner.run_ablations()
        
        LOGGER.info("\n=== Ablation Results ===")
        for name, result in results.items():
            LOGGER.info(
                f"{name}: "
                f"success_rate={result.metrics.compute_success_rate():.2%}, "
                f"pass@2={result.pass_at_2:.2%}"
            )
    else:
        LOGGER.info(f"Running evaluation with baseline: {args.baseline}")
        result = runner.run()
        
        LOGGER.info("\n=== Evaluation Results ===")
        LOGGER.info(f"Run ID: {result.run_id}")
        LOGGER.info(f"Tasks: {result.metrics.total_tasks}")
        LOGGER.info(f"Success Rate: {result.metrics.compute_success_rate():.2%}")
        LOGGER.info(f"Pruning Rate: {result.metrics.compute_pruning_rate():.2%}")
        LOGGER.info(f"Timeout Rate: {result.metrics.compute_timeout_rate():.2%}")
        LOGGER.info(f"Pass@2: {result.pass_at_2:.2%}")
        LOGGER.info(f"Elapsed: {result.elapsed_s:.2f}s")
        LOGGER.info(f"\nOutput directory: {config.output_dir}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
