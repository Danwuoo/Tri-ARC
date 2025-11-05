from __future__ import annotations

import bisect
import collections
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from .budget import SearchBudget
from .strategy import SearchStrategy
from .types import SearchNode


class DepthFirstSearchStrategy(SearchStrategy):
    """Simple depth-first search using a LIFO stack."""

    def __init__(self, budget: SearchBudget):
        super().__init__(name="dfs", budget=budget)
        self._stack: List[SearchNode] = []

    def _push(self, node: SearchNode) -> None:
        self._stack.append(node)

    def _pop(self) -> Optional[SearchNode]:
        while self._stack:
            node = self._stack.pop()
            if node.status.startswith("pruned"):
                continue
            return node
        return None


@dataclass
class _DeferredNode:
    node: SearchNode
    reason: str


class IterativeDeepeningStrategy(SearchStrategy):
    """Depth-first search with iterative deepening on depth limits."""

    def __init__(self, budget: SearchBudget, *, depth_step: int = 1, initial_limit: Optional[int] = None):
        super().__init__(name="iddfs", budget=budget)
        self._limit = initial_limit if initial_limit is not None else 1
        self._depth_step = max(1, depth_step)
        self._stack: List[SearchNode] = []
        self._deferred: Deque[_DeferredNode] = collections.deque()

    def _push(self, node: SearchNode) -> None:
        if node.depth <= self._limit:
            self._stack.append(node)
        else:
            self._deferred.append(_DeferredNode(node=node, reason="depth_limit"))

    def _promote_deferred(self) -> None:
        if not self._deferred:
            return
        self._limit = min(self._limit + self._depth_step, self.budget.max_depth)
        next_batch: Deque[_DeferredNode] = collections.deque()
        while self._deferred:
            item = self._deferred.popleft()
            if item.node.depth <= self._limit:
                self._stack.append(item.node)
            else:
                next_batch.append(item)
        self._deferred = next_batch

    def _pop(self) -> Optional[SearchNode]:
        while True:
            if not self._stack:
                if not self._deferred:
                    return None
                self._promote_deferred()
                if not self._stack and not self._deferred:
                    return None
            if not self._stack:
                continue
            node = self._stack.pop()
            if node.status.startswith("pruned"):
                continue
            return node


class BeamSearchStrategy(SearchStrategy):
    """Beam search ordered by node score."""

    def __init__(self, budget: SearchBudget):
        if budget.beam_width is None or budget.beam_width <= 0:
            raise ValueError("BeamSearchStrategy requires a positive beam_width in the budget.")
        super().__init__(name="beam", budget=budget)
        self._beam: List[Tuple[float, int, SearchNode]] = []
        self._tiebreak = 0

    def _push(self, node: SearchNode) -> None:
        priority = (-node.score, self._tiebreak, node)
        self._tiebreak += 1
        bisect.insort(self._beam, priority)
        if self.budget.beam_width is not None and len(self._beam) > self.budget.beam_width:
            _, _, rejected = self._beam.pop()  # worst score
            self.mark_pruned(rejected, reason="beam_limit")
        # Ensure node flagged as pending if still present

    def _pop(self) -> Optional[SearchNode]:
        while self._beam:
            _, _, node = self._beam.pop(0)
            if node.status.startswith("pruned"):
                continue
            return node
        return None


__all__ = [
    "DepthFirstSearchStrategy",
    "IterativeDeepeningStrategy",
    "BeamSearchStrategy",
]
