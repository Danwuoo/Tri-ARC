from __future__ import annotations

from pathlib import Path

from arc.arbitration.models import CandidateType, VerificationStatus, normalise_candidate
from arc.arbitration.verification import VerificationRunner


def test_verification_accepts_matching_grid(tmp_path: Path) -> None:
    config = {"smt": {"enabled": False}, "arbitrator": {"verification_batch_size": 1}}
    runner = VerificationRunner(config=config, log_dir=tmp_path)
    candidate = normalise_candidate(
        "ttt",
        {"candidate_id": "grid-ok", "type": "grid", "grid": [[1]]},
        index=0,
        default_type=CandidateType.GRID,
    )
    examples = [{"input": [[0]], "output": [[1]]}]
    verified = runner.verify_candidates("task-v", [candidate], examples)
    assert verified[0].verification is not None
    assert verified[0].verification.status is VerificationStatus.PASSED


def test_verification_rejects_mismatched_grid(tmp_path: Path) -> None:
    config = {"smt": {"enabled": False}}
    runner = VerificationRunner(config=config, log_dir=tmp_path)
    candidate = normalise_candidate(
        "ttt",
        {"candidate_id": "grid-bad", "type": "grid", "grid": [[2]]},
        index=0,
        default_type=CandidateType.GRID,
    )
    examples = [{"input": [[0]], "output": [[1]]}]
    verified = runner.verify_candidates("task-v", [candidate], examples)
    assert verified[0].verification is not None
    assert verified[0].verification.status is VerificationStatus.FAILED
    assert verified[0].verification.failure_reason == "output_mismatch"
