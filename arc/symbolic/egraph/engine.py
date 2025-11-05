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

    def generate(self, program: Program) -> Iterable[Program]:
        if not self.enabled:
            return ()
        if self.condition and not self.condition(program):
            return ()
        return self.apply(program)


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


class EGraph:
    """Simplified e-graph that tracks equivalent programs under rewrite rules."""

    def __init__(
        self,
        *,
        cost_fn: Optional[Callable[[Program], float]] = None,
        rewrite_limit: int = 5000,
        history_dir: Optional[Path] = None,
    ):
        self.cost_fn = cost_fn or (lambda program: float(len(program.stages)))
        self.rewrite_limit = rewrite_limit
        self.history_dir = history_dir
        self._records: Dict[str, ProgramRecord] = {}
        self._history: List[RewriteApplication] = []
        self._rules: List[RewriteRule] = []

    def add_rule(self, rule: RewriteRule) -> None:
        self._rules.append(rule)

    def add_rules(self, rules: Sequence[RewriteRule]) -> None:
        for rule in rules:
            self.add_rule(rule)

    def add_program(self, program: Program, *, metadata: Optional[Dict[str, Any]] = None) -> ProgramRecord:
        signature = _program_signature(program)
        cost = self.cost_fn(program)
        existing = self._records.get(signature)
        if existing is None or cost < existing.cost:
            self._records[signature] = ProgramRecord(program=program, cost=cost, metadata=dict(metadata or {}))
        return self._records[signature]

    def saturate(self, *, max_iterations: int = 50) -> SaturationStats:
        iterations = 0
        rewrites = 0
        while iterations < max_iterations and rewrites < self.rewrite_limit:
            iterations += 1
            changed = False
            current_items = list(self._records.items())
            for signature, record in current_items:
                for rule in self._rules:
                    for candidate in rule.generate(record.program):
                        new_signature = _program_signature(candidate)
                        cost = self.cost_fn(candidate)
                        existing = self._records.get(new_signature)
                        applied = False
                        if existing is None or cost < existing.cost:
                            self._records[new_signature] = ProgramRecord(program=candidate, cost=cost)
                            applied = True
                            changed = True
                        if applied:
                            rewrites += 1
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
                    if rewrites >= self.rewrite_limit:
                        break
                if rewrites >= self.rewrite_limit:
                    break
            if not changed:
                break
        history_path = self._dump_history() if self.history_dir else None
        best_cost = min((record.cost for record in self._records.values()), default=float("inf"))
        return SaturationStats(
            iterations=iterations,
            rewrites_applied=rewrites,
            unique_programs=len(self._records),
            best_cost=best_cost,
            history_path=history_path,
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
