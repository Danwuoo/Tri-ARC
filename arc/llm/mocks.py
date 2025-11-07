from __future__ import annotations

from typing import Any, Dict

from arc.core import ModuleResult, ModuleSolveStatus, ModuleTaskContext

from . import LLMModule


class MockLLMModule(LLMModule):
    """Mocked LLM module returning deterministic payloads for smoke tests."""

    def __init__(self, config: Dict[str, Any]) -> None:
        mock_cfg = dict(config)
        llm_section = mock_cfg.setdefault("llm", {})
        llm_section.update({"enabled": True, "backend": "stub"})
        super().__init__(mock_cfg, prompt_version="mock")

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:  # type: ignore[override]
        summary = {
            "lane": self.module_name,
            "prompt_version": "mock",
            "engine": "mock",
            "message": "Mock LLM emitted canned candidate.",
        }
        candidate = {
            "candidate_id": f"mock-{task_context.task_id}",
            "program": "(pipeline (apply identity))",
            "metadata": {
                "prompt_version": "mock",
                "prompt_variant": "mock",
                "engine": "mock",
                "confidence": 0.5,
                "mock": True,
                "train_outputs": [],
                "eval_outputs": [],
            },
        }
        return ModuleResult(
            task_id=task_context.task_id,
            status=ModuleSolveStatus.SUCCESS,
            candidates=[candidate],
            summary=summary,
        )
