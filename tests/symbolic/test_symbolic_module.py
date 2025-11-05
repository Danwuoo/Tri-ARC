from __future__ import annotations

import logging
from typing import Any, Dict

import pytest

from arc.core import ModuleContext, ModuleTaskContext
from arc.symbolic import SymbolicModule
from arc.symbolic.solver import SolverResult, SolverTelemetry


class DummySolver:
    def __init__(self, result: SolverResult) -> None:
        self.result = result
        self.calls: list[Dict[str, Any]] = []

    def solve(self, task: Dict[str, Any]) -> SolverResult:
        self.calls.append(task)
        return self.result


@pytest.fixture
def module_context() -> ModuleContext:
    logger = logging.getLogger("test.symbolic")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return ModuleContext(
        module_name="symbolic",
        config={"symbolic": {"enabled": True}},
        shared_cache={},
        run_id="test-run",
        logger=logger,
        metrics_sink=None,
    )


def build_solver_result(status: str = "success") -> SolverResult:
    telemetry = SolverTelemetry(
        frontier_report=None,
        frontier_log=None,
        diagnostics=[],
        events=[],
        progress_path=None,
        elapsed_s=0.25,
        expansions=10,
        generated_nodes=25,
    )
    summary = {
        "status": status,
        "elapsed_s": telemetry.elapsed_s,
        "expansions": telemetry.expansions,
        "nodes": telemetry.generated_nodes,
        "solutions": 0,
    }
    return SolverResult(task_id="task-1", status=status, candidates=[], telemetry=telemetry, summary=summary)


def test_symbolic_module_success_flow(module_context: ModuleContext) -> None:
    solver_result = build_solver_result("success")
    dummy_solver = DummySolver(solver_result)
    module = SymbolicModule(config={"symbolic": {"enabled": True}}, solver_factory=lambda cfg: dummy_solver)

    module.initialize(module_context)
    task = {"task_id": "task-1", "train_examples": []}
    prepared: ModuleTaskContext = module.prepare_task(task)
    result = module.solve(prepared)

    assert dummy_solver.calls  # ensure solver invoked
    assert result.status.value == "success"
    assert result.summary["lane"] == "symbolic"
    assert "telemetry_snapshot" in result.summary
    assert "solver_summary" in prepared.cache_namespace
    module.shutdown()


def test_symbolic_module_disabled_skips(module_context: ModuleContext) -> None:
    module = SymbolicModule(config={"symbolic": {"enabled": False}})
    module.initialize(module_context)
    prepared = module.prepare_task({"task_id": "task-2"})
    result = module.solve(prepared)
    assert result.status.value == "skipped"
    module.shutdown()


def test_symbolic_module_legacy_adapter(module_context: ModuleContext) -> None:
    solver_result = build_solver_result("no_solution")
    module = SymbolicModule(config={"symbolic": {"enabled": True}}, solver_factory=lambda cfg: DummySolver(solver_result))
    module.initialize(module_context)
    with pytest.warns(DeprecationWarning):
        legacy_payload = module.solve_task({"task_id": "legacy-1"})
    assert legacy_payload["status"] == "failed"
