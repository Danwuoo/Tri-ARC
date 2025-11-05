from __future__ import annotations

from typing import Any, Dict

from arc.core import ModuleResult, ModuleSolveStatus, ModuleTaskContext

from . import LLMModule


class MockLLMModule(LLMModule):
    """Mocked LLM module returning deterministic payloads for smoke tests."""

    def __init__(self, config: Dict[str, Any]) -> None:
        mock_cfg = dict(config)
        mock_cfg.setdefault("llm", {}).update({"enabled": True})
        super().__init__(mock_cfg, prompt_version="mock")

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:  # type: ignore[override]
        summary = {
            "lane": self.module_name,
            "prompt_version": "mock",
            "message": "Mock LLM emitted canned candidate.",
        }
        candidate = {
            "program": "return identity grid",
            "metadata": {"mock": True},
            "verification_passed": False,
        }
        return ModuleResult(
            task_id=task_context.task_id,
            status=ModuleSolveStatus.SUCCESS,
            candidates=[candidate],
            summary=summary,
        )
