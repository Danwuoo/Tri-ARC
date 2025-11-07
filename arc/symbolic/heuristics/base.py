from __future__ import annotations

import abc
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

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


class CalibratedHeuristicEnsemble(HeuristicEnsemble):
    """Ensemble wrapper that normalises the blended score using calibration settings."""

    def __init__(
        self,
        members: Sequence[HeuristicScorer],
        weights: Optional[Sequence[float]] = None,
        *,
        calibration: Optional[Mapping[str, Any]] = None,
        name: str = "calibrated_ensemble",
    ):
        super().__init__(members, weights=weights, name=name)
        cfg = dict(calibration or {})
        self._enabled = bool(cfg.get("enabled", True))
        midpoint_cfg = cfg.get("midpoint", "auto")
        if isinstance(midpoint_cfg, str) and midpoint_cfg.lower() == "auto":
            self._fixed_midpoint: Optional[float] = None
        else:
            self._fixed_midpoint = float(midpoint_cfg)
        self._scale = float(cfg.get("scale", 1.0))
        self._min_score = cfg.get("min_score", 0.0)
        self._max_score = cfg.get("max_score", 1.0)
        self._ema_alpha = float(cfg.get("ema_alpha", 0.2))
        self._report_field = str(cfg.get("report_field", "calibration"))
        self._ema_midpoint: Optional[float] = None

    def initialise(self, context: HeuristicContext) -> None:
        super().initialise(context)
        self._ema_midpoint = None

    def score_node(self, node: SearchNode) -> HeuristicResult:
        base = super().score_node(node)
        if not self._enabled:
            return base
        raw = base.score
        midpoint = self._resolved_midpoint(raw)
        calibrated = logistic_normalise(raw, midpoint=midpoint, scale=self._scale)
        if self._min_score is not None:
            calibrated = max(float(self._min_score), calibrated)
        if self._max_score is not None:
            calibrated = min(float(self._max_score), calibrated)
        base.components["ensemble_total"] = raw
        base.components["calibrated_total"] = calibrated
        diagnostics = base.reasoning.setdefault(self._report_field, {})
        diagnostics.update(
            {
                "raw": raw,
                "midpoint": midpoint,
                "scale": self._scale,
                "min_score": self._min_score,
                "max_score": self._max_score,
            }
        )
        base.score = calibrated
        return base

    def _resolved_midpoint(self, latest_score: float) -> float:
        if self._fixed_midpoint is not None:
            return self._fixed_midpoint
        if self._ema_midpoint is None:
            self._ema_midpoint = latest_score
        else:
            self._ema_midpoint = (1.0 - self._ema_alpha) * self._ema_midpoint + self._ema_alpha * latest_score
        return self._ema_midpoint


def logistic_normalise(value: float, *, midpoint: float = 0.0, scale: float = 1.0) -> float:
    """Normalise a scalar using a logistic curve."""
    return 1.0 / (1.0 + math.exp(-(value - midpoint) / max(scale, 1e-6)))


__all__ = [
    "HeuristicContext",
    "HeuristicResult",
    "HeuristicScorer",
    "HeuristicEnsemble",
    "CalibratedHeuristicEnsemble",
    "logistic_normalise",
]
