"""Tests for symbolic synthesis evaluation infrastructure."""

import json
import tempfile
from pathlib import Path

import pytest

from arc.symbolic.evaluation.baseline import (
    BaselineComparison,
    BaselineConfig,
    BaselineRunner,
)
from arc.symbolic.evaluation.dashboard import (
    DashboardDataGenerator,
    FailureDistributionData,
    RuleHeatmapData,
    TaskCurveData,
)
from arc.symbolic.evaluation.dataset import DatasetManager, DatasetSplit, TaskMetadata
from arc.symbolic.evaluation.metrics import (
    EvaluationMetrics,
    MetricsAggregator,
    compute_metrics_delta,
    compute_pass_at_k,
    compute_pass_at_k_from_metrics,
)
from arc.symbolic.evaluation.runner import EvaluationConfig, EvaluationRunner


class TestEvaluationMetrics:
    """Test evaluation metrics."""
    
    def test_metrics_creation(self):
        """Test creating evaluation metrics."""
        metrics = EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.5,
            expansions=100,
            generated_nodes=500,
            pruned_nodes=200,
            verified_candidates=10,
            program_length=5,
        )
        
        assert metrics.task_id == "test_001"
        assert metrics.success is True
        assert metrics.elapsed_s == 10.5
        assert metrics.program_length == 5
    
    def test_pruning_rate(self):
        """Test pruning rate calculation."""
        metrics = EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.0,
            generated_nodes=800,
            pruned_nodes=200,
        )
        
        # 200 / (800 + 200) = 0.2
        assert metrics.compute_pruning_rate() == 0.2
    
    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        metrics = EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.0,
            cache_hits=80,
            cache_misses=20,
        )
        
        # 80 / (80 + 20) = 0.8
        assert metrics.compute_cache_hit_rate() == 0.8
    
    def test_smt_timeout_rate(self):
        """Test SMT timeout rate calculation."""
        metrics = EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.0,
            smt_calls=10,
            smt_timeouts=2,
        )
        
        # 2 / 10 = 0.2
        assert metrics.compute_smt_timeout_rate() == 0.2
    
    def test_metrics_serialization(self):
        """Test metrics serialization."""
        metrics = EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.0,
            expansions=100,
            generated_nodes=500,
            pruned_nodes=200,
        )
        
        data = metrics.to_dict()
        restored = EvaluationMetrics.from_dict(data)
        
        assert restored.task_id == metrics.task_id
        assert restored.success == metrics.success
        assert restored.elapsed_s == metrics.elapsed_s


class TestMetricsAggregator:
    """Test metrics aggregator."""
    
    def test_aggregation(self):
        """Test metrics aggregation."""
        aggregator = MetricsAggregator()
        
        # Add successful task
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.0,
            generated_nodes=500,
            pruned_nodes=200,
            verified_candidates=5,
            program_length=5,
        ))
        
        # Add failed task
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_002",
            success=False,
            elapsed_s=15.0,
            generated_nodes=800,
            pruned_nodes=100,
            verified_candidates=3,
            failure_type="search_exhausted",
        ))
        
        assert aggregator.total_tasks == 2
        assert aggregator.successful_tasks == 1
        assert aggregator.failed_tasks == 1
        assert aggregator.compute_success_rate() == 0.5
    
    def test_pruning_rate_aggregation(self):
        """Test aggregated pruning rate."""
        aggregator = MetricsAggregator()
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.0,
            generated_nodes=800,
            pruned_nodes=200,
        ))
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_002",
            success=True,
            elapsed_s=10.0,
            generated_nodes=600,
            pruned_nodes=400,
        ))
        
        # Total: 1400 generated, 600 pruned
        # Rate: 600 / (1400 + 600) = 0.3
        assert aggregator.compute_pruning_rate() == 0.3
    
    def test_average_program_length(self):
        """Test average program length calculation."""
        aggregator = MetricsAggregator()
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_001",
            success=True,
            elapsed_s=10.0,
            program_length=5,
        ))
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_002",
            success=True,
            elapsed_s=10.0,
            program_length=7,
        ))
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_003",
            success=False,
            elapsed_s=10.0,
        ))
        
        # Average of successful tasks: (5 + 7) / 2 = 6.0
        assert aggregator.compute_average_program_length() == 6.0
    
    def test_failure_type_tracking(self):
        """Test failure type tracking."""
        aggregator = MetricsAggregator()
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_001",
            success=False,
            elapsed_s=10.0,
            failure_type="search_exhausted",
        ))
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_002",
            success=False,
            elapsed_s=10.0,
            failure_type="search_exhausted",
        ))
        
        aggregator.add_metrics(EvaluationMetrics(
            task_id="test_003",
            success=False,
            elapsed_s=10.0,
            failure_type="timeout",
        ))
        
        assert aggregator.failure_types["search_exhausted"] == 2
        assert aggregator.failure_types["timeout"] == 1


class TestPassAtK:
    """Test pass@k metric."""
    
    def test_pass_at_k_basic(self):
        """Test basic pass@k calculation."""
        results = [True, True, False, True, False]
        pass_at_k = compute_pass_at_k(results, k=2)
        
        # 3 successes out of 5 = 0.6
        assert pass_at_k == 0.6
    
    def test_pass_at_k_from_metrics(self):
        """Test pass@k from metrics."""
        metrics_list = [
            EvaluationMetrics(task_id="t1", success=True, elapsed_s=10.0),
            EvaluationMetrics(task_id="t2", success=True, elapsed_s=10.0),
            EvaluationMetrics(task_id="t3", success=False, elapsed_s=10.0),
        ]
        
        pass_at_k = compute_pass_at_k_from_metrics(metrics_list, k=2)
        assert pass_at_k == 2.0 / 3.0


class TestBaselineConfig:
    """Test baseline configuration."""
    
    def test_full_system(self):
        """Test full system configuration."""
        config = BaselineConfig.full_system()
        
        assert config.name == "full_system"
        assert config.enable_pruning is True
        assert config.enable_witness is True
        assert config.enable_egraph is True
    
    def test_no_pruning(self):
        """Test no-pruning baseline."""
        config = BaselineConfig.no_pruning()
        
        assert config.name == "no_pruning"
        assert config.enable_pruning is False
        assert config.enable_witness is True
    
    def test_minimal(self):
        """Test minimal baseline."""
        config = BaselineConfig.minimal()
        
        assert config.name == "minimal"
        assert config.enable_pruning is False
        assert config.enable_witness is False
        assert config.enable_egraph is False
    
    def test_apply_to_config(self):
        """Test applying baseline to config."""
        baseline = BaselineConfig.no_egraph()
        config = {"symbolic": {}}
        
        modified = baseline.apply_to_config(config)
        
        assert modified["symbolic"]["enhancements"]["egraph"] is False
        assert modified["symbolic"]["enhancements"]["pruning"] is True


class TestBaselineComparison:
    """Test baseline comparison."""
    
    def test_comparison_creation(self):
        """Test creating baseline comparison."""
        baseline_metrics = MetricsAggregator()
        baseline_metrics.total_tasks = 10
        baseline_metrics.successful_tasks = 5
        
        full_metrics = MetricsAggregator()
        full_metrics.total_tasks = 10
        full_metrics.successful_tasks = 7
        
        comparison = BaselineComparison(
            baseline_name="no_pruning",
            baseline_metrics=baseline_metrics,
            full_system_metrics=full_metrics,
        )
        
        assert comparison.baseline_name == "no_pruning"
        assert abs(comparison.delta["success_rate_delta"] - 0.2) < 1e-10  # 0.7 - 0.5
    
    def test_comparison_report(self):
        """Test generating comparison report."""
        baseline_metrics = MetricsAggregator()
        baseline_metrics.total_tasks = 10
        baseline_metrics.successful_tasks = 5
        
        full_metrics = MetricsAggregator()
        full_metrics.total_tasks = 10
        full_metrics.successful_tasks = 7
        
        comparison = BaselineComparison(
            baseline_name="no_pruning",
            baseline_metrics=baseline_metrics,
            full_system_metrics=full_metrics,
        )
        
        report = comparison.format_report()
        
        assert "no_pruning" in report
        assert "Success Rate Delta" in report


class TestDatasetManager:
    """Test dataset manager."""
    
    def test_train_validation_split(self):
        """Test creating train/validation split."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_root = Path(tmpdir)
            train_dir = dataset_root / "train"
            train_dir.mkdir(parents=True)
            
            # Create dummy task files
            for i in range(10):
                (train_dir / f"task_{i:03d}.json").write_text("{}")
            
            manager = DatasetManager(dataset_root, seed=42)
            train_ids, val_ids = manager.create_train_validation_split(
                train_ratio=0.8,
                shuffle=True,
            )
            
            assert len(train_ids) == 8
            assert len(val_ids) == 2
            assert len(set(train_ids) & set(val_ids)) == 0
    
    def test_select_hard_examples(self):
        """Test selecting hard examples."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DatasetManager(Path(tmpdir), seed=42)
            
            # Add metadata
            manager.task_metadata["task_001"] = TaskMetadata(
                task_id="task_001",
                difficulty="easy",
            )
            manager.task_metadata["task_002"] = TaskMetadata(
                task_id="task_002",
                difficulty="hard",
            )
            manager.task_metadata["task_003"] = TaskMetadata(
                task_id="task_003",
                difficulty="hard",
            )
            
            task_ids = ["task_001", "task_002", "task_003"]
            hard_tasks = manager.select_hard_examples(task_ids, difficulty_threshold="hard")
            
            assert len(hard_tasks) == 2
            assert "task_002" in hard_tasks
            assert "task_003" in hard_tasks
    
    def test_sample_tasks(self):
        """Test sampling tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DatasetManager(Path(tmpdir), seed=42)
            
            task_ids = [f"task_{i:03d}" for i in range(100)]
            sampled = manager.sample_tasks(task_ids, count=10)
            
            assert len(sampled) == 10
            assert len(set(sampled)) == 10  # No duplicates


class TestDashboardDataGenerator:
    """Test dashboard data generator."""
    
    def test_task_curve_generation(self):
        """Test generating task curves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = DashboardDataGenerator(Path(tmpdir))
            
            metrics_list = [
                EvaluationMetrics(
                    task_id="test_001",
                    success=True,
                    elapsed_s=10.0,
                    generated_nodes=500,
                    verified_candidates=5,
                ),
            ]
            
            curves = generator.generate_task_curves(metrics_list)
            
            assert "test_001" in curves
            assert len(curves["test_001"].timestamps) > 0
    
    def test_rule_heatmap_generation(self):
        """Test generating rule heatmap."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = DashboardDataGenerator(Path(tmpdir))
            
            metrics_list = [
                EvaluationMetrics(
                    task_id="test_001",
                    success=True,
                    elapsed_s=10.0,
                    metadata={"rule_hits": {"rule_a": 5, "rule_b": 3}},
                ),
                EvaluationMetrics(
                    task_id="test_002",
                    success=True,
                    elapsed_s=10.0,
                    metadata={"rule_hits": {"rule_a": 2, "rule_c": 4}},
                ),
            ]
            
            heatmap = generator.generate_rule_heatmap(metrics_list)
            
            assert "rule_a" in heatmap.rule_ids
            assert "rule_b" in heatmap.rule_ids
            assert "rule_c" in heatmap.rule_ids
    
    def test_failure_distribution_generation(self):
        """Test generating failure distribution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = DashboardDataGenerator(Path(tmpdir))
            
            metrics_list = [
                EvaluationMetrics(
                    task_id="test_001",
                    success=False,
                    elapsed_s=10.0,
                    failure_type="search_exhausted",
                ),
                EvaluationMetrics(
                    task_id="test_002",
                    success=False,
                    elapsed_s=10.0,
                    failure_type="search_exhausted",
                ),
                EvaluationMetrics(
                    task_id="test_003",
                    success=False,
                    elapsed_s=10.0,
                    failure_type="timeout",
                ),
            ]
            
            distribution = generator.generate_failure_distribution(metrics_list)
            
            assert distribution.failure_counts["search_exhausted"] == 2
            assert distribution.failure_counts["timeout"] == 1
            assert distribution.total_failures == 3
    
    def test_export_json(self):
        """Test exporting to JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = DashboardDataGenerator(Path(tmpdir))
            
            metrics_list = [
                EvaluationMetrics(
                    task_id="test_001",
                    success=True,
                    elapsed_s=10.0,
                    generated_nodes=500,
                    verified_candidates=5,
                ),
            ]
            
            curves = generator.generate_task_curves(metrics_list)
            path = generator.export_task_curves_json(curves)
            
            assert path.exists()
            with path.open("r") as f:
                data = json.load(f)
            assert "test_001" in data


class TestEvaluationRunner:
    """Test evaluation runner."""
    
    def test_runner_creation(self):
        """Test creating evaluation runner."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluationConfig(
                run_id="test_run",
                dataset_root=Path(tmpdir) / "data",
                output_dir=Path(tmpdir) / "output",
                split=DatasetSplit.VALIDATION,
                max_tasks=5,
            )
            
            runner = EvaluationRunner(config)
            
            assert runner.config.run_id == "test_run"
            assert runner.config.max_tasks == 5
    
    def test_evaluation_config_serialization(self):
        """Test evaluation config serialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluationConfig(
                run_id="test_run",
                dataset_root=Path(tmpdir) / "data",
                output_dir=Path(tmpdir) / "output",
                split=DatasetSplit.VALIDATION,
                baseline_config=BaselineConfig.no_pruning(),
            )
            
            data = config.to_dict()
            restored = EvaluationConfig.from_dict(data)
            
            assert restored.run_id == config.run_id
            assert restored.split == config.split
            assert restored.baseline_config.name == "no_pruning"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
