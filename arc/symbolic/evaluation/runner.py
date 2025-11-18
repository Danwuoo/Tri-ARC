"""Evaluation runner for symbolic synthesis enhancements."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from arc.symbolic.evaluation.baseline import BaselineConfig, BaselineRunner, BaselineComparison
from arc.symbolic.evaluation.dashboard import DashboardDataGenerator
from arc.symbolic.evaluation.dataset import DatasetManager, DatasetSplit
from arc.symbolic.evaluation.metrics import (
    EvaluationMetrics,
    MetricsAggregator,
    compute_pass_at_k_from_metrics,
)

LOGGER = logging.getLogger("tri_arc.symbolic.evaluation")


def _resolve_override(overrides: Optional[Dict[str, Any]], dotted_key: str) -> Optional[Any]:
    """Resolve nested configuration overrides from either dotted or nested dicts."""
    if not overrides:
        return None
    if dotted_key in overrides:
        return overrides[dotted_key]
    target: Any = overrides
    for part in dotted_key.split("."):
        if isinstance(target, dict) and part in target:
            target = target[part]
        else:
            return None
    return target


@dataclass
class EvaluationConfig:
    """Configuration for evaluation run."""
    
    run_id: str
    dataset_root: Path
    output_dir: Path
    
    # Dataset configuration
    split: DatasetSplit = DatasetSplit.VALIDATION
    max_tasks: Optional[int] = None
    task_ids: Optional[List[str]] = None
    
    # Baseline configuration
    baseline_config: Optional[BaselineConfig] = None
    run_ablations: bool = False
    
    # Execution configuration
    seed: int = 1337
    timeout_per_task: float = 150.0
    
    # Output configuration
    save_metrics: bool = True
    save_dashboard_data: bool = True
    generate_report: bool = True
    
    # Additional config
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["split"] = self.split.value
        data["dataset_root"] = str(self.dataset_root)
        data["output_dir"] = str(self.output_dir)
        if self.baseline_config:
            data["baseline_config"] = self.baseline_config.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluationConfig:
        """Create from dictionary."""
        data = dict(data)
        data["split"] = DatasetSplit(data["split"])
        data["dataset_root"] = Path(data["dataset_root"])
        data["output_dir"] = Path(data["output_dir"])
        if "baseline_config" in data and data["baseline_config"]:
            data["baseline_config"] = BaselineConfig.from_dict(data["baseline_config"])
        return cls(**data)


@dataclass
class EvaluationResult:
    """Result of evaluation run."""
    
    run_id: str
    config: EvaluationConfig
    metrics: MetricsAggregator
    
    start_time: float
    end_time: float
    elapsed_s: float
    
    pass_at_2: float = 0.0
    
    output_files: Dict[str, Path] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "config": self.config.to_dict(),
            "metrics": self.metrics.to_dict(),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "elapsed_s": self.elapsed_s,
            "pass_at_2": self.pass_at_2,
            "output_files": {k: str(v) for k, v in self.output_files.items()},
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluationResult:
        """Create from dictionary."""
        data = dict(data)
        data["config"] = EvaluationConfig.from_dict(data["config"])
        # Reconstruct metrics aggregator
        metrics_data = data["metrics"]
        metrics = MetricsAggregator()
        metrics.total_tasks = metrics_data.get("total_tasks", 0)
        metrics.successful_tasks = metrics_data.get("successful_tasks", 0)
        metrics.failed_tasks = metrics_data.get("failed_tasks", 0)
        metrics.timeout_tasks = metrics_data.get("timeout_tasks", 0)
        metrics.total_time_s = metrics_data.get("total_time_s", 0.0)
        metrics.total_expansions = metrics_data.get("total_expansions", 0)
        metrics.total_nodes = metrics_data.get("total_nodes", 0)
        metrics.total_pruned = metrics_data.get("total_pruned", 0)
        metrics.total_verified = metrics_data.get("total_verified", 0)
        metrics.total_egraph_rewrites = metrics_data.get("total_egraph_rewrites", 0)
        metrics.total_hot_rule_applications = metrics_data.get("total_hot_rule_applications", 0)
        metrics.total_cold_rule_applications = metrics_data.get("total_cold_rule_applications", 0)
        metrics.total_rewrite_density = metrics_data.get("total_rewrite_density", 0.0)
        metrics.total_cache_hits = metrics_data.get("total_cache_hits", 0)
        metrics.total_cache_misses = metrics_data.get("total_cache_misses", 0)
        metrics.total_smt_calls = metrics_data.get("total_smt_calls", 0)
        metrics.total_smt_timeouts = metrics_data.get("total_smt_timeouts", 0)
        metrics.failure_types = metrics_data.get("failure_types", {})
        metrics.extractor_usage = metrics_data.get("extractor_usage", {})
        data["metrics"] = metrics
        data["output_files"] = {k: Path(v) for k, v in data.get("output_files", {}).items()}
        return cls(**data)


class EvaluationRunner:
    """Runs evaluation with enhancements and ablations."""
    
    def __init__(
        self,
        config: EvaluationConfig,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize evaluation runner.
        
        Args:
            config: Evaluation configuration
            logger: Optional logger
        """
        self.config = config
        self.logger = logger or LOGGER
        
        # Create output directory
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.dataset_manager = DatasetManager(
            dataset_root=config.dataset_root,
            seed=config.seed,
        )
        self.dashboard_generator = DashboardDataGenerator(
            output_dir=config.output_dir / "dashboard",
        )
        
        # Metrics aggregator
        self.metrics = MetricsAggregator()
        self.config_overrides = config.config_overrides or {}
        self.extractor_override = _resolve_override(self.config_overrides, "symbolic.egraph.extraction_method")
    
    def run(self) -> EvaluationResult:
        """Run evaluation.
        
        Returns:
            Evaluation result
        """
        self.logger.info(f"Starting evaluation run: {self.config.run_id}")
        start_time = time.time()
        
        # Get task list
        if self.config.task_ids:
            task_ids = self.config.task_ids
        else:
            task_ids = self.dataset_manager.get_task_ids(self.config.split)
            if self.config.max_tasks:
                task_ids = task_ids[:self.config.max_tasks]
        
        self.logger.info(f"Evaluating {len(task_ids)} tasks")
        
        # Run evaluation on tasks
        task_metrics = self._evaluate_tasks(task_ids)
        
        # Aggregate metrics
        for metrics in task_metrics:
            self.metrics.add_metrics(metrics)
        
        # Compute pass@k
        pass_at_2 = compute_pass_at_k_from_metrics(task_metrics, k=2)
        
        end_time = time.time()
        elapsed_s = end_time - start_time
        
        # Create result
        result = EvaluationResult(
            run_id=self.config.run_id,
            config=self.config,
            metrics=self.metrics,
            start_time=start_time,
            end_time=end_time,
            elapsed_s=elapsed_s,
            pass_at_2=pass_at_2,
        )
        
        # Save outputs
        if self.config.save_metrics:
            metrics_path = self._save_metrics(task_metrics)
            result.output_files["metrics"] = metrics_path
        
        if self.config.save_dashboard_data:
            dashboard_files = self._generate_dashboard_data(task_metrics)
            result.output_files.update(dashboard_files)
        
        if self.config.generate_report:
            report_path = self._generate_report(result)
            result.output_files["report"] = report_path
        
        # Save result
        result_path = self._save_result(result)
        result.output_files["result"] = result_path
        
        self.logger.info(f"Evaluation completed in {elapsed_s:.2f}s")
        self.logger.info(f"Success rate: {self.metrics.compute_success_rate():.2%}")
        self.logger.info(f"Pass@2: {pass_at_2:.2%}")
        
        return result
    
    def run_ablations(
        self,
        baselines: Optional[Sequence[BaselineConfig]] = None,
    ) -> Dict[str, EvaluationResult]:
        """Run ablation studies.
        
        Args:
            baselines: Optional list of baseline configurations
            
        Returns:
            Dictionary mapping baseline name to result
        """
        if baselines is None:
            baselines = [
                BaselineConfig.full_system(),
                BaselineConfig.no_pruning(),
                BaselineConfig.no_witness(),
                BaselineConfig.no_egraph(),
            ]
        
        results = {}
        
        for baseline in baselines:
            self.logger.info(f"Running ablation: {baseline.name}")
            
            # Create config for this baseline
            ablation_config = EvaluationConfig(
                run_id=f"{self.config.run_id}_{baseline.name}",
                dataset_root=self.config.dataset_root,
                output_dir=self.config.output_dir / baseline.name,
                split=self.config.split,
                max_tasks=self.config.max_tasks,
                task_ids=self.config.task_ids,
                baseline_config=baseline,
                seed=self.config.seed,
                timeout_per_task=self.config.timeout_per_task,
                save_metrics=True,
                save_dashboard_data=True,
                generate_report=True,
                config_overrides=dict(self.config.config_overrides),
            )
            
            # Run evaluation with this baseline
            runner = EvaluationRunner(ablation_config, logger=self.logger)
            result = runner.run()
            results[baseline.name] = result
        
        # Generate comparison report
        if len(results) > 1:
            self._generate_ablation_comparison(results)
        
        return results
    
    def _evaluate_tasks(
        self,
        task_ids: Sequence[str],
    ) -> List[EvaluationMetrics]:
        """Evaluate tasks.
        
        Args:
            task_ids: List of task IDs
            
        Returns:
            List of evaluation metrics
        """
        task_metrics = []
        
        for i, task_id in enumerate(task_ids):
            self.logger.info(f"Evaluating task {i+1}/{len(task_ids)}: {task_id}")
            
            # In a real implementation, this would call the symbolic solver
            # For now, create dummy metrics
            metrics = self._evaluate_single_task(task_id)
            task_metrics.append(metrics)
        
        return task_metrics
    
    def _evaluate_single_task(self, task_id: str) -> EvaluationMetrics:
        """Evaluate a single task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Evaluation metrics
        """
        # This is a placeholder implementation
        # In a real implementation, this would:
        # 1. Load the task
        # 2. Apply baseline configuration
        # 3. Run the symbolic solver
        # 4. Collect metrics
        
        # For now, return dummy metrics
        import random
        random.seed(hash(task_id) + self.config.seed)
        
        success = random.random() > 0.3
        elapsed_s = random.uniform(10.0, 100.0)
        rewrites = random.randint(10, 100)
        hot_apps = random.randint(0, rewrites)
        cold_apps = max(0, rewrites - hot_apps)
        iterations = random.randint(1, 10)
        rewrite_density = rewrites / max(1, iterations)
        extractor_method = (self.extractor_override or "astar")
        
        metrics = EvaluationMetrics(
            task_id=task_id,
            success=success,
            elapsed_s=elapsed_s,
            expansions=random.randint(100, 1000),
            generated_nodes=random.randint(500, 5000),
            pruned_nodes=random.randint(200, 2000),
            verified_candidates=random.randint(5, 50),
            program_length=random.randint(3, 15) if success else None,
            egraph_rewrites=rewrites,
            hot_rule_applications=hot_apps,
            cold_rule_applications=cold_apps,
            rewrite_density=rewrite_density,
            extraction_method=extractor_method,
            cache_hits=random.randint(50, 500),
            cache_misses=random.randint(10, 100),
            smt_calls=random.randint(5, 50),
            smt_timeouts=random.randint(0, 5),
            timeout=elapsed_s > self.config.timeout_per_task,
            failure_type="search_exhausted" if not success else None,
        )
        metrics.metadata["extraction_method"] = extractor_method
        
        return metrics
    
    def _save_metrics(
        self,
        task_metrics: Sequence[EvaluationMetrics],
    ) -> Path:
        """Save metrics to file.
        
        Args:
            task_metrics: List of task metrics
            
        Returns:
            Path to saved metrics
        """
        metrics_path = self.config.output_dir / "metrics.json"
        
        data = {
            "run_id": self.config.run_id,
            "aggregate": self.metrics.to_dict(),
            "tasks": [m.to_dict() for m in task_metrics],
        }
        
        with metrics_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        self.logger.info(f"Saved metrics to {metrics_path}")
        return metrics_path
    
    def _generate_dashboard_data(
        self,
        task_metrics: Sequence[EvaluationMetrics],
    ) -> Dict[str, Path]:
        """Generate dashboard data.
        
        Args:
            task_metrics: List of task metrics
            
        Returns:
            Dictionary of generated files
        """
        self.logger.info("Generating dashboard data")
        
        files = self.dashboard_generator.generate_all_dashboard_data(
            task_metrics,
            export_format="both",
        )
        
        # Flatten file list
        output_files = {}
        for data_type, paths in files.items():
            for i, path in enumerate(paths):
                key = f"dashboard_{data_type}_{i}"
                output_files[key] = path
        
        return output_files
    
    def _generate_report(self, result: EvaluationResult) -> Path:
        """Generate evaluation report.
        
        Args:
            result: Evaluation result
            
        Returns:
            Path to generated report
        """
        report_path = self.dashboard_generator.generate_summary_report(
            self.metrics,
            filename="evaluation_report.md",
        )
        
        self.logger.info(f"Generated report at {report_path}")
        return report_path
    
    def _save_result(self, result: EvaluationResult) -> Path:
        """Save evaluation result.
        
        Args:
            result: Evaluation result
            
        Returns:
            Path to saved result
        """
        result_path = self.config.output_dir / "result.json"
        
        with result_path.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
        
        return result_path
    
    def _generate_ablation_comparison(
        self,
        results: Dict[str, EvaluationResult],
    ) -> Path:
        """Generate ablation comparison report.
        
        Args:
            results: Dictionary of ablation results
            
        Returns:
            Path to comparison report
        """
        comparison_path = self.config.output_dir / "ablation_comparison.md"
        
        lines = [
            "# Ablation Study Comparison",
            "",
            "## Summary",
            "",
            "| Baseline | Success Rate | Pruning Rate | Timeout Rate | Avg Time (s) | Pass@2 |",
            "|----------|--------------|--------------|--------------|--------------|--------|",
        ]
        
        for name, result in sorted(results.items()):
            metrics = result.metrics
            per_task_time = metrics.compute_per_task_time()
            
            lines.append(
                f"| {name} | "
                f"{metrics.compute_success_rate():.2%} | "
                f"{metrics.compute_pruning_rate():.2%} | "
                f"{metrics.compute_timeout_rate():.2%} | "
                f"{per_task_time['mean']:.2f} | "
                f"{result.pass_at_2:.2%} |"
            )
        
        lines.extend(["", ""])
        
        # Add detailed sections for each baseline
        for name, result in sorted(results.items()):
            lines.extend([
                f"## {name}",
                "",
                f"- **Total Tasks**: {result.metrics.total_tasks}",
                f"- **Successful**: {result.metrics.successful_tasks}",
                f"- **Failed**: {result.metrics.failed_tasks}",
                f"- **Timeouts**: {result.metrics.timeout_tasks}",
                f"- **Pass@2**: {result.pass_at_2:.2%}",
                "",
            ])
        
        with comparison_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        self.logger.info(f"Generated ablation comparison at {comparison_path}")
        return comparison_path
