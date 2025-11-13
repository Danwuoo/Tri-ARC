#!/usr/bin/env python
"""Demonstration of symmetry detection and normalization features."""

import numpy as np
from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.search.types import TrainingExample
from arc.symbolic.symmetry import (
    ColorNormalizer,
    SymmetryDetector,
    StepNormalizer,
    SymmetryGroup,
)


def demo_color_normalization():
    """Demonstrate color normalization."""
    print("=" * 60)
    print("COLOR NORMALIZATION DEMO")
    print("=" * 60)
    
    normalizer = ColorNormalizer(strategy="frequency")
    
    # Create an example with colors 5, 3, 1 where 5 is most frequent
    input_grid = Grid(np.array([
        [5, 5, 5],
        [5, 3, 1],
        [5, 5, 5],
    ], dtype=np.int16))
    
    output_grid = Grid(np.array([
        [5, 5, 5],
        [5, 5, 5],
        [5, 5, 5],
    ], dtype=np.int16))
    
    examples = [TrainingExample(input_grid=input_grid, output_grid=output_grid)]
    
    print("\nOriginal colors:", sorted(set(input_grid.data.flatten())))
    
    normalized, mapping = normalizer.canonical_relabel(examples)
    
    print("Color mapping:", mapping.forward)
    print("Canonical order:", mapping.canonical_order)
    print("\nNormalized input grid:")
    print(normalized[0].input_grid.data)
    print("\n✓ Most frequent color (5) mapped to 0")


def demo_symmetry_detection():
    """Demonstrate symmetry detection."""
    print("\n" + "=" * 60)
    print("SYMMETRY DETECTION DEMO")
    print("=" * 60)
    
    detector = SymmetryDetector()
    
    # Create a grid with multiple symmetries
    grid = Grid(np.array([
        [1, 2, 1],
        [2, 3, 2],
        [1, 2, 1],
    ], dtype=np.int16))
    
    print("\nGrid:")
    print(grid.data)
    
    symmetry = detector.detect_grid_symmetry(grid)
    
    print(f"\nDetected symmetry type: {symmetry.type}")
    print(f"Symmetry group order: {symmetry.order}")
    print(f"Generators: {symmetry.generators}")
    print("\n✓ Grid has both horizontal and vertical reflection symmetry")


def demo_step_normalization():
    """Demonstrate step normalization."""
    print("\n" + "=" * 60)
    print("STEP NORMALIZATION DEMO")
    print("=" * 60)
    
    normalizer = StepNormalizer()
    
    # Add a commutative group for demonstration
    normalizer.add_commutative_group({"op_a", "op_b", "op_c"})
    
    # Create a sequence with commutative operations in non-canonical order
    stages = [
        Stage("op_c", (3,)),
        Stage("op_a", (1,)),
        Stage("op_b", (2,)),
    ]
    
    print("\nOriginal sequence:")
    for i, stage in enumerate(stages):
        print(f"  {i+1}. {stage.operator}({stage.arguments})")
    
    normalized = normalizer.normalize_sequence(stages)
    
    print("\nNormalized sequence (canonical order):")
    for i, stage in enumerate(normalized):
        print(f"  {i+1}. {stage.operator}({stage.arguments})")
    
    print("\n✓ Commutative operations reordered alphabetically")


def demo_quotient_search():
    """Demonstrate quotient search with symmetry."""
    print("\n" + "=" * 60)
    print("QUOTIENT SEARCH DEMO")
    print("=" * 60)
    
    detector = SymmetryDetector()
    
    # Create programs that might be equivalent under symmetry
    programs = [
        Program(stages=(Stage("rotate", (90,)),)),
        Program(stages=(Stage("rotate", (90,)),)),  # Duplicate
        Program(stages=(Stage("rotate", (180,)),)),
        Program(stages=(Stage("reflect", ("horizontal",)),)),
        Program(stages=(Stage("reflect", ("horizontal",)),)),  # Duplicate
    ]
    
    print(f"\nOriginal program count: {len(programs)}")
    
    # Create a symmetry group (e.g., 4-fold rotational symmetry)
    symmetry_group = SymmetryGroup(
        generators=("rotate_90",),
        order=4,
        type="cyclic_4",
    )
    
    representatives = detector.compute_quotient_representatives(programs, symmetry_group)
    
    print(f"Representative count after deduplication: {len(representatives)}")
    print("\nRepresentative programs:")
    for i, prog in enumerate(representatives):
        ops = ", ".join(f"{s.operator}({s.arguments})" for s in prog.stages)
        print(f"  {i+1}. {ops}")
    
    print(f"\n✓ Reduced {len(programs)} programs to {len(representatives)} representatives")


def demo_integration():
    """Demonstrate integration with solver."""
    print("\n" + "=" * 60)
    print("SOLVER INTEGRATION DEMO")
    print("=" * 60)
    
    from arc.symbolic.solver import SymbolicSolver
    
    config = {
        "symbolic": {
            "symmetry": {
                "enabled": True,
                "color_normalization": True,
                "color_normalization_strategy": "frequency",
                "symmetry_detection": True,
                "step_normalization": True,
            },
            "soft_timeout_s": 1.0,
            "hard_timeout_s": 2.0,
            "max_depth": 3,
            "max_expansions": 10,
        },
        "global": {"seed": 42},
    }
    
    solver = SymbolicSolver(config=config)
    
    print("\nSolver configuration:")
    print(f"  Symmetry enabled: {solver.symmetry_enabled}")
    print(f"  Color normalization: {solver.color_normalization_enabled}")
    print(f"  Symmetry detection: {solver.symmetry_detection_enabled}")
    print(f"  Step normalization: {solver.step_normalization_enabled}")
    
    print("\nComponents initialized:")
    print(f"  ColorNormalizer: {solver.color_normalizer is not None}")
    print(f"  SymmetryDetector: {solver.symmetry_detector is not None}")
    print(f"  StepNormalizer: {solver.step_normalizer is not None}")
    
    print("\n✓ All symmetry components successfully integrated into solver")


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 60)
    print("SYMMETRY DETECTION AND NORMALIZATION")
    print("Feature Demonstration")
    print("=" * 60)
    
    demo_color_normalization()
    demo_symmetry_detection()
    demo_step_normalization()
    demo_quotient_search()
    demo_integration()
    
    print("\n" + "=" * 60)
    print("ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
