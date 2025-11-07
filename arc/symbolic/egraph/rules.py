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
    length = len(stages)
    for index in range(length):
        current = stages[index]
        if current.operator != "rotate":
            continue
        try:
            current_steps = int(current.arguments[0])
        except (TypeError, ValueError, IndexError):
            continue
        if current_steps % 4 == 0:
            new_stages = stages[:index] + stages[index + 1 :]
            yield Program(tuple(new_stages))
        if index + 1 < length:
            nxt = stages[index + 1]
            if nxt.operator != "rotate":
                continue
            try:
                next_steps = int(nxt.arguments[0])
            except (TypeError, ValueError, IndexError):
                continue
            steps = (current_steps + next_steps) % 4
            if steps == 0:
                new_stages = stages[:index] + stages[index + 2 :]
            else:
                replacement = Stage("rotate", (steps,))
                new_stages = stages[:index] + [replacement] + stages[index + 2 :]
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


def _simplify_repeat(program: Program) -> Iterable[Program]:
    stages = list(program)
    for index, stage in enumerate(stages):
        if stage.operator != "repeat" or len(stage.arguments) < 2:
            continue
        count_arg = stage.arguments[0]
        nested = stage.arguments[1]
        try:
            count = int(count_arg)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            new_stages = stages[:index] + stages[index + 1 :]
            yield Program(tuple(new_stages))
            continue
        if not isinstance(nested, Stage):
            continue
        if count == 1:
            new_stages = stages[:index] + [nested] + stages[index + 1 :]
            yield Program(tuple(new_stages))
            continue
        if nested.operator == "identity":
            new_stages = stages[:index] + stages[index + 1 :]
            yield Program(tuple(new_stages))


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
        RewriteRule(
            name="repeat_simplify",
            apply=_simplify_repeat,
            description="Simplify repeat combinators with trivial counts or identity bodies.",
        ),
    )


__all__ = ["builtin_rules"]
