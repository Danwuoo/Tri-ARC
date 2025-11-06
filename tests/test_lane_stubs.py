from __future__ import annotations

import logging

from arc.core import ModuleContext
from arc.llm import LLMModule
from arc.llm.mocks import MockLLMModule
from arc.ttt import TTTModule
from arc.ttt.mocks import MockTTTModule


def build_context(name: str, config: dict) -> ModuleContext:
    logger = logging.getLogger(f"test.{name}")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return ModuleContext(
        module_name=name,
        config=config,
        shared_cache={},
        run_id="test-run",
        logger=logger,
        metrics_sink=None,
    )


def build_payload() -> dict:
    base_grid = [[1, 2], [3, 4]]
    return {
        "task_id": "sample-task",
        "train_examples": [{"input": base_grid, "output": base_grid}],
        "eval_examples": [{"input": base_grid}],
    }


def test_ttt_module_generates_candidate() -> None:
    config = {"ttt": {"enabled": True}}
    module = TTTModule(config=config)
    module.initialize(build_context("ttt", config))
    prepared = module.prepare_task(build_payload())
    result = module.solve(prepared)
    assert result.status.value in {"success", "partial"}
    assert result.candidates
    candidate = result.candidates[0]
    metadata = candidate.get("metadata", {})
    train_outputs = metadata.get("train_outputs", [])
    assert train_outputs and train_outputs[0]["grid"] == [[1, 2], [3, 4]]
    module.shutdown()


def test_llm_module_generates_candidate() -> None:
    config = {"llm": {"enabled": True}}
    module = LLMModule(config=config)
    module.initialize(build_context("llm", config))
    prepared = module.prepare_task(build_payload())
    result = module.solve(prepared)
    assert result.status.value in {"success", "partial"}
    assert result.candidates
    candidate = result.candidates[0]
    metadata = candidate.get("metadata", {})
    assert metadata.get("operation")
    train_outputs = metadata.get("train_outputs", [])
    assert train_outputs and train_outputs[0]["grid"] is not None
    module.shutdown()


def test_mock_variants_return_success() -> None:
    ttt_config = {}
    llm_config = {}
    ttt = MockTTTModule(ttt_config)
    llm = MockLLMModule(llm_config)
    ttt.initialize(build_context("ttt", ttt_config))
    llm.initialize(build_context("llm", llm_config))

    ttt_result = ttt.solve(ttt.prepare_task({"task_id": "mock-ttt"}))
    llm_result = llm.solve(llm.prepare_task({"task_id": "mock-llm"}))

    assert ttt_result.status.value == "success"
    assert llm_result.status.value == "success"

    ttt.shutdown()
    llm.shutdown()
