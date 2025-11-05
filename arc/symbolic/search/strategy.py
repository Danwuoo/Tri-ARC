from __future__ import annotations

import abc
import random
import time
from typing import Dict, Optional

from .budget import SearchBudget
from .types import FrontierSnapshot, SearchNode, summarise_nodes


class SearchStrategy(abc.ABC):
    """Base class for enumerator strategies."""

    def __init__(self, name: str, budget: SearchBudget):
        self.name = name
        self.budget = budget
        self._rng = random.Random(budget.seed)
        self._pending: Dict[int, SearchNode] = {}
        self._expanded: Dict[int, SearchNode] = {}
        self._pruned: Dict[int, SearchNode] = {}
        self._initialised = False

    @property
    def rng(self) -> random.Random:
        return self._rng

    def initialise(self, root: SearchNode) -> None:
        if self._initialised:
            raise RuntimeError("SearchStrategy.initialise called more than once.")
        self.budget.start()
        self._register_pending(root)
        self._push(root)
        self._initialised = True

    def push(self, node: SearchNode) -> None:
        self._register_pending(node)
        self._push(node)

    def pop(self) -> Optional[SearchNode]:
        node = self._pop()
        if node is None:
            return None
        self._pending.pop(node.node_id, None)
        node.status = "active"
        return node

    def mark_expanded(self, node: SearchNode) -> None:
        node.status = "expanded"
        self._expanded[node.node_id] = node

    def mark_pruned(self, node: SearchNode, *, reason: str) -> None:
        node.status = f"pruned:{reason}"
        self._pending.pop(node.node_id, None)
        self._pruned[node.node_id] = node

    def __len__(self) -> int:
        return len(self._pending)

    def frontier_snapshot(self, *, notes: Optional[Dict[str, str]] = None) -> FrontierSnapshot:
        now = time.time()
        pending_stats = summarise_nodes(self._pending.values())
        expanded_stats = summarise_nodes(self._expanded.values())
        pruned_stats = summarise_nodes(self._pruned.values())
        total_nodes = pending_stats["total"] + expanded_stats["total"] + pruned_stats["total"]
        max_depth = max(
            pending_stats.get("max_depth", 0),
            expanded_stats.get("max_depth", 0),
            pruned_stats.get("max_depth", 0),
        )
        return FrontierSnapshot(
            timestamp=now,
            strategy=self.name,
            total_nodes=total_nodes,
            pending_nodes=pending_stats["total"],
            expanded_nodes=expanded_stats["total"],
            pruned_nodes=pruned_stats["total"],
            best_score=pending_stats["best"],
            worst_score=pending_stats["worst"],
            average_depth=pending_stats["avg_depth"],
            max_depth=int(max_depth),
            notes=notes or {},
        )

    @abc.abstractmethod
    def _push(self, node: SearchNode) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def _pop(self) -> Optional[SearchNode]:
        raise NotImplementedError

    def _register_pending(self, node: SearchNode) -> None:
        node.status = "pending"
        self._pending[node.node_id] = node


__all__ = ["SearchStrategy"]
