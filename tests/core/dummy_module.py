from __future__ import annotations

from typing import Any, Dict

from arc.core import ModuleResult, ModuleSolveStatus, ModuleTaskContext, SolverModule


class DummySolverModule(SolverModule):
    module_name = "dummy"

    def _on_initialize(self, context) -> None:  # type: ignore[override]
        context.shared_cache.setdefault("dummy_initialised", True)

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:  # type: ignore[override]
        summary: Dict[str, Any] = {"task_id": task_context.task_id, "lane": self.module_name}
        return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SUCCESS, summary=summary)
