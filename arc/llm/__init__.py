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


class LLMModule(SolverModule):
    module_name = "llm"
    capabilities = ModuleCapabilities(
        supports_partial_results=True,
        supports_resume=False,
        requires_gpu=True,
        extras={"lane": "llm"},
    )

    def __init__(self, config: Dict[str, Any], *, prompt_version: Optional[str] = None) -> None:
        super().__init__(config)
        self._prompt_version = prompt_version or config.get("llm", {}).get("prompt_version", "v1")
        self._enabled = bool(config.get("llm", {}).get("enabled", True))

    def _on_initialize(self, context: ModuleContext) -> None:
        if not self._enabled:
            context.logger.info("LLM lane disabled via configuration toggle.")
            return
        context.logger.info("LLM module initialised with prompt_version=%s", self._prompt_version)

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        shared_namespace = task_context.module_context.shared_cache.setdefault(self.module_name, {})
        module_cache = shared_namespace.setdefault(task_context.task_id, {})
        task_context.cache_namespace = module_cache
        task_context.metadata["module"] = self.module_name
        task_context.metadata["prompt_version"] = self._prompt_version
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        if not self._enabled:
            summary = {"lane": self.module_name, "reason": "module_disabled"}
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        summary = {
            "lane": self.module_name,
            "prompt_version": self._prompt_version,
            "message": "LLM stub execution; swap with offline inference pipeline.",
        }
        train_examples = task_context.task_payload.get("train_examples", [])
        grid_output = train_examples[0].get("output") if train_examples else None
        candidate = {
            "candidate_id": f"llm-stub-{task_context.task_id}",
            "type": "grid",
            "grid": grid_output,
            "metadata": {
                "mock": True,
                "prompt_version": self._prompt_version,
                "confidence": 0.35,
                "note": "Stub candidate mirroring first train output.",
            },
            "smt_token": "smt:mock-token-llm",
        }
        task_context.cache_namespace["llm_stub"] = summary
        task_context.cache_namespace["candidates"] = [candidate] if grid_output is not None else []
        return ModuleResult(
            task_id=task_context.task_id,
            status=ModuleSolveStatus.PARTIAL,
            candidates=[candidate] if grid_output is not None else [],
            summary=summary,
        )

    def _on_shutdown(self, context: ModuleContext) -> None:
        context.logger.debug("LLM module teardown complete.")
