from __future__ import annotations

from typing import Any, Dict, Optional


class InterpreterFailure(Exception):
    """Raised when the interpreter encounters a deterministic failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PRIMITIVE_ERROR",
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details: Dict[str, Any] = dict(details or {})
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        payload = {"message": self.message, "code": self.code, "details": dict(self.details)}
        if self.cause is not None:
            payload["cause"] = {
                "type": type(self.cause).__name__,
                "message": str(self.cause),
            }
        return payload

    @classmethod
    def validation(cls, message: str, *, details: Optional[Dict[str, Any]] = None) -> "InterpreterFailure":
        return cls(message=message, code="VALIDATION_ERROR", details=details or {})

    @classmethod
    def missing_env(cls, key: str, *, details: Optional[Dict[str, Any]] = None) -> "InterpreterFailure":
        payload = {"missing_key": key}
        if details:
            payload.update(details)
        return cls(message=f"Environment key '{key}' not found.", code="MISSING_ENV", details=payload)

    @classmethod
    def out_of_bounds(cls, message: str, *, details: Optional[Dict[str, Any]] = None) -> "InterpreterFailure":
        return cls(message=message, code="OUT_OF_BOUNDS", details=details or {})

    @classmethod
    def lambda_error(cls, message: str, *, details: Optional[Dict[str, Any]] = None, cause: Optional[BaseException] = None) -> "InterpreterFailure":
        return cls(message=message, code="LAMBDA_ERROR", details=details or {}, cause=cause)

