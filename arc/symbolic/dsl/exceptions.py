from __future__ import annotations

class DSLParseError(Exception):
    """Raised when the DSL source cannot be parsed into a valid program."""


class DSLExecutionError(Exception):
    """Raised when program execution fails due to semantic errors."""


class PrimitiveNotFoundError(DSLExecutionError):
    """Raised when an operator is not registered in the primitive library."""


class InvalidArgumentError(DSLExecutionError):
    """Raised when primitive arguments fail validation."""


class RegionError(DSLExecutionError):
    """Raised when region construction or usage is invalid."""
