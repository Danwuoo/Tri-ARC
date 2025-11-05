from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("tools/inspect_arbitrator.py")


def _write_sample_decision(decisions_dir: Path, task_id: str) -> None:
    decisions_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task_id,
        "timestamp": "2024-05-01T00:00:00Z",
        "fallback_used": False,
        "low_confidence": False,
        "answers": [
            {
                "candidate_id": "cand-1",
                "module": "symbolic",
                "score": 0.9,
                "signature": "abc123",
                "outputs": [[[1]]],
            }
        ],
        "answers_outputs": [[[[1]]]],
        "rationale": ["Primary candidate cand-1 selected with score 0.900."],
        "rejected_candidates": [],
    }
    (decisions_dir / f"{task_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_inspect_arbitrator_cli_list(tmp_path: Path) -> None:
    decision_dir = tmp_path / "decisions"
    _write_sample_decision(decision_dir, "task-cli")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--decisions-dir", str(decision_dir), "--list"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "task-cli" in result.stdout


def test_inspect_arbitrator_cli_regenerate(tmp_path: Path) -> None:
    decision_dir = tmp_path / "decisions"
    destination = tmp_path / "outputs" / "pass2.json"
    _write_sample_decision(decision_dir, "task-cli")
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--decisions-dir",
            str(decision_dir),
            "--regenerate",
            "--destination",
            str(destination),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert destination.exists()
    data = json.loads(destination.read_text(encoding="utf-8"))
    assert "task-cli" in data
