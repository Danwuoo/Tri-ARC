"""Counterexample minimization using delta debugging.

This module implements counterexample minimization to produce smaller,
more focused counterexamples that are easier to analyze and lead to
better refinement in the CEGIS loop.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Dict, Optional

import numpy as np

from arc.symbolic.dsl.types import Grid, Program
from arc.symbolic.verification.cegis import Counterexample


class CounterexampleMinimizer:
    """Minimizes counterexamples using delta debugging techniques.
    
    The minimizer attempts to shrink counterexamples while preserving
    the failure property. This makes counterexamples more focused and
    easier to analyze.
    
    Attributes:
        config: Configuration dictionary
        verifier: Program verifier for checking if failure is preserved
    """
    
    def __init__(self, config: Dict[str, Any], verifier: Optional[Any] = None):
        """Initialize counterexample minimizer.
        
        Args:
            config: Configuration dictionary
            verifier: Program verifier (optional, can be set later)
        """
        self.config = config
        self.verifier = verifier
        
        # Extract configuration
        minimizer_config = config.get("counterexample_minimizer", {})
        self.max_iterations = minimizer_config.get("max_iterations", 10)
        self.min_grid_size = minimizer_config.get("min_grid_size", 1)
    
    def minimize(
        self,
        program: Program,
        counterexample: Counterexample,
    ) -> Counterexample:
        """Minimize a counterexample while preserving the failure.
        
        Args:
            program: The program that fails on this counterexample
            counterexample: The counterexample to minimize
            
        Returns:
            A minimized Counterexample
        """
        if counterexample.minimal:
            # Already minimized
            return counterexample
        
        # Create a failure predicate
        def preserves_failure(grid: Grid) -> bool:
            """Check if the grid still causes the program to fail."""
            return self._check_failure(program, grid, counterexample.expected_output)
        
        # Try to shrink the grid
        minimized_input = self.shrink_grid(
            counterexample.input_grid,
            preserves_failure,
        )
        
        # Execute program on minimized input to get actual output
        if self.verifier:
            try:
                result = self.verifier.execute(program, minimized_input)
                minimized_actual = result.get("output", minimized_input)
            except Exception:
                minimized_actual = minimized_input
        else:
            minimized_actual = counterexample.actual_output
        
        # Create minimized counterexample
        return Counterexample(
            input_grid=minimized_input,
            expected_output=counterexample.expected_output,
            actual_output=minimized_actual,
            minimal=True,
            metadata={
                **counterexample.metadata,
                "original_shape": counterexample.input_grid.shape,
                "minimized_shape": minimized_input.shape,
            },
        )
    
    def shrink_grid(
        self,
        grid: Grid,
        preserve_failure: Callable[[Grid], bool],
    ) -> Grid:
        """Shrink a grid while preserving the failure property.
        
        Uses delta debugging to iteratively remove rows and columns
        while checking that the failure is still triggered.
        
        Args:
            grid: The grid to shrink
            preserve_failure: Predicate that returns True if failure is preserved
            
        Returns:
            A shrunk Grid
        """
        current_grid = grid
        
        for iteration in range(self.max_iterations):
            # Try to remove rows
            shrunk_rows = self._try_remove_rows(current_grid, preserve_failure)
            if shrunk_rows is not None:
                current_grid = shrunk_rows
                continue
            
            # Try to remove columns
            shrunk_cols = self._try_remove_columns(current_grid, preserve_failure)
            if shrunk_cols is not None:
                current_grid = shrunk_cols
                continue
            
            # Try to simplify colors (replace with background)
            shrunk_colors = self._try_simplify_colors(current_grid, preserve_failure)
            if shrunk_colors is not None:
                current_grid = shrunk_colors
                continue
            
            # No more shrinking possible
            break
        
        return current_grid
    
    def _try_remove_rows(
        self,
        grid: Grid,
        preserve_failure: Callable[[Grid], bool],
    ) -> Optional[Grid]:
        """Try to remove rows from the grid.
        
        Args:
            grid: The grid to shrink
            preserve_failure: Predicate to check if failure is preserved
            
        Returns:
            Shrunk grid if successful, None otherwise
        """
        height, width = grid.shape
        
        if height <= self.min_grid_size:
            return None
        
        # Try removing each row
        for row_idx in range(height):
            # Create grid without this row
            mask = np.ones(height, dtype=bool)
            mask[row_idx] = False
            new_data = grid.data[mask, :]
            new_grid = Grid(new_data)
            
            # Check if failure is preserved
            if preserve_failure(new_grid):
                return new_grid
        
        return None
    
    def _try_remove_columns(
        self,
        grid: Grid,
        preserve_failure: Callable[[Grid], bool],
    ) -> Optional[Grid]:
        """Try to remove columns from the grid.
        
        Args:
            grid: The grid to shrink
            preserve_failure: Predicate to check if failure is preserved
            
        Returns:
            Shrunk grid if successful, None otherwise
        """
        height, width = grid.shape
        
        if width <= self.min_grid_size:
            return None
        
        # Try removing each column
        for col_idx in range(width):
            # Create grid without this column
            mask = np.ones(width, dtype=bool)
            mask[col_idx] = False
            new_data = grid.data[:, mask]
            new_grid = Grid(new_data)
            
            # Check if failure is preserved
            if preserve_failure(new_grid):
                return new_grid
        
        return None
    
    def _try_simplify_colors(
        self,
        grid: Grid,
        preserve_failure: Callable[[Grid], bool],
    ) -> Optional[Grid]:
        """Try to simplify colors by replacing with background color.
        
        Args:
            grid: The grid to simplify
            preserve_failure: Predicate to check if failure is preserved
            
        Returns:
            Simplified grid if successful, None otherwise
        """
        background_color = grid.detect_background_colour()
        
        # Find all non-background cells
        non_background_mask = grid.data != background_color
        non_background_positions = np.argwhere(non_background_mask)
        
        if len(non_background_positions) == 0:
            return None
        
        # Try replacing each non-background cell with background
        for pos in non_background_positions:
            row, col = pos
            
            # Create new grid with this cell replaced
            new_data = grid.data.copy()
            new_data[row, col] = background_color
            new_grid = Grid(new_data)
            
            # Check if failure is preserved
            if preserve_failure(new_grid):
                return new_grid
        
        return None
    
    def _check_failure(
        self,
        program: Program,
        input_grid: Grid,
        expected_output: Grid,
    ) -> bool:
        """Check if a program fails on the given input.
        
        Args:
            program: The program to check
            input_grid: The input grid
            expected_output: The expected output grid
            
        Returns:
            True if the program fails (produces different output), False otherwise
        """
        if self.verifier is None:
            # Without verifier, assume failure is preserved
            return True
        
        try:
            result = self.verifier.verify(program, input_grid, expected_output)
            # Failure is preserved if verification fails
            return not result.get("success", False)
        except Exception:
            # Exception means failure is preserved
            return True
