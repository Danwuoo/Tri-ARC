from __future__ import annotations

from typing import Any, Dict, Optional

from arc.core import (
    ModuleCapabilities,
    ModuleContext,
    ModuleResult,
    ModuleSolveStatus,
    ModuleTaskContext,
    SolverModule,
)


class TTTModule(SolverModule):
    module_name = "ttt"
    capabilities = ModuleCapabilities(
        supports_partial_results=True,
        supports_resume=False,
        requires_gpu=True,
        extras={"lane": "ttt"},
    )

    def __init__(self, config: Dict[str, Any], *, profile: Optional[str] = None) -> None:
        super().__init__(config)
        self._profile = profile or "default"
        self._enabled = bool(config.get("ttt", {}).get("enabled", True))

    def _on_initialize(self, context: ModuleContext) -> None:
        if not self._enabled:
            context.logger.info("TTT lane disabled via configuration toggle.")
            return
        context.logger.info("TTT module initialised with profile=%s", self._profile)

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        shared_namespace = task_context.module_context.shared_cache.setdefault(self.module_name, {})
        module_cache = shared_namespace.setdefault(task_context.task_id, {})
        task_context.cache_namespace = module_cache
        task_context.metadata["module"] = self.module_name
        task_context.metadata["profile"] = self._profile
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        if not self._enabled:
            summary = {"lane": self.module_name, "reason": "module_disabled"}
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        summary = {
            "lane": self.module_name,
            "profile": self._profile,
            "message": "TTT stub execution; replace with full adaptation logic.",
        }
        task_context.cache_namespace["ttt_stub"] = summary
        return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.PARTIAL, summary=summary)

    def _on_shutdown(self, context: ModuleContext) -> None:
        context.logger.debug("TTT module teardown complete.")
