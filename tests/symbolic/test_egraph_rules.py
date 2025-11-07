from __future__ import annotations

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.egraph import rules


def make_program(*stage_defs) -> Program:
    return Program(tuple(Stage(name, args) for name, args in stage_defs))


def test_simplify_repeat_count_one():
    repeat_stage = Stage("repeat", (1, Stage("rotate", (1,))))
    program = Program((repeat_stage,))
    rewrites = list(rules._simplify_repeat(program))  # type: ignore[attr-defined]
    assert rewrites
    assert rewrites[0].stages[0].operator == "rotate"


def test_simplify_repeat_identity_body():
    repeat_stage = Stage("repeat", (3, Stage("identity", ())))
    program = Program((repeat_stage,))
    rewrites = list(rules._simplify_repeat(program))  # type: ignore[attr-defined]
    assert rewrites
    assert rewrites[0].stages == tuple()


def test_simplify_rotate_merges_pairs_and_drops_zero():
    program = make_program(("rotate", (2,)), ("rotate", (2,)), ("rotate", (4,)))
    rewrites = list(rules._simplify_rotate(program))  # type: ignore[attr-defined]
    merged = any(len(candidate.stages) == 1 and candidate.stages[0].operator == "rotate" for candidate in rewrites)
    dropped = any(len(candidate.stages) == 2 for candidate in rewrites)
    assert merged
    assert dropped


def test_builtin_rules_include_repeat():
    rule_names = {rule.name for rule in rules.builtin_rules()}
    assert "repeat_simplify" in rule_names
