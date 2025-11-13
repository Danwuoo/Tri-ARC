"""Counter-Example Guided Inductive Synthesis (CEGIS) coordinator.

This module implements the CEGIS loop for program synthesis:
1. Generate candidate program from examples and counterexamples
2. Verify candidate against all examples
3. If verification fails, generate counterexample and refine
4. Iterate until success or max iterations reached
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from arc.symbolic.dsl.types import Grid, Program


@dataclass
class Counterexample:
    """Represents a counterexample that causes a program to fail.
    
    Attributes:
        input_grid: The input grid that causes failure
        expected_output: The expected output grid
        actual_output: The actual output produced by the program
        minimal: Whether this counterexample has been minimized
        metadata: Additional metadata about the counterexample
    """
    
    input_grid: Grid
    expected_output: Grid
    actual_output: Grid
    minimal: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize Counterexample to dictionary.
        
        Returns:
            Dictionary representation of the counterexample
        """
        return {
            "input_grid": self.input_grid.to_list(),
            "expected_output": self.expected_output.to_list(),
            "actual_output": self.actual_output.to_list(),
            "minimal": self.minimal,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Counterexample:
        """Deserialize Counterexample from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed Counterexample
        """
        return cls(
            input_grid=Grid.from_list(data["input_grid"]),
            expected_output=Grid.from_list(data["expected_output"]),
            actual_output=Grid.from_list(data["actual_output"]),
            minimal=data.get("minimal", False),
            metadata=data.get("metadata", {}),
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class CEGISResult:
    """Result of a CEGIS synthesis loop.
    
    Attributes:
        success: Whether synthesis succeeded
        program: The synthesized program (if successful)
        iterations: Number of CEGIS iterations performed
        counterexamples: List of counterexamples encountered
        verification_time: Total time spent in verification
        synthesis_time: Total time spent in synthesis
        metadata: Additional metadata about the synthesis process
    """
    
    success: bool
    program: Optional[Program] = None
    iterations: int = 0
    counterexamples: List[Counterexample] = field(default_factory=list)
    verification_time: float = 0.0
    synthesis_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize CEGISResult to dictionary.
        
        Returns:
            Dictionary representation of the result
        """
        return {
            "success": self.success,
            "program": str(self.program) if self.program else None,
            "iterations": self.iterations,
            "counterexamples": [ce.to_dict() for ce in self.counterexamples],
            "verification_time": self.verification_time,
            "synthesis_time": self.synthesis_time,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class Example:
    """Training example with input and output grids."""
    
    input_grid: Grid
    output_grid: Grid
    metadata: Dict[str, Any] = field(default_factory=dict)


class CEGISCoordinator:
    """Coordinates the Counter-Example Guided Inductive Synthesis loop.
    
    The CEGIS loop iteratively:
    1. Generates a candidate program from examples and counterexamples
    2. Verifies the candidate against all examples
    3. If verification fails, generates a counterexample
    4. Minimizes the counterexample and adds it to the set
    5. Repeats until success or max iterations reached
    
    Attributes:
        config: Configuration dictionary
        synthesizer: Program synthesizer (injected dependency)
        verifier: Program verifier (injected dependency)
        minimizer: Counterexample minimizer (injected dependency)
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        synthesizer: Optional[Any] = None,
        verifier: Optional[Any] = None,
        minimizer: Optional[Any] = None,
    ):
        """Initialize CEGIS coordinator.
        
        Args:
            config: Configuration dictionary
            synthesizer: Program synthesizer (optional, can be set later)
            verifier: Program verifier (optional, can be set later)
            minimizer: Counterexample minimizer (optional, can be set later)
        """
        self.config = config
        self.synthesizer = synthesizer
        self.verifier = verifier
        self.minimizer = minimizer
        
        # Extract configuration
        cegis_config = config.get("cegis", {})
        self.max_iterations = cegis_config.get("max_iterations", 10)
        self.minimize_counterexamples = cegis_config.get("minimize_counterexamples", True)
        self.timeout_per_iteration = cegis_config.get("timeout_per_iteration", 30.0)
    
    def run_cegis_loop(
        self,
        examples: List[Example],
        max_iterations: Optional[int] = None,
        initial_counterexamples: Optional[List[Counterexample]] = None,
    ) -> CEGISResult:
        """Run the CEGIS loop to synthesize a program.
        
        Args:
            examples: List of training examples
            max_iterations: Maximum number of iterations (overrides config)
            initial_counterexamples: Initial counterexamples to start with
            
        Returns:
            CEGISResult containing the synthesis outcome
        """
        max_iter = max_iterations if max_iterations is not None else self.max_iterations
        counterexamples = list(initial_counterexamples) if initial_counterexamples else []
        
        total_verification_time = 0.0
        total_synthesis_time = 0.0
        
        for iteration in range(max_iter):
            # Generate candidate program
            synthesis_start = time.perf_counter()
            candidate = self.generate_candidate(examples, counterexamples)
            synthesis_time = time.perf_counter() - synthesis_start
            total_synthesis_time += synthesis_time
            
            if candidate is None:
                # Synthesis failed, cannot continue
                return CEGISResult(
                    success=False,
                    program=None,
                    iterations=iteration + 1,
                    counterexamples=counterexamples,
                    verification_time=total_verification_time,
                    synthesis_time=total_synthesis_time,
                    metadata={"failure_reason": "synthesis_failed"},
                )
            
            # Verify candidate
            verification_start = time.perf_counter()
            verification_result = self.verify_candidate(candidate, examples)
            verification_time = time.perf_counter() - verification_start
            total_verification_time += verification_time
            
            if verification_result["success"]:
                # Verification succeeded!
                return CEGISResult(
                    success=True,
                    program=candidate,
                    iterations=iteration + 1,
                    counterexamples=counterexamples,
                    verification_time=total_verification_time,
                    synthesis_time=total_synthesis_time,
                    metadata={"verification_result": verification_result},
                )
            
            # Verification failed, generate counterexample
            failed_example = verification_result.get("failed_example")
            if failed_example is None:
                # No specific failure, cannot continue
                return CEGISResult(
                    success=False,
                    program=candidate,
                    iterations=iteration + 1,
                    counterexamples=counterexamples,
                    verification_time=total_verification_time,
                    synthesis_time=total_synthesis_time,
                    metadata={"failure_reason": "no_counterexample"},
                )
            
            counterexample = self.generate_counterexample(
                candidate,
                failed_example,
            )
            
            # Minimize counterexample if enabled
            if self.minimize_counterexamples and self.minimizer:
                counterexample = self.minimizer.minimize(candidate, counterexample)
            
            counterexamples.append(counterexample)
        
        # Max iterations reached without success
        return CEGISResult(
            success=False,
            program=None,
            iterations=max_iter,
            counterexamples=counterexamples,
            verification_time=total_verification_time,
            synthesis_time=total_synthesis_time,
            metadata={"failure_reason": "max_iterations_reached"},
        )
    
    def generate_candidate(
        self,
        examples: List[Example],
        counterexamples: List[Counterexample],
    ) -> Optional[Program]:
        """Generate a candidate program from examples and counterexamples.
        
        Args:
            examples: List of training examples
            counterexamples: List of counterexamples from previous iterations
            
        Returns:
            A candidate Program, or None if synthesis fails
        """
        if self.synthesizer is None:
            raise ValueError("Synthesizer not set. Cannot generate candidate.")
        
        # Combine examples and counterexamples into a unified training set
        all_examples = list(examples)
        for ce in counterexamples:
            all_examples.append(Example(
                input_grid=ce.input_grid,
                output_grid=ce.expected_output,
                metadata={"from_counterexample": True},
            ))
        
        # Call synthesizer to generate candidate
        # The synthesizer should return a Program or None
        try:
            candidate = self.synthesizer.synthesize(all_examples)
            return candidate
        except Exception as e:
            # Synthesis failed
            return None
    
    def verify_candidate(
        self,
        program: Program,
        examples: List[Example],
    ) -> Dict[str, Any]:
        """Verify a candidate program against all examples.
        
        Args:
            program: The candidate program to verify
            examples: List of examples to verify against
            
        Returns:
            Dictionary with verification result:
                - success: bool indicating if verification passed
                - failed_example: Example that failed (if any)
                - error: Error message (if any)
        """
        if self.verifier is None:
            raise ValueError("Verifier not set. Cannot verify candidate.")
        
        try:
            # Verify program against each example
            for example in examples:
                result = self.verifier.verify(program, example.input_grid, example.output_grid)
                
                if not result["success"]:
                    return {
                        "success": False,
                        "failed_example": example,
                        "actual_output": result.get("actual_output"),
                        "error": result.get("error"),
                    }
            
            # All examples passed
            return {"success": True}
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    def generate_counterexample(
        self,
        program: Program,
        failed_example: Example,
    ) -> Counterexample:
        """Generate a counterexample from a failed verification.
        
        Args:
            program: The program that failed
            failed_example: The example that caused the failure
            
        Returns:
            A Counterexample object
        """
        # Execute program to get actual output
        if self.verifier is None:
            raise ValueError("Verifier not set. Cannot generate counterexample.")
        
        try:
            result = self.verifier.execute(program, failed_example.input_grid)
            actual_output = result.get("output", failed_example.input_grid)
        except Exception as e:
            # Execution failed, use input as actual output
            actual_output = failed_example.input_grid
        
        return Counterexample(
            input_grid=failed_example.input_grid,
            expected_output=failed_example.output_grid,
            actual_output=actual_output,
            minimal=False,
            metadata={
                "program": str(program),
                "iteration": len(self.config.get("counterexamples", [])),
            },
        )
