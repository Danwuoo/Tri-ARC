from __future__ import annotations

from arc.symbolic.dsl.interpreter import validate_program
from arc.symbolic.dsl.parser import parse_program


def test_validate_program_detects_unknown_operator():
    program = parse_program("(pipeline (apply does_not_exist))")
    issues = validate_program(program)
    assert issues, "Expected validation to flag unknown operator."
    assert "unknown operator" in issues[0]
