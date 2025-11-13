from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchBudget:
    """Tracks time and node expansion limits for the symbolic search."""

    max_depth: int
    max_expansions: int
    soft_timeout_s: float
    hard_timeout_s: float
    max_nodes: Optional[int] = None
    beam_width: Optional[int] = None
    max_candidates: int = 10
    seed: Optional[int] = None
    _start_time: Optional[float] = field(default=None, init=False, repr=False)
    _expansions: int = field(default=0, init=False, repr=False)
    _generated_nodes: int = field(default=0, init=False, repr=False)

    def start(self) -> None:
        self._start_time = time.perf_counter()
        self._expansions = 0
        self._generated_nodes = 0

    @property
    def elapsed_s(self) -> float:
        if self._start_time is None:
            return 0.0
        return max(0.0, time.perf_counter() - self._start_time)

    @property
    def expansions(self) -> int:
        return self._expansions

    @property
    def generated_nodes(self) -> int:
        return self._generated_nodes

    def register_node(self) -> bool:
        self._generated_nodes += 1
        if self.max_nodes is None:
            return True
        return self._generated_nodes <= self.max_nodes

    def register_expansion(self) -> bool:
        self._expansions += 1
        return self._expansions <= self.max_expansions

    def within_time(self, *, soft: bool = False) -> bool:
        limit = self.soft_timeout_s if soft else self.hard_timeout_s
        if limit <= 0:
            return True
        return self.elapsed_s <= limit

    def allow_expansion(self) -> bool:
        """Return True if another expansion is permitted under the budget."""
        if not self.within_time(soft=False):
            return False
        if self.max_nodes is not None and self._generated_nodes >= self.max_nodes:
            return False
        if self._expansions >= self.max_expansions:
            return False
        return True

    def remaining_time(self, *, soft: bool = False) -> float:
        limit = self.soft_timeout_s if soft else self.hard_timeout_s
        if limit <= 0:
            return float("inf")
        return max(0.0, limit - self.elapsed_s)
    
    def has_time_remaining(self, *, soft: bool = False) -> bool:
        """Check if there is time remaining in the budget.
        
        Args:
            soft: Whether to check against soft timeout
            
        Returns:
            True if time remaining, False otherwise
        """
        return self.within_time(soft=soft)

    def export_state(self) -> dict:
        """Serialise budget counters for checkpointing."""
        return {
            "max_depth": self.max_depth,
            "max_expansions": self.max_expansions,
            "soft_timeout_s": self.soft_timeout_s,
            "hard_timeout_s": self.hard_timeout_s,
            "max_nodes": self.max_nodes,
            "beam_width": self.beam_width,
            "seed": self.seed,
            "elapsed_s": self.elapsed_s,
            "expansions": self._expansions,
            "generated_nodes": self._generated_nodes,
        }

    def restore_state(self, payload: dict) -> None:
        """Restore budget counters from a checkpoint payload."""
        self._expansions = int(payload.get("expansions", 0))
        self._generated_nodes = int(payload.get("generated_nodes", 0))
        elapsed = float(payload.get("elapsed_s", 0.0))
        if elapsed < 0:
            elapsed = 0.0
        # Reconstruct start time so elapsed calculations stay monotonic.
        self._start_time = time.perf_counter() - elapsed


__all__ = ["SearchBudget"]
