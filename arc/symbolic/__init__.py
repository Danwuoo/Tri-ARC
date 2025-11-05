from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from arc.symbolic.solver import SolverResult, SymbolicSolver


@dataclass
class SymbolicModule:
    config: Dict[str, Any]
    solver: Optional[SymbolicSolver] = field(default=None, init=False, repr=False)

    def initialise(self) -> None:
        """Perform lightweight initialisation to ensure dependencies resolve."""
        symbolic_cfg = self.config.get("symbolic", {})
        if not symbolic_cfg.get("enabled", True):
            return
        if self.solver is None:
            self.solver = SymbolicSolver(config=self.config)

    def solve(self, task: Dict[str, Any]) -> Dict[str, Any]:
        symbolic_cfg = self.config.get("symbolic", {})
        if not symbolic_cfg.get("enabled", True):
            return {
                "task_id": task.get("task_id"),
                "status": "disabled",
                "candidates": [],
            }
        if self.solver is None:
            self.initialise()
        assert self.solver is not None  # for type checkers
        result: SolverResult = self.solver.solve(task)
        return {
            "task_id": result.task_id,
            "status": result.status,
            "candidates": [
                {
                    "node_id": candidate.node_id,
                    "score": candidate.score,
                    "cost": candidate.cost,
                    "solved_examples": candidate.solved_examples,
                    "total_examples": candidate.total_examples,
                    "verification_passed": candidate.verification_passed,
                    "metadata": candidate.metadata,
                    "program": [(stage.operator, stage.arguments) for stage in candidate.program],
                }
                for candidate in result.candidates
            ],
            "telemetry": {
                "frontier_report": str(result.telemetry.frontier_report) if result.telemetry.frontier_report else None,
                "frontier_log": str(result.telemetry.frontier_log) if result.telemetry.frontier_log else None,
                "diagnostics": [str(path) for path in result.telemetry.diagnostics],
                "progress_path": str(result.telemetry.progress_path) if result.telemetry.progress_path else None,
                "elapsed_s": result.telemetry.elapsed_s,
                "expansions": result.telemetry.expansions,
                "generated_nodes": result.telemetry.generated_nodes,
            },
            "summary": result.summary,
        }
