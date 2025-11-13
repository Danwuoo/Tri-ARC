"""Data structures for SMT constraint encoding and verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    z3 = None  # type: ignore


@dataclass
class SMTArray:
    """Represents a grid as an SMT array.
    
    Attributes:
        name: Unique identifier for this array
        shape: (height, width) of the grid
        domain: (min_value, max_value) for cell values (typically (0, 9) for colors)
        z3_array: The actual Z3 array object (if Z3 is available)
    """
    name: str
    shape: Tuple[int, int]
    domain: Tuple[int, int]
    z3_array: Optional[Any] = None  # z3.Array
    
    def __post_init__(self) -> None:
        """Validate the SMT array configuration."""
        if self.shape[0] <= 0 or self.shape[1] <= 0:
            raise ValueError(f"Invalid shape: {self.shape}")
        if self.domain[0] > self.domain[1]:
            raise ValueError(f"Invalid domain: {self.domain}")


@dataclass
class SMTConstraintSet:
    """Collection of SMT constraints for program verification.
    
    Attributes:
        variables: Named Z3 variables used in constraints
        constraints: List of Z3 constraint expressions
        assertions: List of Z3 assertions to be checked
        metadata: Additional information about the constraint set
    """
    variables: Dict[str, Any] = field(default_factory=dict)  # str -> z3 variable
    constraints: List[Any] = field(default_factory=list)  # List of z3 constraints
    assertions: List[Any] = field(default_factory=list)  # List of z3 assertions
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_variable(self, name: str, var: Any) -> None:
        """Add a named variable to the constraint set."""
        self.variables[name] = var
    
    def add_constraint(self, constraint: Any) -> None:
        """Add a constraint to the set."""
        self.constraints.append(constraint)
    
    def add_assertion(self, assertion: Any) -> None:
        """Add an assertion to be checked."""
        self.assertions.append(assertion)
    
    def get_all_constraints(self) -> List[Any]:
        """Get all constraints including assertions."""
        return self.constraints + self.assertions
    
    def clear(self) -> None:
        """Clear all constraints and variables."""
        self.variables.clear()
        self.constraints.clear()
        self.assertions.clear()


@dataclass
class VerificationResult:
    """Result of SMT verification for a candidate program.
    
    Attributes:
        program_id: Identifier for the verified program
        status: Verification status ("sat", "unsat", "unknown", "timeout", "error")
        verification_time: Time taken for verification in seconds
        model: Satisfying model if status is "sat"
        unsat_core: Minimal unsatisfiable core if status is "unsat"
        metadata: Additional verification information
    """
    program_id: str
    status: str  # "sat", "unsat", "unknown", "timeout", "error"
    verification_time: float
    model: Optional[Dict[str, Any]] = None
    unsat_core: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_verified(self) -> bool:
        """Check if the program passed verification."""
        return self.status == "sat"
    
    @property
    def is_refuted(self) -> bool:
        """Check if the program was refuted."""
        return self.status == "unsat"
    
    @property
    def is_inconclusive(self) -> bool:
        """Check if verification was inconclusive."""
        return self.status in ("unknown", "timeout", "error")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "program_id": self.program_id,
            "status": self.status,
            "verification_time": self.verification_time,
            "model": self.model,
            "unsat_core": self.unsat_core,
            "metadata": self.metadata,
        }
