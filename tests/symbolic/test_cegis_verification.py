"""Unit tests for CEGIS and verification infrastructure."""

import numpy as np
import pytest

from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.verification.cegis import CEGISCoordinator, CEGISResult, Counterexample, Example
from arc.symbolic.verification.counterexample import CounterexampleMinimizer
from arc.symbolic.verification.invariant import InvariantChecker
from arc.symbolic.verification.repair import (
    ConstraintBasedRepairer,
    MultiSolutionArbitrator,
    ProgramEdit,
)


# Mock verifier for testing
class MockVerifier:
    """Mock verifier for testing."""
    
    def __init__(self, should_pass=True):
        self.should_pass = should_pass
        self.verify_calls = []
        self.execute_calls = []
    
    def verify(self, program, input_grid, output_grid):
        """Mock verify method."""
        self.verify_calls.append((program, input_grid, output_grid))
        
        if self.should_pass:
            return {"success": True}
        else:
            return {
                "success": False,
                "actual_output": input_grid,  # Return input as actual
            }
    
    def execute(self, program, input_grid):
        """Mock execute method."""
        self.execute_calls.append((program, input_grid))
        return {"output": input_grid}


# Mock synthesizer for testing
class MockSynthesizer:
    """Mock synthesizer for testing."""
    
    def __init__(self, program_to_return=None):
        self.program_to_return = program_to_return
        self.synthesize_calls = []
    
    def synthesize(self, examples):
        """Mock synthesize method."""
        self.synthesize_calls.append(examples)
        return self.program_to_return


class TestCounterexample:
    """Test Counterexample data structure."""
    
    def test_counterexample_creation(self):
        """Test creating a counterexample."""
        input_grid = Grid.from_list([[0, 1], [1, 0]])
        expected = Grid.from_list([[1, 0], [0, 1]])
        actual = Grid.from_list([[0, 0], [0, 0]])
        
        ce = Counterexample(
            input_grid=input_grid,
            expected_output=expected,
            actual_output=actual,
            minimal=False,
        )
        
        assert ce.input_grid.equals(input_grid)
        assert ce.expected_output.equals(expected)
        assert ce.actual_output.equals(actual)
        assert not ce.minimal
    
    def test_counterexample_serialization(self):
        """Test counterexample serialization."""
        input_grid = Grid.from_list([[0, 1]])
        expected = Grid.from_list([[1, 0]])
        actual = Grid.from_list([[0, 0]])
        
        ce = Counterexample(
            input_grid=input_grid,
            expected_output=expected,
            actual_output=actual,
        )
        
        # Test to_dict
        ce_dict = ce.to_dict()
        assert "input_grid" in ce_dict
        assert "expected_output" in ce_dict
        assert "actual_output" in ce_dict
        
        # Test from_dict
        ce_restored = Counterexample.from_dict(ce_dict)
        assert ce_restored.input_grid.equals(input_grid)
        assert ce_restored.expected_output.equals(expected)


class TestCEGISResult:
    """Test CEGISResult data structure."""
    
    def test_cegis_result_creation(self):
        """Test creating a CEGIS result."""
        program = Program(stages=(Stage("rotate", (90,)),))
        
        result = CEGISResult(
            success=True,
            program=program,
            iterations=3,
            verification_time=1.5,
            synthesis_time=2.0,
        )
        
        assert result.success
        assert result.program == program
        assert result.iterations == 3
        assert result.verification_time == 1.5
        assert result.synthesis_time == 2.0
    
    def test_cegis_result_serialization(self):
        """Test CEGIS result serialization."""
        result = CEGISResult(
            success=False,
            iterations=5,
        )
        
        result_dict = result.to_dict()
        assert result_dict["success"] is False
        assert result_dict["iterations"] == 5


class TestCEGISCoordinator:
    """Test CEGISCoordinator."""
    
    def test_cegis_coordinator_initialization(self):
        """Test CEGIS coordinator initialization."""
        config = {"cegis": {"max_iterations": 5}}
        coordinator = CEGISCoordinator(config)
        
        assert coordinator.max_iterations == 5
    
    def test_cegis_loop_success(self):
        """Test successful CEGIS loop."""
        # Create mock components
        program = Program(stages=(Stage("identity", ()),))
        verifier = MockVerifier(should_pass=True)
        synthesizer = MockSynthesizer(program_to_return=program)
        
        config = {"cegis": {"max_iterations": 3}}
        coordinator = CEGISCoordinator(config, synthesizer=synthesizer, verifier=verifier)
        
        # Create examples
        examples = [
            Example(
                input_grid=Grid.from_list([[0, 1]]),
                output_grid=Grid.from_list([[1, 0]]),
            )
        ]
        
        # Run CEGIS loop
        result = coordinator.run_cegis_loop(examples)
        
        assert result.success
        assert result.program == program
        assert result.iterations == 1
    
    def test_cegis_loop_max_iterations(self):
        """Test CEGIS loop reaching max iterations."""
        # Create mock components that always fail
        verifier = MockVerifier(should_pass=False)
        synthesizer = MockSynthesizer(program_to_return=Program(stages=()))
        
        config = {"cegis": {"max_iterations": 2, "minimize_counterexamples": False}}
        coordinator = CEGISCoordinator(config, synthesizer=synthesizer, verifier=verifier)
        
        # Create examples
        examples = [
            Example(
                input_grid=Grid.from_list([[0]]),
                output_grid=Grid.from_list([[1]]),
            )
        ]
        
        # Run CEGIS loop
        result = coordinator.run_cegis_loop(examples, max_iterations=2)
        
        assert not result.success
        assert result.iterations == 2
        assert len(result.counterexamples) == 2


class TestCounterexampleMinimizer:
    """Test CounterexampleMinimizer."""
    
    def test_minimizer_initialization(self):
        """Test minimizer initialization."""
        config = {"counterexample_minimizer": {"max_iterations": 5}}
        minimizer = CounterexampleMinimizer(config)
        
        assert minimizer.max_iterations == 5
    
    def test_shrink_grid_remove_row(self):
        """Test shrinking grid by removing a row."""
        config = {"counterexample_minimizer": {"min_grid_size": 1}}
        minimizer = CounterexampleMinimizer(config)
        
        # Create a 3x2 grid
        grid = Grid.from_list([[0, 1], [1, 0], [0, 1]])
        
        # Predicate that always returns True (failure preserved)
        def always_fails(g):
            return True
        
        # Shrink grid
        shrunk = minimizer.shrink_grid(grid, always_fails)
        
        # Should have removed at least one row
        assert shrunk.shape[0] < grid.shape[0]
    
    def test_shrink_grid_remove_column(self):
        """Test shrinking grid by removing a column."""
        config = {"counterexample_minimizer": {"min_grid_size": 1}}
        minimizer = CounterexampleMinimizer(config)
        
        # Create a 2x3 grid
        grid = Grid.from_list([[0, 1, 0], [1, 0, 1]])
        
        # Predicate that always returns True
        def always_fails(g):
            return True
        
        # Shrink grid
        shrunk = minimizer.shrink_grid(grid, always_fails)
        
        # Should have removed at least one column
        assert shrunk.shape[1] < grid.shape[1]


class TestInvariantChecker:
    """Test InvariantChecker."""
    
    def test_invariant_checker_initialization(self):
        """Test invariant checker initialization."""
        config = {"invariants": {"enabled": ["color_conservation"]}}
        checker = InvariantChecker(config)
        
        assert "color_conservation" in checker.enabled_invariants
    
    def test_check_color_conservation_pass(self):
        """Test color conservation check that passes."""
        config = {}
        checker = InvariantChecker(config)
        
        input_grid = Grid.from_list([[0, 1, 2], [1, 2, 0]])
        output_grid = Grid.from_list([[1, 2], [0, 1]])  # Subset of colors
        
        result = checker.check_color_conservation(input_grid, output_grid)
        assert result is True
    
    def test_check_color_conservation_fail(self):
        """Test color conservation check that fails."""
        config = {"invariants": {"color_tolerance": 0}}
        checker = InvariantChecker(config)
        
        input_grid = Grid.from_list([[0, 1]])
        output_grid = Grid.from_list([[0, 1, 2, 3]])  # New colors
        
        result = checker.check_color_conservation(input_grid, output_grid)
        assert result is False
    
    def test_check_object_count(self):
        """Test object count check."""
        config = {"invariants": {"object_count_tolerance": 1}}
        checker = InvariantChecker(config)
        
        # Input: 2 objects (two separate 1s)
        input_grid = Grid.from_list([[1, 0, 1], [0, 0, 0]])
        
        # Output: 1 object (connected 1s)
        output_grid = Grid.from_list([[1, 1, 0], [0, 0, 0]])
        
        # Should pass with tolerance of 1
        result = checker.check_object_count(input_grid, output_grid, tolerance=1)
        assert result is True
    
    def test_check_topology(self):
        """Test topology check."""
        config = {}
        checker = InvariantChecker(config)
        
        input_grid = Grid.from_list([[1, 1], [1, 1]])
        output_grid = Grid.from_list([[1, 1], [1, 1]])
        
        result = checker.check_topology(input_grid, output_grid)
        assert result is True


class TestConstraintBasedRepairer:
    """Test ConstraintBasedRepairer."""
    
    def test_repairer_initialization(self):
        """Test repairer initialization."""
        config = {"repair": {"max_repairs": 3}}
        repairer = ConstraintBasedRepairer(config)
        
        assert repairer.max_repairs == 3
    
    def test_apply_edit_insert(self):
        """Test applying insert edit."""
        config = {}
        repairer = ConstraintBasedRepairer(config)
        
        program = Program(stages=(Stage("rotate", (90,)),))
        edit = ProgramEdit(
            edit_type="insert",
            location=0,
            content=Stage("reflect", ("horizontal",)),
        )
        
        repaired = repairer.apply_edit(program, edit)
        
        assert len(repaired.stages) == 2
        assert repaired.stages[0].operator == "reflect"
        assert repaired.stages[1].operator == "rotate"
    
    def test_apply_edit_delete(self):
        """Test applying delete edit."""
        config = {}
        repairer = ConstraintBasedRepairer(config)
        
        program = Program(stages=(
            Stage("rotate", (90,)),
            Stage("reflect", ("horizontal",)),
        ))
        edit = ProgramEdit(edit_type="delete", location=0)
        
        repaired = repairer.apply_edit(program, edit)
        
        assert len(repaired.stages) == 1
        assert repaired.stages[0].operator == "reflect"
    
    def test_apply_edit_replace(self):
        """Test applying replace edit."""
        config = {}
        repairer = ConstraintBasedRepairer(config)
        
        program = Program(stages=(Stage("rotate", (90,)),))
        edit = ProgramEdit(
            edit_type="replace",
            location=0,
            content=Stage("reflect", ("vertical",)),
        )
        
        repaired = repairer.apply_edit(program, edit)
        
        assert len(repaired.stages) == 1
        assert repaired.stages[0].operator == "reflect"


class TestMultiSolutionArbitrator:
    """Test MultiSolutionArbitrator."""
    
    def test_arbitrator_initialization(self):
        """Test arbitrator initialization."""
        config = {"multi_solution_arbitrator": {"diversity_weight": 0.3}}
        arbitrator = MultiSolutionArbitrator(config)
        
        assert arbitrator.diversity_weight == 0.3
    
    def test_score_solution(self):
        """Test scoring a solution."""
        verifier = MockVerifier(should_pass=True)
        config = {}
        arbitrator = MultiSolutionArbitrator(config, verifier=verifier)
        
        program = Program(stages=(Stage("identity", ()),))
        examples = [
            Example(
                input_grid=Grid.from_list([[0]]),
                output_grid=Grid.from_list([[0]]),
            )
        ]
        
        score = arbitrator.score_solution(program, examples, {})
        
        # Score should be positive
        assert score > 0
    
    def test_arbitrate_solutions(self):
        """Test arbitrating multiple solutions."""
        verifier = MockVerifier(should_pass=True)
        config = {"multi_solution_arbitrator": {"diversity_weight": 0.0}}
        arbitrator = MultiSolutionArbitrator(config, verifier=verifier)
        
        # Create solutions of different lengths
        solution1 = Program(stages=(Stage("identity", ()),))
        solution2 = Program(stages=(
            Stage("rotate", (90,)),
            Stage("reflect", ("horizontal",)),
        ))
        
        examples = [
            Example(
                input_grid=Grid.from_list([[0]]),
                output_grid=Grid.from_list([[0]]),
            )
        ]
        
        ranked = arbitrator.arbitrate_solutions([solution1, solution2], examples)
        
        # Should return ranked list
        assert len(ranked) == 2
        # Shorter program should rank higher (with equal correctness)
        assert len(ranked[0][0].stages) <= len(ranked[1][0].stages)


class TestProgramEdit:
    """Test ProgramEdit data structure."""
    
    def test_program_edit_creation(self):
        """Test creating a program edit."""
        edit = ProgramEdit(
            edit_type="insert",
            location=0,
            content=Stage("rotate", (90,)),
            cost=1.5,
        )
        
        assert edit.edit_type == "insert"
        assert edit.location == 0
        assert edit.content.operator == "rotate"
        assert edit.cost == 1.5
    
    def test_program_edit_serialization(self):
        """Test program edit serialization."""
        edit = ProgramEdit(
            edit_type="delete",
            location=2,
            cost=1.0,
        )
        
        edit_dict = edit.to_dict()
        assert edit_dict["edit_type"] == "delete"
        assert edit_dict["location"] == 2
        assert edit_dict["cost"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
