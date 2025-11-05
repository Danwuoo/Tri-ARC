from __future__ import annotations

from typing import Iterable, List, Tuple

from arc.symbolic.dsl.types import Program, Stage

from .engine import RewriteRule


def _remove_identity(program: Program) -> Iterable[Program]:
    stages = list(program)
    changed = False
    cleaned: List[Stage] = []
    for stage in stages:
        if stage.operator == "identity":
            changed = True
            continue
        cleaned.append(stage)
    if changed:
        yield Program(tuple(cleaned))


def _simplify_rotate(program: Program) -> Iterable[Program]:
    stages = list(program)
    for index in range(len(stages) - 1):
        current = stages[index]
        nxt = stages[index + 1]
        if current.operator == "rotate" and nxt.operator == "rotate":
            steps = (int(current.arguments[0]) + int(nxt.arguments[0])) % 4
            replacement = Stage("rotate", (steps,))
            new_stages = stages[:index] + [replacement] + stages[index + 2 :]
            yield Program(tuple(new_stages))
        if current.operator == "rotate" and int(current.arguments[0]) % 4 == 0:
            new_stages = stages[:index] + stages[index + 1 :]
            yield Program(tuple(new_stages))


def _transpose_pair(program: Program) -> Iterable[Program]:
    stages = list(program)
    for index in range(len(stages) - 1):
        if stages[index].operator == "transpose" and stages[index + 1].operator == "transpose":
            new_stages = stages[:index] + stages[index + 2 :]
            yield Program(tuple(new_stages))


def _reflect_twice(program: Program) -> Iterable[Program]:
    stages = list(program)
    for index in range(len(stages) - 1):
        a = stages[index]
        b = stages[index + 1]
        if a.operator == "reflect" and b.operator == "reflect" and a.arguments == b.arguments:
            new_stages = stages[:index] + stages[index + 2 :]
            yield Program(tuple(new_stages))


def _compose_flatten(program: Program) -> Iterable[Program]:
    stages = list(program)
    flattened = False
    result: List[Stage] = []
    for stage in stages:
        if stage.operator == "compose":
            flattened = True
            for inner in stage.arguments:
                if isinstance(inner, Stage):
                    result.append(inner)
        else:
            result.append(stage)
    if flattened:
        yield Program(tuple(result))


def builtin_rules() -> Tuple[RewriteRule, ...]:
    return (
        RewriteRule(
            name="remove_identity",
            apply=_remove_identity,
            description="Drop identity stages inside compose chains.",
        ),
        RewriteRule(
            name="rotate_merge",
            apply=_simplify_rotate,
            description="Combine consecutive rotations.",
        ),
        RewriteRule(
            name="transpose_pair",
            apply=_transpose_pair,
            description="Two transposes cancel out.",
        ),
        RewriteRule(
            name="reflect_twice",
            apply=_reflect_twice,
            description="Two identical reflections cancel out.",
        ),
        RewriteRule(
            name="compose_flatten",
            apply=_compose_flatten,
            description="Flatten compose operators into linear stages.",
        ),
    )


__all__ = ["builtin_rules"]
