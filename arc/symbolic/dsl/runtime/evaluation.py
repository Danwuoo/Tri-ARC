from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

from arc.symbolic.dsl.types import ExecutionState, LambdaExpression, Stage

from .context import InterpreterConfig
from .errors import InterpreterFailure


@dataclass
class EvaluationContext:
    state: ExecutionState
    config: InterpreterConfig
    stage_index: int
    operator: str
    locals: Dict[str, Any] = field(default_factory=dict)

    def with_locals(self, updates: Dict[str, Any]) -> "EvaluationContext":
        merged = dict(self.locals)
        merged.update(updates)
        return EvaluationContext(
            state=self.state,
            config=self.config,
            stage_index=self.stage_index,
            operator=self.operator,
            locals=merged,
        )


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return value is not None


def _require_env(state: ExecutionState, key: str, operator: str, stage_index: int) -> Any:
    if key not in state.env:
        raise InterpreterFailure.missing_env(
            key,
            details={"operator": operator, "stage_index": stage_index},
        )
    return state.env[key]


def evaluate_expression(expr: Any, ctx: EvaluationContext) -> Any:
    if isinstance(expr, Stage):
        return expr
    if expr is None:
        return None
    if isinstance(expr, (int, float, bool)):
        return expr
    if isinstance(expr, list):
        return [evaluate_expression(item, ctx) for item in expr]
    if isinstance(expr, tuple):
        if not expr:
            return tuple()
        head, *tail = expr
        head_str = str(head)
        if head_str == "tuple":
            return tuple(evaluate_expression(item, ctx) for item in tail)
        if head_str == "list":
            return [evaluate_expression(item, ctx) for item in tail]
        if head_str == "if":
            if len(tail) != 3:
                raise InterpreterFailure.validation(
                    "if expression requires exactly three operands.",
                    details={"operator": ctx.operator, "stage_index": ctx.stage_index},
                )
            cond = evaluate_expression(tail[0], ctx)
            branch = tail[1] if _bool(cond) else tail[2]
            return evaluate_expression(branch, ctx)
        if head_str in {"eq", "ne", "lt", "le", "gt", "ge"}:
            if len(tail) != 2:
                raise InterpreterFailure.validation(
                    f"{head_str} expression expects two operands.",
                    details={"operator": ctx.operator, "stage_index": ctx.stage_index},
                )
            left = evaluate_expression(tail[0], ctx)
            right = evaluate_expression(tail[1], ctx)
            if head_str == "eq":
                return left == right
            if head_str == "ne":
                return left != right
            if head_str == "lt":
                return left < right
            if head_str == "le":
                return left <= right
            if head_str == "gt":
                return left > right
            return left >= right
        if head_str in {"and", "or"}:
            if len(tail) < 2:
                raise InterpreterFailure.validation(
                    f"{head_str} requires at least two operands.",
                    details={"operator": ctx.operator, "stage_index": ctx.stage_index},
                )
            vals = [evaluate_expression(item, ctx) for item in tail]
            if head_str == "and":
                return all(_bool(v) for v in vals)
            return any(_bool(v) for v in vals)
        if head_str == "not":
            if len(tail) != 1:
                raise InterpreterFailure.validation(
                    "not expression expects exactly one operand.",
                    details={"operator": ctx.operator, "stage_index": ctx.stage_index},
                )
            return not _bool(evaluate_expression(tail[0], ctx))
        if head_str == "get":
            if len(tail) != 2:
                raise InterpreterFailure.validation(
                    "get expression expects a target and key.",
                    details={"operator": ctx.operator, "stage_index": ctx.stage_index},
                )
            target = evaluate_expression(tail[0], ctx)
            key = evaluate_expression(tail[1], ctx)
            if isinstance(target, dict):
                if key not in target:
                    raise InterpreterFailure.validation(
                        f"Key {key!r} not present in mapping.",
                        details={"operator": ctx.operator, "stage_index": ctx.stage_index},
                    )
                return target[key]
            if isinstance(target, (list, tuple)) and isinstance(key, int):
                return target[key]
            if hasattr(target, key):
                return getattr(target, key)
            raise InterpreterFailure.validation(
                f"Unsupported get target {type(target).__name__}.",
                details={"operator": ctx.operator, "stage_index": ctx.stage_index},
            )
        raise InterpreterFailure.validation(
            f"Unknown expression head '{head_str}'.",
            details={"operator": ctx.operator, "stage_index": ctx.stage_index},
        )
    if isinstance(expr, str):
        if expr.startswith("@"):
            key = expr[1:]
            return _require_env(ctx.state, key, ctx.operator, ctx.stage_index)
        if expr in ctx.locals:
            return ctx.locals[expr]
        return expr
    if isinstance(expr, LambdaExpression):
        return build_lambda(expr, ctx)
    return expr


def build_lambda(lambda_expr: LambdaExpression, ctx: EvaluationContext):
    if len(lambda_expr.parameters) != 1:
        raise InterpreterFailure.validation(
            "map_cells lambdas must declare exactly one parameter.",
            details={"operator": ctx.operator, "stage_index": ctx.stage_index},
        )
    param = lambda_expr.parameters[0]

    def _invoke(arg: Any) -> Any:
        local_ctx = ctx.with_locals({param: arg})
        try:
            return evaluate_expression(lambda_expr.body, local_ctx)
        except InterpreterFailure:
            raise
        except Exception as exc:
            raise InterpreterFailure.lambda_error(
                "Lambda evaluation raised an exception.",
                details={"operator": ctx.operator, "stage_index": ctx.stage_index},
                cause=exc,
            ) from exc

    return _invoke

