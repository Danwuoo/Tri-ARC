from __future__ import annotations

from typing import Any, Iterable, List, Sequence, Tuple

from .exceptions import DSLParseError
from .types import LambdaExpression, Program, Stage

Token = str


def tokenize(source: str) -> List[Token]:
    tokens: List[str] = []
    current: List[str] = []
    in_string = False
    for char in source:
        if in_string:
            current.append(char)
            if char == '"':
                in_string = False
                tokens.append("".join(current))
                current = []
            continue

        if char == '"':
            if current:
                tokens.append("".join(current))
                current = []
            in_string = True
            current.append(char)
            continue

        if char in ("(", ")"):
            if current:
                tokens.append("".join(current))
                current = []
            tokens.append(char)
        elif char.isspace():
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)

    if current:
        tokens.append("".join(current))

    return tokens


def _parse(tokens: Sequence[Token], index: int = 0) -> Tuple[Any, int]:
    if index >= len(tokens):
        raise DSLParseError("Unexpected end of tokens during parsing.")

    token = tokens[index]
    if token == "(":
        items: List[Any] = []
        index += 1
        while index < len(tokens) and tokens[index] != ")":
            node, index = _parse(tokens, index)
            items.append(node)
        if index >= len(tokens) or tokens[index] != ")":
            raise DSLParseError("Missing closing parenthesis.")
        return items, index + 1
    if token == ")":
        raise DSLParseError("Unmatched closing parenthesis.")
    return _atom(token), index + 1


def _atom(token: str) -> Any:
    lower = token.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"null", "none"}:
        return None
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return token[1:-1]
    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return token


def _normalise_expression(expr: Any) -> Any:
    if isinstance(expr, list):
        if not expr:
            return tuple()
        head, *tail = expr
        if head == "apply":
            if not tail:
                raise DSLParseError("`apply` requires at least an operator identifier.")
            operator = tail[0]
            if not isinstance(operator, str):
                raise DSLParseError("Operator name must be a string identifier.")
            arguments = tuple(_normalise_expression(arg) for arg in tail[1:])
            return Stage(operator=operator, arguments=arguments)
        if head == "lambda":
            if len(tail) != 2:
                raise DSLParseError("lambda must have parameter list and body.")
            params_raw, body_raw = tail
            if not isinstance(params_raw, list):
                raise DSLParseError("lambda parameters must be provided as a list.")
            params: Tuple[str, ...] = tuple(str(p) for p in params_raw)
            body = _normalise_expression(body_raw)
            return LambdaExpression(parameters=params, body=body)
        return tuple(_normalise_expression(arg) for arg in expr)
    return expr


def parse_program(source: str) -> Program:
    tokens = tokenize(source)
    if not tokens:
        raise DSLParseError("Empty program source.")
    parsed, index = _parse(tokens, 0)
    if index != len(tokens):
        raise DSLParseError("Unexpected trailing tokens after parsing program.")
    if not isinstance(parsed, list) or not parsed:
        raise DSLParseError("Program must start with a pipeline expression.")
    head, *tail = parsed
    if head != "pipeline":
        raise DSLParseError("Program root must be `(pipeline ...)`.")

    stages: List[Stage] = []
    for stage_expr in tail:
        normalised = _normalise_expression(stage_expr)
        if not isinstance(normalised, Stage):
            raise DSLParseError("Only `apply` forms are permitted directly under pipeline.")
        stages.append(normalised)

    return Program(tuple(stages))


def parse_expression(source: str) -> Any:
    tokens = tokenize(source)
    parsed, index = _parse(tokens, 0)
    if index != len(tokens):
        raise DSLParseError("Unexpected trailing tokens in expression.")
    return _normalise_expression(parsed)


def program_from_stages(stages: Iterable[Stage]) -> Program:
    return Program(tuple(stages))
