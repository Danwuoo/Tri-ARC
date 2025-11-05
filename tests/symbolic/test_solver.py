from __future__ import annotations

from pathlib import Path

from arc.config import load_config
from arc.symbolic.solver import SymbolicSolver


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
