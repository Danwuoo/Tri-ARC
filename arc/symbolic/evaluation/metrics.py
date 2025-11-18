"""Metrics collection system for symbolic synthesis evaluation."""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class EvaluationMetrics:
    """Comprehensive metrics for a single task evaluation."""
    
    task_id: str
    success: bool
    elapsed_s: float
    
    # Search metrics
    expansions: int = 0
    generated_nodes: int = 0
    pruned_nodes: int = 0
    verified_candidates: int = 0
    
    # Program metrics
    program_length: Optional[int] = None
    best_cost: Optional[float] = None
    
    # Enhancement metrics
    egraph_rewrites: int = 0
    hot_rule_applications: int = 0
    cold_rule_applications: int = 0
    rewrite_density: float = 0.0
    extraction_method: Optional[str] = None
    cache_hits: int = 0
    cache_misses: int = 0
    smt_calls: int = 0
    smt_timeouts: int = 0
    counterexamples_generated: int = 0
    fragments_mined: int = 0
    rules_learned: int = 0
    symmetries_detected: int = 0
    
    # Failure information
    failure_type: Optional[str] = None
    timeout: bool = False
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def compute_pruning_rate(self) -> float:
        """Compute pruning rate.
        
        Returns:
            Fraction of nodes pruned (0.0 to 1.0)
        """
        total = self.generated_nodes + self.pruned_nodes
        if total == 0:
            return 0.0
        return self.pruned_nodes / total
    
    def compute_cache_hit_rate(self) -> float:
        """Compute cache hit rate.
        
        Returns:
            Fraction of cache hits (0.0 to 1.0)
        """
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total
    
    def compute_smt_timeout_rate(self) -> float:
        """Compute SMT timeout rate.
        
        Returns:
            Fraction of SMT calls that timed out (0.0 to 1.0)
        """
        if self.smt_calls == 0:
            return 0.0
        return self.smt_timeouts / self.smt_calls
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluationMetrics:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class MetricsAggregator:
    """Aggregates metrics across multiple task evaluations."""
    
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    timeout_tasks: int = 0
    
    total_time_s: float = 0.0
    total_expansions: int = 0
    total_nodes: int = 0
    total_pruned: int = 0
    total_verified: int = 0
    
    total_egraph_rewrites: int = 0
    total_hot_rule_applications: int = 0
    total_cold_rule_applications: int = 0
    total_rewrite_density: float = 0.0
    total_cache_hits: int = 0
    total_cache_misses: int = 0
    total_smt_calls: int = 0
    total_smt_timeouts: int = 0
    
    task_metrics: List[EvaluationMetrics] = field(default_factory=list)
    failure_types: Dict[str, int] = field(default_factory=dict)
    extractor_usage: Dict[str, int] = field(default_factory=dict)
    
    def add_metrics(self, metrics: EvaluationMetrics) -> None:
        """Add metrics from a task evaluation.
        
        Args:
            metrics: Metrics to add
        """
        self.total_tasks += 1
        
        if metrics.success:
            self.successful_tasks += 1
        else:
            self.failed_tasks += 1
            if metrics.failure_type:
                self.failure_types[metrics.failure_type] = (
                    self.failure_types.get(metrics.failure_type, 0) + 1
                )
        
        if metrics.timeout:
            self.timeout_tasks += 1
        
        self.total_time_s += metrics.elapsed_s
        self.total_expansions += metrics.expansions
        self.total_nodes += metrics.generated_nodes
        self.total_pruned += metrics.pruned_nodes
        self.total_verified += metrics.verified_candidates
        
        self.total_egraph_rewrites += metrics.egraph_rewrites
        self.total_hot_rule_applications += metrics.hot_rule_applications
        self.total_cold_rule_applications += metrics.cold_rule_applications
        self.total_rewrite_density += metrics.rewrite_density
        self.total_cache_hits += metrics.cache_hits
        self.total_cache_misses += metrics.cache_misses
        self.total_smt_calls += metrics.smt_calls
        self.total_smt_timeouts += metrics.smt_timeouts
        if metrics.extraction_method:
            key = metrics.extraction_method.lower()
            self.extractor_usage[key] = self.extractor_usage.get(key, 0) + 1
        
        self.task_metrics.append(metrics)
    
    def compute_pruning_rate(self) -> float:
        """Compute overall pruning rate.
        
        Returns:
            Fraction of nodes pruned (0.0 to 1.0)
        """
        total = self.total_nodes + self.total_pruned
        if total == 0:
            return 0.0
        return self.total_pruned / total
    
    def compute_average_verified_candidates(self) -> float:
        """Compute average number of verified candidates per task.
        
        Returns:
            Average verified candidates
        """
        if self.total_tasks == 0:
            return 0.0
        return self.total_verified / self.total_tasks
    
    def compute_average_program_length(self) -> Optional[float]:
        """Compute average program length for successful tasks.
        
        Returns:
            Average program length or None if no successful tasks
        """
        lengths = [
            m.program_length
            for m in self.task_metrics
            if m.success and m.program_length is not None
        ]
        if not lengths:
            return None
        return statistics.mean(lengths)
    
    def compute_timeout_rate(self) -> float:
        """Compute timeout rate.
        
        Returns:
            Fraction of tasks that timed out (0.0 to 1.0)
        """
        if self.total_tasks == 0:
            return 0.0
        return self.timeout_tasks / self.total_tasks
    
    def compute_per_task_time(self) -> Dict[str, float]:
        """Compute per-task time statistics.
        
        Returns:
            Dictionary with mean, median, p95, max times
        """
        if not self.task_metrics:
            return {
                "mean": 0.0,
                "median": 0.0,
                "p95": 0.0,
                "max": 0.0,
                "min": 0.0,
            }
        
        times = [m.elapsed_s for m in self.task_metrics]
        sorted_times = sorted(times)
        
        p95_index = min(len(sorted_times) - 1, int(math.ceil(0.95 * len(sorted_times))) - 1)
        
        return {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "p95": sorted_times[p95_index],
            "max": max(times),
            "min": min(times),
        }
    
    def compute_success_rate(self) -> float:
        """Compute success rate.
        
        Returns:
            Fraction of successful tasks (0.0 to 1.0)
        """
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "timeout_tasks": self.timeout_tasks,
            "success_rate": self.compute_success_rate(),
            "pruning_rate": self.compute_pruning_rate(),
            "average_verified_candidates": self.compute_average_verified_candidates(),
            "average_program_length": self.compute_average_program_length(),
            "timeout_rate": self.compute_timeout_rate(),
            "per_task_time": self.compute_per_task_time(),
            "total_time_s": self.total_time_s,
            "total_expansions": self.total_expansions,
            "total_nodes": self.total_nodes,
            "total_pruned": self.total_pruned,
            "total_verified": self.total_verified,
            "total_egraph_rewrites": self.total_egraph_rewrites,
            "total_hot_rule_applications": self.total_hot_rule_applications,
            "total_cold_rule_applications": self.total_cold_rule_applications,
            "total_rewrite_density": self.total_rewrite_density,
            "total_cache_hits": self.total_cache_hits,
            "total_cache_misses": self.total_cache_misses,
            "total_smt_calls": self.total_smt_calls,
            "total_smt_timeouts": self.total_smt_timeouts,
            "failure_types": dict(self.failure_types),
            "extractor_usage": dict(self.extractor_usage),
        }
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"MetricsAggregator(tasks={self.total_tasks}, "
            f"success_rate={self.compute_success_rate():.2%}, "
            f"pruning_rate={self.compute_pruning_rate():.2%}, "
            f"timeout_rate={self.compute_timeout_rate():.2%})"
        )


def compute_pass_at_k(
    results: Sequence[bool],
    k: int = 2,
) -> float:
    """Compute pass@k metric.
    
    Args:
        results: Sequence of boolean results (True = success)
        k: Number of attempts per task
        
    Returns:
        Pass@k score (0.0 to 1.0)
    """
    if not results:
        return 0.0
    
    # For pass@k, we consider a task solved if at least one of k attempts succeeds
    # Since we typically have one result per task, we compute the success rate
    return sum(1 for r in results if r) / len(results)


def compute_pass_at_k_from_metrics(
    metrics_list: Sequence[EvaluationMetrics],
    k: int = 2,
) -> float:
    """Compute pass@k from evaluation metrics.
    
    Args:
        metrics_list: List of evaluation metrics
        k: Number of attempts per task
        
    Returns:
        Pass@k score (0.0 to 1.0)
    """
    results = [m.success for m in metrics_list]
    return compute_pass_at_k(results, k=k)


def compute_metrics_delta(
    current: MetricsAggregator,
    baseline: MetricsAggregator,
) -> Dict[str, Any]:
    """Compute delta between current and baseline metrics.
    
    Args:
        current: Current metrics
        baseline: Baseline metrics
        
    Returns:
        Dictionary of metric deltas
    """
    return {
        "success_rate_delta": current.compute_success_rate() - baseline.compute_success_rate(),
        "pruning_rate_delta": current.compute_pruning_rate() - baseline.compute_pruning_rate(),
        "timeout_rate_delta": current.compute_timeout_rate() - baseline.compute_timeout_rate(),
        "avg_verified_delta": (
            current.compute_average_verified_candidates() - 
            baseline.compute_average_verified_candidates()
        ),
        "avg_program_length_delta": (
            (current.compute_average_program_length() or 0.0) -
            (baseline.compute_average_program_length() or 0.0)
        ),
        "avg_time_delta": (
            current.compute_per_task_time()["mean"] -
            baseline.compute_per_task_time()["mean"]
        ),
        "tasks_delta": current.total_tasks - baseline.total_tasks,
        "successful_tasks_delta": current.successful_tasks - baseline.successful_tasks,
        "egraph_rewrites_delta": current.total_egraph_rewrites - baseline.total_egraph_rewrites,
        "hot_rule_applications_delta": current.total_hot_rule_applications - baseline.total_hot_rule_applications,
        "cold_rule_applications_delta": current.total_cold_rule_applications - baseline.total_cold_rule_applications,
    }
