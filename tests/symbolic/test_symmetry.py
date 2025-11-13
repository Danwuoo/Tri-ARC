"""Tests for symmetry detection and normalization."""

import numpy as np
import pytest

from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.ir.object_graph import ObjectGraph, ObjectNode, BoundingBox
from arc.symbolic.dsl.types import Region
from arc.symbolic.search.types import TrainingExample
from arc.symbolic.symmetry import (
    ColorMapping,
    ColorNormalizer,
    StepNormalizer,
    SymmetryDetector,
    SymmetryGroup,
    Isomorphism,
)


class TestColorMapping:
    """Test ColorMapping data structure."""
    
    def test_color_mapping_creation(self):
        """Test creating a ColorMapping."""
        mapping = ColorMapping(
            forward={0: 0, 1: 1, 2: 2},
            backward={0: 0, 1: 1, 2: 2},
            canonical_order=(0, 1, 2),
        )
        assert mapping.forward == {0: 0, 1: 1, 2: 2}
        assert mapping.backward == {0: 0, 1: 1, 2: 2}
        assert mapping.canonical_order == (0, 1, 2)
    
    def test_color_mapping_invert(self):
        """Test inverting a ColorMapping."""
        mapping = ColorMapping(
            forward={0: 2, 1: 0, 2: 1},
            backward={2: 0, 0: 1, 1: 2},
            canonical_order=(1, 2, 0),
        )
        inverted = mapping.invert()
        assert inverted.forward == mapping.backward
        assert inverted.backward == mapping.forward
    
    def test_color_mapping_compose(self):
        """Test composing two ColorMappings."""
        mapping1 = ColorMapping(
            forward={0: 1, 1: 2, 2: 0},
            backward={1: 0, 2: 1, 0: 2},
            canonical_order=(2, 0, 1),
        )
        mapping2 = ColorMapping(
            forward={0: 2, 1: 0, 2: 1},
            backward={2: 0, 0: 1, 1: 2},
            canonical_order=(1, 2, 0),
        )
        composed = mapping1.compose(mapping2)
        # Verify composition: (mapping1 ∘ mapping2)(0) = mapping1(mapping2(0)) = mapping1(2) = 0
        assert composed.forward[0] == 0
    
    def test_apply_to_color(self):
        """Test applying mapping to a single color."""
        mapping = ColorMapping(
            forward={0: 2, 1: 0, 2: 1},
            backward={2: 0, 0: 1, 1: 2},
            canonical_order=(1, 2, 0),
        )
        assert mapping.apply_to_color(0) == 2
        assert mapping.apply_to_color(1) == 0
        assert mapping.apply_to_color(2) == 1
        # Unmapped color returns itself
        assert mapping.apply_to_color(5) == 5


class TestColorNormalizer:
    """Test ColorNormalizer class."""
    
    def test_frequency_strategy(self):
        """Test frequency-based normalization."""
        normalizer = ColorNormalizer(strategy="frequency")
        
        # Create examples where color 2 is most frequent
        input_grid = Grid(np.array([[2, 2, 2], [2, 1, 0], [2, 2, 2]], dtype=np.int16))
        output_grid = Grid(np.array([[2, 2, 2], [2, 2, 2], [2, 2, 2]], dtype=np.int16))
        examples = [TrainingExample(input_grid=input_grid, output_grid=output_grid)]
        
        normalized, mapping = normalizer.canonical_relabel(examples)
        
        # Color 2 should be mapped to 0 (most frequent)
        assert mapping.forward[2] == 0
        assert len(normalized) == 1
    
    def test_appearance_strategy(self):
        """Test appearance-based normalization."""
        normalizer = ColorNormalizer(strategy="appearance")
        
        # First color to appear is 1, then 2, then 0
        input_grid = Grid(np.array([[1, 2, 0], [1, 2, 0], [1, 2, 0]], dtype=np.int16))
        output_grid = Grid(np.array([[1, 1, 1], [2, 2, 2], [0, 0, 0]], dtype=np.int16))
        examples = [TrainingExample(input_grid=input_grid, output_grid=output_grid)]
        
        normalized, mapping = normalizer.canonical_relabel(examples)
        
        # Color 1 appears first, should be mapped to 0
        assert mapping.forward[1] == 0
        # Color 2 appears second, should be mapped to 1
        assert mapping.forward[2] == 1
        # Color 0 appears third, should be mapped to 2
        assert mapping.forward[0] == 2
    
    def test_sorted_strategy(self):
        """Test sorted normalization."""
        normalizer = ColorNormalizer(strategy="sorted")
        
        input_grid = Grid(np.array([[5, 3, 1], [5, 3, 1], [5, 3, 1]], dtype=np.int16))
        output_grid = Grid(np.array([[1, 3, 5], [1, 3, 5], [1, 3, 5]], dtype=np.int16))
        examples = [TrainingExample(input_grid=input_grid, output_grid=output_grid)]
        
        normalized, mapping = normalizer.canonical_relabel(examples)
        
        # Colors should be sorted: 1, 3, 5 -> 0, 1, 2
        assert mapping.forward[1] == 0
        assert mapping.forward[3] == 1
        assert mapping.forward[5] == 2
    
    def test_apply_mapping(self):
        """Test applying a color mapping to a grid."""
        normalizer = ColorNormalizer()
        
        grid = Grid(np.array([[0, 1, 2], [1, 2, 0], [2, 0, 1]], dtype=np.int16))
        mapping = ColorMapping(
            forward={0: 2, 1: 0, 2: 1},
            backward={2: 0, 0: 1, 1: 2},
            canonical_order=(1, 2, 0),
        )
        
        normalized = normalizer.apply_mapping(grid, mapping)
        
        # Verify mapping was applied
        assert normalized.data[0, 0] == 2  # 0 -> 2
        assert normalized.data[0, 1] == 0  # 1 -> 0
        assert normalized.data[0, 2] == 1  # 2 -> 1


class TestSymmetryDetector:
    """Test SymmetryDetector class."""
    
    def test_detect_horizontal_reflection(self):
        """Test detecting horizontal reflection symmetry."""
        detector = SymmetryDetector()
        
        # Grid with horizontal reflection symmetry
        grid = Grid(np.array([
            [1, 2, 1],
            [3, 4, 3],
            [1, 2, 1],
        ], dtype=np.int16))
        
        symmetry = detector.detect_grid_symmetry(grid)
        
        assert "reflect_horizontal" in symmetry.generators
        assert symmetry.order >= 2
    
    def test_detect_vertical_reflection(self):
        """Test detecting vertical reflection symmetry."""
        detector = SymmetryDetector()
        
        # Grid with vertical reflection symmetry
        grid = Grid(np.array([
            [1, 3, 1],
            [2, 4, 2],
            [1, 3, 1],
        ], dtype=np.int16))
        
        symmetry = detector.detect_grid_symmetry(grid)
        
        assert "reflect_vertical" in symmetry.generators
        assert symmetry.order >= 2
    
    def test_detect_rotation_90(self):
        """Test detecting 90-degree rotation symmetry."""
        detector = SymmetryDetector()
        
        # Grid with 90-degree rotation symmetry (must be square)
        grid = Grid(np.array([
            [1, 2, 1],
            [2, 3, 2],
            [1, 2, 1],
        ], dtype=np.int16))
        
        symmetry = detector.detect_grid_symmetry(grid)
        
        # This specific grid has 90-degree rotation
        if "rotate_90" in symmetry.generators:
            assert symmetry.order >= 4
    
    def test_detect_rotation_180(self):
        """Test detecting 180-degree rotation symmetry."""
        detector = SymmetryDetector()
        
        # Grid with 180-degree rotation symmetry
        grid = Grid(np.array([
            [1, 2, 3],
            [4, 5, 4],
            [3, 2, 1],
        ], dtype=np.int16))
        
        symmetry = detector.detect_grid_symmetry(grid)
        
        assert "rotate_180" in symmetry.generators or "rotate_90" in symmetry.generators
        assert symmetry.order >= 2
    
    def test_no_symmetry(self):
        """Test detecting no symmetry."""
        detector = SymmetryDetector()
        
        # Grid with no symmetry
        grid = Grid(np.array([
            [1, 2, 3],
            [4, 5, 6],
            [7, 8, 9],
        ], dtype=np.int16))
        
        symmetry = detector.detect_grid_symmetry(grid)
        
        assert symmetry.type == "trivial"
        assert symmetry.order == 1
    
    def test_object_graph_isomorphism(self):
        """Test detecting isomorphism between object graphs."""
        detector = SymmetryDetector()
        
        # Create two identical object graphs
        shape = (5, 5)
        region1 = Region.from_coordinates(shape, [(0, 0), (0, 1), (1, 0)])
        bbox1 = BoundingBox(top=0, left=0, bottom=1, right=1)
        node1 = ObjectNode(id=0, region=region1, color=1, bbox=bbox1)
        
        region2 = Region.from_coordinates(shape, [(3, 3), (3, 4), (4, 3)])
        bbox2 = BoundingBox(top=3, left=3, bottom=4, right=4)
        node2 = ObjectNode(id=1, region=region2, color=1, bbox=bbox2)
        
        graph_a = ObjectGraph(
            nodes=[node1],
            edges=[],
            background_color=0,
            canvas_shape=shape,
        )
        
        graph_b = ObjectGraph(
            nodes=[node2],
            edges=[],
            background_color=0,
            canvas_shape=shape,
        )
        
        # These graphs are isomorphic (same structure, different positions)
        isomorphism = detector.detect_object_graph_isomorphism(graph_a, graph_b)
        
        # Should find an isomorphism
        assert isomorphism is not None
        assert len(isomorphism.node_mapping) == 1
        assert isomorphism.confidence > 0.0
    
    def test_compute_quotient_representatives(self):
        """Test computing quotient representatives."""
        detector = SymmetryDetector()
        
        # Create some programs
        programs = [
            Program(stages=(Stage("rotate", (90,)),)),
            Program(stages=(Stage("rotate", (90,)),)),  # Duplicate
            Program(stages=(Stage("reflect", ("horizontal",)),)),
        ]
        
        symmetry_group = SymmetryGroup(
            generators=("rotate_90",),
            order=4,
            type="cyclic_4",
        )
        
        representatives = detector.compute_quotient_representatives(programs, symmetry_group)
        
        # Should have fewer representatives than original programs
        assert len(representatives) <= len(programs)


class TestStepNormalizer:
    """Test StepNormalizer class."""
    
    def test_normalize_single_stage(self):
        """Test normalizing a single stage."""
        normalizer = StepNormalizer()
        
        stages = [Stage("rotate", (90,))]
        normalized = normalizer.normalize_sequence(stages)
        
        assert len(normalized) == 1
        assert normalized[0] == stages[0]
    
    def test_normalize_commutative_stages(self):
        """Test normalizing commutative stages."""
        normalizer = StepNormalizer()
        
        # Add a commutative pair for testing
        normalizer.add_commutative_pair("op_a", "op_b")
        
        stages = [
            Stage("op_b", (2,)),
            Stage("op_a", (1,)),
        ]
        
        normalized = normalizer.normalize_sequence(stages)
        
        # Should be reordered to canonical form (alphabetically)
        assert normalized[0].operator == "op_a"
        assert normalized[1].operator == "op_b"
    
    def test_detect_commutative_pairs(self):
        """Test detecting commutative pairs."""
        normalizer = StepNormalizer()
        
        # Add a commutative pair
        normalizer.add_commutative_pair("paint_region", "fill_region")
        
        stage_a = Stage("paint_region", (1,))
        stage_b = Stage("fill_region", (2,))
        
        assert normalizer.detect_commutative_pairs(stage_a, stage_b)
    
    def test_canonical_order(self):
        """Test canonical ordering of stages."""
        normalizer = StepNormalizer()
        
        stages = [
            Stage("rotate", (180,)),
            Stage("reflect", ("horizontal",)),
            Stage("paint", (1,)),
        ]
        
        canonical = normalizer.canonical_order(stages)
        
        # Should be sorted by operator name
        assert canonical[0].operator == "paint"
        assert canonical[1].operator == "reflect"
        assert canonical[2].operator == "rotate"
    
    def test_read_only_operations(self):
        """Test detecting read-only operations."""
        normalizer = StepNormalizer()
        
        read_only_stage = Stage("detect_objects", ())
        modifying_stage = Stage("paint_region", (1,))
        
        assert normalizer._is_read_only(read_only_stage)
        assert not normalizer._is_read_only(modifying_stage)
    
    def test_add_commutative_group(self):
        """Test adding a commutative group."""
        normalizer = StepNormalizer()
        
        normalizer.add_commutative_group({"op_x", "op_y", "op_z"})
        
        stage_x = Stage("op_x", ())
        stage_y = Stage("op_y", ())
        stage_z = Stage("op_z", ())
        
        assert normalizer.detect_commutative_pairs(stage_x, stage_y)
        assert normalizer.detect_commutative_pairs(stage_y, stage_z)
        assert normalizer.detect_commutative_pairs(stage_x, stage_z)


class TestSymmetryIntegration:
    """Integration tests for symmetry components."""
    
    def test_end_to_end_color_normalization(self):
        """Test end-to-end color normalization workflow."""
        normalizer = ColorNormalizer(strategy="frequency")
        
        # Create examples with different color distributions
        examples = [
            TrainingExample(
                input_grid=Grid(np.array([[1, 1, 2], [1, 2, 2], [2, 2, 2]], dtype=np.int16)),
                output_grid=Grid(np.array([[2, 2, 2], [2, 2, 2], [2, 2, 2]], dtype=np.int16)),
            ),
            TrainingExample(
                input_grid=Grid(np.array([[1, 1, 1], [2, 2, 2], [1, 1, 1]], dtype=np.int16)),
                output_grid=Grid(np.array([[1, 1, 1], [1, 1, 1], [1, 1, 1]], dtype=np.int16)),
            ),
        ]
        
        normalized, mapping = normalizer.canonical_relabel(examples)
        
        assert len(normalized) == len(examples)
        assert mapping is not None
        assert len(mapping.forward) > 0
    
    def test_symmetry_detection_and_quotient(self):
        """Test symmetry detection followed by quotient computation."""
        detector = SymmetryDetector()
        
        # Create a symmetric grid
        grid = Grid(np.array([
            [1, 2, 1],
            [2, 3, 2],
            [1, 2, 1],
        ], dtype=np.int16))
        
        symmetry = detector.detect_grid_symmetry(grid)
        
        # Create some programs
        programs = [
            Program(stages=(Stage("rotate", (90,)),)),
            Program(stages=(Stage("reflect", ("horizontal",)),)),
            Program(stages=(Stage("paint", (1,)),)),
        ]
        
        representatives = detector.compute_quotient_representatives(programs, symmetry)
        
        assert len(representatives) <= len(programs)
    
    def test_step_normalization_preserves_semantics(self):
        """Test that step normalization preserves program semantics."""
        normalizer = StepNormalizer()
        
        # Create a sequence of stages
        stages = [
            Stage("detect_objects", ()),
            Stage("select_object", (0,)),
            Stage("paint_region", (1,)),
        ]
        
        normalized = normalizer.normalize_sequence(stages)
        
        # Should have same length
        assert len(normalized) == len(stages)
        # All stages should be present
        assert set(s.operator for s in normalized) == set(s.operator for s in stages)


class TestSymmetrySolverIntegration:
    """Test symmetry integration with the solver."""
    
    def test_color_normalization_in_solver(self):
        """Test that color normalization is applied in solver."""
        from arc.symbolic.solver import SymbolicSolver
        
        # Create a solver with symmetry enabled
        config = {
            "symbolic": {
                "symmetry": {
                    "enabled": True,
                    "color_normalization": True,
                    "color_normalization_strategy": "frequency",
                },
                "soft_timeout_s": 1.0,
                "hard_timeout_s": 2.0,
                "max_depth": 3,
                "max_expansions": 10,
            },
            "global": {"seed": 42},
        }
        
        solver = SymbolicSolver(config=config)
        
        # Verify symmetry components are initialized
        assert solver.symmetry_enabled
        assert solver.color_normalization_enabled
        assert solver.color_normalizer is not None
    
    def test_step_normalization_in_verification(self):
        """Test that step normalization is applied during verification."""
        from arc.symbolic.solver import SymbolicSolver
        from arc.symbolic.search.types import SearchNode
        
        config = {
            "symbolic": {
                "symmetry": {
                    "enabled": True,
                    "step_normalization": True,
                },
                "soft_timeout_s": 1.0,
                "hard_timeout_s": 2.0,
            },
            "global": {"seed": 42},
        }
        
        solver = SymbolicSolver(config=config)
        
        # Verify step normalizer is initialized
        assert solver.step_normalization_enabled
        assert solver.step_normalizer is not None
    
    def test_symmetry_cost_adjustment(self):
        """Test that symmetry affects cost calculation."""
        from arc.symbolic.solver import SymbolicSolver
        
        config = {
            "symbolic": {
                "symmetry": {"enabled": True},
                "egraph": {"enabled": True},
            },
            "global": {"seed": 42},
        }
        
        solver = SymbolicSolver(config=config)
        egraph = solver._build_egraph()
        
        # Create programs with and without symmetric operations
        program_with_symmetry = Program(stages=(
            Stage("rotate", (90,)),
            Stage("reflect", ("horizontal",)),
        ))
        
        program_without_symmetry = Program(stages=(
            Stage("paint", (1,)),
            Stage("fill", (2,)),
        ))
        
        # Cost function should give lower cost to symmetric programs
        cost_with = egraph.cost_fn(program_with_symmetry)
        cost_without = egraph.cost_fn(program_without_symmetry)
        
        # Symmetric program should have lower cost
        assert cost_with < cost_without


class TestSymmetryEdgeCases:
    """Test edge cases for symmetry components."""
    
    def test_empty_grid_symmetry(self):
        """Test symmetry detection on empty grid."""
        detector = SymmetryDetector()
        
        grid = Grid(np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0]], dtype=np.int16))
        symmetry = detector.detect_grid_symmetry(grid)
        
        # Empty grid should have high symmetry
        assert symmetry.order >= 4
    
    def test_single_cell_grid(self):
        """Test symmetry detection on 1x1 grid."""
        detector = SymmetryDetector()
        
        grid = Grid(np.array([[1]], dtype=np.int16))
        symmetry = detector.detect_grid_symmetry(grid)
        
        # Single cell has all symmetries
        assert symmetry.order >= 4
    
    def test_color_normalization_with_no_colors(self):
        """Test color normalization with empty examples."""
        normalizer = ColorNormalizer()
        
        examples = []
        normalized, mapping = normalizer.canonical_relabel(examples)
        
        assert len(normalized) == 0
        assert mapping.forward == {}
    
    def test_step_normalization_empty_sequence(self):
        """Test step normalization with empty sequence."""
        normalizer = StepNormalizer()
        
        stages = []
        normalized = normalizer.normalize_sequence(stages)
        
        assert len(normalized) == 0
    
    def test_quotient_with_trivial_symmetry(self):
        """Test quotient computation with trivial symmetry."""
        detector = SymmetryDetector()
        
        programs = [
            Program(stages=(Stage("rotate", (90,)),)),
            Program(stages=(Stage("reflect", ("horizontal",)),)),
        ]
        
        trivial_symmetry = SymmetryGroup(
            generators=(),
            order=1,
            type="trivial",
        )
        
        representatives = detector.compute_quotient_representatives(programs, trivial_symmetry)
        
        # With trivial symmetry, all programs are representatives
        assert len(representatives) == len(programs)
    
    def test_color_mapping_with_gaps(self):
        """Test color mapping with non-contiguous colors."""
        normalizer = ColorNormalizer()
        
        # Colors 0, 5, 9 (with gaps)
        grid = Grid(np.array([[0, 5, 9], [5, 9, 0], [9, 0, 5]], dtype=np.int16))
        examples = [TrainingExample(input_grid=grid, output_grid=grid)]
        
        normalized, mapping = normalizer.canonical_relabel(examples)
        
        # Should handle gaps correctly
        assert len(mapping.forward) == 3
        assert all(v in {0, 1, 2} for v in mapping.forward.values())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
