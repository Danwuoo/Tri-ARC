from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from arc.common.grid import grids_equal, normalise_grid
from arc.symbolic.dsl.parser import parse_program
from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.dsl.interpreter import DSLInterpreter

from .models import (
    ArbitrationCandidate,
    CandidateType,
    VerificationRecord,
    VerificationStatus,
    VerificationTrace,
)

LOGGER = logging.getLogger("arc.arbitration.verification")


class SMTAttestationError(RuntimeError):
    """Raised when SMT attestation requirements fail."""


@dataclass
class SMTAttestationVerifier:
    """Lightweight verifier ensuring candidates embed valid SMT attestation tokens."""

    enabled: bool
    accepted_prefix: str

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "SMTAttestationVerifier":
        smt_cfg = config.get("smt", {})
        enabled = bool(smt_cfg.get("enabled", True))
        prefix = str(smt_cfg.get("token_prefix", "smt:"))
        return cls(enabled=enabled, accepted_prefix=prefix)

    def verify(self, candidate: ArbitrationCandidate) -> None:
        if not self.enabled:
            return

        if candidate.candidate_type not in {CandidateType.PROGRAM, CandidateType.FALLBACK}:
            return

        requires_token = candidate.module in {"llm", "symbolic"} or candidate.metadata.get("requires_smt", False)
        if not requires_token:
            return

        token = candidate.smt_token or candidate.metadata.get("smt_token")
        if not token:
            raise SMTAttestationError("missing_smt_token")
        token = str(token)
        if not token.startswith(self.accepted_prefix):
            raise SMTAttestationError("invalid_smt_token_prefix")
        if len(token) < len(self.accepted_prefix) + 8:
            raise SMTAttestationError("smt_token_too_short")


class VerificationRunner:
    """Executes deterministic verification across candidate types."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        interpreter: Optional[DSLInterpreter] = None,
        log_dir: Optional[Path] = None,
        smt_verifier: Optional[SMTAttestationVerifier] = None,
    ) -> None:
        self.config = config
        self.interpreter = interpreter or DSLInterpreter(config=config)
        self.log_dir = Path(log_dir or "logs/arbitrator/verification")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.smt_verifier = smt_verifier or SMTAttestationVerifier.from_config(config)
        self.batch_size = int(config.get("arbitrator", {}).get("verification_batch_size", 1))

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def verify_candidates(
        self,
        task_id: str,
        candidates: Sequence[ArbitrationCandidate],
        train_examples: Sequence[Dict[str, Any]],
    ) -> List[ArbitrationCandidate]:
        verified: List[ArbitrationCandidate] = []
        for candidate in candidates:
            record = self._verify_single(task_id, candidate, train_examples)
            candidate.verification = record
            self._emit_trace(task_id, candidate)
            verified.append(candidate)
        return verified

    def execute_candidate(
        self,
        candidate: ArbitrationCandidate,
        grid: Any,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Grid:
        """Execute candidate deterministically (without verification feedback)."""
        if candidate.candidate_type == CandidateType.GRID:
            normalised = normalise_grid(candidate.payload.get("grid"))
            return normalised.copy()

        program = self._load_program(candidate)
        run_id = metadata.get("run_id") if metadata else None
        trace = self.interpreter.run(program, grid, metadata=metadata, run_id=run_id)
        return trace.final_grid.copy()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _verify_single(
        self,
        task_id: str,
        candidate: ArbitrationCandidate,
        train_examples: Sequence[Dict[str, Any]],
    ) -> VerificationRecord:
        start = time.perf_counter()
        traces: List[VerificationTrace] = []

        try:
            self.smt_verifier.verify(candidate)
        except SMTAttestationError as exc:
            duration_ms = (time.perf_counter() - start) * 1000.0
            reason = f"smt_attestation_failed:{exc}"
            LOGGER.debug(
                "Candidate %s rejected due to SMT attestation failure (%s).",
                candidate.candidate_id,
                exc,
            )
            return VerificationRecord(
                status=VerificationStatus.REJECTED,
                duration_ms=duration_ms,
                traces=[],
                failure_reason=reason,
            )

        for index, example in enumerate(train_examples):
            expected_output = example.get("output")
            if expected_output is None:
                continue
            try:
                produced = self.execute_candidate(
                    candidate,
                    example.get("input"),
                    metadata={"task_id": task_id, "example_index": index},
                )
            except Exception as exc:  # pragma: no cover - interpreter exceptions captured
                trace = VerificationTrace(
                    example_index=index,
                    input_grid=example.get("input"),
                    expected_output=expected_output,
                    produced_output=None,
                    notes={"error": repr(exc)},
                )
                traces.append(trace)
                duration_ms = (time.perf_counter() - start) * 1000.0
                return VerificationRecord(
                    status=VerificationStatus.REJECTED,
                    duration_ms=duration_ms,
                    traces=traces,
                    failure_reason=f"execution_error:{type(exc).__name__}",
                )

            produced_grid = produced
            if not isinstance(produced_grid, Grid):
                produced_grid = normalise_grid(produced_grid)

            expected_grid = normalise_grid(expected_output)
            if not grids_equal(expected_grid, produced_grid):
                trace = VerificationTrace(
                    example_index=index,
                    input_grid=example.get("input"),
                    expected_output=expected_output,
                    produced_output=produced_grid.to_list(),
                    notes={
                        "reason": "mismatch",
                        "difference": self._grid_difference(expected_grid, produced_grid),
                    },
                )
                traces.append(trace)
                duration_ms = (time.perf_counter() - start) * 1000.0
                return VerificationRecord(
                    status=VerificationStatus.FAILED,
                    duration_ms=duration_ms,
                    traces=traces,
                    failure_reason="output_mismatch",
                )

        duration_ms = (time.perf_counter() - start) * 1000.0
        return VerificationRecord(
            status=VerificationStatus.PASSED,
            duration_ms=duration_ms,
            traces=traces,
        )

    def _emit_trace(self, task_id: str, candidate: ArbitrationCandidate) -> None:
        record = candidate.verification
        if record is None:
            return
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"{task_id}_{candidate.candidate_id}_{timestamp}.json"
        path = self.log_dir / filename
        payload = {
            "task_id": task_id,
            "candidate_id": candidate.candidate_id,
            "module": candidate.module,
            "status": record.status.value,
            "duration_ms": record.duration_ms,
            "failure_reason": record.failure_reason,
            "score": candidate.score.to_dict() if candidate.score else None,
            "metadata": candidate.metadata,
            "provenance": candidate.provenance,
            "traces": record.to_dict()["traces"],
        }
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except Exception as exc:  # pragma: no cover - trace emission best effort
            LOGGER.warning("Failed to write verification trace for %s: %s", candidate.candidate_id, exc)

    def _load_program(self, candidate: ArbitrationCandidate) -> Program:
        program_payload = candidate.payload.get("program")
        if program_payload is None:
            raise ValueError("Program candidate missing program payload.")
        if isinstance(program_payload, Program):
            return program_payload
        if isinstance(program_payload, str):
            return parse_program(program_payload)
        if isinstance(program_payload, Sequence):
            stages: List[Stage] = []
            for item in program_payload:
                if not isinstance(item, Sequence) or len(item) != 2:
                    raise ValueError(f"Invalid stage representation: {item!r}")
                operator, arguments = item
                if not isinstance(arguments, Sequence):
                    raise ValueError(f"Stage arguments must be sequence; received {type(arguments).__name__}.")
                stages.append(Stage(operator=operator, arguments=tuple(arguments)))
            return Program(tuple(stages))
        raise TypeError(f"Unsupported program payload type: {type(program_payload).__name__}.")

    def _grid_difference(self, expected: Grid, produced: Grid) -> Dict[str, Any]:
        if expected.shape != produced.shape:
            return {
                "type": "shape_mismatch",
                "expected_shape": expected.shape,
                "produced_shape": produced.shape,
            }
        mismatches: List[Tuple[int, int]] = []
        exp = expected.data
        prod = produced.data
        rows, cols = expected.shape
        for row in range(rows):
            for col in range(cols):
                if int(exp[row, col]) != int(prod[row, col]):
                    mismatches.append((row, col))
                    if len(mismatches) >= 5:
                        break
            if len(mismatches) >= 5:
                break
        return {
            "type": "value_mismatch",
            "first_positions": mismatches,
        }


__all__ = ["VerificationRunner", "SMTAttestationVerifier", "SMTAttestationError"]

