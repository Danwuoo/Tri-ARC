from __future__ import annotations

import abc
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Sequence

from arc.symbolic.dsl.types import Program, Stage

from .types import SearchNode, TrainingExample


@dataclass(frozen=True)
class EnumeratorContext:
    task_id: str
    examples: Sequence[TrainingExample]
    rng: random.Random
    max_depth: int
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class ExpansionCandidate:
    stage: Stage
    metadata: Dict[str, Any]
    incremental_cost: float = 1.0
    is_solution: bool = False
    reason: str = ""


class ProgramEnumerator(abc.ABC):
    """Abstract base class that yields expansion candidates for a search node."""

    def __init__(self, *, name: str = "enumerator"):
        self.name = name

    @abc.abstractmethod
    def expand(self, node: SearchNode, context: EnumeratorContext) -> Iterable[ExpansionCandidate]:
        raise NotImplementedError

    def initialise(self, context: EnumeratorContext) -> None:
        """Optional hook invoked before search begins."""

    def shutdown(self) -> None:
        """Optional cleanup hook."""


class NullEnumerator(ProgramEnumerator):
    """Enumerator that produces no expansions. Useful as a placeholder."""

    def __init__(self):
        super().__init__(name="null")

    def expand(self, node: SearchNode, context: EnumeratorContext) -> Iterable[ExpansionCandidate]:
        if node.depth == 0:
            yield ExpansionCandidate(
                stage=Stage(operator="identity", arguments=()),
                metadata={"note": "placeholder"},
                incremental_cost=0.0,
                is_solution=True,
                reason="Null enumerator returns identity program.",
            )
        return []


__all__ = [
    "ProgramEnumerator",
    "EnumeratorContext",
    "ExpansionCandidate",
    "NullEnumerator",
]
