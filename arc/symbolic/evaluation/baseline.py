"""Baseline comparison framework for ablation studies."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from arc.symbolic.evaluation.metrics import MetricsAggregator, compute_metrics_delta


@dataclass
class BaselineConfig:
    """Configuration for a baseline variant."""
    
    name: str
    description: str
    
    # Feature flags
    enable_pruning: bool = True
    enable_witness: bool = True
    enable_egraph: bool = True
    enable_cegis: bool = True
    enable_smt: bool = True
    enable_symmetry: bool = True
    enable_abstract_interpretation: bool = True
    enable_sketch_guided: bool = True
    enable_decomposition: bool = True
    
    # Additional config overrides
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaselineConfig:
        """Create from dictionary."""
        return cls(**data)
    
    @classmethod
    def full_system(cls) -> BaselineConfig:
        """Create full system configuration (all enhancements enabled)."""
        return cls(
            name="full_system",
            description="Full system with all enhancements enabled",
        )
    
    @classmethod
    def no_pruning(cls) -> BaselineConfig:
        """Create no-pruning baseline."""
        return cls(
            name="no_pruning",
            description="Baseline without pruning mechanisms",
            enable_pruning=False,
        )
    
    @classmethod
    def no_witness(cls) -> BaselineConfig:
        """Create no-witness baseline."""
        return cls(
            name="no_witness",
            description="Baseline without witness functions",
            enable_witness=False,
        )
    
    @classmethod
    def no_egraph(cls) -> BaselineConfig:
        """Create no-egraph baseline."""
        return cls(
            name="no_egraph",
            description="Baseline without e-graph optimization",
            enable_egraph=False,
        )
    
    @classmethod
    def no_cegis(cls) -> BaselineConfig:
        """Create no-CEGIS baseline."""
        return cls(
            name="no_cegis",
            description="Baseline without CEGIS loop",
            enable_cegis=False,
        )
    
    @classmethod
    def no_smt(cls) -> BaselineConfig:
        """Create no-SMT baseline."""
        return cls(
            name="no_smt",
            description="Baseline without SMT verification",
            enable_smt=False,
        )
    
    @classmethod
    def minimal(cls) -> BaselineConfig:
        """Create minimal baseline (all enhancements disabled)."""
        return cls(
            name="minimal",
            description="Minimal baseline with all enhancements disabled",
            enable_pruning=False,
            enable_witness=False,
            enable_egraph=False,
            enable_cegis=False,
            enable_smt=False,
            enable_symmetry=False,
            enable_abstract_interpretation=False,
            enable_sketch_guided=False,
            enable_decomposition=False,
        )
    
    def apply_to_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply baseline configuration to system config.
        
        Args:
            config: Base system configuration
            
        Returns:
            Modified configuration
        """
        config = dict(config)
        
        # Apply feature flags
        symbolic_config = config.setdefault("symbolic", {})
        enhancements = symbolic_config.setdefault("enhancements", {})
        
        enhancements["pruning"] = self.enable_pruning
        enhancements["witness_functions"] = self.enable_witness
        enhancements["egraph"] = self.enable_egraph
        enhancements["cegis"] = self.enable_cegis
        enhancements["smt"] = self.enable_smt
        enhancements["symmetry"] = self.enable_symmetry
        enhancements["abstract_interpretation"] = self.enable_abstract_interpretation
        enhancements["sketch_guided"] = self.enable_sketch_guided
        enhancements["decomposition"] = self.enable_decomposition
        
        # Apply additional overrides
        for key, value in self.config_overrides.items():
            keys = key.split(".")
            target = config
            for k in keys[:-1]:
                target = target.setdefault(k, {})
            target[keys[-1]] = value
        
        return config


@dataclass
class BaselineComparison:
    """Comparison between baseline and full system."""
    
    baseline_name: str
    baseline_metrics: MetricsAggregator
    full_system_metrics: MetricsAggregator
    delta: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Compute delta after initialization."""
        if not self.delta:
            self.delta = compute_metrics_delta(
                self.full_system_metrics,
                self.baseline_metrics,
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "baseline_name": self.baseline_name,
            "baseline_metrics": self.baseline_metrics.to_dict(),
            "full_system_metrics": self.full_system_metrics.to_dict(),
            "delta": self.delta,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaselineComparison:
        """Create from dictionary."""
        return cls(
            baseline_name=data["baseline_name"],
            baseline_metrics=MetricsAggregator(**data["baseline_metrics"]),
            full_system_metrics=MetricsAggregator(**data["full_system_metrics"]),
            delta=data.get("delta", {}),
        )
    
    def format_report(self) -> str:
        """Format comparison as markdown report.
        
        Returns:
            Markdown formatted report
        """
        lines = [
            f"# Baseline Comparison: {self.baseline_name}",
            "",
            "## Summary",
            "",
            f"- **Success Rate Delta**: {self.delta['success_rate_delta']:+.2%}",
            f"- **Pruning Rate Delta**: {self.delta['pruning_rate_delta']:+.2%}",
            f"- **Timeout Rate Delta**: {self.delta['timeout_rate_delta']:+.2%}",
            f"- **Avg Verified Candidates Delta**: {self.delta['avg_verified_delta']:+.2f}",
            f"- **Avg Program Length Delta**: {self.delta['avg_program_length_delta']:+.2f}",
            f"- **Avg Time Delta**: {self.delta['avg_time_delta']:+.2f}s",
            "",
            "## Detailed Metrics",
            "",
            "### Baseline",
            "",
            f"- Tasks: {self.baseline_metrics.total_tasks}",
            f"- Success Rate: {self.baseline_metrics.compute_success_rate():.2%}",
            f"- Pruning Rate: {self.baseline_metrics.compute_pruning_rate():.2%}",
            f"- Timeout Rate: {self.baseline_metrics.compute_timeout_rate():.2%}",
            f"- Avg Verified: {self.baseline_metrics.compute_average_verified_candidates():.2f}",
            f"- Avg Program Length: {self.baseline_metrics.compute_average_program_length() or 0.0:.2f}",
            "",
            "### Full System",
            "",
            f"- Tasks: {self.full_system_metrics.total_tasks}",
            f"- Success Rate: {self.full_system_metrics.compute_success_rate():.2%}",
            f"- Pruning Rate: {self.full_system_metrics.compute_pruning_rate():.2%}",
            f"- Timeout Rate: {self.full_system_metrics.compute_timeout_rate():.2%}",
            f"- Avg Verified: {self.full_system_metrics.compute_average_verified_candidates():.2f}",
            f"- Avg Program Length: {self.full_system_metrics.compute_average_program_length() or 0.0:.2f}",
            "",
        ]
        
        return "\n".join(lines)


class BaselineRunner:
    """Runs baseline comparisons and ablation studies."""
    
    def __init__(
        self,
        output_dir: Path,
        baselines: Optional[Sequence[BaselineConfig]] = None,
    ):
        """Initialize baseline runner.
        
        Args:
            output_dir: Directory for output files
            baselines: List of baseline configurations (defaults to standard set)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if baselines is None:
            self.baselines = [
                BaselineConfig.full_system(),
                BaselineConfig.no_pruning(),
                BaselineConfig.no_witness(),
                BaselineConfig.no_egraph(),
                BaselineConfig.minimal(),
            ]
        else:
            self.baselines = list(baselines)
    
    def save_baseline_configs(self) -> Path:
        """Save baseline configurations to file.
        
        Returns:
            Path to saved configurations
        """
        config_path = self.output_dir / "baseline_configs.json"
        
        configs = {
            baseline.name: baseline.to_dict()
            for baseline in self.baselines
        }
        
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(configs, f, indent=2)
        
        return config_path
    
    def load_baseline_results(
        self,
        results_dir: Path,
    ) -> Dict[str, MetricsAggregator]:
        """Load baseline results from directory.
        
        Args:
            results_dir: Directory containing baseline results
            
        Returns:
            Dictionary mapping baseline name to metrics
        """
        results_dir = Path(results_dir)
        results = {}
        
        for baseline in self.baselines:
            result_file = results_dir / f"{baseline.name}_metrics.json"
            if result_file.exists():
                with result_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Reconstruct MetricsAggregator from saved data
                    aggregator = MetricsAggregator()
                    aggregator.total_tasks = data.get("total_tasks", 0)
                    aggregator.successful_tasks = data.get("successful_tasks", 0)
                    aggregator.failed_tasks = data.get("failed_tasks", 0)
                    aggregator.timeout_tasks = data.get("timeout_tasks", 0)
                    aggregator.total_time_s = data.get("total_time_s", 0.0)
                    aggregator.total_expansions = data.get("total_expansions", 0)
                    aggregator.total_nodes = data.get("total_nodes", 0)
                    aggregator.total_pruned = data.get("total_pruned", 0)
                    aggregator.total_verified = data.get("total_verified", 0)
                    aggregator.failure_types = data.get("failure_types", {})
                    results[baseline.name] = aggregator
        
        return results
    
    def compare_baselines(
        self,
        results: Dict[str, MetricsAggregator],
        full_system_name: str = "full_system",
    ) -> List[BaselineComparison]:
        """Compare baselines against full system.
        
        Args:
            results: Dictionary of baseline results
            full_system_name: Name of full system baseline
            
        Returns:
            List of baseline comparisons
        """
        if full_system_name not in results:
            raise ValueError(f"Full system baseline '{full_system_name}' not found in results")
        
        full_system = results[full_system_name]
        comparisons = []
        
        for name, metrics in results.items():
            if name == full_system_name:
                continue
            
            comparison = BaselineComparison(
                baseline_name=name,
                baseline_metrics=metrics,
                full_system_metrics=full_system,
            )
            comparisons.append(comparison)
        
        return comparisons
    
    def save_comparisons(
        self,
        comparisons: Sequence[BaselineComparison],
    ) -> Path:
        """Save baseline comparisons to file.
        
        Args:
            comparisons: List of comparisons
            
        Returns:
            Path to saved comparisons
        """
        comparison_path = self.output_dir / "baseline_comparisons.json"
        
        data = {
            comp.baseline_name: comp.to_dict()
            for comp in comparisons
        }
        
        with comparison_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        return comparison_path
    
    def generate_comparison_report(
        self,
        comparisons: Sequence[BaselineComparison],
    ) -> Path:
        """Generate markdown comparison report.
        
        Args:
            comparisons: List of comparisons
            
        Returns:
            Path to generated report
        """
        report_path = self.output_dir / "baseline_comparison_report.md"
        
        lines = [
            "# Baseline Comparison Report",
            "",
            "## Overview",
            "",
            "This report compares various baseline configurations against the full system.",
            "",
        ]
        
        for comparison in comparisons:
            lines.extend([
                "---",
                "",
                comparison.format_report(),
                "",
            ])
        
        with report_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        return report_path
    
    def create_comparison_script(self) -> Path:
        """Create shell script for running baseline comparisons.
        
        Returns:
            Path to created script
        """
        script_path = self.output_dir / "run_baseline_comparison.sh"
        
        lines = [
            "#!/bin/bash",
            "# Baseline comparison script",
            "# Generated automatically",
            "",
            "set -e",
            "",
            "RESULTS_DIR=\"${1:-./baseline_results}\"",
            "mkdir -p \"$RESULTS_DIR\"",
            "",
        ]
        
        for baseline in self.baselines:
            lines.extend([
                f"echo \"Running baseline: {baseline.name}\"",
                f"python scripts/run_eval.py \\",
                f"  --preset {baseline.name} \\",
                f"  --split validation \\",
                f"  --run-id baseline_{baseline.name} \\",
                f"  --output \"$RESULTS_DIR/{baseline.name}_metrics.json\"",
                "",
            ])
        
        lines.extend([
            "echo \"All baselines completed\"",
            "echo \"Results saved to $RESULTS_DIR\"",
            "",
        ])
        
        with script_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        script_path.chmod(0o755)
        return script_path
