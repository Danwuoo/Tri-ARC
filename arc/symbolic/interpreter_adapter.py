from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from arc.symbolic.dsl.interpreter import DSLInterpreter, validate_program
from arc.symbolic.dsl.parser import parse_program
from arc.symbolic.dsl.verify import verify_directory, VerificationSummary


@dataclass
class InterpreterAdapter:
    """Thin adapter that exposes the DSL interpreter to symbolic solver pipelines."""

    interpreter: DSLInterpreter = field(default_factory=DSLInterpreter)

    def execute(self, program_source: str, grid: Any, *, metadata: Optional[Dict[str, Any]] = None):
        program = parse_program(program_source)
        issues = validate_program(program, self.interpreter.registry)
        if issues:
            raise ValueError(f"Program failed validation: {issues}")
        return self.interpreter.run(program, grid, metadata=metadata)

    def lint(self, program_source: str) -> Iterable[str]:
        program = parse_program(program_source)
        return validate_program(program, self.interpreter.registry)

    def verify_fixtures(
        self,
        fixtures_dir: Path,
        *,
        log_dir: Optional[Path] = Path("logs/verification"),
    ) -> VerificationSummary:
        return verify_directory(fixtures_dir, interpreter=self.interpreter, log_dir=log_dir)


__all__ = ["InterpreterAdapter"]

