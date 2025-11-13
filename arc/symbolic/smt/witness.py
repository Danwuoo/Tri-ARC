"""Witness function generator for backward constraint propagation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid, Stage
from arc.symbolic.ir.sketch import Hole, ProgramSketch

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    z3 = None  # type: ignore


class WitnessFunctionGenerator:
    """Generates witness functions for sketch holes by backward propagation.
    
    Witness functions constrain the possible values for holes in a program sketch
    by propagating constraints backward from the expected output.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the witness function generator.
        
        Args:
            config: Configuration dictionary
        """
        if not Z3_AVAILABLE:
            raise ImportError("Z3 solver is required but not installed")
        
        self.config = config or {}
        self.timeout_ms = int(self.config.get("timeout_ms", 5000))
    
    def generate_witness(
        self,
        sketch: ProgramSketch,
        input_grid: Grid,
        expected_output: Grid
    ) -> Dict[str, Set[Any]]:
        """Generate witness constraints for each hole in the sketch.
        
        Args:
            sketch: Program sketch with holes
            input_grid: Input grid
            expected_output: Expected output grid
            
        Returns:
            Dictionary mapping hole IDs to sets of possible values
        """
        witness_constraints: Dict[str, Set[Any]] = {}
        
        # Initialize with hole domains
        for stage in sketch.stages:
            if isinstance(stage, Hole):
                witness_constraints[stage.id] = set(stage.domain)
        
        # Backward propagate from output
        current_grid = expected_output
        
        # Process stages in reverse order
        for stage in reversed(sketch.stages):
            if isinstance(stage, Hole):
                # Refine hole domain based on current constraints
                refined_domain = self._refine_hole_domain(
                    stage, current_grid, input_grid
                )
                if refined_domain:
                    witness_constraints[stage.id] &= refined_domain
            elif isinstance(stage, Stage):
                # Backward propagate through concrete stage
                current_grid = self._backward_propagate_stage(
                    stage, current_grid
                )
        
        return witness_constraints
    
    def backward_propagate(
        self,
        output_grid: Grid,
        stage: Stage
    ) -> Set[Any]:
        """Backward propagate constraints from output through a stage.
        
        Args:
            output_grid: Output grid after the stage
            stage: The stage to propagate through
            
        Returns:
            Set of possible values/constraints for the stage inputs
        """
        operator = stage.operator
        
        # Dispatch to operator-specific backward propagation
        if operator == "rotate":
            return self._backward_rotate(output_grid, stage)
        elif operator == "reflect":
            return self._backward_reflect(output_grid, stage)
        elif operator == "replace_colour":
            return self._backward_replace_colour(output_grid, stage)
        elif operator == "paint_region":
            return self._backward_paint_region(output_grid, stage)
        else:
            # Unknown operator - return empty set
            return set()
    
    def _refine_hole_domain(
        self,
        hole: Hole,
        current_grid: Grid,
        input_grid: Grid
    ) -> Optional[Set[Any]]:
        """Refine the domain of a hole based on grid constraints.
        
        Args:
            hole: The hole to refine
            current_grid: Current grid state
            input_grid: Original input grid
            
        Returns:
            Refined domain set, or None if no refinement possible
        """
        # Type-based refinement
        if hole.type == "colour":
            # Constrain to colors present in the grids
            input_colors = set(np.unique(input_grid.data))
            output_colors = set(np.unique(current_grid.data))
            all_colors = input_colors | output_colors
            return all_colors & set(hole.domain)
        
        elif hole.type == "int":
            # For integer holes, check if there are size constraints
            if "min" in hole.constraints and "max" in hole.constraints:
                min_val = hole.constraints["min"]
                max_val = hole.constraints["max"]
                return set(range(min_val, max_val + 1)) & set(hole.domain)
        
        # No refinement possible
        return None
    
    def _backward_propagate_stage(
        self,
        stage: Stage,
        output_grid: Grid
    ) -> Grid:
        """Backward propagate through a concrete stage to get input grid.
        
        Note: This is an approximation - true backward propagation would
        require inverting the operation, which is not always possible.
        
        Args:
            stage: The stage to propagate through
            output_grid: Output grid after the stage
            
        Returns:
            Approximated input grid before the stage
        """
        operator = stage.operator
        
        # For invertible operations, compute the inverse
        if operator == "rotate":
            # Inverse of rotate(k) is rotate(4-k)
            if stage.arguments and isinstance(stage.arguments[0], int):
                steps = stage.arguments[0]
                inverse_steps = (4 - steps) % 4
                return self._apply_rotation(output_grid, inverse_steps)
        
        elif operator == "reflect":
            # Reflection is self-inverse
            if stage.arguments and isinstance(stage.arguments[0], str):
                axis = stage.arguments[0]
                return self._apply_reflection(output_grid, axis)
        
        elif operator == "transpose":
            # Transpose is self-inverse
            return Grid(output_grid.data.T)
        
        # For non-invertible operations, return output as-is
        return output_grid
    
    def _backward_rotate(
        self,
        output_grid: Grid,
        stage: Stage
    ) -> Set[Any]:
        """Backward propagate through rotation.
        
        Args:
            output_grid: Output grid
            stage: Rotation stage
            
        Returns:
            Set of constraints (empty for now)
        """
        # Rotation is invertible, so no additional constraints needed
        return set()
    
    def _backward_reflect(
        self,
        output_grid: Grid,
        stage: Stage
    ) -> Set[Any]:
        """Backward propagate through reflection.
        
        Args:
            output_grid: Output grid
            stage: Reflection stage
            
        Returns:
            Set of constraints (empty for now)
        """
        # Reflection is invertible, so no additional constraints needed
        return set()
    
    def _backward_replace_colour(
        self,
        output_grid: Grid,
        stage: Stage
    ) -> Set[Any]:
        """Backward propagate through color replacement.
        
        Args:
            output_grid: Output grid
            stage: Replace color stage
            
        Returns:
            Set of possible source colors
        """
        # If we see dst_color in output, it could have been src_color in input
        if len(stage.arguments) >= 2:
            dst_color = stage.arguments[1]
            if isinstance(dst_color, int):
                output_colors = set(np.unique(output_grid.data))
                if dst_color in output_colors:
                    # The source color could be any color
                    return set(range(10))  # All ARC colors
        return set()
    
    def _backward_paint_region(
        self,
        output_grid: Grid,
        stage: Stage
    ) -> Set[Any]:
        """Backward propagate through paint_region.
        
        Args:
            output_grid: Output grid
            stage: Paint region stage
            
        Returns:
            Set of possible colors
        """
        # The painted color must be present in the output
        output_colors = set(np.unique(output_grid.data))
        return output_colors
    
    def _apply_rotation(self, grid: Grid, steps: int) -> Grid:
        """Apply rotation to a grid.
        
        Args:
            grid: Input grid
            steps: Number of 90-degree clockwise rotations
            
        Returns:
            Rotated grid
        """
        steps = steps % 4
        data = grid.data
        
        for _ in range(steps):
            data = np.rot90(data, k=-1)  # Clockwise rotation
        
        return Grid(data)
    
    def _apply_reflection(self, grid: Grid, axis: str) -> Grid:
        """Apply reflection to a grid.
        
        Args:
            grid: Input grid
            axis: "horizontal" or "vertical"
            
        Returns:
            Reflected grid
        """
        axis = axis.lower()
        
        if axis in ("horizontal", "h"):
            return Grid(np.fliplr(grid.data))
        elif axis in ("vertical", "v"):
            return Grid(np.flipud(grid.data))
        else:
            return grid
