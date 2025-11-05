from __future__ import annotations

import abc
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from arc.symbolic.search.types import SearchNode, TrainingExample


@dataclass
class HeuristicContext:
    """Shared context passed to heuristics for scoring partial programs."""

    task_id: str
    examples: Sequence[TrainingExample]
    metadata: Dict[str, Any]
    max_depth: int
    device: str
    seed: Optional[int] = None
    created_at: float = field(default_factory=lambda: time.time())
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)


@dataclass
class HeuristicResult:
    score: float
    components: Dict[str, float] = field(default_factory=dict)
    reasoning: Dict[str, Any] = field(default_factory=dict)


class HeuristicScorer(abc.ABC):
    """Base class for search heuristics."""

    def __init__(self, name: str):
        self.name = name
        self.context: Optional[HeuristicContext] = None

    def initialise(self, context: HeuristicContext) -> None:
        self.context = context

    @abc.abstractmethod
    def score_node(self, node: SearchNode) -> HeuristicResult:
        raise NotImplementedError

    def score(self, node: SearchNode) -> HeuristicResult:
        if self.context is None:
            raise RuntimeError("HeuristicScorer.score called before initialise().")
        return self.score_node(node)

    def shutdown(self) -> None:
        """Optional cleanup hook."""
        self.context = None


class HeuristicEnsemble(HeuristicScorer):
    """Blend multiple heuristics with configurable weights."""

    def __init__(self, members: Sequence[HeuristicScorer], weights: Optional[Sequence[float]] = None, *, name: str = "ensemble"):
        super().__init__(name=name)
        self.members = list(members)
        if weights is not None and len(weights) != len(members):
            raise ValueError("Weights length must match heuristics.")
        self.weights = list(weights) if weights is not None else [1.0] * len(members)

    def initialise(self, context: HeuristicContext) -> None:
        super().initialise(context)
        for member in self.members:
            member.initialise(context)

    def score_node(self, node: SearchNode) -> HeuristicResult:
        total = 0.0
        components: Dict[str, float] = {}
        reasoning: Dict[str, Any] = {}
        for member, weight in zip(self.members, self.weights):
            result = member.score(node)
            weighted = result.score * weight
            components[member.name] = weighted
            total += weighted
            if result.reasoning:
                reasoning[member.name] = result.reasoning
        return HeuristicResult(score=total, components=components, reasoning=reasoning)

    def shutdown(self) -> None:
        for member in self.members:
            member.shutdown()
        super().shutdown()


def logistic_normalise(value: float, *, midpoint: float = 0.0, scale: float = 1.0) -> float:
    """Normalise a scalar using a logistic curve."""
    return 1.0 / (1.0 + math.exp(-(value - midpoint) / max(scale, 1e-6)))


__all__ = [
    "HeuristicContext",
    "HeuristicResult",
    "HeuristicScorer",
    "HeuristicEnsemble",
    "logistic_normalise",
]
