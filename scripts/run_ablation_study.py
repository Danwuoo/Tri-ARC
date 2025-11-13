"""Ablation study script for symbolic synthesis enhancements.

This script runs ablation studies to measure the impact of individual enhancements:
- No pruning (disable abstract interpretation and early pruning)
- No witness functions (disable SMT witness generation)
- No e-graph (disable e-graph compression and rewriting)
- No symmetry (disable symmetry detection and normalization)
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from arc.config import load_config
from arc.data import load_dataset
from arc.symbolic.solver import SymbolicSolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def create_ablation_configs(base_config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Create configuration variants for ablation study.
    
    Args:
        base_config: Base configuration
        
    Returns:
        Dictionary mapping ablation name to configuration
    """
    configs = {}
    
    # Baseline: all enhancements enabled
    baseline = dict(base_config)
    baseline["symbolic"]["egraph"] = {"enabled": True}
    baseline["symbolic"]["ir"] = {"enabled": True}
    baseline["symbolic"]["symmetry"] = {"enabled": True}
    baseline["symbolic"]["smt"] = {"enabled": False}  # Disabled for testing
    baseline["symbolic"]["advanced_search"] = {
        "enabled": True,
        "enable_abstract_interpretation": True,
    }
    configs["baseline"] = baseline
    
    # No e-graph
    no_egraph = dict(base_config)
    no_egraph["symbolic"]["egraph"] = {"enabled": False}
    no_egraph["symbolic"]["ir"] = {"enabled": True}
    no_egraph["symbolic"]["symmetry"] = {"enabled": True}
    no_egraph["symbolic"]["advanced_search"] = {
        "enabled": True,
        "enable_abstract_interpretation": True,
    }
    configs["no_egraph"] = no_egraph
    
    # No pruning (disable abstract interpretation)
    no_pruning = dict(base_config)
    no_pruning["symbolic"]["egraph"] = {"enabled": True}
    no_pruning["symbolic"]["ir"] = {"enabled": True}
    no_pruning["symbolic"]["symmetry"] = {"enabled": True}
    no_pruning["symbolic"]["advanced_search"] = {
        "enabled": True,
        "enable_abstract_interpretation": False,
    }
    configs["no_pruning"] = no_pruning
    
    # No witness functions (disable SMT)
    no_witness = dict(base_config)
    no_witness["symbolic"]["egraph"] = {"enabled": True}
    no_witness["symbolic"]["ir"] = {"enabled": True}
    no_witness["symbolic"]["symmetry"] = {"enabled": True}
    no_witness["symbolic"]["smt"] = {"enabled": False}
    no_witness["symbolic"]["advanced_search"] = {
        "enabled": True,
        "enable_abstract_interpretation": True,
    }
    configs["no_witness"] = no_witness
    
    # No symmetry
    no_symmetry = dict(base_config)
    no_symmetry["symbolic"]["egraph"] = {"enabled": True}
    no_symmetry["symbolic"]["ir"] = {"enabled": True}
    no_symmetry["symbolic"]["symmetry"] = {"enabled": False}
    no_symmetry["symbolic"]["advanced_search"] = {
        "enabled": True,
        "enable_abstract_interpretation": True,
    }
    configs["no_symmetry"] = no_symmetry
    
    # No IR layer
    no_ir = dict(base_config)
    no_ir["symbolic"]["egraph"] = {"enabled": True}
    no_ir["symbolic"]["ir"] = {"enabled": False}
    no_ir["symbolic"]["symmetry"] = {"enabled": True}
    no_ir["symbolic"]["advanced_search"] = {
        "enabled": True,
        "enable_abstract_interpretation": True,
    }
    configs["no_ir"] = no_ir
    
    # Minimal (all enhancements disabled)
    minimal = dict(base_config)
    minimal["symbolic"]["egraph"] = {"enabled": False}
    minimal["symbolic"]["ir"] = {"enabled": False}
    minimal["symbolic"]["symmetry"] = {"enabled": False}
    minimal["symbolic"]["smt"] = {"enabled": False}
    minimal["symbolic"]["advanced_search"] = {"enabled": False}
    configs["minimal"] = minimal
    
    return configs


def run_ablation_variant(
    variant_name: str,
    config: Dict[str, Any],
    dataset: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run a single ablation variant.
    
    Args:
        variant_name: Name of the ablation variant
        config: Configuration for this variant
        dataset: Dataset to test on
        
    Returns:
        Results dictionary
    """
    logger.info(f"Running ablation variant: {variant_name}")
    
    solver = SymbolicSolver(config)
    
    results = []
    start_time = time.time()
    
    for idx, task_data in enumerate(dataset):
        task_id = task_data.get("task_id", f"task_{idx}")
        
        try:
            result = solver.solve(task_data)
            
            task_result = {
                "task_id": task_id,
                "status": result.status,
                "elapsed_s": result.telemetry.elapsed_s,
                "expansions": result.telemetry.expansions,
                "generated_nodes": result.telemetry.generated_nodes,
                "candidates": len(result.candidates),
                "success": result.status == "success",
            }
            
            results.append(task_result)
            
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            results.append({
                "task_id": task_id,
                "status": "error",
                "error": str(e),
            })
    
    total_elapsed = time.time() - start_time
    
    # Compute statistics
    successful = [r for r in results if r.get("success", False)]
    solve_times = [r["elapsed_s"] for r in results if "elapsed_s" in r]
    expansions = [r["expansions"] for r in results if "expansions" in r]
    nodes = [r["generated_nodes"] for r in results if "generated_nodes" in r]
    
    summary = {
        "variant": variant_name,
        "total_tasks": len(dataset),
        "successful_tasks": len(successful),
        "success_rate": len(successful) / len(dataset) if dataset else 0,
        "total_elapsed_s": total_elapsed,
        "avg_solve_time_s": sum(solve_times) / len(solve_times) if solve_times else 0,
        "avg_expansions": sum(expansions) / len(expansions) if expansions else 0,
        "avg_nodes": sum(nodes) / len(nodes) if nodes else 0,
    }
    
    logger.info(f"Variant {variant_name} complete:")
    logger.info(f"  Success rate: {summary['success_rate']:.2%}")
    logger.info(f"  Avg solve time: {summary['avg_solve_time_s']:.2f}s")
    logger.info(f"  Avg expansions: {summary['avg_expansions']:.0f}")
    
    return {
        "summary": summary,
        "task_results": results,
    }


def compare_ablations(
    results: Dict[str, Dict[str, Any]],
    output_dir: Path,
) -> None:
    """Compare ablation results and generate report.
    
    Args:
        results: Dictionary mapping variant name to results
        output_dir: Output directory
    """
    logger.info("Generating ablation comparison report")
    
    # Extract summaries
    summaries = {name: res["summary"] for name, res in results.items()}
    
    # Get baseline
    baseline = summaries.get("baseline")
    if not baseline:
        logger.warning("No baseline results found")
        return
    
    # Compute deltas
    comparisons = []
    for name, summary in summaries.items():
        if name == "baseline":
            continue
        
        comparison = {
            "variant": name,
            "success_rate": summary["success_rate"],
            "success_rate_delta": summary["success_rate"] - baseline["success_rate"],
            "avg_solve_time_s": summary["avg_solve_time_s"],
            "solve_time_delta": summary["avg_solve_time_s"] - baseline["avg_solve_time_s"],
            "solve_time_speedup": baseline["avg_solve_time_s"] / summary["avg_solve_time_s"] if summary["avg_solve_time_s"] > 0 else 0,
            "avg_expansions": summary["avg_expansions"],
            "expansions_delta": summary["avg_expansions"] - baseline["avg_expansions"],
        }
        
        comparisons.append(comparison)
    
    # Sort by success rate delta
    comparisons.sort(key=lambda x: x["success_rate_delta"], reverse=True)
    
    # Generate markdown report
    report_lines = [
        "# Ablation Study Results",
        "",
        f"Baseline configuration: all enhancements enabled",
        f"- Success rate: {baseline['success_rate']:.2%}",
        f"- Avg solve time: {baseline['avg_solve_time_s']:.2f}s",
        f"- Avg expansions: {baseline['avg_expansions']:.0f}",
        "",
        "## Comparison",
        "",
        "| Variant | Success Rate | Delta | Avg Time (s) | Delta | Speedup | Avg Expansions | Delta |",
        "|---------|--------------|-------|--------------|-------|---------|----------------|-------|",
    ]
    
    for comp in comparisons:
        report_lines.append(
            f"| {comp['variant']} | "
            f"{comp['success_rate']:.2%} | "
            f"{comp['success_rate_delta']:+.2%} | "
            f"{comp['avg_solve_time_s']:.2f} | "
            f"{comp['solve_time_delta']:+.2f} | "
            f"{comp['solve_time_speedup']:.2f}x | "
            f"{comp['avg_expansions']:.0f} | "
            f"{comp['expansions_delta']:+.0f} |"
        )
    
    report_lines.extend([
        "",
        "## Findings",
        "",
    ])
    
    # Add findings
    best_variant = comparisons[0] if comparisons else None
    if best_variant and best_variant["success_rate_delta"] > 0:
        report_lines.append(
            f"- Removing **{best_variant['variant']}** had the least negative impact "
            f"(only {-best_variant['success_rate_delta']:.2%} drop in success rate)"
        )
    
    worst_variant = comparisons[-1] if comparisons else None
    if worst_variant and worst_variant["success_rate_delta"] < 0:
        report_lines.append(
            f"- Removing **{worst_variant['variant']}** had the most negative impact "
            f"({-worst_variant['success_rate_delta']:.2%} drop in success rate)"
        )
    
    # Find fastest variant
    fastest = min(comparisons, key=lambda x: x["avg_solve_time_s"]) if comparisons else None
    if fastest:
        report_lines.append(
            f"- **{fastest['variant']}** was fastest "
            f"({fastest['solve_time_speedup']:.2f}x speedup over baseline)"
        )
    
    # Save report
    report_path = output_dir / "ablation_comparison.md"
    report_path.write_text("\n".join(report_lines))
    logger.info(f"Comparison report saved to {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Run ablation studies")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to base config file"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="data/arcagi2/arc-agi_training_challenges.json",
        help="Path to dataset file"
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=20,
        help="Maximum number of tasks to test per variant"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/ablation",
        help="Output directory for results"
    )
    parser.add_argument(
        "--variants",
        type=str,
        nargs="+",
        default=None,
        help="Specific variants to run (default: all)"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load configuration
    if args.config:
        with open(args.config) as f:
            base_config = json.load(f)
    else:
        base_config = load_config()
    
    # Load dataset
    logger.info(f"Loading dataset from {args.dataset}")
    dataset = load_dataset(args.dataset)
    
    if args.max_tasks:
        dataset = dataset[:args.max_tasks]
    
    logger.info(f"Running ablation study on {len(dataset)} tasks")
    
    # Create ablation configs
    configs = create_ablation_configs(base_config)
    
    # Filter variants if specified
    if args.variants:
        configs = {k: v for k, v in configs.items() if k in args.variants}
    
    # Run ablations
    all_results = {}
    for variant_name, config in configs.items():
        result = run_ablation_variant(variant_name, config, dataset)
        all_results[variant_name] = result
        
        # Save individual result
        result_file = output_dir / f"ablation_{variant_name}.json"
        with result_file.open("w") as f:
            json.dump(result, f, indent=2)
    
    # Compare results
    compare_ablations(all_results, output_dir)
    
    # Save combined results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    combined_file = output_dir / f"ablation_study_{timestamp}.json"
    with combined_file.open("w") as f:
        json.dump(all_results, f, indent=2)
    
    logger.info(f"Ablation study complete. Results saved to {output_dir}")


if __name__ == "__main__":
    main()
