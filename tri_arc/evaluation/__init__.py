"""
Evaluation harness orchestrating dataset iteration and metric reporting.
"""

from .harness import EvaluationHarness, EvaluationResult, EvaluationSettings, TaskOutcome

__all__ = ["EvaluationHarness", "EvaluationResult", "EvaluationSettings", "TaskOutcome"]
