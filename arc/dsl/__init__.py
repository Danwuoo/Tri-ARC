from __future__ import annotations

"""DSL interpreter package for Tri-ARC."""

from .interpreter import DSLInterpreter, validate_program
from .runtime.errors import InterpreterFailure

__all__ = ["DSLInterpreter", "InterpreterFailure", "validate_program"]

