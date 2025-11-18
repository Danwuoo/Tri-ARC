"""Lightweight fallback shim that emulates a tiny subset of the Z3 API.

This module intentionally mirrors the handful of constructors and helpers that
Tri-ARC touches inside the symbolic SMT gateway.  It does *not* attempt to
perform real SMT solving; instead it creates opaque expression objects and a
stub solver that always reports ``unknown``.  The goal is to keep unit tests
and higher layers working in environments where the ``z3-solver`` wheel is not
available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Tuple

__all__ = [
    "ArraySort",
    "Bool",
    "BoolVal",
    "Const",
    "If",
    "Implies",
    "Int",
    "IntSort",
    "Not",
    "Or",
    "Select",
    "Solver",
    "simplify",
    "sat",
    "unsat",
    "unknown",
]


sat = "sat"
unsat = "unsat"
unknown = "unknown"


@dataclass(frozen=True)
class _Sort:
    name: str
    args: Tuple[Any, ...] = ()

    def __repr__(self) -> str:
        if not self.args:
            return self.name
        inner = ", ".join(repr(arg) for arg in self.args)
        return f"{self.name}({inner})"


class _Expr:
    __slots__ = ("op", "args", "_sort")

    def __init__(self, op: str, *args: Any) -> None:
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "args", args)
        object.__setattr__(self, "_sort", None)

    def __repr__(self) -> str:
        if not self.args:
            return self.op
        joined = ", ".join(repr(arg) for arg in self.args)
        return f"{self.op}({joined})"

    def _binary(self, op: str, other: Any) -> "_Expr":
        return _Expr(op, self, other)

    def __eq__(self, other: Any) -> "_Expr":  # type: ignore[override]
        return self._binary("==", other)

    def __ne__(self, other: Any) -> "_Expr":  # type: ignore[override]
        return self._binary("!=", other)

    def __lt__(self, other: Any) -> "_Expr":
        return self._binary("<", other)

    def __le__(self, other: Any) -> "_Expr":
        return self._binary("<=", other)

    def __gt__(self, other: Any) -> "_Expr":
        return self._binary(">", other)

    def __ge__(self, other: Any) -> "_Expr":
        return self._binary(">=", other)

    def __hash__(self) -> int:
        return id(self)

    def __bool__(self) -> bool:
        raise TypeError("Symbolic expressions cannot be used as booleans.")

    def sort(self) -> _Sort:
        if self._sort is not None:
            return self._sort  # type: ignore[return-value]
        return _Sort("UnknownSort")


def IntSort() -> _Sort:
    return _Sort("IntSort")


def ArraySort(domain: _Sort, range_sort: _Sort) -> _Sort:
    return _Sort("ArraySort", (domain, range_sort))


def Int(name: str) -> _Expr:
    return _Expr(f"IntVar:{name}")


def Bool(name: str) -> _Expr:
    return _Expr(f"BoolVar:{name}")


def BoolVal(value: bool) -> _Expr:
    return _Expr(f"BoolVal:{bool(value)}")


def Const(name: str, sort: _Sort) -> _Expr:
    expr = _Expr(f"Const:{name}", sort)
    object.__setattr__(expr, "_sort", sort)
    return expr


def Select(array_expr: _Expr, index: Any) -> _Expr:
    return _Expr("Select", array_expr, index)


def If(condition: Any, true_value: Any, false_value: Any) -> _Expr:
    return _Expr("If", condition, true_value, false_value)


def Not(expr: Any) -> _Expr:
    return _Expr("Not", expr)


def Or(*exprs: Any) -> _Expr:
    return _Expr("Or", *exprs)


def Implies(left: Any, right: Any) -> _Expr:
    return _Expr("Implies", left, right)


def simplify(expr: Any) -> Any:
    return expr


class _Model:
    def decls(self) -> List[Any]:
        return []

    def __getitem__(self, key: Any) -> Any:
        return None


class Solver:
    """Tiny stand-in for z3.Solver that always reports ``unknown``."""

    def __init__(self) -> None:
        self._constraints: List[Any] = []
        self._stack: List[int] = []
        self._params: dict[str, Any] = {}

    def set(self, *args: Any, **params: Any) -> None:
        if args:
            if len(args) != 2:
                raise TypeError("Solver.set() expects key/value or keyword arguments.")
            key, value = args
            params[str(key)] = value
        self._params.update(params)

    def add(self, *constraints: Any) -> None:
        self._constraints.extend(constraints)

    def push(self) -> None:
        self._stack.append(len(self._constraints))

    def pop(self) -> None:
        if not self._stack:
            raise IndexError("pop from empty solver stack")
        size = self._stack.pop()
        del self._constraints[size:]

    def check(self) -> str:
        return unknown

    def model(self) -> _Model:
        return _Model()

    def unsat_core(self) -> List[Any]:
        return []

    def reason_unknown(self) -> str:
        return "stubbed_z3"
