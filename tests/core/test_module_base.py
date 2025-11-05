from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import pytest

from arc.core import (
    ModuleCapabilities,
    ModuleContext,
    ModuleError,
    ModuleResult,
    ModuleSolveStatus,
    ModuleTaskContext,
    SolverModule,
)


class SampleModule(SolverModule):
    module_name = "sample_module"
    capabilities = ModuleCapabilities(
        supports_partial_results=True,
        supports_resume=False,
        requires_gpu=False,
    )

    def __init__(self, config: Dict[str, Any], *, record: List[Dict[str, Any]]) -> None:
        super().__init__(config)
        self.record = record

    def _on_initialize(self, context: ModuleContext) -> None:
        self.record.append({"stage": "initialize", "run_id": context.run_id})
        context.shared_cache["initialised"] = True

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        task_context.cache_namespace["prepared"] = True
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        self.record.append({"stage": "solve", "task_id": task_context.task_id})
        status = ModuleSolveStatus.SUCCESS
        summary = {"prepared": task_context.cache_namespace.get("prepared", False)}
        return ModuleResult(task_id=task_context.task_id, status=status, summary=summary)

    def _on_shutdown(self, context: ModuleContext) -> None:
        self.record.append({"stage": "shutdown"})
        context.shared_cache["shutdown"] = True


class IncompleteModule(SolverModule):
    module_name = "incomplete_module"


@pytest.fixture
def metrics_buffer() -> List[Dict[str, Any]]:
    return []


@pytest.fixture
def module_context(metrics_buffer: List[Dict[str, Any]]) -> ModuleContext:
    logger = logging.getLogger("test.module")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return ModuleContext(
        module_name="sample_module",
        config={},
        shared_cache={},
        run_id="run-001",
        logger=logger,
        metrics_sink=metrics_buffer.append,
    )


def test_successful_lifecycle(module_context: ModuleContext, metrics_buffer: List[Dict[str, Any]]) -> None:
    record: List[Dict[str, Any]] = []
    module = SampleModule(config={}, record=record)

    module.initialize(module_context)
    assert module.state.name.lower() == "ready"

    prepared = module.prepare_task({"task_id": "task-123", "examples": []})
    assert isinstance(prepared, ModuleTaskContext)
    assert prepared.cache_namespace["prepared"] is True

    result = module.solve(prepared)
    assert isinstance(result, ModuleResult)
    assert result.status is ModuleSolveStatus.SUCCESS
    assert result.summary["prepared"] is True
    assert module.last_telemetry is not None

    module.shutdown()
    assert module.state.name.lower() == "shutdown"
    assert module_context.shared_cache["shutdown"] is True

    events = [entry["event"] for entry in metrics_buffer]
    assert events.count("module_start") == events.count("module_stop")
    assert record == [
        {"stage": "initialize", "run_id": "run-001"},
        {"stage": "solve", "task_id": "task-123"},
        {"stage": "shutdown"},
    ]


def test_missing_solve_handler_raises_actionable_error(module_context: ModuleContext) -> None:
    module = IncompleteModule(config={})
    module.initialize(module_context)
    prepared = module.prepare_task({"task_id": "task-xyz"})

    with pytest.raises(ModuleError) as excinfo:
        module.solve(prepared)
    assert "has not implemented required handler" in str(excinfo.value)


def test_cannot_prepare_before_initialise(metrics_buffer: List[Dict[str, Any]]) -> None:
    logger = logging.getLogger("test.detached")
    module = SampleModule(config={}, record=[])
    with pytest.raises(ModuleError):
        module.prepare_task({"task_id": "no-init"})


def test_guardrail_emits_metrics(module_context: ModuleContext, metrics_buffer: List[Dict[str, Any]]) -> None:
    module_context.extras["guardrails"] = {"max_duration_s": 0.0}

    class SlowModule(SampleModule):
        def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
            time.sleep(0.001)
            return super()._on_solve(task_context)

    module = SlowModule(config={}, record=[])
    module.initialize(module_context)
    prepared = module.prepare_task({"task_id": "guardrail"})
    module.solve(prepared)
    module.shutdown()

    guardrail_events = [entry for entry in metrics_buffer if entry.get("event") == "guardrail_trigger"]
    assert guardrail_events
    alert = guardrail_events[0]["alerts"][0]
    assert alert["type"] == "duration"
