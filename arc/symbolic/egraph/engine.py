from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from arc.symbolic.dsl.types import Program, Stage

LOGGER = logging.getLogger("arc.symbolic.egraph.engine")


def _program_signature(program: Program) -> str:
    return json.dumps([(stage.operator, stage.arguments) for stage in program], sort_keys=False)


@dataclass(frozen=True)
class RewriteRule:
    name: str
    apply: Callable[[Program], Iterable[Program]]
    condition: Optional[Callable[[Program], bool]] = None
    enabled: bool = True
    description: str = ""
    tier: str = "cold"  # "hot" or "cold" for tiered application
    priority: int = 0  # Higher priority rules applied first
    
    # Statistics for rule scheduling
    applications: int = 0
    successes: int = 0

    def generate(self, program: Program) -> Iterable[Program]:
        if not self.enabled:
            return ()
        if self.condition and not self.condition(program):
            return ()
        return self.apply(program)
    
    def effectiveness(self) -> float:
        """Compute rule effectiveness for scheduling"""
        if self.applications == 0:
            return 0.0
        return self.successes / self.applications


@dataclass
class ProgramRecord:
    program: Program
    cost: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RewriteApplication:
    rule: str
    source_signature: str
    target_signature: str
    cost_delta: float


@dataclass
class SaturationStats:
    iterations: int
    rewrites_applied: int
    unique_programs: int
    best_cost: float
    history_path: Optional[Path] = None
    hot_rule_applications: int = 0
    cold_rule_applications: int = 0
    saturation_limit_reached: bool = False


class EGraph:
    """Simplified e-graph that tracks equivalent programs under rewrite rules."""

    def __init__(
        self,
        *,
        cost_fn: Optional[Callable[[Program], float]] = None,
        rewrite_limit: int = 5000,
        saturation_limit: int = 10000,
        history_dir: Optional[Path] = None,
        enable_tiered_rules: bool = True,
        enable_rule_scheduling: bool = True,
    ):
        self.cost_fn = cost_fn or (lambda program: float(len(program.stages)))
        self.rewrite_limit = rewrite_limit
        self.saturation_limit = saturation_limit
        self.history_dir = history_dir
        self.enable_tiered_rules = enable_tiered_rules
        self.enable_rule_scheduling = enable_rule_scheduling
        self._records: Dict[str, ProgramRecord] = {}
        self._history: List[RewriteApplication] = []
        self._rules: List[RewriteRule] = []
        self._hot_rules: List[RewriteRule] = []
        self._cold_rules: List[RewriteRule] = []
        self._rule_stats: Dict[str, Tuple[int, int]] = {}  # (applications, successes)

    def add_rule(self, rule: RewriteRule) -> None:
        self._rules.append(rule)
        self._rule_stats[rule.name] = (0, 0)
        # Categorize into hot/cold rules
        if self.enable_tiered_rules:
            if rule.tier == "hot":
                self._hot_rules.append(rule)
            else:
                self._cold_rules.append(rule)

    def add_rules(self, rules: Sequence[RewriteRule]) -> None:
        for rule in rules:
            self.add_rule(rule)
    
    def _update_rule_stats(self, rule_name: str, success: bool) -> None:
        """Update rule application statistics"""
        applications, successes = self._rule_stats.get(rule_name, (0, 0))
        applications += 1
        if success:
            successes += 1
        self._rule_stats[rule_name] = (applications, successes)
    
    def _schedule_rules(self) -> List[RewriteRule]:
        """Schedule rules based on effectiveness"""
        if not self.enable_rule_scheduling:
            return self._rules
        
        # Sort rules by effectiveness (success rate) and priority
        def rule_key(rule: RewriteRule) -> Tuple[int, float]:
            applications, successes = self._rule_stats.get(rule.name, (0, 0))
            effectiveness = successes / applications if applications > 0 else 0.5
            return (-rule.priority, -effectiveness)
        
        return sorted(self._rules, key=rule_key)

    def add_program(self, program: Program, *, metadata: Optional[Dict[str, Any]] = None) -> ProgramRecord:
        signature = _program_signature(program)
        cost = self.cost_fn(program)
        existing = self._records.get(signature)
        if existing is None or cost < existing.cost:
            self._records[signature] = ProgramRecord(program=program, cost=cost, metadata=dict(metadata or {}))
        return self._records[signature]

    def saturate(self, *, max_iterations: int = 50) -> SaturationStats:
        """
        Execute saturation with tiered rule application and scheduling.
        
        Hot rules are applied every iteration, cold rules less frequently.
        Rules are scheduled based on their effectiveness.
        """
        iterations = 0
        rewrites = 0
        hot_applications = 0
        cold_applications = 0
        saturation_limit_reached = False
        
        while iterations < max_iterations and rewrites < self.rewrite_limit:
            iterations += 1
            changed = False
            
            # Check saturation limit (total unique programs)
            if len(self._records) >= self.saturation_limit:
                saturation_limit_reached = True
                LOGGER.debug("Saturation limit reached: %d programs", len(self._records))
                break
            
            current_items = list(self._records.items())
            
            # Determine which rules to apply this iteration
            if self.enable_tiered_rules:
                # Apply hot rules every iteration
                rules_to_apply = list(self._hot_rules)
                # Apply cold rules every 3rd iteration
                if iterations % 3 == 0:
                    rules_to_apply.extend(self._cold_rules)
            else:
                rules_to_apply = self._schedule_rules()
            
            for signature, record in current_items:
                for rule in rules_to_apply:
                    rule_applied = False
                    for candidate in rule.generate(record.program):
                        new_signature = _program_signature(candidate)
                        cost = self.cost_fn(candidate)
                        existing = self._records.get(new_signature)
                        applied = False
                        
                        if existing is None or cost < existing.cost:
                            self._records[new_signature] = ProgramRecord(program=candidate, cost=cost)
                            applied = True
                            changed = True
                            rule_applied = True
                        
                        if applied:
                            rewrites += 1
                            if rule.tier == "hot":
                                hot_applications += 1
                            else:
                                cold_applications += 1
                            
                            self._history.append(
                                RewriteApplication(
                                    rule=rule.name,
                                    source_signature=signature,
                                    target_signature=new_signature,
                                    cost_delta=cost - record.cost,
                                )
                            )
                        
                        if rewrites >= self.rewrite_limit:
                            break
                    
                    # Update rule statistics
                    self._update_rule_stats(rule.name, rule_applied)
                    
                    if rewrites >= self.rewrite_limit:
                        break
                
                if rewrites >= self.rewrite_limit:
                    break
            
            if not changed:
                LOGGER.debug("Saturation converged after %d iterations", iterations)
                break
        
        history_path = self._dump_history() if self.history_dir else None
        best_cost = min((record.cost for record in self._records.values()), default=float("inf"))
        
        return SaturationStats(
            iterations=iterations,
            rewrites_applied=rewrites,
            unique_programs=len(self._records),
            best_cost=best_cost,
            history_path=history_path,
            hot_rule_applications=hot_applications,
            cold_rule_applications=cold_applications,
            saturation_limit_reached=saturation_limit_reached,
        )

    def extract_best(self) -> Optional[ProgramRecord]:
        if not self._records:
            return None
        best_signature = min(self._records, key=lambda key: self._records[key].cost)
        return self._records[best_signature]

    def _dump_history(self) -> Optional[Path]:
        if not self._history:
            return None
        assert self.history_dir is not None
        self.history_dir.mkdir(parents=True, exist_ok=True)
        path = self.history_dir / "egraph_history.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for entry in self._history:
                payload = {
                    "rule": entry.rule,
                    "source": entry.source_signature,
                    "target": entry.target_signature,
                    "cost_delta": entry.cost_delta,
                }
                handle.write(json.dumps(payload) + "\n")
        LOGGER.debug("Wrote e-graph rewrite history to %s", path)
        return path

    def reset(self) -> None:
        self._records.clear()
        self._history.clear()


__all__ = [
    "EGraph",
    "ProgramRecord",
    "RewriteRule",
    "RewriteApplication",
    "SaturationStats",
]
