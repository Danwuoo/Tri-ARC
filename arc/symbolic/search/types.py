from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple

from arc.symbolic.dsl.types import Program, Stage


@dataclass(frozen=True)
class TrainingExample:
    """Container for a single ARC training example."""

    input_grid: Any
    output_grid: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchNode:
    """Represents a partial (or complete) program under exploration."""

    node_id: int
    stages: Tuple[Stage, ...]
    depth: int
    score: float
    cost: float
    created_at: float = field(default_factory=lambda: time.time())
    parent_id: Optional[int] = None
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def program(self) -> Program:
        return Program(stages=self.stages)

    def with_stage(self, stage: Stage, *, node_id: int, score: float, cost: float) -> "SearchNode":
        """Create a new node by appending a stage."""
        return SearchNode(
            node_id=node_id,
            stages=self.stages + (stage,),
            depth=self.depth + 1,
            score=score,
            cost=cost,
            parent_id=self.node_id,
        )


@dataclass
class CandidateProgram:
    """Fully instantiated program with evaluation metadata."""

    node_id: int
    program: Program
    score: float
    cost: float
    solved_examples: int = 0
    total_examples: int = 0
    verification_passed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FrontierSnapshot:
    """Summary of the current frontier state for telemetry and replay."""

    timestamp: float
    strategy: str
    total_nodes: int
    pending_nodes: int
    expanded_nodes: int
    pruned_nodes: int
    best_score: Optional[float]
    worst_score: Optional[float]
    average_depth: float
    max_depth: int
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchTraceEvent:
    """Structured event emitted during search for progress replay."""

    timestamp: float
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)


def summarise_nodes(nodes: Iterable[SearchNode]) -> Dict[str, Any]:
    """Compute basic statistics for an iterable of nodes."""
    total = 0
    depths = 0
    best = None
    worst = None
    max_depth = 0
    for node in nodes:
        total += 1
        depths += node.depth
        best = node.score if best is None else max(best, node.score)
        worst = node.score if worst is None else min(worst, node.score)
        max_depth = max(max_depth, node.depth)
    avg_depth = depths / total if total else 0.0
    return {"total": total, "best": best, "worst": worst, "avg_depth": avg_depth, "max_depth": max_depth}


__all__ = [
    "TrainingExample",
    "SearchNode",
    "CandidateProgram",
    "FrontierSnapshot",
    "SearchTraceEvent",
    "summarise_nodes",
]
