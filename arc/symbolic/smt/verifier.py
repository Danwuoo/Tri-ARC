"""Batch verifier for SMT-based program verification."""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Optional, Tuple

from arc.symbolic.dsl.types import Grid, Program

from .encoder import ConstraintEncoder
from .types import SMTConstraintSet, VerificationResult

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    z3 = None  # type: ignore


class BatchVerifier:
    """Batch verifier for SMT-based program verification.
    
    This verifier can check multiple candidate programs in parallel,
    with caching and incremental solving support.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the batch verifier.
        
        Args:
            config: Configuration dictionary
        """
        if not Z3_AVAILABLE:
            raise ImportError("Z3 solver is required but not installed")
        
        self.config = config or {}
        self.encoder = ConstraintEncoder(config)
        self.timeout_per_candidate = float(self.config.get("timeout_per_candidate", 2.0))
        self.enable_caching = bool(self.config.get("enable_caching", True))
        self.max_workers = int(self.config.get("max_workers", 4))
        
        # Cache for verification results
        self._cache: Dict[str, VerificationResult] = {}
        self._cache_hits = 0
        self._cache_misses = 0
    
    def verify_batch(
        self,
        candidates: List[Tuple[Program, Grid, Grid]],
        timeout_per_candidate: Optional[float] = None
    ) -> List[VerificationResult]:
        """Verify a batch of candidate programs in parallel.
        
        Args:
            candidates: List of (program, input_grid, expected_output) tuples
            timeout_per_candidate: Timeout in seconds for each candidate
            
        Returns:
            List of VerificationResult objects
        """
        timeout = timeout_per_candidate or self.timeout_per_candidate
        results = []
        
        # Use thread pool for parallel verification
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i, (program, input_grid, expected_output) in enumerate(candidates):
                program_id = f"candidate_{i}"
                future = executor.submit(
                    self._verify_single,
                    program_id,
                    program,
                    input_grid,
                    expected_output,
                    timeout
                )
                futures.append(future)
            
            # Collect results
            for future in futures:
                try:
                    result = future.result(timeout=timeout + 1.0)
                    results.append(result)
                except FuturesTimeoutError:
                    results.append(VerificationResult(
                        program_id="unknown",
                        status="timeout",
                        verification_time=timeout,
                        metadata={"error": "Thread pool timeout"}
                    ))
                except Exception as e:
                    results.append(VerificationResult(
                        program_id="unknown",
                        status="error",
                        verification_time=0.0,
                        metadata={"error": str(e)}
                    ))
        
        return results
    
    def verify_incremental(
        self,
        program: Program,
        input_grid: Grid,
        expected_output: Grid,
        solver_context: Optional[Any] = None
    ) -> VerificationResult:
        """Verify a program using incremental solving (push/pop).
        
        Args:
            program: Program to verify
            input_grid: Input grid
            expected_output: Expected output grid
            solver_context: Existing Z3 solver context (optional)
            
        Returns:
            VerificationResult
        """
        program_id = self._compute_program_hash(program, input_grid, expected_output)
        
        # Check cache
        if self.enable_caching and program_id in self._cache:
            self._cache_hits += 1
            cached_result = self._cache[program_id]
            cached_result.metadata["cache_hit"] = True
            return cached_result
        
        self._cache_misses += 1
        
        start_time = time.perf_counter()
        
        try:
            # Create or reuse solver
            if solver_context is None:
                solver = z3.Solver()
                solver.set("timeout", int(self.timeout_per_candidate * 1000))
            else:
                solver = solver_context
                solver.push()  # Save current state
            
            # Encode program
            constraint_set = self.encoder.encode_program(
                program, input_grid, expected_output
            )
            
            # Check if encoding succeeded
            if "unsupported_primitive" in constraint_set.metadata:
                elapsed = time.perf_counter() - start_time
                result = VerificationResult(
                    program_id=program_id,
                    status="unknown",
                    verification_time=elapsed,
                    metadata={
                        "unsupported_primitive": constraint_set.metadata["unsupported_primitive"]
                    }
                )
                if solver_context is not None:
                    solver.pop()  # Restore state
                return result
            
            # Add constraints to solver
            for constraint in constraint_set.get_all_constraints():
                solver.add(constraint)
            
            # Check satisfiability
            check_result = solver.check()
            elapsed = time.perf_counter() - start_time
            
            if check_result == z3.sat:
                model = solver.model()
                result = VerificationResult(
                    program_id=program_id,
                    status="sat",
                    verification_time=elapsed,
                    model=self._extract_model(model),
                    metadata={"constraint_count": len(constraint_set.get_all_constraints())}
                )
            elif check_result == z3.unsat:
                unsat_core = self._extract_unsat_core(solver)
                result = VerificationResult(
                    program_id=program_id,
                    status="unsat",
                    verification_time=elapsed,
                    unsat_core=unsat_core,
                    metadata={"constraint_count": len(constraint_set.get_all_constraints())}
                )
            else:  # unknown
                result = VerificationResult(
                    program_id=program_id,
                    status="unknown",
                    verification_time=elapsed,
                    metadata={
                        "reason": solver.reason_unknown(),
                        "constraint_count": len(constraint_set.get_all_constraints())
                    }
                )
            
            # Restore solver state if using incremental
            if solver_context is not None:
                solver.pop()
            
            # Cache result
            if self.enable_caching:
                self._cache[program_id] = result
            
            return result
            
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            result = VerificationResult(
                program_id=program_id,
                status="error",
                verification_time=elapsed,
                metadata={"error": str(e), "error_type": type(e).__name__}
            )
            
            if solver_context is not None:
                try:
                    solver.pop()
                except:
                    pass
            
            return result
    
    def _verify_single(
        self,
        program_id: str,
        program: Program,
        input_grid: Grid,
        expected_output: Grid,
        timeout: float
    ) -> VerificationResult:
        """Verify a single program (internal method for parallel execution).
        
        Args:
            program_id: Unique identifier for the program
            program: Program to verify
            input_grid: Input grid
            expected_output: Expected output grid
            timeout: Timeout in seconds
            
        Returns:
            VerificationResult
        """
        # Use incremental verification
        return self.verify_incremental(program, input_grid, expected_output)
    
    def _compute_program_hash(
        self,
        program: Program,
        input_grid: Grid,
        expected_output: Grid
    ) -> str:
        """Compute a hash for caching purposes.
        
        Args:
            program: Program
            input_grid: Input grid
            expected_output: Expected output grid
            
        Returns:
            Hash string
        """
        # Create a string representation
        program_str = str([(s.operator, s.arguments) for s in program.stages])
        input_str = str(input_grid.to_list())
        output_str = str(expected_output.to_list())
        
        combined = f"{program_str}|{input_str}|{output_str}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _extract_model(self, model: Any) -> Dict[str, Any]:
        """Extract model values from Z3 model.
        
        Args:
            model: Z3 model
            
        Returns:
            Dictionary of variable assignments
        """
        result = {}
        try:
            for decl in model.decls():
                name = decl.name()
                value = model[decl]
                result[name] = str(value)
        except Exception:
            pass
        return result
    
    def _extract_unsat_core(self, solver: Any) -> Optional[List[str]]:
        """Extract unsat core from solver.
        
        Args:
            solver: Z3 solver
            
        Returns:
            List of constraint names in the unsat core, or None
        """
        try:
            core = solver.unsat_core()
            return [str(c) for c in core]
        except Exception:
            return None
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache hits, misses, and size
        """
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self._cache),
            "hit_rate": self._cache_hits / max(1, self._cache_hits + self._cache_misses)
        }
    
    def clear_cache(self) -> None:
        """Clear the verification cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
