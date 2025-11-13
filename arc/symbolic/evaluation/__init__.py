"""Evaluation infrastructure for symbolic synthesis enhancements."""

from arc.symbolic.evaluation.metrics import (
    EvaluationMetrics,
    MetricsAggregator,
    compute_pass_at_k,
)
from arc.symbolic.evaluation.baseline import (
    BaselineConfig,
    BaselineRunner,
    BaselineComparison,
)
from arc.symbolic.evaluation.dataset import (
    DatasetManager,
    DatasetSplit,
)
from arc.symbolic.evaluation.dashboard import (
    DashboardDataGenerator,
    TaskCurveData,
    RuleHeatmapData,
    FailureDistributionData,
)
from arc.symbolic.evaluation.runner import (
    EvaluationRunner,
    EvaluationConfig,
    EvaluationResult,
)

__all__ = [
    "EvaluationMetrics",
    "MetricsAggregator",
    "compute_pass_at_k",
    "BaselineConfig",
    "BaselineRunner",
    "BaselineComparison",
    "DatasetManager",
    "DatasetSplit",
    "DashboardDataGenerator",
    "TaskCurveData",
    "RuleHeatmapData",
    "FailureDistributionData",
    "EvaluationRunner",
    "EvaluationConfig",
    "EvaluationResult",
]
