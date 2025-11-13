"""SMT Gateway for constraint-based verification.

This module provides SMT-based verification using Z3 solver for DSL programs.
It includes constraint encoding, batch verification, witness function generation,
and BDD support for grid operations.
"""

from __future__ import annotations

from .encoder import ConstraintEncoder
from .types import SMTArray, SMTConstraintSet, VerificationResult
from .verifier import BatchVerifier
from .witness import WitnessFunctionGenerator

__all__ = [
    "ConstraintEncoder",
    "SMTArray",
    "SMTConstraintSet",
    "VerificationResult",
    "BatchVerifier",
    "WitnessFunctionGenerator",
]
