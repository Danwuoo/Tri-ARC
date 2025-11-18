"""Tri-ARC core package."""

from __future__ import annotations

import importlib
import sys

__all__ = ["config", "logging_utils"]

__version__ = "0.1.0"


def _ensure_z3_runtime() -> None:
    """Provide a fallback Z3 shim when the real solver is absent."""
    try:
        module = importlib.import_module("z3")
    except ModuleNotFoundError:
        module = None
    if module and all(hasattr(module, attr) for attr in ("Int", "Bool", "Solver", "ArraySort")):
        return
    from arc.symbolic.smt import z3_stub

    sys.modules["z3"] = z3_stub


_ensure_z3_runtime()
