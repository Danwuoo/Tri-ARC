from __future__ import annotations

import logging
from pathlib import Path
import warnings
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from arc.core import (
    ModuleCapabilities,
    ModuleContext,
    ModuleError,
    ModuleResult,
    ModuleSolveStatus,
    ModuleTaskContext,
    SolverModule,
)

if TYPE_CHECKING:
    from arc.symbolic.solver import SolverResult, SymbolicSolver

LOGGER = logging.getLogger("arc.module.symbolic")


def _normalise_status(status: str) -> ModuleSolveStatus:
    token = status.lower()
    if token == "success":
        return ModuleSolveStatus.SUCCESS
    if token in {"no_solution", "failed"}:
        return ModuleSolveStatus.FAILED
    if token in {"timeout", "partial"}:
        return ModuleSolveStatus.PARTIAL
    if token in {"skipped", "disabled"}:
        return ModuleSolveStatus.SKIPPED
    return ModuleSolveStatus.ERROR


class SymbolicModule(SolverModule):
    module_name = "symbolic"
    capabilities = ModuleCapabilities(
        supports_partial_results=True,
        supports_resume=True,
        requires_gpu=False,
        extras={"lane": "symbolic"},
    )

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        solver_factory: Optional[Callable[[Dict[str, Any]], "SymbolicSolver"]] = None,
    ) -> None:
        super().__init__(config)
        if solver_factory is None:
            from arc.symbolic.solver import SymbolicSolver as _SymbolicSolver

            self._solver_factory = _SymbolicSolver
        else:
            self._solver_factory = solver_factory
        self._solver: Optional["SymbolicSolver"] = None
        self._enabled = bool(config.get("symbolic", {}).get("enabled", True))

    # ------------------------------------------------------------------ #
    # Lifecycle hooks
    # ------------------------------------------------------------------ #
    def _on_initialize(self, context: ModuleContext) -> None:
        if not self._enabled:
            context.logger.info("Symbolic lane disabled via configuration toggle.")
            return
        self._solver = self._solver_factory(self.config)
        self._ensure_migration_log(context)

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        shared_namespace = task_context.module_context.shared_cache.setdefault(self.module_name, {})
        module_cache = shared_namespace.setdefault(task_context.task_id, {})
        task_context.cache_namespace = module_cache
        task_context.metadata["module"] = self.module_name
        task_context.metadata["cache_key"] = f"{self.module_name}:{task_context.task_id}"
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        if not self._enabled:
            summary = {"reason": "module_disabled", "lane": self.module_name}
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        if self._solver is None:
            raise ModuleError("Symbolic solver must be initialised before solving.")

        payload = dict(task_context.task_payload)
        payload.setdefault("task_id", task_context.task_id)

        solver_result = self._solver.solve(payload)
        module_result = self._build_module_result(task_context, solver_result)
        task_context.cache_namespace["solver_summary"] = module_result.summary
        task_context.cache_namespace["candidates"] = module_result.candidates
        return module_result

    def _on_shutdown(self, context: ModuleContext) -> None:
        if not self._enabled:
            return
        context.logger.debug("Symbolic module shutdown complete.")

    # ------------------------------------------------------------------ #
    # Legacy compatibility
    # ------------------------------------------------------------------ #
    def solve_task(self, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        warnings.warn(
            "SymbolicModule.solve_task is deprecated; migrate to prepare_task() + solve().",
            DeprecationWarning,
            stacklevel=2,
        )
        task_context = self.prepare_task(task_payload)
        result = self.solve(task_context)
        return self._serialise_result(result)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _build_module_result(self, task_context: ModuleTaskContext, solver_result: "SolverResult") -> ModuleResult:
        status = _normalise_status(solver_result.status)
        candidates = [
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
            for candidate in solver_result.candidates
        ]

        telemetry = solver_result.telemetry
        telemetry_payload = {
            "frontier_report": str(telemetry.frontier_report) if telemetry.frontier_report else None,
            "frontier_log": str(telemetry.frontier_log) if telemetry.frontier_log else None,
            "diagnostics": [str(path) for path in telemetry.diagnostics],
            "progress_path": str(telemetry.progress_path) if telemetry.progress_path else None,
            "checkpoint_path": str(telemetry.checkpoint_path) if telemetry.checkpoint_path else None,
            "elapsed_s": telemetry.elapsed_s,
            "expansions": telemetry.expansions,
            "generated_nodes": telemetry.generated_nodes,
        }

        summary = dict(solver_result.summary)
        summary.setdefault("lane", self.module_name)
        summary["candidate_count"] = len(candidates)
        summary["telemetry_snapshot"] = telemetry_payload

        task_context.metadata["telemetry_snapshot"] = telemetry_payload
        return ModuleResult(task_id=solver_result.task_id, status=status, candidates=candidates, summary=summary)

    def _serialise_result(self, result: ModuleResult) -> Dict[str, Any]:
        return {
            "task_id": result.task_id,
            "status": result.status.value,
            "candidates": result.candidates,
            "telemetry": result.summary.get("telemetry_snapshot", {}),
            "summary": result.summary,
        }

    def _ensure_migration_log(self, context: ModuleContext) -> None:
        target = context.extras.get("migration_log_path", "reports/module_interface_migration.md")
        path = Path(target)
        try:
            if path.exists():
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            header_lines = [
                "# Module Interface Migration Log",
                "",
                "This file tracks baseline expectations when modules adopt the shared SolverModule contract.",
                "",
                "## Symbolic Lane",
                "",
                f"- Migration initialised for run `{context.run_id}`.",
            ]
            path.write_text("\n".join(header_lines) + "\n", encoding="utf-8")
        except Exception as exc:  # pragma: no cover - best effort
            context.logger.debug("Unable to initialise migration log at %s: %s", path, exc)
