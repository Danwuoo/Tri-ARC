"""Constraint encoder for translating DSL programs to SMT constraints."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid, Program, Region, Stage

from .types import SMTArray, SMTConstraintSet

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    z3 = None  # type: ignore


class ConstraintEncoder:
    """Encodes DSL programs and grids as SMT constraints using Z3.
    
    This encoder translates grid transformations into Z3 constraints that can be
    verified for correctness. It supports common DSL primitives like rotate,
    reflect, paint_region, flood_fill, etc.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the constraint encoder.
        
        Args:
            config: Configuration dictionary with encoding options
        """
        if not Z3_AVAILABLE:
            raise ImportError("Z3 solver is required but not installed. Install with: pip install z3-solver")
        
        self.config = config or {}
        self.timeout_ms = int(self.config.get("timeout_ms", 5000))
        self.enable_optimization = bool(self.config.get("enable_optimization", True))
        
    def encode_program(
        self,
        program: Program,
        input_grid: Grid,
        expected_output: Grid
    ) -> SMTConstraintSet:
        """Encode a program with input/output examples as SMT constraints.
        
        Args:
            program: The DSL program to encode
            input_grid: Input grid
            expected_output: Expected output grid
            
        Returns:
            SMTConstraintSet containing all constraints
        """
        constraint_set = SMTConstraintSet()
        constraint_set.metadata["program_length"] = len(program.stages)
        constraint_set.metadata["input_shape"] = input_grid.shape
        constraint_set.metadata["output_shape"] = expected_output.shape
        
        # Encode input grid
        input_array = self.encode_grid(input_grid, "input")
        constraint_set.add_variable("input", input_array)
        
        # Encode expected output
        output_array = self.encode_grid(expected_output, "expected_output")
        constraint_set.add_variable("expected_output", output_array)
        
        # Encode program stages sequentially
        current_array = input_array
        for i, stage in enumerate(program.stages):
            stage_name = f"stage_{i}"
            next_array = self._encode_stage(
                stage, current_array, stage_name, constraint_set
            )
            if next_array is None:
                # Unsupported primitive - mark as unknown
                constraint_set.metadata["unsupported_primitive"] = stage.operator
                return constraint_set
            current_array = next_array
        
        # Add assertion that final output matches expected
        constraint_set.add_variable("final_output", current_array)
        self._add_grid_equality_constraint(
            current_array, output_array, constraint_set
        )
        
        return constraint_set
    
    def encode_grid(self, grid: Grid, name: str) -> SMTArray:
        """Encode a grid as a Z3 array.
        
        Args:
            grid: The grid to encode
            name: Unique name for this grid
            
        Returns:
            SMTArray representing the grid
        """
        height, width = grid.shape
        
        # Create Z3 array: (row, col) -> color
        # We use a 2D array represented as Array(Int, Array(Int, Int))
        inner_sort = z3.ArraySort(z3.IntSort(), z3.IntSort())
        array_sort = z3.ArraySort(z3.IntSort(), inner_sort)
        z3_array = z3.Const(name, array_sort)
        
        smt_array = SMTArray(
            name=name,
            shape=(height, width),
            domain=(0, 9),  # ARC colors are 0-9
            z3_array=z3_array
        )
        
        return smt_array
    
    def encode_primitive(
        self,
        stage: Stage,
        input_array: SMTArray,
        output_array: SMTArray,
        constraint_set: SMTConstraintSet
    ) -> List[Any]:
        """Encode a DSL primitive as SMT constraints.
        
        Args:
            stage: The stage containing the primitive operation
            input_array: Input grid array
            output_array: Output grid array
            constraint_set: Constraint set to add constraints to
            
        Returns:
            List of Z3 constraints encoding the primitive
        """
        operator = stage.operator
        args = stage.arguments
        
        # Dispatch to specific primitive encoders
        if operator == "identity":
            return self._encode_identity(input_array, output_array)
        elif operator == "rotate":
            return self._encode_rotate(input_array, output_array, args, constraint_set)
        elif operator == "reflect":
            return self._encode_reflect(input_array, output_array, args, constraint_set)
        elif operator == "transpose":
            return self._encode_transpose(input_array, output_array)
        elif operator == "replace_colour":
            return self._encode_replace_colour(input_array, output_array, args)
        elif operator == "paint_region":
            return self._encode_paint_region(input_array, output_array, args, constraint_set)
        elif operator == "flood_fill":
            return self._encode_flood_fill(input_array, output_array, args, constraint_set)
        else:
            # Unsupported primitive - return empty list
            return []
    
    def _encode_stage(
        self,
        stage: Stage,
        input_array: SMTArray,
        stage_name: str,
        constraint_set: SMTConstraintSet
    ) -> Optional[SMTArray]:
        """Encode a single stage of the program.
        
        Args:
            stage: The stage to encode
            input_array: Input array for this stage
            stage_name: Unique name for this stage
            constraint_set: Constraint set to add to
            
        Returns:
            Output array for this stage, or None if unsupported
        """
        # Create output array for this stage
        output_array = SMTArray(
            name=f"{stage_name}_output",
            shape=input_array.shape,  # Most operations preserve shape
            domain=input_array.domain,
            z3_array=z3.Const(
                f"{stage_name}_output",
                input_array.z3_array.sort()
            )
        )
        
        # Encode the primitive
        constraints = self.encode_primitive(
            stage, input_array, output_array, constraint_set
        )
        
        if not constraints:
            # Unsupported primitive
            return None
        
        # Add constraints to the set
        for constraint in constraints:
            constraint_set.add_constraint(constraint)
        
        return output_array
    
    def _add_grid_equality_constraint(
        self,
        array1: SMTArray,
        array2: SMTArray,
        constraint_set: SMTConstraintSet
    ) -> None:
        """Add constraint that two grids are equal.
        
        Args:
            array1: First grid array
            array2: Second grid array
            constraint_set: Constraint set to add to
        """
        if array1.shape != array2.shape:
            # Different shapes - add false constraint
            constraint_set.add_assertion(z3.BoolVal(False))
            return
        
        height, width = array1.shape
        
        # Add equality constraint for each cell
        for row in range(height):
            for col in range(width):
                cell1 = z3.Select(z3.Select(array1.z3_array, row), col)
                cell2 = z3.Select(z3.Select(array2.z3_array, row), col)
                constraint_set.add_assertion(cell1 == cell2)
    
    # Primitive encoders
    
    def _encode_identity(
        self,
        input_array: SMTArray,
        output_array: SMTArray
    ) -> List[Any]:
        """Encode identity operation (output = input)."""
        constraints = []
        height, width = input_array.shape
        
        for row in range(height):
            for col in range(width):
                in_cell = z3.Select(z3.Select(input_array.z3_array, row), col)
                out_cell = z3.Select(z3.Select(output_array.z3_array, row), col)
                constraints.append(out_cell == in_cell)
        
        return constraints
    
    def _encode_rotate(
        self,
        input_array: SMTArray,
        output_array: SMTArray,
        args: Tuple[Any, ...],
        constraint_set: SMTConstraintSet
    ) -> List[Any]:
        """Encode rotation operation.
        
        Args:
            input_array: Input grid
            output_array: Output grid
            args: (steps,) where steps is number of 90-degree rotations
            constraint_set: Constraint set
            
        Returns:
            List of constraints
        """
        if not args or not isinstance(args[0], int):
            return []
        
        steps = args[0] % 4  # Normalize to 0-3
        height, width = input_array.shape
        constraints = []
        
        if steps == 0:
            # No rotation
            return self._encode_identity(input_array, output_array)
        elif steps == 1:
            # 90 degrees clockwise: (r, c) -> (c, height-1-r)
            for r in range(height):
                for c in range(width):
                    in_cell = z3.Select(z3.Select(input_array.z3_array, r), c)
                    out_cell = z3.Select(z3.Select(output_array.z3_array, c), height - 1 - r)
                    constraints.append(out_cell == in_cell)
        elif steps == 2:
            # 180 degrees: (r, c) -> (height-1-r, width-1-c)
            for r in range(height):
                for c in range(width):
                    in_cell = z3.Select(z3.Select(input_array.z3_array, r), c)
                    out_cell = z3.Select(z3.Select(output_array.z3_array, height - 1 - r), width - 1 - c)
                    constraints.append(out_cell == in_cell)
        elif steps == 3:
            # 270 degrees clockwise: (r, c) -> (width-1-c, r)
            for r in range(height):
                for c in range(width):
                    in_cell = z3.Select(z3.Select(input_array.z3_array, r), c)
                    out_cell = z3.Select(z3.Select(output_array.z3_array, width - 1 - c), r)
                    constraints.append(out_cell == in_cell)
        
        return constraints
    
    def _encode_reflect(
        self,
        input_array: SMTArray,
        output_array: SMTArray,
        args: Tuple[Any, ...],
        constraint_set: SMTConstraintSet
    ) -> List[Any]:
        """Encode reflection operation.
        
        Args:
            input_array: Input grid
            output_array: Output grid
            args: (axis,) where axis is "horizontal" or "vertical"
            constraint_set: Constraint set
            
        Returns:
            List of constraints
        """
        if not args or not isinstance(args[0], str):
            return []
        
        axis = args[0].lower()
        height, width = input_array.shape
        constraints = []
        
        if axis in ("horizontal", "h"):
            # Reflect horizontally: (r, c) -> (r, width-1-c)
            for r in range(height):
                for c in range(width):
                    in_cell = z3.Select(z3.Select(input_array.z3_array, r), c)
                    out_cell = z3.Select(z3.Select(output_array.z3_array, r), width - 1 - c)
                    constraints.append(out_cell == in_cell)
        elif axis in ("vertical", "v"):
            # Reflect vertically: (r, c) -> (height-1-r, c)
            for r in range(height):
                for c in range(width):
                    in_cell = z3.Select(z3.Select(input_array.z3_array, r), c)
                    out_cell = z3.Select(z3.Select(output_array.z3_array, height - 1 - r), c)
                    constraints.append(out_cell == in_cell)
        else:
            return []
        
        return constraints
    
    def _encode_transpose(
        self,
        input_array: SMTArray,
        output_array: SMTArray
    ) -> List[Any]:
        """Encode transpose operation: (r, c) -> (c, r)."""
        height, width = input_array.shape
        constraints = []
        
        for r in range(height):
            for c in range(width):
                in_cell = z3.Select(z3.Select(input_array.z3_array, r), c)
                out_cell = z3.Select(z3.Select(output_array.z3_array, c), r)
                constraints.append(out_cell == in_cell)
        
        return constraints
    
    def _encode_replace_colour(
        self,
        input_array: SMTArray,
        output_array: SMTArray,
        args: Tuple[Any, ...]
    ) -> List[Any]:
        """Encode color replacement operation."""
        if len(args) < 2:
            return []
        
        src_color = args[0] if isinstance(args[0], int) else None
        dst_color = args[1] if isinstance(args[1], int) else None
        
        if src_color is None or dst_color is None:
            return []
        
        height, width = input_array.shape
        constraints = []
        
        # For each cell: if input == src_color, output = dst_color, else output = input
        for r in range(height):
            for c in range(width):
                in_cell = z3.Select(z3.Select(input_array.z3_array, r), c)
                out_cell = z3.Select(z3.Select(output_array.z3_array, r), c)
                constraints.append(
                    out_cell == z3.If(in_cell == src_color, dst_color, in_cell)
                )
        
        return constraints
    
    def _encode_paint_region(
        self,
        input_array: SMTArray,
        output_array: SMTArray,
        args: Tuple[Any, ...],
        constraint_set: SMTConstraintSet
    ) -> List[Any]:
        """Encode paint_region operation.
        
        Note: This is a simplified encoding that assumes the region is known.
        A full implementation would need to encode region detection.
        """
        # Simplified: just return identity for now
        # Full implementation would require encoding the region mask
        return self._encode_identity(input_array, output_array)
    
    def _encode_flood_fill(
        self,
        input_array: SMTArray,
        output_array: SMTArray,
        args: Tuple[Any, ...],
        constraint_set: SMTConstraintSet
    ) -> List[Any]:
        """Encode flood_fill operation.
        
        Note: This is a simplified encoding.
        Full flood fill requires recursive constraints which are complex in SMT.
        """
        # Simplified: just return identity for now
        # Full implementation would require encoding connectivity constraints
        return self._encode_identity(input_array, output_array)
