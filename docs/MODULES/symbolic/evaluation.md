# Symbolic Synthesis Evaluation Infrastructure

This module provides comprehensive evaluation infrastructure for the symbolic synthesis enhancements, including metrics collection, baseline comparisons, dataset management, dashboard data generation, and evaluation runners.

## Overview

The evaluation infrastructure supports:

- **Metrics Collection**: Comprehensive metrics for synthesis operations including pruning rate, verified candidates, program length, timeout rate, and pass@k
- **Baseline Comparisons**: Framework for running ablation studies comparing different feature configurations
- **Dataset Management**: Tools for managing train/validation splits, selecting hard examples, and reproducible sampling
- **Dashboard Data**: Generation of visualization-friendly data (task curves, rule heatmaps, failure distributions)
- **Evaluation Runner**: Orchestration of full evaluation runs with configurable baselines and ablations

## Components

### Metrics (`metrics.py`)

#### EvaluationMetrics

Captures comprehensive metrics for a single task evaluation:

```python
from arc.symbolic.evaluation.metrics import EvaluationMetrics

metrics = EvaluationMetrics(
    task_id="task_001",
    success=True,
    elapsed_s=45.2,
    expansions=1500,
    generated_nodes=5000,
    pruned_nodes=2000,
    verified_candidates=15,
    program_length=7,
    egraph_rewrites=120,
    cache_hits=450,
    cache_misses=50,
    smt_calls=20,
    smt_timeouts=2,
)

# Compute derived metrics
pruning_rate = metrics.compute_pruning_rate()  # 0.4 (2000 / 5000)
cache_hit_rate = metrics.compute_cache_hit_rate()  # 0.9 (450 / 500)
```

#### MetricsAggregator

Aggregates metrics across multiple tasks:

```python
from arc.symbolic.evaluation.metrics import MetricsAggregator

aggregator = MetricsAggregator()
for metrics in task_metrics_list:
    aggregator.add_metrics(metrics)

# Get aggregate statistics
print(f"Success Rate: {aggregator.compute_success_rate():.2%}")
print(f"Pruning Rate: {aggregator.compute_pruning_rate():.2%}")
print(f"Timeout Rate: {aggregator.compute_timeout_rate():.2%}")
print(f"Avg Program Length: {aggregator.compute_average_program_length():.2f}")
```

#### Pass@k Metric

Compute pass@k accuracy:

```python
from arc.symbolic.evaluation.metrics import compute_pass_at_k_from_metrics

pass_at_2 = compute_pass_at_k_from_metrics(task_metrics_list, k=2)
print(f"Pass@2: {pass_at_2:.2%}")
```

### Baseline Comparison (`baseline.py`)

#### BaselineConfig

Predefined baseline configurations for ablation studies:

```python
from arc.symbolic.evaluation.baseline import BaselineConfig

# Full system with all enhancements
full_system = BaselineConfig.full_system()

# Ablation baselines
no_pruning = BaselineConfig.no_pruning()
no_witness = BaselineConfig.no_witness()
no_egraph = BaselineConfig.no_egraph()
minimal = BaselineConfig.minimal()  # All enhancements disabled

# Apply to system config
config = baseline.apply_to_config(base_config)
```

#### BaselineRunner

Run and compare baselines:

```python
from arc.symbolic.evaluation.baseline import BaselineRunner

runner = BaselineRunner(output_dir=Path("reports/baselines"))

# Save baseline configurations
runner.save_baseline_configs()

# Load results from evaluation runs
results = runner.load_baseline_results(Path("baseline_results"))

# Compare against full system
comparisons = runner.compare_baselines(results)

# Generate comparison report
runner.generate_comparison_report(comparisons)
```

### Dataset Management (`dataset.py`)

#### DatasetManager

Manage dataset splits and task selection:

```python
from arc.symbolic.evaluation.dataset import DatasetManager, DatasetSplit

manager = DatasetManager(
    dataset_root=Path("data/arcagi2"),
    seed=1337,
)

# Create train/validation split
train_ids, val_ids = manager.create_train_validation_split(
    train_ratio=0.8,
    shuffle=True,
)

# Select hard examples
hard_tasks = manager.select_hard_examples(
    task_ids=val_ids,
    difficulty_threshold="hard",
    max_count=50,
)

# Sample tasks with stratification
sampled = manager.sample_tasks(
    task_ids=train_ids,
    count=100,
    stratify_by="difficulty",
)

# Create evaluation subset with filters
eval_subset = manager.create_evaluation_subset(
    split=DatasetSplit.VALIDATION,
    max_count=100,
    difficulty="hard",
    min_grid_size=10,
    max_grid_size=30,
)
```

### Dashboard Data (`dashboard.py`)

#### DashboardDataGenerator

Generate visualization-friendly data:

```python
from arc.symbolic.evaluation.dashboard import DashboardDataGenerator

generator = DashboardDataGenerator(output_dir=Path("reports/dashboard"))

# Generate all dashboard data
exported_files = generator.generate_all_dashboard_data(
    metrics_list=task_metrics,
    export_format="both",  # JSON and CSV
)

# Generate individual components
curves = generator.generate_task_curves(task_metrics)
heatmap = generator.generate_rule_heatmap(task_metrics)
distribution = generator.generate_failure_distribution(task_metrics)

# Generate summary report
report_path = generator.generate_summary_report(aggregator)
```

### Evaluation Runner (`runner.py`)

#### EvaluationRunner

Orchestrate full evaluation runs:

```python
from arc.symbolic.evaluation.runner import EvaluationConfig, EvaluationRunner
from arc.symbolic.evaluation.dataset import DatasetSplit
from arc.symbolic.evaluation.baseline import BaselineConfig

# Create configuration
config = EvaluationConfig(
    run_id="eval_20241112",
    dataset_root=Path("data/arcagi2"),
    output_dir=Path("reports/evaluation"),
    split=DatasetSplit.VALIDATION,
    max_tasks=100,
    baseline_config=BaselineConfig.full_system(),
    seed=1337,
    timeout_per_task=150.0,
    save_metrics=True,
    save_dashboard_data=True,
    generate_report=True,
)

# Run evaluation
runner = EvaluationRunner(config)
result = runner.run()

print(f"Success Rate: {result.metrics.compute_success_rate():.2%}")
print(f"Pass@2: {result.pass_at_2:.2%}")
```

#### Run Ablations

Run multiple baseline configurations:

```python
# Run all ablation studies
results = runner.run_ablations(baselines=[
    BaselineConfig.full_system(),
    BaselineConfig.no_pruning(),
    BaselineConfig.no_witness(),
    BaselineConfig.no_egraph(),
])

# Results include comparison report
for name, result in results.items():
    print(f"{name}: {result.metrics.compute_success_rate():.2%}")
```

## Command-Line Interface

### Evaluation Runner Script

Run evaluations from command line:

```bash
# Run full system evaluation
python scripts/run_symbolic_evaluation.py \
  --run-id eval_full_system \
  --split validation \
  --max-tasks 100 \
  --baseline full_system

# Run ablation studies
python scripts/run_symbolic_evaluation.py \
  --run-id eval_ablations \
  --split validation \
  --max-tasks 100 \
  --run-ablations

# Run specific baseline
python scripts/run_symbolic_evaluation.py \
  --run-id eval_no_pruning \
  --split validation \
  --baseline no_pruning \
  --max-tasks 50

# Run on specific tasks
python scripts/run_symbolic_evaluation.py \
  --run-id eval_hard_tasks \
  --split validation \
  --task-ids task_001 task_002 task_003
```

### Available Baselines

- `full_system`: All enhancements enabled
- `no_pruning`: Pruning disabled
- `no_witness`: Witness functions disabled
- `no_egraph`: E-graph optimization disabled
- `no_cegis`: CEGIS loop disabled
- `no_smt`: SMT verification disabled
- `minimal`: All enhancements disabled

## Output Structure

Evaluation runs produce the following output structure:

```
reports/evaluation/{run_id}/
├── result.json                    # Overall evaluation result
├── metrics.json                   # Detailed metrics for all tasks
├── evaluation_report.md           # Human-readable summary report
├── dashboard/
│   ├── task_curves.json          # Task-level time series data
│   ├── task_curves.csv
│   ├── rule_heatmap.json         # Rule usage heatmap
│   ├── rule_heatmap.csv
│   ├── failure_distribution.json # Failure type distribution
│   └── failure_distribution.csv
└── {baseline_name}/              # Per-baseline results (if ablations)
    └── ...
```

## Key Metrics

### Primary Metrics

- **Success Rate**: Fraction of tasks solved successfully
- **Pass@k**: Probability of solving with k attempts
- **Pruning Rate**: Fraction of nodes pruned during search
- **Average Verified Candidates**: Mean number of candidates verified per task
- **Average Program Length**: Mean length of successful programs
- **Timeout Rate**: Fraction of tasks that timed out

### Secondary Metrics

- **Per-Task Time**: Mean, median, P95, max, min times
- **E-graph Rewrites**: Total rewrite operations
- **Cache Hit Rate**: Fraction of cache hits
- **SMT Timeout Rate**: Fraction of SMT calls that timed out
- **Failure Distribution**: Breakdown of failure types

## Integration with Existing System

The evaluation infrastructure integrates with the existing Tri-ARC evaluation harness:

```python
# In arc/symbolic/solver.py
from arc.symbolic.evaluation.metrics import EvaluationMetrics

class SymbolicSolver:
    def solve(self, task):
        start_time = time.time()
        
        # ... synthesis logic ...
        
        # Collect metrics
        metrics = EvaluationMetrics(
            task_id=task["task_id"],
            success=result.success,
            elapsed_s=time.time() - start_time,
            expansions=self.search_stats.expansions,
            generated_nodes=self.search_stats.nodes_generated,
            pruned_nodes=self.search_stats.nodes_pruned,
            verified_candidates=self.search_stats.verified,
            program_length=len(result.program.stages) if result.success else None,
            # ... additional metrics ...
        )
        
        # Store in telemetry
        result.telemetry.extras["evaluation_metrics"] = metrics.to_dict()
        
        return result
```

## Testing

Run tests:

```bash
# Run all evaluation tests
pytest tests/symbolic/test_evaluation.py -v

# Run specific test class
pytest tests/symbolic/test_evaluation.py::TestEvaluationMetrics -v

# Run with coverage
pytest tests/symbolic/test_evaluation.py --cov=arc.symbolic.evaluation
```

## Requirements

The evaluation infrastructure requires:

- Python 3.11+
- Standard library modules (json, csv, pathlib, dataclasses)
- Project dependencies (see requirements.txt)

No additional dependencies are required beyond the base Tri-ARC system.

## Future Enhancements

Potential future improvements:

1. **Real-time Monitoring**: Stream metrics during evaluation
2. **Distributed Evaluation**: Support for multi-machine evaluation
3. **Advanced Visualizations**: Interactive dashboards with Plotly/Dash
4. **Statistical Analysis**: Confidence intervals, significance tests
5. **Automated Regression Detection**: Alert on metric degradation
6. **Cost-Benefit Analysis**: Track computational cost vs. accuracy gains

## References

- Requirements: 13.1-13.9 in requirements.md
- Design: Evaluation & Metrics section in design.md
- Tasks: Phase 11 in tasks.md
