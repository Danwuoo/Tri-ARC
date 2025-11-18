"""BDD (Binary Decision Diagram) support for grid operations.

This module provides BDD-based encoding and equivalence checking for grids.
BDDs can be more efficient than SMT for certain types of grid operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    z3 = None  # type: ignore


class BDDEncoder:
    """Encodes grids and operations using Binary Decision Diagrams.
    
    BDDs provide a compact representation for boolean functions and can be
    more efficient than SMT for certain grid operations, especially those
    involving boolean masks and connectivity.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the BDD encoder.
        
        Args:
            config: Configuration dictionary
        """
        if not Z3_AVAILABLE:
            raise ImportError("Z3 solver is required but not installed")
        
        self.config = config or {}
        self.max_grid_size = int(self.config.get("max_grid_size", 900))  # 30x30
    
    def encode_grid_as_bdd(
        self,
        grid: Grid,
        color: int
    ) -> Any:
        """Encode a grid as a BDD for a specific color.
        
        Creates a boolean function that is true for cells with the given color.
        
        Args:
            grid: Grid to encode
            color: Color to encode
            
        Returns:
            Z3 boolean expression representing the BDD
        """
        height, width = grid.shape
        
        if height * width > self.max_grid_size:
            raise ValueError(f"Grid too large for BDD encoding: {height}x{width}")
        
        # Create boolean variables for each cell
        cells = []
        for r in range(height):
            row = []
            for c in range(width):
                var = z3.Bool(f"cell_{r}_{c}")
                # Set value based on whether cell has the target color
                value = grid.data[r, c] == color
                row.append(var if value else z3.Not(var))
            cells.append(row)
        
        # Combine into a single BDD expression
        # For now, we just return the grid of boolean expressions
        return cells
    
    def check_equivalence(
        self,
        grid1: Grid,
        grid2: Grid
    ) -> bool:
        """Check if two grids are equivalent using BDD.
        
        Args:
            grid1: First grid
            grid2: Second grid
            
        Returns:
            True if grids are equivalent
        """
        # Simple check: grids must have same shape
        if grid1.shape != grid2.shape:
            return False
        
        # Check cell-by-cell equality
        return np.array_equal(grid1.data, grid2.data)
    
    def encode_connectivity(
        self,
        grid: Grid,
        color: int,
        connectivity: int = 4
    ) -> List[Any]:
        """Encode connectivity constraints as BDD.
        
        Args:
            grid: Grid to encode
            color: Color to check connectivity for
            connectivity: 4 or 8 connectivity
            
        Returns:
            List of Z3 constraints encoding connectivity
        """
        height, width = grid.shape
        constraints = []
        
        # Create boolean variables for each cell
        cell_vars = {}
        for r in range(height):
            for c in range(width):
                var = z3.Bool(f"conn_{r}_{c}")
                cell_vars[(r, c)] = var
                # Cell is true if it has the target color
                if grid.data[r, c] == color:
                    constraints.append(var)
                else:
                    constraints.append(z3.Not(var))
        
        # Add connectivity constraints
        for r in range(height):
            for c in range(width):
                if grid.data[r, c] == color:
                    # This cell should be connected to at least one neighbor
                    neighbors = []
                    
                    # 4-connectivity: up, down, left, right
                    if r > 0 and grid.data[r-1, c] == color:
                        neighbors.append(cell_vars[(r-1, c)])
                    if r < height-1 and grid.data[r+1, c] == color:
                        neighbors.append(cell_vars[(r+1, c)])
                    if c > 0 and grid.data[r, c-1] == color:
                        neighbors.append(cell_vars[(r, c-1)])
                    if c < width-1 and grid.data[r, c+1] == color:
                        neighbors.append(cell_vars[(r, c+1)])
                    
                    # 8-connectivity: add diagonals
                    if connectivity == 8:
                        if r > 0 and c > 0 and grid.data[r-1, c-1] == color:
                            neighbors.append(cell_vars[(r-1, c-1)])
                        if r > 0 and c < width-1 and grid.data[r-1, c+1] == color:
                            neighbors.append(cell_vars[(r-1, c+1)])
                        if r < height-1 and c > 0 and grid.data[r+1, c-1] == color:
                            neighbors.append(cell_vars[(r+1, c-1)])
                        if r < height-1 and c < width-1 and grid.data[r+1, c+1] == color:
                            neighbors.append(cell_vars[(r+1, c+1)])
                    
                    # Add constraint: if this cell is true, at least one neighbor is true
                    if neighbors:
                        constraints.append(
                            z3.Implies(cell_vars[(r, c)], z3.Or(*neighbors))
                        )
        
        return constraints
    
    def encode_region_mask(
        self,
        grid: Grid,
        mask: np.ndarray
    ) -> List[Any]:
        """Encode a region mask as BDD constraints.
        
        Args:
            grid: Grid
            mask: Boolean mask indicating the region
            
        Returns:
            List of Z3 constraints
        """
        height, width = grid.shape
        constraints = []
        
        for r in range(height):
            for c in range(width):
                var = z3.Bool(f"mask_{r}_{c}")
                if mask[r, c]:
                    constraints.append(var)
                else:
                    constraints.append(z3.Not(var))
        
        return constraints
    
    def simplify_bdd(self, bdd_expr: Any) -> Any:
        """Simplify a BDD expression.
        
        Args:
            bdd_expr: Z3 boolean expression
            
        Returns:
            Simplified expression
        """
        if Z3_AVAILABLE:
            return z3.simplify(bdd_expr)
        return bdd_expr


class BDDVerifier:
    """Verifier using BDD-based equivalence checking.
    
    This verifier uses BDDs to check equivalence of grid operations,
    which can be more efficient than SMT for certain types of operations.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the BDD verifier.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.encoder = BDDEncoder(config)
    
    def verify_equivalence(
        self,
        grid1: Grid,
        grid2: Grid
    ) -> bool:
        """Verify that two grids are equivalent.
        
        Args:
            grid1: First grid
            grid2: Second grid
            
        Returns:
            True if grids are equivalent
        """
        return self.encoder.check_equivalence(grid1, grid2)
    
    def verify_connectivity(
        self,
        grid: Grid,
        color: int,
        expected_components: int,
        connectivity: int = 4
    ) -> bool:
        """Verify connectivity properties of a grid.
        
        Args:
            grid: Grid to verify
            color: Color to check
            expected_components: Expected number of connected components
            connectivity: 4 or 8 connectivity
            
        Returns:
            True if connectivity matches expectation
        """
        # Use connected components analysis
        from arc.symbolic.dsl.runtime.utils import connected_components

        # Count components that match the requested colour.  We pass a sentinel
        # background (-1) so that every colour in the grid is considered.
        components = connected_components(grid, connectivity=connectivity, background=-1)
        matching = sum(1 for entry in components if entry.get("colour") == color)
        return matching == expected_components
