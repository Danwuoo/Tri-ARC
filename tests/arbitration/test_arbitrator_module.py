from __future__ import annotations

import json
import logging
from pathlib import Path

from arc.arbitration import ArbitratorModule
from arc.core import ModuleContext, ModuleSolveStatus


def _build_context(tmp_path: Path, config: dict, shared_cache: dict) -> ModuleContext:
    logger = logging.getLogger("test.arbitrator")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return ModuleContext(
        module_name="arbitrator",
        config=config,
        shared_cache=shared_cache,
        run_id="test-run",
        logger=logger,
        metrics_sink=lambda payload: None,
    )


def test_arbitrator_selects_verified_candidate(tmp_path: Path) -> None:
    outputs_dir = tmp_path / "outputs"
    reports_dir = tmp_path / "reports"
    logs_dir = tmp_path / "logs"
    config = {
        "arbitrator": {
            "outputs_dir": str(outputs_dir),
            "reports_dir": str(reports_dir),
            "logs_dir": str(logs_dir),
            "confidence_threshold": 0.5,
            "diversity_gap": 0.1,
        },
        "smt": {"enabled": False},
    }
    shared_cache = {
        "symbolic": {
            "task-alpha": {
                "candidates": [
                    {
                        "candidate_id": "sym-1",
                        "type": "grid",
                        "grid": [[1]],
                        "metadata": {"confidence": 0.9},
                    }
                ]
            }
        }
    }
    module = ArbitratorModule(config=config)
    context = _build_context(tmp_path, config, shared_cache)
    module.initialize(context)
    payload = {
        "task_id": "task-alpha",
        "train_examples": [{"input": [[0]], "output": [[1]]}],
        "test_examples": [{"input": [[0]]}],
    }
    task_context = module.prepare_task(payload)
    result = module.solve(task_context)
    assert result.status is ModuleSolveStatus.SUCCESS
    assert result.summary["fallback_used"] is False
    assert len(result.summary["answers"]) == 1
    answer = result.summary["answers"][0]
    assert answer["outputs"] == [[[1]]]
    pass2_path = outputs_dir / "pass2.json"
    assert pass2_path.exists()
    recorded = json.loads(pass2_path.read_text(encoding="utf-8"))
    assert recorded["task-alpha"] == [[[[1]]]]
    health_files = list(reports_dir.glob("arbitrator_health_*.md"))
    assert health_files, "Health dashboard not generated."
    module.shutdown()


def test_arbitrator_triggers_fallback_when_needed(tmp_path: Path) -> None:
    outputs_dir = tmp_path / "outputs"
    reports_dir = tmp_path / "reports"
    logs_dir = tmp_path / "logs"
    config = {
        "arbitrator": {
            "outputs_dir": str(outputs_dir),
            "reports_dir": str(reports_dir),
            "logs_dir": str(logs_dir),
            "confidence_threshold": 0.8,
            "diversity_gap": 0.1,
        },
        "smt": {"enabled": False},
    }
    shared_cache = {
        "ttt": {
            "task-beta": {
                "candidates": [
                    {
                        "candidate_id": "ttt-1",
                        "type": "grid",
                        "grid": [[2]],
                        "metadata": {"confidence": 0.2},
                    }
                ]
            }
        }
    }
    module = ArbitratorModule(config=config)
    context = _build_context(tmp_path, config, shared_cache)
    module.initialize(context)
    payload = {
        "task_id": "task-beta",
        "train_examples": [{"input": [[0]], "output": [[1]]}],
        "test_examples": [{"input": [[0]]}],
    }
    task_context = module.prepare_task(payload)
    result = module.solve(task_context)
    assert result.summary["fallback_used"] is True
    assert len(result.summary["answers"]) == 1
    answer = result.summary["answers"][0]
    assert answer["module"] == "fallback"
    assert answer["outputs"] == [[[0]]]
    module.shutdown()
