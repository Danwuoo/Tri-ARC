from __future__ import annotations

import json
from pathlib import Path

from arc.config import load_config
from arc.symbolic.dsl.types import Stage
from arc.symbolic.heuristics.base import HeuristicContext, HeuristicResult, HeuristicScorer
from arc.symbolic.search.generator import ExpansionCandidate, ProgramEnumerator
from arc.symbolic.solver import SymbolicSolver


class StubEnumerator(ProgramEnumerator):
    def __init__(self) -> None:
        super().__init__(name="stub-enumerator")

    def expand(self, node, context):
        if node.depth == 0:
            yield ExpansionCandidate(
                stage=Stage(operator="identity", arguments=()),
                metadata={"note": "stub"},
                incremental_cost=0.0,
                is_solution=True,
                reason="stub_identity",
            )
        return []


class ConstantHeuristic(HeuristicScorer):
    def __init__(self) -> None:
        super().__init__(name="constant")

    def initialise(self, context: HeuristicContext) -> None:
        super().initialise(context)

    def score_node(self, node):
        return HeuristicResult(score=0.5, components={"base": 0.5}, reasoning={})


def test_symbolic_solver_identity_solution(tmp_path):
    log_root = tmp_path / "logs"
    cache_root = tmp_path / "cache"
    reports_root = tmp_path / "reports"
    overrides = {
        "global": {
            "log_root": str(log_root),
            "cache_root": str(cache_root),
            "data_root": str(tmp_path / "data"),
        },
        "symbolic": {
            "telemetry": {
                "progress_file": str(log_root / "symbolic" / "solve_progress.jsonl"),
                "diagnostics_dir": str(log_root / "symbolic" / "diagnostics"),
                "checkpoint_dir": str(cache_root / "symbolic" / "checkpoints"),
            },
            "frontier": {
                "report_dir": str(reports_root / "symbolic"),
                "log_path": str(log_root / "symbolic" / "symbolic_frontier.log"),
                "snapshot_interval_s": 0.1,
            },
            "max_depth": 2,
            "max_expansions": 10,
            "max_nodes": 10,
            "soft_timeout_s": 5,
            "hard_timeout_s": 5,
            "heuristics": {
                "neural": {"enabled": False},
            },
        },
    }
    config = load_config(overrides=overrides)
    solver = SymbolicSolver(config=config)
    task = {
        "task_id": "identity_demo",
        "train_examples": [
            {"input": [[2, 2], [2, 2]], "output": [[2, 2], [2, 2]]},
        ],
    }
    result = solver.solve(task)
    assert result.status == "success"
    assert any(candidate.verification_passed for candidate in result.candidates)
    assert result.telemetry.frontier_report is not None
    assert Path(result.telemetry.frontier_report).exists()
    assert result.telemetry.progress_path is not None
    assert Path(result.telemetry.progress_path).exists()


def test_symbolic_solver_pause_and_resume(tmp_path):
    log_root = tmp_path / "logs"
    cache_root = tmp_path / "cache"
    reports_root = tmp_path / "reports"
    control_path = tmp_path / "control.json"
    control_path.write_text(json.dumps({"action": "pause"}), encoding="utf-8")

    overrides = {
        "global": {
            "log_root": str(log_root),
            "cache_root": str(cache_root),
            "data_root": str(tmp_path / "data"),
        },
        "symbolic": {
            "telemetry": {
                "progress_file": str(log_root / "symbolic" / "solve_progress.jsonl"),
                "diagnostics_dir": str(log_root / "symbolic" / "diagnostics"),
                "checkpoint_dir": str(cache_root / "symbolic" / "checkpoints"),
                "control_dir": str(cache_root / "symbolic" / "control"),
            },
            "frontier": {
                "report_dir": str(reports_root / "symbolic"),
                "log_path": str(log_root / "symbolic" / "symbolic_frontier.log"),
                "snapshot_interval_s": 0.1,
            },
            "max_depth": 2,
            "max_expansions": 10,
            "max_nodes": 10,
            "soft_timeout_s": 5,
            "hard_timeout_s": 5,
            "heuristics": {
                "neural": {"enabled": False},
            },
        },
    }
    config = load_config(overrides=overrides)
    solver = SymbolicSolver(config=config, enumerator=StubEnumerator(), heuristic=ConstantHeuristic())

    task = {
        "task_id": "pause_task",
        "train_examples": [
            {"input": [[2, 2], [2, 2]], "output": [[2, 2], [2, 2]]},
        ],
        "control": {"signal_path": str(control_path)},
    }

    paused_result = solver.solve(task)
    assert paused_result.status == "partial"
    assert paused_result.telemetry.checkpoint_path is not None
    checkpoint_path = Path(paused_result.telemetry.checkpoint_path)
    assert checkpoint_path.exists()
    assert paused_result.summary.get("control_reason") == "pause"

    control_path.write_text(json.dumps({"action": "resume"}), encoding="utf-8")
    resume_task = dict(task)
    resume_task["resume"] = True
    resumed_result = solver.solve(resume_task)
    assert resumed_result.status == "success"
    assert any(candidate.verification_passed for candidate in resumed_result.candidates)
