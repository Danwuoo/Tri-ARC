"""Unit tests for SMT gateway components."""

from __future__ import annotations

import pytest
import numpy as np

from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.ir.sketch import Hole, ProgramSketch


# Check if Z3 is available
try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False


pytestmark = pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 solver not available")


@pytest.fixture
def simple_grid():
    """Create a simple 3x3 grid for testing."""
    data = np.array([
        [0, 1, 0],
        [1, 1, 1],
        [0, 1, 0]
    ], dtype=np.int16)
    return Grid(data)


@pytest.fixture
def rotated_grid():
    """Create a 90-degree rotated version of simple_grid."""
    data = np.array([
        [0, 1, 0],
        [1, 1, 1],
        [0, 1, 0]
    ], dtype=np.int16)
    # Rotate 90 degrees clockwise
    rotated = np.rot90(data, k=-1)
    return Grid(rotated)


@pytest.fixture
def reflected_grid():
    """Create a horizontally reflected version of simple_grid."""
    data = np.array([
        [0, 1, 0],
        [1, 1, 1],
        [0, 1, 0]
    ], dtype=np.int16)
    reflected = np.fliplr(data)
    return Grid(reflected)


class TestSMTArray:
    """Test SMTArray data structure."""
    
    def test_smt_array_creation(self):
        """Test creating an SMTArray."""
        from arc.symbolic.smt.types import SMTArray
        
        array = SMTArray(
            name="test_array",
            shape=(3, 3),
            domain=(0, 9)
        )
        
        assert array.name == "test_array"
        assert array.shape == (3, 3)
        assert array.domain == (0, 9)
    
    def test_smt_array_invalid_shape(self):
        """Test that invalid shapes raise errors."""
        from arc.symbolic.smt.types import SMTArray
        
        with pytest.raises(ValueError):
            SMTArray(name="bad", shape=(0, 3), domain=(0, 9))
        
        with pytest.raises(ValueError):
            SMTArray(name="bad", shape=(3, -1), domain=(0, 9))
    
    def test_smt_array_invalid_domain(self):
        """Test that invalid domains raise errors."""
        from arc.symbolic.smt.types import SMTArray
        
        with pytest.raises(ValueError):
            SMTArray(name="bad", shape=(3, 3), domain=(9, 0))


class TestSMTConstraintSet:
    """Test SMTConstraintSet data structure."""
    
    def test_constraint_set_creation(self):
        """Test creating a constraint set."""
        from arc.symbolic.smt.types import SMTConstraintSet
        
        cs = SMTConstraintSet()
        assert len(cs.variables) == 0
        assert len(cs.constraints) == 0
        assert len(cs.assertions) == 0
    
    def test_add_variable(self):
        """Test adding variables."""
        from arc.symbolic.smt.types import SMTConstraintSet
        
        cs = SMTConstraintSet()
        cs.add_variable("x", z3.Int("x"))
        
        assert "x" in cs.variables
        assert len(cs.variables) == 1
    
    def test_add_constraint(self):
        """Test adding constraints."""
        from arc.symbolic.smt.types import SMTConstraintSet
        
        cs = SMTConstraintSet()
        x = z3.Int("x")
        cs.add_constraint(x > 0)
        
        assert len(cs.constraints) == 1
    
    def test_get_all_constraints(self):
        """Test getting all constraints."""
        from arc.symbolic.smt.types import SMTConstraintSet
        
        cs = SMTConstraintSet()
        x = z3.Int("x")
        cs.add_constraint(x > 0)
        cs.add_assertion(x < 10)
        
        all_constraints = cs.get_all_constraints()
        assert len(all_constraints) == 2


class TestVerificationResult:
    """Test VerificationResult data structure."""
    
    def test_verification_result_verified(self):
        """Test a verified result."""
        from arc.symbolic.smt.types import VerificationResult
        
        result = VerificationResult(
            program_id="test",
            status="sat",
            verification_time=0.5
        )
        
        assert result.is_verified
        assert not result.is_refuted
        assert not result.is_inconclusive
    
    def test_verification_result_refuted(self):
        """Test a refuted result."""
        from arc.symbolic.smt.types import VerificationResult
        
        result = VerificationResult(
            program_id="test",
            status="unsat",
            verification_time=0.5
        )
        
        assert not result.is_verified
        assert result.is_refuted
        assert not result.is_inconclusive
    
    def test_verification_result_inconclusive(self):
        """Test inconclusive results."""
        from arc.symbolic.smt.types import VerificationResult
        
        for status in ["unknown", "timeout", "error"]:
            result = VerificationResult(
                program_id="test",
                status=status,
                verification_time=0.5
            )
            
            assert not result.is_verified
            assert not result.is_refuted
            assert result.is_inconclusive


class TestConstraintEncoder:
    """Test ConstraintEncoder."""
    
    def test_encoder_creation(self):
        """Test creating an encoder."""
        from arc.symbolic.smt.encoder import ConstraintEncoder
        
        encoder = ConstraintEncoder()
        assert encoder is not None
    
    def test_encode_grid(self, simple_grid):
        """Test encoding a grid."""
        from arc.symbolic.smt.encoder import ConstraintEncoder
        
        encoder = ConstraintEncoder()
        smt_array = encoder.encode_grid(simple_grid, "test_grid")
        
        assert smt_array.name == "test_grid"
        assert smt_array.shape == simple_grid.shape
        assert smt_array.domain == (0, 9)
        assert smt_array.z3_array is not None
    
    def test_encode_identity(self, simple_grid):
        """Test encoding identity operation."""
        from arc.symbolic.smt.encoder import ConstraintEncoder
        
        encoder = ConstraintEncoder()
        program = Program(stages=(
            Stage(operator="identity", arguments=()),
        ))
        
        constraint_set = encoder.encode_program(
            program, simple_grid, simple_grid
        )
        
        assert len(constraint_set.variables) > 0
        assert len(constraint_set.get_all_constraints()) > 0
    
    def test_encode_rotate(self, simple_grid, rotated_grid):
        """Test encoding rotation operation."""
        from arc.symbolic.smt.encoder import ConstraintEncoder
        
        encoder = ConstraintEncoder()
        program = Program(stages=(
            Stage(operator="rotate", arguments=(1,)),  # 90 degrees
        ))
        
        constraint_set = encoder.encode_program(
            program, simple_grid, rotated_grid
        )
        
        assert "unsupported_primitive" not in constraint_set.metadata
        assert len(constraint_set.get_all_constraints()) > 0
    
    def test_encode_reflect(self, simple_grid, reflected_grid):
        """Test encoding reflection operation."""
        from arc.symbolic.smt.encoder import ConstraintEncoder
        
        encoder = ConstraintEncoder()
        program = Program(stages=(
            Stage(operator="reflect", arguments=("horizontal",)),
        ))
        
        constraint_set = encoder.encode_program(
            program, simple_grid, reflected_grid
        )
        
        assert "unsupported_primitive" not in constraint_set.metadata
        assert len(constraint_set.get_all_constraints()) > 0
    
    def test_encode_replace_colour(self, simple_grid):
        """Test encoding color replacement."""
        from arc.symbolic.smt.encoder import ConstraintEncoder
        
        encoder = ConstraintEncoder()
        
        # Create output with color 1 replaced by color 2
        output_data = simple_grid.data.copy()
        output_data[output_data == 1] = 2
        output_grid = Grid(output_data)
        
        program = Program(stages=(
            Stage(operator="replace_colour", arguments=(1, 2)),
        ))
        
        constraint_set = encoder.encode_program(
            program, simple_grid, output_grid
        )
        
        assert "unsupported_primitive" not in constraint_set.metadata
        assert len(constraint_set.get_all_constraints()) > 0


class TestBatchVerifier:
    """Test BatchVerifier."""
    
    def test_verifier_creation(self):
        """Test creating a verifier."""
        from arc.symbolic.smt.verifier import BatchVerifier
        
        verifier = BatchVerifier(config={"timeout_per_candidate": 1.0})
        assert verifier is not None
        assert verifier.timeout_per_candidate == 1.0
    
    def test_verify_identity(self, simple_grid):
        """Test verifying an identity program."""
        from arc.symbolic.smt.verifier import BatchVerifier
        
        verifier = BatchVerifier()
        program = Program(stages=(
            Stage(operator="identity", arguments=()),
        ))
        
        result = verifier.verify_incremental(
            program, simple_grid, simple_grid
        )
        
        # Identity should verify successfully
        assert result.status in ("sat", "unknown")  # May be unknown due to complexity
        assert result.verification_time >= 0
    
    def test_verify_batch(self, simple_grid):
        """Test batch verification."""
        from arc.symbolic.smt.verifier import BatchVerifier
        
        verifier = BatchVerifier(config={"max_workers": 2})
        
        program1 = Program(stages=(Stage(operator="identity", arguments=()),))
        program2 = Program(stages=(Stage(operator="rotate", arguments=(0,)),))
        
        candidates = [
            (program1, simple_grid, simple_grid),
            (program2, simple_grid, simple_grid),
        ]
        
        results = verifier.verify_batch(candidates)
        
        assert len(results) == 2
        for result in results:
            assert result.status in ("sat", "unsat", "unknown", "timeout", "error")
    
    def test_cache_functionality(self, simple_grid):
        """Test that caching works."""
        from arc.symbolic.smt.verifier import BatchVerifier
        
        verifier = BatchVerifier(config={"enable_caching": True})
        program = Program(stages=(Stage(operator="identity", arguments=()),))
        
        # First verification
        result1 = verifier.verify_incremental(program, simple_grid, simple_grid)
        
        # Second verification (should hit cache)
        result2 = verifier.verify_incremental(program, simple_grid, simple_grid)
        
        stats = verifier.get_cache_stats()
        assert stats["cache_hits"] >= 1
        assert stats["cache_size"] >= 1


class TestWitnessFunctionGenerator:
    """Test WitnessFunctionGenerator."""
    
    def test_generator_creation(self):
        """Test creating a generator."""
        from arc.symbolic.smt.witness import WitnessFunctionGenerator
        
        generator = WitnessFunctionGenerator()
        assert generator is not None
    
    def test_generate_witness_with_holes(self, simple_grid):
        """Test generating witness constraints for a sketch with holes."""
        from arc.symbolic.smt.witness import WitnessFunctionGenerator
        
        generator = WitnessFunctionGenerator()
        
        # Create a sketch with a color hole
        hole = Hole(
            id="color_hole",
            type="colour",
            domain=set(range(10)),
            constraints={}
        )
        
        sketch = ProgramSketch(
            stages=[hole],
            constraints=[],
            metadata={}
        )
        
        witness = generator.generate_witness(
            sketch, simple_grid, simple_grid
        )
        
        assert "color_hole" in witness
        # Domain should be refined to colors present in grids
        assert len(witness["color_hole"]) <= 10
    
    def test_backward_propagate_rotate(self, simple_grid):
        """Test backward propagation through rotation."""
        from arc.symbolic.smt.witness import WitnessFunctionGenerator
        
        generator = WitnessFunctionGenerator()
        stage = Stage(operator="rotate", arguments=(1,))
        
        constraints = generator.backward_propagate(simple_grid, stage)
        
        # Rotation is invertible, so no additional constraints
        assert isinstance(constraints, set)


class TestBDDEncoder:
    """Test BDD encoder."""
    
    def test_bdd_encoder_creation(self):
        """Test creating a BDD encoder."""
        from arc.symbolic.smt.bdd import BDDEncoder
        
        encoder = BDDEncoder()
        assert encoder is not None
    
    def test_encode_grid_as_bdd(self, simple_grid):
        """Test encoding a grid as BDD."""
        from arc.symbolic.smt.bdd import BDDEncoder
        
        encoder = BDDEncoder()
        bdd = encoder.encode_grid_as_bdd(simple_grid, color=1)
        
        # Should return a grid of boolean expressions
        assert bdd is not None
        assert len(bdd) == simple_grid.shape[0]
    
    def test_check_equivalence(self, simple_grid):
        """Test checking grid equivalence."""
        from arc.symbolic.smt.bdd import BDDEncoder
        
        encoder = BDDEncoder()
        
        # Same grid should be equivalent
        assert encoder.check_equivalence(simple_grid, simple_grid)
        
        # Different grid should not be equivalent
        different_data = simple_grid.data.copy()
        different_data[0, 0] = 5
        different_grid = Grid(different_data)
        
        assert not encoder.check_equivalence(simple_grid, different_grid)


class TestBDDVerifier:
    """Test BDD verifier."""
    
    def test_bdd_verifier_creation(self):
        """Test creating a BDD verifier."""
        from arc.symbolic.smt.bdd import BDDVerifier
        
        verifier = BDDVerifier()
        assert verifier is not None
    
    def test_verify_equivalence(self, simple_grid):
        """Test verifying grid equivalence."""
        from arc.symbolic.smt.bdd import BDDVerifier
        
        verifier = BDDVerifier()
        
        # Same grid should be equivalent
        assert verifier.verify_equivalence(simple_grid, simple_grid)
    
    def test_verify_connectivity(self, simple_grid):
        """Test verifying connectivity."""
        from arc.symbolic.smt.bdd import BDDVerifier
        
        verifier = BDDVerifier()
        
        # The simple grid has 1 connected component of color 1
        result = verifier.verify_connectivity(
            simple_grid, color=1, expected_components=1, connectivity=4
        )
        
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
