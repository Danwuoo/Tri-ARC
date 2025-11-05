from __future__ import annotations

from typing import Any, Dict

from arc.core import ModuleResult, ModuleSolveStatus, ModuleTaskContext

from . import TTTModule


class MockTTTModule(TTTModule):
    """Lightweight mock for CI and smoke tests."""

    def __init__(self, config: Dict[str, Any]) -> None:
        mock_cfg = dict(config)
        mock_cfg.setdefault("ttt", {}).update({"enabled": True})
        super().__init__(mock_cfg, profile="mock")

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:  # type: ignore[override]
        summary = {
            "lane": self.module_name,
            "profile": "mock",
            "message": "Mock TTT module emitted static candidate.",
        }
        candidate = {
            "program": [],
            "score": 0.0,
            "metadata": {"mock": True},
            "verification_passed": False,
        }
        return ModuleResult(
            task_id=task_context.task_id,
            status=ModuleSolveStatus.SUCCESS,
            candidates=[candidate],
            summary=summary,
        )
