from __future__ import annotations

"""Tri-ARC symbolic DSL package with lazy imports to avoid circular dependencies."""

from importlib import import_module
from typing import Any

__all__ = ["DSLInterpreter", "InterpreterFailure", "validate_program"]


def __getattr__(name: str) -> Any:
    if name == "DSLInterpreter" or name == "validate_program":
        module = import_module("arc.symbolic.dsl.interpreter")
        return getattr(module, name)
    if name == "InterpreterFailure":
        module = import_module("arc.symbolic.dsl.runtime.errors")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
