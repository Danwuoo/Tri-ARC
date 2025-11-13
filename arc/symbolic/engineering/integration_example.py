"""Example integration of engineering infrastructure components.

This module demonstrates how to use all engineering infrastructure
components together in a symbolic solver.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from arc.symbolic.dsl.types import Program
from arc.symbolic.engineering import (
    AdaptiveBudgetManager,
    ArtifactManager,
    CacheManager,
    CircuitBreaker,
    FallbackStrategy,
    SynthesisMetrics,
    TelemetryCollector,
    TimeoutGuard,
)
from arc.symbolic.engineering.circuit_breaker import FallbackManager
from arc.symbolic.engineering.metrics import MetricsCollector
from arc.symbolic.engineering.telemetry import PhaseTimer
from arc.symbolic.search.budget import SearchBudget


class EngineeringInfrastructure:
    """Integrated engineering infrastructure for symbolic solver."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize all engineering components.
        
        Args:
            config: Configuration dictionary
        """
        config = config or {}
        
        # Cache management
        self.cache = CacheManager(
            program_cache_size=config.get("program_cache_size", 10000),
            fragment_cache_size=config.get("fragment_cache_size", 5000),
            verification_cache_size=config.get("verification_cache_size", 2000),
        )
        
        # Budget management
        self.budget_manager = AdaptiveBudgetManager(config.get("budget", {}))
        
        # Telemetry and metrics
        self.telemetry = TelemetryCollector(
            log_dir=config.get("log_dir", "logs/symbolic"),
            enable_file_logging=config.get("enable_telemetry", True),
        )
        self.metrics_collector = MetricsCollector()
        
        # Artifact management
        self.artifacts = ArtifactManager(
            artifact_dir=config.get("artifact_dir", "cache/symbolic/artifacts"),
            enable_compression=config.get("enable_compression", True),
        )
        
        # Circuit breakers
        self.smt_breaker = CircuitBreaker(
            failure_threshold=config.get("smt_failure_threshold", 5),
            recovery_timeout=config.get("smt_recovery_timeout", 60.0),
            name="smt_solver",
        )
        
        self.search_breaker = CircuitBreaker(
            failure_threshold=config.get("search_failure_threshold", 3),
            recovery_timeout=config.get("search_recovery_timeout", 30.0),
            name="search",
        )
        
        # Fallback manager
        self.fallback_manager = FallbackManager()
        self.fallback_manager.register_strategy("smt_solver", FallbackStrategy.RETURN_NONE)
        self.fallback_manager.register_strategy("search", FallbackStrategy.RETURN_PARTIAL)
    
    def solve_with_infrastructure(
        self,
        task: Dict[str, Any],
        global_budget: SearchBudget,
        search_func: Any,
        verify_func: Any,
    ) -> Dict[str, Any]:
        """Solve task with full engineering infrastructure.
        
        Args:
            task: Task to solve
            global_budget: Global search budget
            search_func: Search function
            verify_func: Verification function
            
        Returns:
            Solution result
        """
        task_id = task.get("task_id", "unknown")
        
        # Start metrics collection
        self.metrics_collector.start_task(task_id)
        
        # Allocate adaptive budget
        budget = self.budget_manager.allocate_budget(task, global_budget)
        
        # Check cache first
        semantic_hash = self._compute_task_hash(task)
        cached_program = self.cache.get_cached_program(semantic_hash)
        
        if cached_program:
            self.telemetry.record_cache_access("program", hit=True, task_id=task_id)
            self.metrics_collector.record_cache_hit()
            
            # Return cached result
            metrics = self.metrics_collector.finish_task(
                success=True,
                elapsed_s=0.0,
                program_length=len(cached_program.stages) if hasattr(cached_program, "stages") else 0,
            )
            
            return {
                "success": True,
                "program": cached_program,
                "cached": True,
                "metrics": metrics,
            }
        
        self.telemetry.record_cache_access("program", hit=False, task_id=task_id)
        self.metrics_collector.record_cache_miss()
        
        # Perform search with timeout protection
        result = None
        with TimeoutGuard(budget.hard_timeout_s) as guard:
            # Search phase
            with PhaseTimer(self.telemetry, "search", task_id) as search_timer:
                try:
                    result = self.search_breaker.call(
                        search_func,
                        task=task,
                        budget=budget,
                        guard=guard,
                        fallback=lambda *args, **kwargs: {"candidates": []},
                    )
                    search_timer.mark_success()
                except Exception as e:
                    self.telemetry.record_error(
                        error_type="search_error",
                        message=str(e),
                        task_id=task_id,
                    )
                    result = {"candidates": []}
            
            # Verification phase
            if result and result.get("candidates"):
                with PhaseTimer(self.telemetry, "verification", task_id) as verify_timer:
                    verified_candidates = []
                    
                    for candidate in result["candidates"]:
                        try:
                            # Use circuit breaker for SMT verification
                            verification = self.smt_breaker.call(
                                verify_func,
                                program=candidate,
                                examples=task.get("train", []),
                                fallback=lambda *args, **kwargs: {"status": "unknown"},
                            )
                            
                            if verification.get("status") == "sat":
                                verified_candidates.append(candidate)
                                self.metrics_collector.record_verification()
                            
                            self.telemetry.record_candidate_verified(
                                task_id=task_id,
                                success=verification.get("status") == "sat",
                                verification_time=verification.get("time", 0.0),
                            )
                        except Exception as e:
                            self.telemetry.record_error(
                                error_type="verification_error",
                                message=str(e),
                                task_id=task_id,
                            )
                    
                    result["verified_candidates"] = verified_candidates
                    verify_timer.mark_success()
        
        # Select best candidate
        best_program = None
        if result and result.get("verified_candidates"):
            best_program = result["verified_candidates"][0]
            
            # Cache successful program
            self.cache.cache_program_semantics(
                best_program,
                task.get("train", []),
            )
            
            # Save artifact
            self.artifacts.save_program(
                task_id=task_id,
                program=best_program,
                metadata={
                    "score": getattr(best_program, "score", 0.0),
                    "verification": "passed",
                },
            )
        
        # Finish metrics collection
        success = best_program is not None
        elapsed = guard.elapsed()
        program_length = len(best_program.stages) if best_program and hasattr(best_program, "stages") else None
        
        metrics = self.metrics_collector.finish_task(
            success=success,
            elapsed_s=elapsed,
            program_length=program_length,
        )
        
        # Record performance for future budget allocation
        from arc.symbolic.engineering.budget import TaskFeatures
        features = TaskFeatures.from_task(task)
        self.budget_manager.record_performance(
            task_id=task_id,
            success=success,
            elapsed_time=elapsed,
            expansions=metrics.expansions,
            features=features,
        )
        
        return {
            "success": success,
            "program": best_program,
            "cached": False,
            "metrics": metrics,
            "budget": budget,
        }
    
    def _compute_task_hash(self, task: Dict[str, Any]) -> str:
        """Compute hash for task caching."""
        import hashlib
        import json
        
        # Hash based on training examples
        train = task.get("train", [])
        train_str = json.dumps(train, sort_keys=True)
        return hashlib.sha256(train_str.encode()).hexdigest()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics from all components.
        
        Returns:
            Statistics dictionary
        """
        return {
            "cache": self.cache.get_stats(),
            "budget": self.budget_manager.get_statistics(),
            "metrics": self.metrics_collector.get_aggregate().to_dict(),
            "artifacts": self.artifacts.get_stats(),
            "smt_breaker": self.smt_breaker.get_stats(),
            "search_breaker": self.search_breaker.get_stats(),
            "fallbacks": self.fallback_manager.get_stats(),
        }
    
    def close(self) -> None:
        """Close all components and flush buffers."""
        self.telemetry.close()


# Example usage
def example_usage():
    """Example of using the integrated infrastructure."""
    
    # Initialize infrastructure
    config = {
        "program_cache_size": 10000,
        "log_dir": "logs/symbolic",
        "enable_telemetry": True,
    }
    
    infra = EngineeringInfrastructure(config)
    
    # Define mock search and verify functions
    def mock_search(task, budget, guard, **kwargs):
        # Simulate search
        return {
            "candidates": [
                Program(stages=[]),
            ]
        }
    
    def mock_verify(program, examples, **kwargs):
        # Simulate verification
        return {"status": "sat", "time": 0.5}
    
    # Solve task
    task = {
        "task_id": "example_001",
        "train": [
            {"input": [[1, 2]], "output": [[2, 1]]}
        ],
    }
    
    global_budget = SearchBudget(
        max_depth=10,
        max_expansions=1000,
        soft_timeout_s=60.0,
        hard_timeout_s=90.0,
    )
    
    result = infra.solve_with_infrastructure(
        task=task,
        global_budget=global_budget,
        search_func=mock_search,
        verify_func=mock_verify,
    )
    
    print(f"Success: {result['success']}")
    print(f"Cached: {result['cached']}")
    print(f"Metrics: {result['metrics']}")
    
    # Get statistics
    stats = infra.get_statistics()
    print(f"Statistics: {stats}")
    
    # Close infrastructure
    infra.close()


if __name__ == "__main__":
    example_usage()
