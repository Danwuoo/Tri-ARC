"""Circuit breaker and fallback mechanisms for resource protection."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, Dict, Optional


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class FallbackStrategy(Enum):
    """Fallback strategies when circuit is open."""
    RETURN_NONE = "return_none"
    RETURN_EMPTY = "return_empty"
    RETURN_PARTIAL = "return_partial"
    SKIP_CANDIDATE = "skip_candidate"
    INCREASE_DEPTH = "increase_depth"
    ABORT = "abort"


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
        name: str = "circuit_breaker",
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying half-open
            success_threshold: Successes needed in half-open to close
            name: Name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
    
    def call(
        self,
        func: Callable[..., Any],
        *args,
        fallback: Optional[Callable[..., Any]] = None,
        **kwargs,
    ) -> Any:
        """Call function with circuit breaker protection.
        
        Args:
            func: Function to call
            *args: Positional arguments
            fallback: Optional fallback function
            **kwargs: Keyword arguments
            
        Returns:
            Function result or fallback result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open and no fallback
        """
        self.total_calls += 1
        
        # Check circuit state
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                if fallback is not None:
                    return fallback(*args, **kwargs)
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is open"
                )
        
        # Attempt call
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if fallback is not None:
                return fallback(*args, **kwargs)
            raise e
    
    def _on_success(self) -> None:
        """Handle successful call."""
        self.total_successes += 1
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Check if should attempt to reset circuit."""
        if self.last_failure_time is None:
            return False
        
        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.recovery_timeout
    
    def reset(self) -> None:
        """Manually reset circuit breaker."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_rate": (
                self.total_failures / self.total_calls
                if self.total_calls > 0
                else 0.0
            ),
        }
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"CircuitBreaker(name='{self.name}', "
            f"state={self.state.value}, "
            f"failures={self.failure_count}/{self.failure_threshold})"
        )


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class FallbackManager:
    """Manages fallback strategies for different failure scenarios."""
    
    def __init__(self):
        self.strategies: Dict[str, FallbackStrategy] = {}
        self.fallback_counts: Dict[str, int] = {}
    
    def register_strategy(
        self,
        component: str,
        strategy: FallbackStrategy,
    ) -> None:
        """Register fallback strategy for component.
        
        Args:
            component: Component name (e.g., "smt_solver", "search")
            strategy: Fallback strategy to use
        """
        self.strategies[component] = strategy
        self.fallback_counts[component] = 0
    
    def get_strategy(self, component: str) -> FallbackStrategy:
        """Get fallback strategy for component.
        
        Args:
            component: Component name
            
        Returns:
            Fallback strategy (default: RETURN_NONE)
        """
        return self.strategies.get(component, FallbackStrategy.RETURN_NONE)
    
    def execute_fallback(
        self,
        component: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute fallback strategy.
        
        Args:
            component: Component name
            error: Exception that triggered fallback
            context: Optional context information
            
        Returns:
            Fallback result based on strategy
        """
        strategy = self.get_strategy(component)
        self.fallback_counts[component] = self.fallback_counts.get(component, 0) + 1
        
        if strategy == FallbackStrategy.RETURN_NONE:
            return None
        elif strategy == FallbackStrategy.RETURN_EMPTY:
            return []
        elif strategy == FallbackStrategy.RETURN_PARTIAL:
            return context.get("partial_result", []) if context else []
        elif strategy == FallbackStrategy.SKIP_CANDIDATE:
            return None
        elif strategy == FallbackStrategy.INCREASE_DEPTH:
            return {"action": "increase_depth"}
        elif strategy == FallbackStrategy.ABORT:
            raise error
        else:
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fallback statistics."""
        return {
            "strategies": {k: v.value for k, v in self.strategies.items()},
            "fallback_counts": self.fallback_counts.copy(),
            "total_fallbacks": sum(self.fallback_counts.values()),
        }
    
    def reset(self) -> None:
        """Reset fallback counts."""
        self.fallback_counts.clear()


class ResourceLimitGuard:
    """Guards against resource limit violations with graceful degradation."""
    
    def __init__(
        self,
        max_memory_mb: Optional[float] = None,
        max_nodes: Optional[int] = None,
        max_expansions: Optional[int] = None,
    ):
        """Initialize resource limit guard.
        
        Args:
            max_memory_mb: Maximum memory in MB
            max_nodes: Maximum number of nodes
            max_expansions: Maximum number of expansions
        """
        self.max_memory_mb = max_memory_mb
        self.max_nodes = max_nodes
        self.max_expansions = max_expansions
        
        self.current_nodes = 0
        self.current_expansions = 0
    
    def check_memory(self) -> bool:
        """Check if memory limit exceeded.
        
        Returns:
            True if within limits
        """
        if self.max_memory_mb is None:
            return True
        
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            return memory_mb < self.max_memory_mb
        except ImportError:
            return True
    
    def check_nodes(self, count: Optional[int] = None) -> bool:
        """Check if node limit exceeded.
        
        Args:
            count: Optional node count (uses internal if None)
            
        Returns:
            True if within limits
        """
        if self.max_nodes is None:
            return True
        
        nodes = count if count is not None else self.current_nodes
        return nodes < self.max_nodes
    
    def check_expansions(self, count: Optional[int] = None) -> bool:
        """Check if expansion limit exceeded.
        
        Args:
            count: Optional expansion count (uses internal if None)
            
        Returns:
            True if within limits
        """
        if self.max_expansions is None:
            return True
        
        expansions = count if count is not None else self.current_expansions
        return expansions < self.max_expansions
    
    def increment_nodes(self, count: int = 1) -> None:
        """Increment node count."""
        self.current_nodes += count
    
    def increment_expansions(self, count: int = 1) -> None:
        """Increment expansion count."""
        self.current_expansions += count
    
    def reset(self) -> None:
        """Reset counters."""
        self.current_nodes = 0
        self.current_expansions = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get resource usage statistics."""
        stats = {
            "current_nodes": self.current_nodes,
            "current_expansions": self.current_expansions,
        }
        
        if self.max_nodes is not None:
            stats["node_utilization"] = self.current_nodes / self.max_nodes
        if self.max_expansions is not None:
            stats["expansion_utilization"] = (
                self.current_expansions / self.max_expansions
            )
        
        return stats
