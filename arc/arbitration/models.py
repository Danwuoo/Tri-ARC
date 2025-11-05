from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class CandidateType(str, Enum):
    """Normalised candidate surface types handled by the arbitrator."""

    PROGRAM = "program"
    GRID = "grid"
    FALLBACK = "fallback"


class VerificationStatus(str, Enum):
    """Verification outcomes used when filtering candidates."""

    PASSED = "passed"
    FAILED = "failed"
    REJECTED = "rejected"
    SKIPPED = "skipped"


@dataclass
class VerificationTrace:
    """Detailed verification trace captured for audits."""

    example_index: int
    input_grid: Any
    expected_output: Any
    produced_output: Any
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationRecord:
    """Summary of verification for a single candidate."""

    status: VerificationStatus
    duration_ms: float
    traces: List[VerificationTrace] = field(default_factory=list)
    failure_reason: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "failure_reason": self.failure_reason,
            "extras": self.extras,
            "traces": [
                {
                    "example_index": trace.example_index,
                    "input_grid": trace.input_grid,
                    "expected_output": trace.expected_output,
                    "produced_output": trace.produced_output,
                    "notes": trace.notes,
                }
                for trace in self.traces
            ],
        }


@dataclass
class ScoreBreakdown:
    """Scoring diagnostics preserved for replay tooling."""

    module_prior: float
    confidence: float
    runtime_penalty: float
    diversity_bonus: float
    extras: Dict[str, Any] = field(default_factory=dict)

    def total(self) -> float:
        return max(0.0, min(1.0, self.module_prior + self.confidence + self.diversity_bonus - self.runtime_penalty))

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "module_prior": self.module_prior,
            "confidence": self.confidence,
            "runtime_penalty": self.runtime_penalty,
            "diversity_bonus": self.diversity_bonus,
            "total": self.total(),
        }
        if self.extras:
            payload["extras"] = self.extras
        return payload


@dataclass
class ArbitrationCandidate:
    """Normalised candidate record consumed by verification and scoring."""

    candidate_id: str
    module: str
    candidate_type: CandidateType
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    smt_token: Optional[str] = None
    verification: Optional[VerificationRecord] = None
    score: Optional[ScoreBreakdown] = None
    signature: Optional[str] = None

    def normalised_score(self) -> float:
        return self.score.total() if self.score else 0.0

    def is_verified(self) -> bool:
        return self.verification is not None and self.verification.status == VerificationStatus.PASSED

    def compute_signature(self) -> str:
        if self.signature:
            return self.signature
        signature_fields: List[Any] = [
            self.module,
            self.candidate_type.value,
            self.payload.get("program"),
            self.payload.get("grid"),
            self.metadata.get("transforms"),
        ]
        serialised = json.dumps(signature_fields, sort_keys=True, default=_fallback_json_encoder)
        digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
        self.signature = digest
        return digest

    def transformation_summary(self) -> str:
        if "transformation_summary" in self.metadata:
            return str(self.metadata["transformation_summary"])
        if self.candidate_type == CandidateType.PROGRAM and "program" in self.payload:
            program = self.payload["program"]
            if isinstance(program, str):
                return program.splitlines()[0][:80]
            if isinstance(program, Sequence):
                return repr(program[:3])
        if self.candidate_type == CandidateType.GRID:
            return "grid_candidate"
        return "fallback"


def _fallback_json_encoder(value: Any) -> Any:
    if isinstance(value, (set, tuple)):
        return list(value)
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return value.__dict__
        except Exception:
            pass
    return str(value)


def normalise_candidate(
    module: str,
    raw_candidate: Dict[str, Any],
    index: int,
    *,
    default_type: CandidateType = CandidateType.PROGRAM,
) -> ArbitrationCandidate:
    """Normalise heterogeneous module candidates into a standard payload."""
    candidate_type = _infer_candidate_type(raw_candidate, default_type=default_type)
    candidate_id = raw_candidate.get("candidate_id") or f"{module}-{index}"
    payload = {}
    metadata = dict(raw_candidate.get("metadata") or {})

    if candidate_type == CandidateType.PROGRAM:
        program = raw_candidate.get("program") or raw_candidate.get("program_source")
        payload["program"] = program
    elif candidate_type == CandidateType.GRID:
        payload["grid"] = raw_candidate.get("grid") or raw_candidate.get("output")
    else:
        payload.update(raw_candidate.get("payload", {}))

    provenance = {
        "module": module,
        "source": raw_candidate.get("source", module),
        "raw_index": index,
    }
    if "provenance" in raw_candidate:
        provenance.update(raw_candidate["provenance"])

    smt_token = raw_candidate.get("smt_token") or metadata.get("smt_token")

    candidate = ArbitrationCandidate(
        candidate_id=str(candidate_id),
        module=module,
        candidate_type=candidate_type,
        payload=payload,
        metadata=metadata,
        provenance=provenance,
        smt_token=smt_token,
    )
    candidate.signature = candidate.compute_signature()
    return candidate


def _infer_candidate_type(raw_candidate: Dict[str, Any], *, default_type: CandidateType) -> CandidateType:
    explicit_type = raw_candidate.get("type") or raw_candidate.get("candidate_type")
    if explicit_type:
        try:
            return CandidateType(str(explicit_type))
        except ValueError:
            pass
    if "program" in raw_candidate or "program_source" in raw_candidate:
        return CandidateType.PROGRAM
    if "grid" in raw_candidate or "output" in raw_candidate:
        return CandidateType.GRID
    return default_type


def normalise_candidates(
    module: str,
    raw_candidates: Iterable[Dict[str, Any]],
    *,
    default_type: CandidateType = CandidateType.PROGRAM,
) -> List[ArbitrationCandidate]:
    return [normalise_candidate(module, raw, index, default_type=default_type) for index, raw in enumerate(raw_candidates)]

