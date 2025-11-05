from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from arc.symbolic.search.types import SearchNode

from .base import HeuristicContext, HeuristicResult, HeuristicScorer, logistic_normalise


@dataclass
class RuleBasedWeights:
    coverage: float = 2.0
    consistency: float = 1.5
    progress: float = 1.0
    novelty: float = 0.5
    depth_penalty: float = 1.0
    cost_penalty: float = 0.2
    stagnation_penalty: float = 0.5
    normalise_scale: float = 1.0


class RuleBasedHeuristic(HeuristicScorer):
    """Hand-crafted heuristic to prioritise promising partial programs."""

    def __init__(self, *, weights: Optional[RuleBasedWeights] = None, name: str = "rule_based"):
        super().__init__(name=name)
        self.weights = weights or RuleBasedWeights()

    def initialise(self, context: HeuristicContext) -> None:
        super().initialise(context)

    def score_node(self, node: SearchNode) -> HeuristicResult:
        assert self.context is not None
        data = node.metadata
        coverage = float(data.get("coverage", 0.0))
        consistency = float(data.get("consistency", coverage))
        progress = float(data.get("progress", 0.0))
        novelty = float(data.get("novelty", 0.0))
        stagnation = float(data.get("stagnation", 0.0))
        cost = float(node.cost)
        depth_ratio = node.depth / max(1, self.context.max_depth)

        positive = (
            coverage * self.weights.coverage
            + consistency * self.weights.consistency
            + progress * self.weights.progress
            + novelty * self.weights.novelty
        )
        negative = (
            depth_ratio * self.weights.depth_penalty
            + cost * self.weights.cost_penalty
            + stagnation * self.weights.stagnation_penalty
        )
        raw = positive - negative
        score = logistic_normalise(raw, scale=self.weights.normalise_scale)
        reasoning: Dict[str, float] = {
            "coverage": coverage,
            "consistency": consistency,
            "progress": progress,
            "novelty": novelty,
            "depth_ratio": depth_ratio,
            "cost": cost,
            "stagnation": stagnation,
        }
        return HeuristicResult(score=score, components={"rule": score}, reasoning=reasoning)


__all__ = ["RuleBasedHeuristic", "RuleBasedWeights"]
