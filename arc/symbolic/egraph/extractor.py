"""Optimal program extraction from e-graphs using various algorithms."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from arc.symbolic.dsl.types import Program

from .engine import ProgramRecord

LOGGER = logging.getLogger("arc.symbolic.egraph.extractor")


class OptimalExtractor:
    """Extract optimal programs from e-graphs using various algorithms"""
    
    def __init__(
        self,
        cost_fn: Optional[Callable[[Program], float]] = None,
        method: str = "astar",
    ):
        """
        Initialize the extractor.
        
        Args:
            cost_fn: Cost function for programs (default: program length)
            method: Extraction method - "astar", "ilp", or "cp_sat"
        """
        self.cost_fn = cost_fn or (lambda program: float(len(program.stages)))
        self.method = (method or "astar").lower()
    
    def extract_best(
        self,
        records: Dict[str, ProgramRecord],
        **kwargs
    ) -> Optional[ProgramRecord]:
        """
        Extract the best program from e-graph records.
        
        Args:
            records: Dictionary of program signature to ProgramRecord
            **kwargs: Additional arguments for specific extraction methods
            
        Returns:
            Best ProgramRecord or None if no programs available
        """
        if not records:
            return None
        
        method = (kwargs.pop("method", None) or self.method or "astar").lower()
        if method == "astar":
            return self._extract_astar(records)
        if method == "ilp":
            return self._extract_ilp(records, **kwargs)
        if method == "cp_sat":
            return self._extract_cp_sat(records, **kwargs)
        
        LOGGER.warning("Unknown extraction method %s, falling back to A*", method)
        return self._extract_astar(records)
    
    @staticmethod
    def _normalize_eclass_id(signature: str, record: ProgramRecord, fallback_idx: int) -> str:
        """Resolve an identifier for the e-class that owns this record."""
        metadata = record.metadata or {}
        if "eclass_id" in metadata:
            return str(metadata["eclass_id"])
        if "eclass" in metadata:
            return str(metadata["eclass"])
        return f"sig:{fallback_idx}:{signature[:16]}"
    
    def _prepare_candidates(
        self,
        records: Dict[str, ProgramRecord],
        forbidden_eclasses: Optional[Iterable[str]] = None,
    ) -> Tuple[List[Tuple[str, ProgramRecord]], Dict[str, List[int]]]:
        """Filter out forbidden records and index membership per e-class."""
        forbidden = {str(e) for e in forbidden_eclasses or []}
        ordered_items = list(records.items())
        candidates: List[Tuple[str, ProgramRecord]] = []
        membership: Dict[str, List[int]] = defaultdict(list)
        
        for idx, (signature, record) in enumerate(ordered_items):
            metadata = record.metadata or {}
            if metadata.get("forbidden"):
                continue
            eclass_id = self._normalize_eclass_id(signature, record, idx)
            if eclass_id in forbidden:
                continue
            candidates.append((signature, record))
            membership[eclass_id].append(len(candidates) - 1)
        
        return candidates, membership
    
    def _extract_astar(
        self,
        records: Dict[str, ProgramRecord]
    ) -> Optional[ProgramRecord]:
        """
        Extract best program using A* search.
        
        This is a simplified version that just finds the minimum cost program.
        A full A* implementation would explore the e-graph structure.
        """
        if not records:
            return None
        
        candidates, _ = self._prepare_candidates(records)
        if not candidates:
            return None
        
        # Find minimum cost program
        best_record = min((record for _, record in candidates), key=lambda r: r.cost)
        LOGGER.debug("A* extraction found program with cost %.2f", best_record.cost)
        return best_record
    
    def _extract_ilp(
        self,
        records: Dict[str, ProgramRecord],
        timeout: float = 5.0
    ) -> Optional[ProgramRecord]:
        """
        Extract best program using Integer Linear Programming.
        
        This builds a binary ILP that selects exactly one program while
        respecting e-class exclusivity constraints.
        """
        try:
            import pulp  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "ILP extraction requires the 'pulp' package. Install PuLP to enable this extractor."
            ) from exc
        
        candidates, membership = self._prepare_candidates(records)
        if not candidates:
            LOGGER.warning("ILP extraction received no eligible records; using fallback.")
            return self._extract_astar(records)
        
        LOGGER.debug("ILP extraction with PuLP (timeout=%.1fs, candidates=%d)", timeout, len(candidates))
        problem = pulp.LpProblem("EGraphOptimalExtraction", pulp.LpMinimize)
        selection_vars = []
        var_index: Dict[str, ProgramRecord] = {}
        
        for idx, (_, record) in enumerate(candidates):
            var = pulp.LpVariable(f"record_{idx}", cat="Binary")
            selection_vars.append(var)
            var_index[var.name] = record
        
        objective = pulp.lpSum(record.cost * selection_vars[idx] for idx, (_, record) in enumerate(candidates))
        problem += objective
        
        problem += pulp.lpSum(selection_vars) == 1, "select_single_program"
        for eclass_id, indices in membership.items():
            if len(indices) <= 1:
                continue
            vars_in_class = [selection_vars[i] for i in indices]
            problem += pulp.lpSum(vars_in_class) <= 1, f"eclass_{eclass_id}_uniqueness"
        
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=max(0.0, float(timeout)))
        status = problem.solve(solver)
        state = pulp.LpStatus.get(status, "Unknown")
        if state != "Optimal":
            LOGGER.warning("ILP extraction failed with status %s; using fallback.", state)
            return self._extract_astar(records)
        
        for var in selection_vars:
            if var.varValue and var.varValue > 0.5:
                LOGGER.debug("ILP extraction selected program with cost %.3f", var_index[var.name].cost)
                return var_index[var.name]
        
        LOGGER.warning("ILP extraction produced no assignment; using fallback.")
        return self._extract_astar(records)
    
    def _extract_cp_sat(
        self,
        records: Dict[str, ProgramRecord],
        timeout: float = 5.0
    ) -> Optional[ProgramRecord]:
        """
        Extract best program using CP-SAT solver from OR-Tools.
        
        This formulates the extraction as a CP-SAT minimization problem so we
        can take advantage of OR-Tools' exact search and timeout controls.
        """
        try:
            from ortools.sat.python import cp_model  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "CP-SAT extraction requires the 'ortools' package. Install OR-Tools to enable this extractor."
            ) from exc
        
        candidates, membership = self._prepare_candidates(records)
        if not candidates:
            LOGGER.warning("CP-SAT extraction received no eligible records; using fallback.")
            return self._extract_astar(records)
        
        LOGGER.debug("CP-SAT extraction with OR-Tools (timeout=%.1fs, candidates=%d)", timeout, len(candidates))
        model = cp_model.CpModel()
        selection_vars: List[Tuple["cp_model.IntVar", ProgramRecord]] = []
        for idx, (_, record) in enumerate(candidates):
            var = model.NewBoolVar(f"record_{idx}")
            selection_vars.append((var, record))
        
        model.Add(sum(var for var, _ in selection_vars) == 1)
        for indices in membership.values():
            if len(indices) <= 1:
                continue
            model.Add(sum(selection_vars[i][0] for i in indices) <= 1)
        
        scale = 1_000_000  # Maintain precision while using integer objective.
        model.Minimize(sum(int(record.cost * scale) * var for var, record in selection_vars))
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.0, float(timeout))
        solver.parameters.num_search_workers = 8
        
        status = solver.Solve(model)
        if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            LOGGER.warning("CP-SAT extraction failed with status %s; using fallback.", solver.StatusName(status))
            return self._extract_astar(records)
        
        for var, record in selection_vars:
            if solver.BooleanValue(var):
                LOGGER.debug("CP-SAT extraction selected program with cost %.3f", record.cost)
                return record
        
        LOGGER.warning("CP-SAT extraction produced no assignment; using fallback.")
        return self._extract_astar(records)


class GreedyExtractor:
    """Greedy extraction for fast approximate solutions"""
    
    def __init__(self, cost_fn: Optional[Callable[[Program], float]] = None):
        self.cost_fn = cost_fn or (lambda program: float(len(program.stages)))
    
    def extract_best(
        self,
        records: Dict[str, ProgramRecord]
    ) -> Optional[ProgramRecord]:
        """Extract best program greedily"""
        if not records:
            return None
        
        return min(records.values(), key=lambda r: r.cost)


class BeamExtractor:
    """Beam search extraction for balanced quality/speed"""
    
    def __init__(
        self,
        cost_fn: Optional[Callable[[Program], float]] = None,
        beam_width: int = 10
    ):
        self.cost_fn = cost_fn or (lambda program: float(len(program.stages)))
        self.beam_width = beam_width
    
    def extract_best(
        self,
        records: Dict[str, ProgramRecord]
    ) -> Optional[ProgramRecord]:
        """Extract best program using beam search"""
        if not records:
            return None
        
        # Sort by cost and take top beam_width
        sorted_records = sorted(records.values(), key=lambda r: r.cost)
        beam = sorted_records[:self.beam_width]
        
        # Return best from beam
        return min(beam, key=lambda r: r.cost)


class MultiObjectiveExtractor:
    """Extract programs optimizing multiple objectives"""
    
    def __init__(
        self,
        cost_fns: List[Callable[[Program], float]],
        weights: Optional[List[float]] = None
    ):
        """
        Initialize multi-objective extractor.
        
        Args:
            cost_fns: List of cost functions
            weights: Optional weights for each cost function (default: equal weights)
        """
        self.cost_fns = cost_fns
        self.weights = weights or [1.0] * len(cost_fns)
        
        if len(self.weights) != len(self.cost_fns):
            raise ValueError("Number of weights must match number of cost functions")
    
    def extract_best(
        self,
        records: Dict[str, ProgramRecord]
    ) -> Optional[ProgramRecord]:
        """Extract best program considering multiple objectives"""
        if not records:
            return None
        
        def combined_cost(record: ProgramRecord) -> float:
            total = 0.0
            for cost_fn, weight in zip(self.cost_fns, self.weights):
                total += weight * cost_fn(record.program)
            return total
        
        return min(records.values(), key=combined_cost)


__all__ = [
    "OptimalExtractor",
    "GreedyExtractor",
    "BeamExtractor",
    "MultiObjectiveExtractor",
]
