"""Performance testing script for symbolic synthesis enhancements.

This script runs benchmarks on the ARC-AGI-2 training set and measures:
- Memory usage under load
- CPU and GPU utilization
- Solve time per task
- Throughput (tasks per hour)
"""

from __future__ import annotations

import argparse
import json
import logging
import psutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from arc.config import load_config
from arc.data import load_dataset
from arc.symbolic.solver import SymbolicSolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor system performance during testing."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.start_time = None
        self.measurements = []
    
    def start(self):
        """Start monitoring."""
        self.start_time = time.time()
        self.measurements = []
    
    def sample(self) -> Dict[str, Any]:
        """Take a performance sample."""
        sample = {
            "timestamp": time.time() - self.start_time,
            "cpu_percent": self.process.cpu_percent(),
            "memory_mb": self.process.memory_info().rss / (1024 * 1024),
            "memory_percent": self.process.memory_percent(),
        }
        
        if TORCH_AVAILABLE and torch.cuda.is_available():
            sample["gpu_memory_mb"] = torch.cuda.memory_allocated() / (1024 * 1024)
            sample["gpu_memory_reserved_mb"] = torch.cuda.memory_reserved() / (1024 * 1024)
        
        self.measurements.append(sample)
        return sample
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        if not self.measurements:
            return {}
        
        cpu_values = [m["cpu_percent"] for m in self.measurements]
        memory_values = [m["memory_mb"] for m in self.measurements]
        
        stats = {
            "cpu_percent_avg": sum(cpu_values) / len(cpu_values),
            "cpu_percent_max": max(cpu_values),
            "memory_mb_avg": sum(memory_values) / len(memory_values),
            "memory_mb_max": max(memory_values),
            "memory_mb_min": min(memory_values),
            "num_samples": len(self.measurements),
        }
        
        if TORCH_AVAILABLE and torch.cuda.is_available():
            gpu_mem_values = [m.get("gpu_memory_mb", 0) for m in self.measurements]
            stats["gpu_memory_mb_avg"] = sum(gpu_mem_values) / len(gpu_mem_values)
            stats["gpu_memory_mb_max"] = max(gpu_mem_values)
        
        return stats


def run_performance_test(
    config: Dict[str, Any],
    dataset_path: Path,
    max_tasks: Optional[int] = None,
    output_dir: Path = Path("reports/performance"),
) -> Dict[str, Any]:
    """Run performance test on dataset.
    
    Args:
        config: Configuration dictionary
        dataset_path: Path to dataset
        max_tasks: Maximum number of tasks to test (None for all)
        output_dir: Directory to save results
        
    Returns:
        Performance test results
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading dataset from {dataset_path}")
    dataset = load_dataset(str(dataset_path))
    
    if max_tasks:
        dataset = dataset[:max_tasks]
    
    logger.info(f"Running performance test on {len(dataset)} tasks")
    
    # Initialize solver
    solver = SymbolicSolver(config)
    
    # Initialize monitor
    monitor = PerformanceMonitor()
    monitor.start()
    
    # Run tests
    results = []
    start_time = time.time()
    
    for idx, task_data in enumerate(dataset):
        task_id = task_data.get("task_id", f"task_{idx}")
        logger.info(f"Testing task {idx + 1}/{len(dataset)}: {task_id}")
        
        # Sample before task
        monitor.sample()
        
        task_start = time.time()
        try:
            result = solver.solve(task_data)
            task_elapsed = time.time() - task_start
            
            task_result = {
                "task_id": task_id,
                "status": result.status,
                "elapsed_s": task_elapsed,
                "expansions": result.telemetry.expansions,
                "generated_nodes": result.telemetry.generated_nodes,
                "candidates": len(result.candidates),
                "success": result.status == "success",
            }
            
            results.append(task_result)
            logger.info(
                f"Task {task_id}: {result.status} in {task_elapsed:.2f}s "
                f"({result.telemetry.expansions} expansions, "
                f"{result.telemetry.generated_nodes} nodes)"
            )
            
        except Exception as e:
            logger.error(f"Task {task_id} failed with error: {e}")
            results.append({
                "task_id": task_id,
                "status": "error",
                "error": str(e),
                "elapsed_s": time.time() - task_start,
            })
        
        # Sample after task
        monitor.sample()
    
    total_elapsed = time.time() - start_time
    
    # Compute statistics
    successful_tasks = [r for r in results if r.get("success", False)]
    failed_tasks = [r for r in results if not r.get("success", False)]
    
    solve_times = [r["elapsed_s"] for r in results if "elapsed_s" in r]
    expansions = [r["expansions"] for r in results if "expansions" in r]
    nodes = [r["generated_nodes"] for r in results if "generated_nodes" in r]
    
    performance_stats = monitor.get_stats()
    
    summary = {
        "total_tasks": len(dataset),
        "successful_tasks": len(successful_tasks),
        "failed_tasks": len(failed_tasks),
        "success_rate": len(successful_tasks) / len(dataset) if dataset else 0,
        "total_elapsed_s": total_elapsed,
        "avg_solve_time_s": sum(solve_times) / len(solve_times) if solve_times else 0,
        "min_solve_time_s": min(solve_times) if solve_times else 0,
        "max_solve_time_s": max(solve_times) if solve_times else 0,
        "avg_expansions": sum(expansions) / len(expansions) if expansions else 0,
        "avg_nodes": sum(nodes) / len(nodes) if nodes else 0,
        "throughput_tasks_per_hour": len(dataset) / (total_elapsed / 3600) if total_elapsed > 0 else 0,
        "performance": performance_stats,
    }
    
    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results_file = output_dir / f"performance_test_{timestamp}.json"
    
    full_report = {
        "summary": summary,
        "task_results": results,
        "config": config,
    }
    
    with results_file.open("w") as f:
        json.dump(full_report, f, indent=2)
    
    logger.info(f"Performance test complete. Results saved to {results_file}")
    logger.info(f"Summary:")
    logger.info(f"  Total tasks: {summary['total_tasks']}")
    logger.info(f"  Successful: {summary['successful_tasks']}")
    logger.info(f"  Failed: {summary['failed_tasks']}")
    logger.info(f"  Success rate: {summary['success_rate']:.2%}")
    logger.info(f"  Avg solve time: {summary['avg_solve_time_s']:.2f}s")
    logger.info(f"  Throughput: {summary['throughput_tasks_per_hour']:.1f} tasks/hour")
    logger.info(f"  Avg CPU: {performance_stats.get('cpu_percent_avg', 0):.1f}%")
    logger.info(f"  Max memory: {performance_stats.get('memory_mb_max', 0):.1f} MB")
    
    if "gpu_memory_mb_max" in performance_stats:
        logger.info(f"  Max GPU memory: {performance_stats['gpu_memory_mb_max']:.1f} MB")
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run performance tests on symbolic solver")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: use default config)"
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
        default=None,
        help="Maximum number of tasks to test (default: all)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/performance",
        help="Output directory for results"
    )
    parser.add_argument(
        "--preset",
        type=str,
        choices=["minimal", "enhanced", "full"],
        default="minimal",
        help="Configuration preset to use"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    if args.config:
        with open(args.config) as f:
            config = json.load(f)
    else:
        config = load_config()
    
    # Apply preset
    if args.preset == "minimal":
        config["symbolic"]["egraph"] = {"enabled": False}
        config["symbolic"]["ir"] = {"enabled": False}
        config["symbolic"]["symmetry"] = {"enabled": False}
        config["symbolic"]["max_expansions"] = 1000
    elif args.preset == "enhanced":
        config["symbolic"]["egraph"] = {"enabled": True}
        config["symbolic"]["ir"] = {"enabled": True}
        config["symbolic"]["symmetry"] = {"enabled": True}
        config["symbolic"]["max_expansions"] = 5000
    elif args.preset == "full":
        config["symbolic"]["egraph"] = {"enabled": True}
        config["symbolic"]["ir"] = {"enabled": True}
        config["symbolic"]["symmetry"] = {"enabled": True}
        config["symbolic"]["cegis"] = {"enabled": True}
        config["symbolic"]["advanced_search"] = {"enabled": True}
        config["symbolic"]["library"] = {"enabled": True}
        config["symbolic"]["max_expansions"] = 10000
    
    # Run test
    run_performance_test(
        config=config,
        dataset_path=Path(args.dataset),
        max_tasks=args.max_tasks,
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
