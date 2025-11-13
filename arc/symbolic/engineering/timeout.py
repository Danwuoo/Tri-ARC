"""Timeout protection and time tracking utilities."""

from __future__ import annotations

import time
from typing import Optional


class TimeoutGuard:
    """Guards against timeout with cooperative cancellation support."""
    
    def __init__(self, timeout_s: float, start_time: Optional[float] = None):
        """Initialize timeout guard.
        
        Args:
            timeout_s: Timeout duration in seconds
            start_time: Optional start time (defaults to now)
        """
        self.timeout_s = timeout_s
        self.start_time = start_time if start_time is not None else time.perf_counter()
        self._cancelled = False
    
    def check(self) -> bool:
        """Check if timeout has been reached.
        
        Returns:
            True if still within timeout, False if timed out
        """
        if self._cancelled:
            return False
        
        elapsed = time.perf_counter() - self.start_time
        return elapsed < self.timeout_s
    
    def remaining(self) -> float:
        """Get remaining time in seconds.
        
        Returns:
            Remaining time (0.0 if timed out)
        """
        if self._cancelled:
            return 0.0
        
        elapsed = time.perf_counter() - self.start_time
        return max(0.0, self.timeout_s - elapsed)
    
    def elapsed(self) -> float:
        """Get elapsed time in seconds.
        
        Returns:
            Time elapsed since start
        """
        return time.perf_counter() - self.start_time
    
    def cancel(self) -> None:
        """Cooperatively cancel the operation."""
        self._cancelled = True
    
    def is_cancelled(self) -> bool:
        """Check if operation was cancelled.
        
        Returns:
            True if cancelled
        """
        return self._cancelled
    
    def reset(self, new_timeout: Optional[float] = None) -> None:
        """Reset the timeout guard.
        
        Args:
            new_timeout: Optional new timeout duration
        """
        self.start_time = time.perf_counter()
        self._cancelled = False
        if new_timeout is not None:
            self.timeout_s = new_timeout
    
    def extend(self, additional_time: float) -> None:
        """Extend the timeout by additional time.
        
        Args:
            additional_time: Additional seconds to add to timeout
        """
        self.timeout_s += additional_time
    
    def __enter__(self) -> TimeoutGuard:
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        pass
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"TimeoutGuard(timeout={self.timeout_s:.2f}s, "
            f"elapsed={self.elapsed():.2f}s, "
            f"remaining={self.remaining():.2f}s, "
            f"cancelled={self._cancelled})"
        )


class SoftTimeoutGuard(TimeoutGuard):
    """Timeout guard with soft and hard timeout thresholds."""
    
    def __init__(
        self,
        soft_timeout_s: float,
        hard_timeout_s: float,
        start_time: Optional[float] = None,
    ):
        """Initialize soft timeout guard.
        
        Args:
            soft_timeout_s: Soft timeout (warning threshold)
            hard_timeout_s: Hard timeout (must stop)
            start_time: Optional start time
        """
        super().__init__(hard_timeout_s, start_time)
        self.soft_timeout_s = soft_timeout_s
        self.hard_timeout_s = hard_timeout_s
    
    def check_soft(self) -> bool:
        """Check if soft timeout has been reached.
        
        Returns:
            True if still within soft timeout
        """
        if self._cancelled:
            return False
        
        elapsed = time.perf_counter() - self.start_time
        return elapsed < self.soft_timeout_s
    
    def check_hard(self) -> bool:
        """Check if hard timeout has been reached.
        
        Returns:
            True if still within hard timeout
        """
        return self.check()
    
    def remaining_soft(self) -> float:
        """Get remaining soft timeout.
        
        Returns:
            Remaining soft timeout in seconds
        """
        if self._cancelled:
            return 0.0
        
        elapsed = time.perf_counter() - self.start_time
        return max(0.0, self.soft_timeout_s - elapsed)
    
    def remaining_hard(self) -> float:
        """Get remaining hard timeout.
        
        Returns:
            Remaining hard timeout in seconds
        """
        return self.remaining()
    
    def is_soft_timeout(self) -> bool:
        """Check if soft timeout reached but not hard timeout.
        
        Returns:
            True if in soft timeout zone
        """
        return not self.check_soft() and self.check_hard()
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SoftTimeoutGuard(soft={self.soft_timeout_s:.2f}s, "
            f"hard={self.hard_timeout_s:.2f}s, "
            f"elapsed={self.elapsed():.2f}s, "
            f"remaining_soft={self.remaining_soft():.2f}s, "
            f"remaining_hard={self.remaining_hard():.2f}s, "
            f"cancelled={self._cancelled})"
        )
