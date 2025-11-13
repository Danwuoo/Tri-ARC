"""Dashboard data generation for visualization."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from arc.symbolic.evaluation.metrics import EvaluationMetrics, MetricsAggregator


@dataclass
class TaskCurveData:
    """Time-series data for a single task."""
    
    task_id: str
    timestamps: List[float] = field(default_factory=list)
    nodes_generated: List[int] = field(default_factory=list)
    candidates_verified: List[int] = field(default_factory=list)
    elapsed_time: List[float] = field(default_factory=list)
    
    def add_point(
        self,
        timestamp: float,
        nodes: int,
        candidates: int,
        elapsed: float,
    ) -> None:
        """Add a data point to the curve.
        
        Args:
            timestamp: Timestamp of measurement
            nodes: Cumulative nodes generated
            candidates: Cumulative candidates verified
            elapsed: Elapsed time
        """
        self.timestamps.append(timestamp)
        self.nodes_generated.append(nodes)
        self.candidates_verified.append(candidates)
        self.elapsed_time.append(elapsed)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskCurveData:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RuleHeatmapData:
    """Heatmap data for rule usage."""
    
    rule_ids: List[str] = field(default_factory=list)
    task_ids: List[str] = field(default_factory=list)
    hit_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    def record_hit(self, rule_id: str, task_id: str, count: int = 1) -> None:
        """Record a rule hit.
        
        Args:
            rule_id: Rule identifier
            task_id: Task identifier
            count: Number of hits
        """
        if rule_id not in self.rule_ids:
            self.rule_ids.append(rule_id)
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)
        
        self.hit_counts.setdefault(rule_id, {})[task_id] = (
            self.hit_counts.get(rule_id, {}).get(task_id, 0) + count
        )
    
    def get_matrix(self) -> List[List[int]]:
        """Get heatmap as 2D matrix.
        
        Returns:
            Matrix of hit counts (rules x tasks)
        """
        matrix = []
        for rule_id in self.rule_ids:
            row = []
            for task_id in self.task_ids:
                count = self.hit_counts.get(rule_id, {}).get(task_id, 0)
                row.append(count)
            matrix.append(row)
        return matrix
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_ids": self.rule_ids,
            "task_ids": self.task_ids,
            "hit_counts": self.hit_counts,
            "matrix": self.get_matrix(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RuleHeatmapData:
        """Create from dictionary."""
        return cls(
            rule_ids=data.get("rule_ids", []),
            task_ids=data.get("task_ids", []),
            hit_counts=data.get("hit_counts", {}),
        )


@dataclass
class FailureDistributionData:
    """Distribution of failure types."""
    
    failure_counts: Dict[str, int] = field(default_factory=dict)
    total_failures: int = 0
    
    def record_failure(self, failure_type: str, count: int = 1) -> None:
        """Record a failure.
        
        Args:
            failure_type: Type of failure
            count: Number of failures
        """
        self.failure_counts[failure_type] = (
            self.failure_counts.get(failure_type, 0) + count
        )
        self.total_failures += count
    
    def get_percentages(self) -> Dict[str, float]:
        """Get failure percentages.
        
        Returns:
            Dictionary mapping failure type to percentage
        """
        if self.total_failures == 0:
            return {}
        
        return {
            failure_type: (count / self.total_failures) * 100
            for failure_type, count in self.failure_counts.items()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "failure_counts": self.failure_counts,
            "total_failures": self.total_failures,
            "percentages": self.get_percentages(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FailureDistributionData:
        """Create from dictionary."""
        return cls(
            failure_counts=data.get("failure_counts", {}),
            total_failures=data.get("total_failures", 0),
        )


class DashboardDataGenerator:
    """Generates dashboard-friendly data from evaluation metrics."""
    
    def __init__(self, output_dir: Path):
        """Initialize dashboard data generator.
        
        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_task_curves(
        self,
        metrics_list: Sequence[EvaluationMetrics],
    ) -> Dict[str, TaskCurveData]:
        """Generate task-level curves.
        
        Args:
            metrics_list: List of evaluation metrics
            
        Returns:
            Dictionary mapping task ID to curve data
        """
        curves = {}
        
        for metrics in metrics_list:
            curve = TaskCurveData(task_id=metrics.task_id)
            
            # Create a simple curve from final metrics
            # In a real implementation, this would use time-series data
            curve.add_point(
                timestamp=0.0,
                nodes=0,
                candidates=0,
                elapsed=0.0,
            )
            curve.add_point(
                timestamp=metrics.elapsed_s,
                nodes=metrics.generated_nodes,
                candidates=metrics.verified_candidates,
                elapsed=metrics.elapsed_s,
            )
            
            curves[metrics.task_id] = curve
        
        return curves
    
    def generate_rule_heatmap(
        self,
        metrics_list: Sequence[EvaluationMetrics],
    ) -> RuleHeatmapData:
        """Generate rule hit heatmap.
        
        Args:
            metrics_list: List of evaluation metrics
            
        Returns:
            Rule heatmap data
        """
        heatmap = RuleHeatmapData()
        
        for metrics in metrics_list:
            # Extract rule hits from metadata
            rule_hits = metrics.metadata.get("rule_hits", {})
            for rule_id, count in rule_hits.items():
                heatmap.record_hit(rule_id, metrics.task_id, count)
        
        return heatmap
    
    def generate_failure_distribution(
        self,
        metrics_list: Sequence[EvaluationMetrics],
    ) -> FailureDistributionData:
        """Generate failure type distribution.
        
        Args:
            metrics_list: List of evaluation metrics
            
        Returns:
            Failure distribution data
        """
        distribution = FailureDistributionData()
        
        for metrics in metrics_list:
            if not metrics.success and metrics.failure_type:
                distribution.record_failure(metrics.failure_type)
        
        return distribution
    
    def export_task_curves_json(
        self,
        curves: Dict[str, TaskCurveData],
        filename: str = "task_curves.json",
    ) -> Path:
        """Export task curves to JSON.
        
        Args:
            curves: Dictionary of task curves
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        output_path = self.output_dir / filename
        
        data = {
            task_id: curve.to_dict()
            for task_id, curve in curves.items()
        }
        
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        return output_path
    
    def export_task_curves_csv(
        self,
        curves: Dict[str, TaskCurveData],
        filename: str = "task_curves.csv",
    ) -> Path:
        """Export task curves to CSV.
        
        Args:
            curves: Dictionary of task curves
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        output_path = self.output_dir / filename
        
        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "task_id",
                "timestamp",
                "nodes_generated",
                "candidates_verified",
                "elapsed_time",
            ])
            
            for task_id, curve in curves.items():
                for i in range(len(curve.timestamps)):
                    writer.writerow([
                        task_id,
                        curve.timestamps[i],
                        curve.nodes_generated[i],
                        curve.candidates_verified[i],
                        curve.elapsed_time[i],
                    ])
        
        return output_path
    
    def export_rule_heatmap_json(
        self,
        heatmap: RuleHeatmapData,
        filename: str = "rule_heatmap.json",
    ) -> Path:
        """Export rule heatmap to JSON.
        
        Args:
            heatmap: Rule heatmap data
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        output_path = self.output_dir / filename
        
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(heatmap.to_dict(), f, indent=2)
        
        return output_path
    
    def export_rule_heatmap_csv(
        self,
        heatmap: RuleHeatmapData,
        filename: str = "rule_heatmap.csv",
    ) -> Path:
        """Export rule heatmap to CSV.
        
        Args:
            heatmap: Rule heatmap data
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        output_path = self.output_dir / filename
        
        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            
            # Header row
            writer.writerow(["rule_id"] + heatmap.task_ids)
            
            # Data rows
            matrix = heatmap.get_matrix()
            for i, rule_id in enumerate(heatmap.rule_ids):
                writer.writerow([rule_id] + matrix[i])
        
        return output_path
    
    def export_failure_distribution_json(
        self,
        distribution: FailureDistributionData,
        filename: str = "failure_distribution.json",
    ) -> Path:
        """Export failure distribution to JSON.
        
        Args:
            distribution: Failure distribution data
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        output_path = self.output_dir / filename
        
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(distribution.to_dict(), f, indent=2)
        
        return output_path
    
    def export_failure_distribution_csv(
        self,
        distribution: FailureDistributionData,
        filename: str = "failure_distribution.csv",
    ) -> Path:
        """Export failure distribution to CSV.
        
        Args:
            distribution: Failure distribution data
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        output_path = self.output_dir / filename
        
        percentages = distribution.get_percentages()
        
        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["failure_type", "count", "percentage"])
            
            for failure_type, count in distribution.failure_counts.items():
                percentage = percentages.get(failure_type, 0.0)
                writer.writerow([failure_type, count, f"{percentage:.2f}"])
        
        return output_path
    
    def generate_all_dashboard_data(
        self,
        metrics_list: Sequence[EvaluationMetrics],
        export_format: str = "both",  # "json", "csv", or "both"
    ) -> Dict[str, List[Path]]:
        """Generate all dashboard data.
        
        Args:
            metrics_list: List of evaluation metrics
            export_format: Export format ("json", "csv", or "both")
            
        Returns:
            Dictionary mapping data type to list of exported file paths
        """
        exported_files = {
            "task_curves": [],
            "rule_heatmap": [],
            "failure_distribution": [],
        }
        
        # Generate task curves
        curves = self.generate_task_curves(metrics_list)
        if export_format in ("json", "both"):
            path = self.export_task_curves_json(curves)
            exported_files["task_curves"].append(path)
        if export_format in ("csv", "both"):
            path = self.export_task_curves_csv(curves)
            exported_files["task_curves"].append(path)
        
        # Generate rule heatmap
        heatmap = self.generate_rule_heatmap(metrics_list)
        if export_format in ("json", "both"):
            path = self.export_rule_heatmap_json(heatmap)
            exported_files["rule_heatmap"].append(path)
        if export_format in ("csv", "both"):
            path = self.export_rule_heatmap_csv(heatmap)
            exported_files["rule_heatmap"].append(path)
        
        # Generate failure distribution
        distribution = self.generate_failure_distribution(metrics_list)
        if export_format in ("json", "both"):
            path = self.export_failure_distribution_json(distribution)
            exported_files["failure_distribution"].append(path)
        if export_format in ("csv", "both"):
            path = self.export_failure_distribution_csv(distribution)
            exported_files["failure_distribution"].append(path)
        
        return exported_files
    
    def generate_summary_report(
        self,
        aggregator: MetricsAggregator,
        filename: str = "evaluation_summary.md",
    ) -> Path:
        """Generate markdown summary report.
        
        Args:
            aggregator: Metrics aggregator
            filename: Output filename
            
        Returns:
            Path to generated report
        """
        output_path = self.output_dir / filename
        
        per_task_time = aggregator.compute_per_task_time()
        
        lines = [
            "# Evaluation Summary",
            "",
            "## Overall Metrics",
            "",
            f"- **Total Tasks**: {aggregator.total_tasks}",
            f"- **Successful Tasks**: {aggregator.successful_tasks}",
            f"- **Failed Tasks**: {aggregator.failed_tasks}",
            f"- **Timeout Tasks**: {aggregator.timeout_tasks}",
            f"- **Success Rate**: {aggregator.compute_success_rate():.2%}",
            f"- **Timeout Rate**: {aggregator.compute_timeout_rate():.2%}",
            "",
            "## Performance Metrics",
            "",
            f"- **Pruning Rate**: {aggregator.compute_pruning_rate():.2%}",
            f"- **Avg Verified Candidates**: {aggregator.compute_average_verified_candidates():.2f}",
            f"- **Avg Program Length**: {aggregator.compute_average_program_length() or 0.0:.2f}",
            "",
            "## Time Metrics",
            "",
            f"- **Mean Time**: {per_task_time['mean']:.2f}s",
            f"- **Median Time**: {per_task_time['median']:.2f}s",
            f"- **P95 Time**: {per_task_time['p95']:.2f}s",
            f"- **Max Time**: {per_task_time['max']:.2f}s",
            f"- **Min Time**: {per_task_time['min']:.2f}s",
            "",
            "## Resource Usage",
            "",
            f"- **Total Nodes Generated**: {aggregator.total_nodes:,}",
            f"- **Total Nodes Pruned**: {aggregator.total_pruned:,}",
            f"- **Total Verified Candidates**: {aggregator.total_verified:,}",
            f"- **Total E-graph Rewrites**: {aggregator.total_egraph_rewrites:,}",
            f"- **Total SMT Calls**: {aggregator.total_smt_calls:,}",
            f"- **SMT Timeouts**: {aggregator.total_smt_timeouts:,}",
            "",
        ]
        
        if aggregator.failure_types:
            lines.extend([
                "## Failure Distribution",
                "",
            ])
            for failure_type, count in sorted(
                aggregator.failure_types.items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                percentage = (count / aggregator.failed_tasks) * 100 if aggregator.failed_tasks > 0 else 0.0
                lines.append(f"- **{failure_type}**: {count} ({percentage:.1f}%)")
            lines.append("")
        
        with output_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        return output_path
