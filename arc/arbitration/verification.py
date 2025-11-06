from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence, Tuple

from arc.common.grid import grids_equal, normalise_grid
from arc.logging_utils import append_metric
from arc.scheduler.cache import LRUCache
from arc.symbolic.dsl.types import Grid

if TYPE_CHECKING:
    from arc.symbolic.dsl.interpreter import DSLInterpreter
    from arc.symbolic.dsl.types import Program

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
        interpreter: Optional["DSLInterpreter"] = None,
        log_dir: Optional[Path] = None,
        smt_verifier: Optional[SMTAttestationVerifier] = None,
    ) -> None:
        self.config = config
        if interpreter is None:
            from arc.symbolic.dsl.interpreter import DSLInterpreter

            self.interpreter = DSLInterpreter(config=config)
        else:
            self.interpreter = interpreter
        logging_cfg = config.get("logging", {}) or {}
        global_cfg = config.get("global", {}) or {}
        log_root = Path(global_cfg.get("log_root", "logs"))
        metrics_name = logging_cfg.get("metrics_file", "metrics.jsonl")
        self._metrics_path = log_root / metrics_name
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
        self._emit_metrics = bool(logging_cfg.get("emit_metrics", True))
        smt_cfg = config.get("smt", {}) or {}
        raw_cache_size = int(smt_cfg.get("clause_cache_max_items", smt_cfg.get("max_clause_cache", 0)))
        self._clause_cache: Optional[LRUCache] = LRUCache(max(1, raw_cache_size)) if raw_cache_size > 0 else None
        self._smt_guardrails = dict(config.get("guardrails", {}).get("smt", {}) or {})
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
            if candidate.module in {"ttt", "llm"} and metadata is not None:
                example_index = metadata.get("example_index")
                if example_index is not None:
                    outputs = candidate.metadata.get("train_outputs") or []
                    for record in outputs:
                        if record.get("index") == example_index and record.get("grid") is not None:
                            return normalise_grid(record["grid"]).copy()
            normalised = normalise_grid(candidate.payload.get("grid"))
            return normalised.copy()

        cache_key: Optional[str] = None
        if self._clause_cache is not None:
            cache_key = self._clause_cache_key(candidate, grid)
            cached_output = self._clause_cache.get(cache_key)
            if cached_output is not None:
                self._record_clause_metric("hit", candidate, cache_key, metadata)
                return Grid.from_list(cached_output).copy()

        program = self._load_program(candidate)
        run_id = metadata.get("run_id") if metadata else None
        trace = self.interpreter.run(program, grid, metadata=metadata, run_id=run_id)
        final_grid = trace.final_grid.copy()
        if self._clause_cache is not None and cache_key is not None:
            self._clause_cache.set(cache_key, final_grid.to_list())
            self._record_clause_metric("miss", candidate, cache_key, metadata)
        return final_grid

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

    def _clause_cache_key(self, candidate: ArbitrationCandidate, grid: Any) -> str:
        grid_payload = normalise_grid(grid).to_list()
        payload = {
            "signature": candidate.compute_signature(),
            "grid": grid_payload,
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _record_clause_metric(
        self,
        kind: str,
        candidate: ArbitrationCandidate,
        cache_key: str,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        if not self._emit_metrics or self._metrics_path is None:
            return
        payload: Dict[str, Any] = {
            "event": "smt_clause_cache",
            "kind": kind,
            "cache_key": cache_key,
            "candidate_module": candidate.module,
            "candidate_signature": candidate.compute_signature(),
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        if metadata:
            task_id = metadata.get("task_id")
            if task_id is not None:
                payload["task_id"] = task_id
            example_index = metadata.get("example_index")
            if example_index is not None:
                payload["example_index"] = example_index
        if self._clause_cache is not None:
            stats = self._clause_cache.stats()
            payload["stats"] = stats
            miss_rate = 1.0 - float(stats.get("hit_rate", 0.0))
            payload["miss_rate"] = miss_rate
            threshold = self._smt_guardrails.get("clause_cache_miss_threshold")
            if threshold is not None and miss_rate > float(threshold):
                payload.setdefault("alerts", []).append({
                    "type": "smt_clause_miss_rate",
                    "limit": float(threshold),
                    "observed": miss_rate,
                })
        append_metric(self._metrics_path, payload)

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

    def _load_program(self, candidate: ArbitrationCandidate) -> "Program":
        program_payload = candidate.payload.get("program")
        if program_payload is None:
            raise ValueError("Program candidate missing program payload.")
        from arc.symbolic.dsl.parser import parse_program
        from arc.symbolic.dsl.types import Program, Stage

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
