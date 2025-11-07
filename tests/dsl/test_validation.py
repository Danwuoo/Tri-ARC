from __future__ import annotations

from arc.symbolic.dsl.interpreter import validate_program
from arc.symbolic.dsl.parser import parse_program


def test_validate_program_detects_unknown_operator():
    program = parse_program("(pipeline (apply does_not_exist))")
    issues = validate_program(program)
    assert issues, "Expected validation to flag unknown operator."
    assert "unknown operator" in issues[0]


def test_validate_program_flags_non_stage_argument():
    program = parse_program("(pipeline (apply repeat 2 3))")
    issues = validate_program(program)
    assert any("must be a Stage literal" in issue for issue in issues)


def test_validate_program_flags_missing_lambda():
    program = parse_program("(pipeline (apply region_all)\n                   (apply map_cells @last_region 42))")
    issues = validate_program(program)
    assert any("must be a lambda expression" in issue for issue in issues)
