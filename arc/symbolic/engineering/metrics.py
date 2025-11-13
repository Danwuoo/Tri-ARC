"""Metrics collection for synthesis operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SynthesisMetrics:
    """Metrics for a synthesis operation."""
    
    task_id: str
    elapsed_s: float
    expansions: int
    generated_nodes: int
    pruned_nodes: int
    verified_candidates: int
    egraph_rewrites: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    smt_calls: int = 0
    smt_timeouts: int = 0
    counterexamples_generated: int = 0
    fragments_mined: int = 0
    rules_learned: int = 0
    symmetries_detected: int = 0
    success: bool = False
    program_length: Optional[int] = None
    best_cost: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SynthesisMetrics:
        """Create metrics from dictionary."""
        return cls(**data)
    
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
    
    def compute_nodes_per_second(self) -> float:
        """Compute node generation rate.
        
        Returns:
            Nodes generated per second
        """
        if self.elapsed_s == 0:
            return 0.0
        return self.generated_nodes / self.elapsed_s
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SynthesisMetrics(task={self.task_id}, "
            f"success={self.success}, "
            f"time={self.elapsed_s:.2f}s, "
            f"nodes={self.generated_nodes}, "
            f"pruned={self.pruned_nodes}, "
            f"verified={self.verified_candidates})"
        )


@dataclass
class AggregateMetrics:
    """Aggregate metrics across multiple synthesis operations."""
    
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_time_s: float = 0.0
    total_expansions: int = 0
    total_nodes: int = 0
    total_pruned: int = 0
    total_verified: int = 0
    total_egraph_rewrites: int = 0
    total_cache_hits: int = 0
    total_cache_misses: int = 0
    total_smt_calls: int = 0
    total_smt_timeouts: int = 0
    task_metrics: List[SynthesisMetrics] = field(default_factory=list)
    
    def add_metrics(self, metrics: SynthesisMetrics) -> None:
        """Add metrics from a synthesis operation.
        
        Args:
            metrics: Metrics to add
        """
        self.total_tasks += 1
        if metrics.success:
            self.successful_tasks += 1
        else:
            self.failed_tasks += 1
        
        self.total_time_s += metrics.elapsed_s
        self.total_expansions += metrics.expansions
        self.total_nodes += metrics.generated_nodes
        self.total_pruned += metrics.pruned_nodes
        self.total_verified += metrics.verified_candidates
        self.total_egraph_rewrites += metrics.egraph_rewrites
        self.total_cache_hits += metrics.cache_hits
        self.total_cache_misses += metrics.cache_misses
        self.total_smt_calls += metrics.smt_calls
        self.total_smt_timeouts += metrics.smt_timeouts
        
        self.task_metrics.append(metrics)
    
    def compute_success_rate(self) -> float:
        """Compute success rate.
        
        Returns:
            Fraction of successful tasks (0.0 to 1.0)
        """
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks
    
    def compute_avg_time(self) -> float:
        """Compute average time per task.
        
        Returns:
            Average time in seconds
        """
        if self.total_tasks == 0:
            return 0.0
        return self.total_time_s / self.total_tasks
    
    def compute_avg_expansions(self) -> float:
        """Compute average expansions per task.
        
        Returns:
            Average number of expansions
        """
        if self.total_tasks == 0:
            return 0.0
        return self.total_expansions / self.total_tasks
    
    def compute_avg_verified(self) -> float:
        """Compute average verified candidates per task.
        
        Returns:
            Average number of verified candidates
        """
        if self.total_tasks == 0:
            return 0.0
        return self.total_verified / self.total_tasks
    
    def compute_pruning_rate(self) -> float:
        """Compute overall pruning rate.
        
        Returns:
            Fraction of nodes pruned (0.0 to 1.0)
        """
        total = self.total_nodes + self.total_pruned
        if total == 0:
            return 0.0
        return self.total_pruned / total
    
    def compute_cache_hit_rate(self) -> float:
        """Compute overall cache hit rate.
        
        Returns:
            Fraction of cache hits (0.0 to 1.0)
        """
        total = self.total_cache_hits + self.total_cache_misses
        if total == 0:
            return 0.0
        return self.total_cache_hits / total
    
    def compute_smt_timeout_rate(self) -> float:
        """Compute overall SMT timeout rate.
        
        Returns:
            Fraction of SMT calls that timed out (0.0 to 1.0)
        """
        if self.total_smt_calls == 0:
            return 0.0
        return self.total_smt_timeouts / self.total_smt_calls
    
    def compute_avg_program_length(self) -> Optional[float]:
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
        return sum(lengths) / len(lengths)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert aggregate metrics to dictionary."""
        return {
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": self.compute_success_rate(),
            "avg_time_s": self.compute_avg_time(),
            "avg_expansions": self.compute_avg_expansions(),
            "avg_verified": self.compute_avg_verified(),
            "pruning_rate": self.compute_pruning_rate(),
            "cache_hit_rate": self.compute_cache_hit_rate(),
            "smt_timeout_rate": self.compute_smt_timeout_rate(),
            "avg_program_length": self.compute_avg_program_length(),
            "total_time_s": self.total_time_s,
            "total_expansions": self.total_expansions,
            "total_nodes": self.total_nodes,
            "total_pruned": self.total_pruned,
            "total_verified": self.total_verified,
            "total_egraph_rewrites": self.total_egraph_rewrites,
            "total_cache_hits": self.total_cache_hits,
            "total_cache_misses": self.total_cache_misses,
            "total_smt_calls": self.total_smt_calls,
            "total_smt_timeouts": self.total_smt_timeouts,
        }
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"AggregateMetrics(tasks={self.total_tasks}, "
            f"success_rate={self.compute_success_rate():.2%}, "
            f"avg_time={self.compute_avg_time():.2f}s, "
            f"pruning_rate={self.compute_pruning_rate():.2%})"
        )


class MetricsCollector:
    """Collects and aggregates synthesis metrics."""
    
    def __init__(self):
        self.aggregate = AggregateMetrics()
        self.current_metrics: Optional[SynthesisMetrics] = None
    
    def start_task(self, task_id: str) -> None:
        """Start collecting metrics for a task.
        
        Args:
            task_id: Task identifier
        """
        self.current_metrics = SynthesisMetrics(
            task_id=task_id,
            elapsed_s=0.0,
            expansions=0,
            generated_nodes=0,
            pruned_nodes=0,
            verified_candidates=0,
        )
    
    def finish_task(
        self,
        success: bool,
        elapsed_s: float,
        program_length: Optional[int] = None,
        best_cost: Optional[float] = None,
    ) -> SynthesisMetrics:
        """Finish collecting metrics for current task.
        
        Args:
            success: Whether task was successful
            elapsed_s: Total elapsed time
            program_length: Optional program length
            best_cost: Optional best cost
            
        Returns:
            Completed metrics
        """
        if self.current_metrics is None:
            raise ValueError("No task in progress")
        
        self.current_metrics.success = success
        self.current_metrics.elapsed_s = elapsed_s
        self.current_metrics.program_length = program_length
        self.current_metrics.best_cost = best_cost
        
        self.aggregate.add_metrics(self.current_metrics)
        
        completed = self.current_metrics
        self.current_metrics = None
        return completed
    
    def record_expansion(self, count: int = 1) -> None:
        """Record search expansions."""
        if self.current_metrics:
            self.current_metrics.expansions += count
    
    def record_node_generation(self, count: int = 1) -> None:
        """Record node generation."""
        if self.current_metrics:
            self.current_metrics.generated_nodes += count
    
    def record_node_pruning(self, count: int = 1) -> None:
        """Record node pruning."""
        if self.current_metrics:
            self.current_metrics.pruned_nodes += count
    
    def record_verification(self, count: int = 1) -> None:
        """Record candidate verification."""
        if self.current_metrics:
            self.current_metrics.verified_candidates += count
    
    def record_egraph_rewrite(self, count: int = 1) -> None:
        """Record e-graph rewrite."""
        if self.current_metrics:
            self.current_metrics.egraph_rewrites += count
    
    def record_cache_hit(self, count: int = 1) -> None:
        """Record cache hit."""
        if self.current_metrics:
            self.current_metrics.cache_hits += count
    
    def record_cache_miss(self, count: int = 1) -> None:
        """Record cache miss."""
        if self.current_metrics:
            self.current_metrics.cache_misses += count
    
    def record_smt_call(self, timed_out: bool = False) -> None:
        """Record SMT solver call."""
        if self.current_metrics:
            self.current_metrics.smt_calls += 1
            if timed_out:
                self.current_metrics.smt_timeouts += 1
    
    def get_aggregate(self) -> AggregateMetrics:
        """Get aggregate metrics."""
        return self.aggregate
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.aggregate = AggregateMetrics()
        self.current_metrics = None
