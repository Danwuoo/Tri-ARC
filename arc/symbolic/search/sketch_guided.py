"""Sketch-guided synthesis for program synthesis.

This module implements sketch-guided synthesis, which uses program templates
(sketches) with holes to guide the search process. It includes:
- Sketch extraction from successful programs
- Version Space Algebra (VSA) for hole domain reduction
- Sketch-guided program synthesis
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage
from arc.symbolic.ir.sketch import Hole, ProgramSketch
from arc.symbolic.search.budget import SearchBudget
from arc.symbolic.search.types import TrainingExample

logger = logging.getLogger(__name__)


@dataclass
class SketchLibraryEntry:
    """Entry in the sketch library.
    
    Attributes:
        sketch: The program sketch template
        frequency: Number of times this sketch pattern appeared
        success_rate: Success rate of programs using this sketch
        avg_cost: Average cost of programs using this sketch
        source_programs: List of program IDs that contributed to this sketch
    """
    
    sketch: ProgramSketch
    frequency: int = 1
    success_rate: float = 1.0
    avg_cost: float = 0.0
    source_programs: List[str] = field(default_factory=list)
    
    def update_stats(self, cost: float, success: bool) -> None:
        """Update statistics with a new program instance.
        
        Args:
            cost: Cost of the new program
            success: Whether the program was successful
        """
        # Update frequency
        self.frequency += 1
        
        # Update success rate (exponential moving average)
        alpha = 0.3
        self.success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * self.success_rate
        
        # Update average cost (exponential moving average)
        self.avg_cost = alpha * cost + (1 - alpha) * self.avg_cost


class SketchGuidedSynthesizer:
    """Sketch-guided synthesizer for program synthesis.
    
    This class implements sketch-guided synthesis, which uses program templates
    to guide the search process. It maintains a library of sketches extracted
    from successful programs and uses Version Space Algebra (VSA) to refine
    hole domains based on examples.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the sketch-guided synthesizer.
        
        Args:
            config: Configuration dictionary with optional parameters:
                - min_sketch_frequency: Minimum frequency for sketch extraction
                - max_sketch_library_size: Maximum number of sketches to keep
                - vsa_enabled: Whether to use VSA for domain reduction
                - abstraction_level: Level of abstraction for sketch extraction
        """
        self.config = config or {}
        self.min_sketch_frequency = self.config.get("min_sketch_frequency", 2)
        self.max_sketch_library_size = self.config.get("max_sketch_library_size", 100)
        self.vsa_enabled = self.config.get("vsa_enabled", True)
        self.abstraction_level = self.config.get("abstraction_level", "operator")
        
        # Sketch library: maps sketch signature to library entry
        self.sketch_library: Dict[str, SketchLibraryEntry] = {}
        
        logger.info(
            f"Initialized SketchGuidedSynthesizer with "
            f"min_frequency={self.min_sketch_frequency}, "
            f"max_library_size={self.max_sketch_library_size}, "
            f"vsa_enabled={self.vsa_enabled}"
        )
    
    def synthesize_from_sketch(
        self,
        sketch: ProgramSketch,
        examples: List[TrainingExample],
        budget: SearchBudget,
        interpreter: Any = None,
    ) -> List[Program]:
        """Synthesize programs from a sketch by filling holes.
        
        This method takes a sketch with holes and attempts to fill them
        to create complete programs that satisfy the given examples.
        
        Args:
            sketch: Program sketch with holes to fill
            examples: Training examples to satisfy
            budget: Search budget for synthesis
            interpreter: DSL interpreter for program execution
            
        Returns:
            List of synthesized programs that satisfy the examples
        """
        logger.info(f"Synthesizing from sketch with {len(sketch.get_holes())} holes")
        
        # Apply VSA to refine hole domains if enabled
        if self.vsa_enabled and interpreter:
            sketch = self.apply_vsa(sketch, examples, interpreter)
        
        # Get all holes in the sketch
        holes = sketch.get_holes()
        
        if not holes:
            # Sketch is already complete
            logger.info("Sketch is already complete, no holes to fill")
            return [self._sketch_to_program(sketch)]
        
        # Generate candidate programs by filling holes
        candidates = self._enumerate_hole_assignments(sketch, holes, budget)
        
        # Filter candidates that satisfy examples
        valid_programs = []
        for program in candidates:
            if interpreter and self._check_program(program, examples, interpreter):
                valid_programs.append(program)
                if len(valid_programs) >= budget.max_candidates:
                    break
        
        logger.info(f"Synthesized {len(valid_programs)} valid programs from sketch")
        return valid_programs
    
    def extract_sketch_library(
        self,
        successful_programs: List[Tuple[Program, float, bool]],
    ) -> List[ProgramSketch]:
        """Extract sketch library from successful programs.
        
        This method analyzes successful programs to extract common patterns
        and create sketches that can guide future synthesis.
        
        Args:
            successful_programs: List of (program, cost, success) tuples
            
        Returns:
            List of extracted sketches
        """
        logger.info(f"Extracting sketches from {len(successful_programs)} programs")
        
        # Group programs by structure
        structure_groups = defaultdict(list)
        
        for program, cost, success in successful_programs:
            signature = self._compute_program_signature(program)
            structure_groups[signature].append((program, cost, success))
        
        # Extract sketches from frequent patterns
        extracted_sketches = []
        
        for signature, programs in structure_groups.items():
            if len(programs) >= self.min_sketch_frequency:
                # Create sketch from this group
                sketch = self._create_sketch_from_group(programs)
                
                # Add or update in library
                if signature in self.sketch_library:
                    entry = self.sketch_library[signature]
                    for _, cost, success in programs:
                        entry.update_stats(cost, success)
                else:
                    # Calculate initial stats
                    avg_cost = sum(cost for _, cost, _ in programs) / len(programs)
                    success_rate = sum(1 for _, _, success in programs if success) / len(programs)
                    
                    entry = SketchLibraryEntry(
                        sketch=sketch,
                        frequency=len(programs),
                        success_rate=success_rate,
                        avg_cost=avg_cost,
                        source_programs=[f"prog_{i}" for i in range(len(programs))],
                    )
                    self.sketch_library[signature] = entry
                
                extracted_sketches.append(sketch)
        
        # Prune library if it exceeds max size
        self._prune_library()
        
        logger.info(
            f"Extracted {len(extracted_sketches)} sketches, "
            f"library size: {len(self.sketch_library)}"
        )
        
        return extracted_sketches
    
    def apply_vsa(
        self,
        sketch: ProgramSketch,
        examples: List[TrainingExample],
        interpreter: Any,
    ) -> ProgramSketch:
        """Apply Version Space Algebra to refine hole domains.
        
        VSA uses the examples to constrain the possible values for each hole
        by analyzing which values would be consistent with the examples.
        
        Args:
            sketch: Program sketch with holes
            examples: Training examples
            interpreter: DSL interpreter for program execution
            
        Returns:
            Refined sketch with narrower hole domains
        """
        logger.debug(f"Applying VSA to sketch with {len(sketch.get_holes())} holes")
        
        holes = sketch.get_holes()
        
        for hole in holes:
            # Skip if hole already has a small domain
            if hole.domain and len(hole.domain) <= 3:
                continue
            
            # Analyze examples to refine domain
            refined_domain = self._refine_hole_domain(
                sketch, hole, examples, interpreter
            )
            
            if refined_domain:
                original_size = len(hole.domain) if hole.domain else float('inf')
                hole.refine_domain(refined_domain)
                new_size = len(hole.domain)
                
                logger.debug(
                    f"Refined hole {hole.id} domain: "
                    f"{original_size} -> {new_size} values"
                )
        
        return sketch
    
    def get_best_sketches(self, top_k: int = 10) -> List[ProgramSketch]:
        """Get the best sketches from the library.
        
        Args:
            top_k: Number of top sketches to return
            
        Returns:
            List of top-k sketches sorted by utility score
        """
        # Score sketches by utility (success_rate * frequency / avg_cost)
        scored_sketches = []
        
        for entry in self.sketch_library.values():
            utility = entry.success_rate * entry.frequency / max(entry.avg_cost, 1.0)
            scored_sketches.append((utility, entry.sketch))
        
        # Sort by utility (descending)
        scored_sketches.sort(key=lambda x: x[0], reverse=True)
        
        return [sketch for _, sketch in scored_sketches[:top_k]]
    
    def _compute_program_signature(self, program: Program) -> str:
        """Compute a signature for a program based on its structure.
        
        Args:
            program: Program to compute signature for
            
        Returns:
            String signature representing the program structure
        """
        if self.abstraction_level == "operator":
            # Signature based on operator sequence
            operators = [stage.operator for stage in program.stages]
            return "|".join(operators)
        
        elif self.abstraction_level == "operator_arity":
            # Signature based on operator and argument count
            parts = []
            for stage in program.stages:
                parts.append(f"{stage.operator}:{len(stage.arguments)}")
            return "|".join(parts)
        
        else:
            # Full signature (no abstraction)
            return str(program)
    
    def _create_sketch_from_group(
        self,
        programs: List[Tuple[Program, float, bool]],
    ) -> ProgramSketch:
        """Create a sketch from a group of similar programs.
        
        Args:
            programs: List of (program, cost, success) tuples
            
        Returns:
            Program sketch with holes for varying parts
        """
        if not programs:
            raise ValueError("Cannot create sketch from empty program group")
        
        # Use the first program as template
        template_program = programs[0][0]
        
        # Analyze which parts vary across programs
        stages_list = [prog.stages for prog, _, _ in programs]
        sketch_stages = []
        
        for stage_idx in range(len(template_program.stages)):
            # Get all stages at this position
            stages_at_pos = [stages[stage_idx] for stages in stages_list if stage_idx < len(stages)]
            
            # Check if operator varies
            operators = [stage.operator for stage in stages_at_pos]
            operator_counts = Counter(operators)
            
            if len(operator_counts) == 1:
                # Operator is constant, use the stage directly
                sketch_stages.append(template_program.stages[stage_idx])
            else:
                # Operator varies, create a hole
                hole = Hole(
                    id=f"hole_op_{stage_idx}",
                    type="operator",
                    domain=set(operators),
                )
                sketch_stages.append(hole)
        
        return ProgramSketch(
            stages=sketch_stages,
            metadata={
                "source": "group_extraction",
                "group_size": len(programs),
            }
        )
    
    def _enumerate_hole_assignments(
        self,
        sketch: ProgramSketch,
        holes: List[Hole],
        budget: SearchBudget,
    ) -> List[Program]:
        """Enumerate possible hole assignments to generate programs.
        
        Args:
            sketch: Program sketch with holes
            holes: List of holes to fill
            budget: Search budget
            
        Returns:
            List of programs with holes filled
        """
        # Simple enumeration: try all combinations up to budget
        programs = []
        
        # Generate assignments recursively
        def generate_assignments(
            hole_idx: int,
            current_assignment: Dict[str, Any],
        ) -> None:
            if len(programs) >= budget.max_candidates:
                return
            
            if hole_idx >= len(holes):
                # All holes assigned, create program
                program = self._instantiate_sketch(sketch, current_assignment)
                if program:
                    programs.append(program)
                return
            
            hole = holes[hole_idx]
            domain = hole.domain if hole.domain else self._get_default_domain(hole.type)
            
            for value in domain:
                if hole.is_satisfied(value):
                    current_assignment[hole.id] = value
                    generate_assignments(hole_idx + 1, current_assignment)
                    del current_assignment[hole.id]
        
        generate_assignments(0, {})
        return programs
    
    def _instantiate_sketch(
        self,
        sketch: ProgramSketch,
        assignment: Dict[str, Any],
    ) -> Optional[Program]:
        """Instantiate a sketch with a hole assignment.
        
        Args:
            sketch: Program sketch
            assignment: Mapping from hole IDs to values
            
        Returns:
            Complete program, or None if instantiation fails
        """
        stages = []
        
        for stage in sketch.stages:
            if isinstance(stage, Hole):
                if stage.id not in assignment:
                    return None
                # Create a stage from the hole assignment
                # This is simplified - in practice, you'd need to handle
                # different hole types appropriately
                value = assignment[stage.id]
                if stage.type == "operator":
                    # Create a stage with the operator
                    stages.append(Stage(operator=value, arguments=()))
                else:
                    # For other types, we'd need more context
                    return None
            else:
                stages.append(stage)
        
        return Program(stages=tuple(stages))
    
    def _sketch_to_program(self, sketch: ProgramSketch) -> Program:
        """Convert a complete sketch (no holes) to a program.
        
        Args:
            sketch: Complete program sketch
            
        Returns:
            Program
        """
        stages = [stage for stage in sketch.stages if isinstance(stage, Stage)]
        return Program(stages=tuple(stages))
    
    def _refine_hole_domain(
        self,
        sketch: ProgramSketch,
        hole: Hole,
        examples: List[TrainingExample],
        interpreter: Any,
    ) -> Set[Any]:
        """Refine a hole's domain based on examples.
        
        Args:
            sketch: Program sketch
            hole: Hole to refine
            examples: Training examples
            interpreter: DSL interpreter
            
        Returns:
            Refined domain for the hole
        """
        # Get initial domain
        domain = hole.domain if hole.domain else self._get_default_domain(hole.type)
        
        # Try each value and see which ones could work
        valid_values = set()
        
        for value in domain:
            # Create a partial assignment with this value
            assignment = {hole.id: value}
            
            # Try to instantiate and check if it could work
            # This is a simplified check - in practice, you'd do more analysis
            if hole.is_satisfied(value):
                valid_values.add(value)
        
        return valid_values if valid_values else domain
    
    def _get_default_domain(self, hole_type: str) -> Set[Any]:
        """Get default domain for a hole type.
        
        Args:
            hole_type: Type of the hole
            
        Returns:
            Default domain for the hole type
        """
        if hole_type == "operator":
            # Common DSL operators
            return {
                "rotate_cw", "rotate_ccw", "reflect_horizontal", "reflect_vertical",
                "flood_fill", "paint_region", "detect_objects", "select_object",
            }
        elif hole_type == "color":
            return set(range(10))  # ARC colors 0-9
        elif hole_type == "int":
            return set(range(-5, 6))  # Small integers
        else:
            return set()
    
    def _check_program(
        self,
        program: Program,
        examples: List[TrainingExample],
        interpreter: Any,
    ) -> bool:
        """Check if a program satisfies the examples.
        
        Args:
            program: Program to check
            examples: Training examples
            interpreter: DSL interpreter
            
        Returns:
            True if program satisfies all examples, False otherwise
        """
        try:
            for example in examples:
                # Execute program on input
                result = interpreter.run(program, example.input_grid)
                
                # Check if output matches expected
                if not self._grids_equal(result, example.output_grid):
                    return False
            
            return True
        except Exception:
            return False
    
    def _grids_equal(self, grid1: Any, grid2: Any) -> bool:
        """Check if two grids are equal.
        
        Args:
            grid1: First grid
            grid2: Second grid
            
        Returns:
            True if grids are equal, False otherwise
        """
        # This is a simplified check - in practice, you'd use proper grid comparison
        try:
            import numpy as np
            return np.array_equal(grid1, grid2)
        except Exception:
            return grid1 == grid2
    
    def _prune_library(self) -> None:
        """Prune the sketch library to keep only the best sketches."""
        if len(self.sketch_library) <= self.max_sketch_library_size:
            return
        
        # Score sketches by utility
        scored_entries = []
        for signature, entry in self.sketch_library.items():
            utility = entry.success_rate * entry.frequency / max(entry.avg_cost, 1.0)
            scored_entries.append((utility, signature))
        
        # Sort by utility (descending)
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        
        # Keep only top entries
        keep_signatures = {sig for _, sig in scored_entries[:self.max_sketch_library_size]}
        
        # Remove low-utility entries
        to_remove = [sig for sig in self.sketch_library if sig not in keep_signatures]
        for sig in to_remove:
            del self.sketch_library[sig]
        
        logger.info(f"Pruned sketch library: removed {len(to_remove)} entries")


__all__ = [
    "SketchGuidedSynthesizer",
    "SketchLibraryEntry",
]
