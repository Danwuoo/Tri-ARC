"""SMT gateway package with lazy accessors.

The heavy submodules inside this package depend on optional third-party
libraries (notably ``z3-solver``).  To avoid import-time failures when those
dependencies are missing, the public attributes are resolved lazily via
``__getattr__``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Tuple

__all__ = [
    "ConstraintEncoder",
    "SMTArray",
    "SMTConstraintSet",
    "VerificationResult",
    "BatchVerifier",
    "WitnessFunctionGenerator",
    "z3_stub",
]

_LAZY_EXPORTS: Dict[str, Tuple[str, str | None]] = {
    "ConstraintEncoder": (".encoder", "ConstraintEncoder"),
    "SMTArray": (".types", "SMTArray"),
    "SMTConstraintSet": (".types", "SMTConstraintSet"),
    "VerificationResult": (".types", "VerificationResult"),
    "BatchVerifier": (".verifier", "BatchVerifier"),
    "WitnessFunctionGenerator": (".witness", "WitnessFunctionGenerator"),
    "z3_stub": (".z3_stub", None),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _LAZY_EXPORTS[name]
    module = import_module(module_name, __name__)
    value = module if attribute is None else getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
