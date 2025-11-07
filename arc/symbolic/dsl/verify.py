from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from arc.symbolic.dsl.interpreter import DSLInterpreter
from arc.symbolic.dsl.parser import parse_program
from arc.symbolic.dsl.types import Region


@dataclass(frozen=True)
class VerificationCase:
    name: str
    path: Path
    program: str
    input_grid: Sequence[Sequence[int]]
    expected_grid: Optional[Sequence[Sequence[int]]] = None
    expected_region_mask: Optional[Sequence[Sequence[int]]] = None
    expected_value: Optional[Any] = None
    focus_stage: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseResult:
    case: VerificationCase
    passed: bool
    duration_ms: float
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationSummary:
    results: List[CaseResult]
    elapsed_ms: float
    log_path: Optional[Path] = None

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed(self) -> int:
        return sum(1 for result in self.results if not result.passed)

    @property
    def total(self) -> int:
        return len(self.results)


def _load_case(path: Path) -> VerificationCase:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    return VerificationCase(
        name=payload.get("name", path.stem),
        path=path,
        program=payload["program"],
        input_grid=payload["input_grid"],
        expected_grid=payload.get("expected_grid"),
        expected_region_mask=payload.get("expected_region_mask"),
        expected_value=payload.get("expected_value"),
        focus_stage=payload.get("focus_stage"),
        metadata=metadata,
    )


def _format_grid(grid: Any) -> Any:
    if hasattr(grid, "to_list"):
        return grid.to_list()
    try:
        return grid.tolist()
    except AttributeError:
        return grid


def _json_default(obj: Any) -> Any:
    try:
        return obj.tolist()
    except AttributeError:
        return str(obj)


def _run_case(case: VerificationCase, interpreter: DSLInterpreter) -> CaseResult:
    start = time.perf_counter()
    try:
        program = parse_program(case.program)
    except Exception as exc:  # pragma: no cover - defensive
        duration_ms = (time.perf_counter() - start) * 1000.0
        return CaseResult(
            case=case,
            passed=False,
            duration_ms=duration_ms,
            message="Failed to parse program.",
            details={"error": repr(exc)},
        )

    try:
        trace = interpreter.run(program, case.input_grid, metadata={"case": case.name})
    except Exception as exc:  # pragma: no cover - defensive
        duration_ms = (time.perf_counter() - start) * 1000.0
        return CaseResult(
            case=case,
            passed=False,
            duration_ms=duration_ms,
            message="Interpreter raised an exception.",
            details={"error": repr(exc)},
        )

    issues: Dict[str, Any] = {}
    if case.expected_grid is not None:
        final_grid = _format_grid(trace.final_state.grid)
        if final_grid != case.expected_grid:
            issues["grid_mismatch"] = {
                "expected": case.expected_grid,
                "actual": final_grid,
            }

    if case.expected_value is not None:
        focus_index = case.focus_stage if case.focus_stage is not None else len(trace) - 1
        if focus_index < 0 or focus_index >= len(trace):
            issues["focus_stage"] = {
                "requested": focus_index,
                "available": len(trace),
            }
        else:
            value = trace[focus_index].value
            if value != case.expected_value:
                issues["value_mismatch"] = {
                    "expected": case.expected_value,
                    "actual": value,
                    "focus_stage": focus_index,
                }
    if case.expected_region_mask is not None:
        focus_index = case.focus_stage if case.focus_stage is not None else len(trace) - 1
        if focus_index < 0 or focus_index >= len(trace):
            issues["region_focus"] = {
                "requested": focus_index,
                "available": len(trace),
            }
        else:
            value = trace[focus_index].value
            if not isinstance(value, Region):
                issues["region_type"] = {
                    "focus_stage": focus_index,
                    "actual_type": type(value).__name__,
                }
            else:
                mask = value.mask.astype(int).tolist()
                if mask != case.expected_region_mask:
                    issues["region_mismatch"] = {
                        "expected": case.expected_region_mask,
                        "actual": mask,
                        "focus_stage": focus_index,
                    }

    duration_ms = (time.perf_counter() - start) * 1000.0
    if issues:
        return CaseResult(
            case=case,
            passed=False,
            duration_ms=duration_ms,
            message="Case failed validation.",
            details=issues,
        )

    return CaseResult(case=case, passed=True, duration_ms=duration_ms)


def verify_cases(
    cases: Iterable[VerificationCase],
    *,
    interpreter: Optional[DSLInterpreter] = None,
    log_path: Optional[Path] = None,
) -> VerificationSummary:
    interpreter = interpreter or DSLInterpreter()
    start = time.perf_counter()
    results: List[CaseResult] = []
    for case in cases:
        results.append(_run_case(case, interpreter))
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    resolved_log_path = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as handle:
            for result in results:
                payload = {
                    "case": result.case.name,
                    "path": str(result.case.path),
                    "passed": result.passed,
                    "duration_ms": result.duration_ms,
                    "message": result.message,
                    "details": result.details,
                }
                json.dump(payload, handle, default=_json_default)
                handle.write("\n")
        resolved_log_path = log_path

    return VerificationSummary(results=results, elapsed_ms=elapsed_ms, log_path=resolved_log_path)


def verify_directory(
    fixtures_dir: Path,
    *,
    interpreter: Optional[DSLInterpreter] = None,
    log_dir: Optional[Path] = Path("logs/verification"),
    pattern: str = "*.json",
) -> VerificationSummary:
    fixtures_dir = fixtures_dir.resolve()
    cases = [_load_case(path) for path in sorted(fixtures_dir.glob(pattern))]
    log_path: Optional[Path] = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"verification_{timestamp}.jsonl"
    return verify_cases(cases, interpreter=interpreter, log_path=log_path)


__all__ = [
    "VerificationCase",
    "CaseResult",
    "VerificationSummary",
    "verify_cases",
    "verify_directory",
]
