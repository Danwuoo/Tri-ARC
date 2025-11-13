"""Invariant checking for program verification.

This module implements various invariant checkers that can be used
as hard constraints during program synthesis and verification.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import numpy as np
from scipy import ndimage

from arc.symbolic.dsl.types import Grid


class InvariantChecker:
    """Checks various invariants on grid transformations.
    
    Invariants are properties that should be preserved or satisfied
    by valid programs. They can be used as hard constraints to prune
    invalid candidates early.
    
    Attributes:
        config: Configuration dictionary
        enabled_invariants: Set of enabled invariant types
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize invariant checker.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        
        # Extract configuration
        invariant_config = config.get("invariants", {})
        self.enabled_invariants = set(invariant_config.get("enabled", [
            "color_conservation",
            "object_count",
            "topology",
        ]))
        
        # Tolerance settings
        self.object_count_tolerance = invariant_config.get("object_count_tolerance", 0)
        self.color_tolerance = invariant_config.get("color_tolerance", 0)
    
    def check_all_invariants(
        self,
        input_grid: Grid,
        output_grid: Grid,
        invariants: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Check all enabled invariants.
        
        Args:
            input_grid: The input grid
            output_grid: The output grid
            invariants: List of specific invariants to check (None = all enabled)
            
        Returns:
            Dictionary mapping invariant name to pass/fail boolean
        """
        invariants_to_check = invariants if invariants else list(self.enabled_invariants)
        results = {}
        
        for invariant in invariants_to_check:
            if invariant == "color_conservation":
                results[invariant] = self.check_color_conservation(input_grid, output_grid)
            elif invariant == "object_count":
                results[invariant] = self.check_object_count(input_grid, output_grid)
            elif invariant == "topology":
                results[invariant] = self.check_topology(input_grid, output_grid)
            else:
                # Unknown invariant, skip
                results[invariant] = True
        
        return results
    
    def check_color_conservation(
        self,
        input_grid: Grid,
        output_grid: Grid,
    ) -> bool:
        """Check if colors are conserved between input and output.
        
        Color conservation means that the set of colors in the output
        is a subset of (or equal to) the colors in the input, possibly
        with a small tolerance.
        
        Args:
            input_grid: The input grid
            output_grid: The output grid
            
        Returns:
            True if color conservation holds, False otherwise
        """
        # Get unique colors in each grid
        input_colors = set(np.unique(input_grid.data).tolist())
        output_colors = set(np.unique(output_grid.data).tolist())
        
        # Check if output colors are subset of input colors (with tolerance)
        new_colors = output_colors - input_colors
        
        return len(new_colors) <= self.color_tolerance
    
    def check_object_count(
        self,
        input_grid: Grid,
        output_grid: Grid,
        tolerance: Optional[int] = None,
    ) -> bool:
        """Check if object count is preserved (within tolerance).
        
        Object count is the number of connected components in the grid.
        This invariant checks if the number of objects is similar between
        input and output.
        
        Args:
            input_grid: The input grid
            output_grid: The output grid
            tolerance: Tolerance for object count difference (None = use config)
            
        Returns:
            True if object count is preserved within tolerance, False otherwise
        """
        tol = tolerance if tolerance is not None else self.object_count_tolerance
        
        # Count objects in input
        input_object_count = self._count_objects(input_grid)
        
        # Count objects in output
        output_object_count = self._count_objects(output_grid)
        
        # Check if counts are within tolerance
        diff = abs(input_object_count - output_object_count)
        return diff <= tol
    
    def check_topology(
        self,
        input_grid: Grid,
        output_grid: Grid,
    ) -> bool:
        """Check if topological features are preserved.
        
        Topological features include:
        - Number of connected components
        - Presence of holes
        - Connectivity structure
        
        This is a more relaxed check that looks at structural similarity
        rather than exact preservation.
        
        Args:
            input_grid: The input grid
            output_grid: The output grid
            
        Returns:
            True if topology is reasonably preserved, False otherwise
        """
        # Get topological features for both grids
        input_features = self._extract_topological_features(input_grid)
        output_features = self._extract_topological_features(output_grid)
        
        # Check if features are similar
        # For now, we check if the number of components is similar
        component_diff = abs(
            input_features["num_components"] - output_features["num_components"]
        )
        
        # Allow some variation in component count
        max_component_diff = max(2, input_features["num_components"] // 2)
        
        return component_diff <= max_component_diff
    
    def _count_objects(self, grid: Grid) -> int:
        """Count the number of connected objects in a grid.
        
        Args:
            grid: The grid to analyze
            
        Returns:
            Number of connected components
        """
        # Get background color
        background_color = grid.detect_background_colour()
        
        # Create binary mask of non-background cells
        mask = grid.data != background_color
        
        # Label connected components (4-connectivity)
        labeled, num_objects = ndimage.label(mask, structure=np.ones((3, 3)))
        
        return num_objects
    
    def _extract_topological_features(self, grid: Grid) -> Dict[str, Any]:
        """Extract topological features from a grid.
        
        Args:
            grid: The grid to analyze
            
        Returns:
            Dictionary of topological features
        """
        background_color = grid.detect_background_colour()
        mask = grid.data != background_color
        
        # Count connected components
        labeled, num_components = ndimage.label(mask, structure=np.ones((3, 3)))
        
        # Count holes (connected components in the background)
        background_mask = grid.data == background_color
        _, num_holes = ndimage.label(background_mask, structure=np.ones((3, 3)))
        # Subtract 1 for the main background component
        num_holes = max(0, num_holes - 1)
        
        # Compute density (ratio of non-background cells)
        density = np.sum(mask) / mask.size if mask.size > 0 else 0.0
        
        return {
            "num_components": num_components,
            "num_holes": num_holes,
            "density": density,
        }
    
    def check_custom_invariant(
        self,
        input_grid: Grid,
        output_grid: Grid,
        invariant_spec: Dict[str, Any],
    ) -> bool:
        """Check a custom invariant specified by a dictionary.
        
        Args:
            input_grid: The input grid
            output_grid: The output grid
            invariant_spec: Specification of the custom invariant
            
        Returns:
            True if invariant holds, False otherwise
        """
        invariant_type = invariant_spec.get("type")
        
        if invariant_type == "color_set_equal":
            # Check if color sets are exactly equal
            input_colors = set(np.unique(input_grid.data).tolist())
            output_colors = set(np.unique(output_grid.data).tolist())
            return input_colors == output_colors
        
        elif invariant_type == "shape_preserved":
            # Check if grid shape is preserved
            return input_grid.shape == output_grid.shape
        
        elif invariant_type == "color_count_preserved":
            # Check if the count of each color is preserved
            input_counts = np.bincount(input_grid.data.flatten(), minlength=10)
            output_counts = np.bincount(output_grid.data.flatten(), minlength=10)
            return np.array_equal(input_counts, output_counts)
        
        elif invariant_type == "symmetry_preserved":
            # Check if symmetry is preserved
            input_symmetric = self._check_symmetry(input_grid)
            output_symmetric = self._check_symmetry(output_grid)
            return input_symmetric == output_symmetric
        
        else:
            # Unknown invariant type, assume it holds
            return True
    
    def _check_symmetry(self, grid: Grid) -> Dict[str, bool]:
        """Check various symmetries in a grid.
        
        Args:
            grid: The grid to check
            
        Returns:
            Dictionary of symmetry flags
        """
        data = grid.data
        
        # Check horizontal symmetry
        horizontal = np.array_equal(data, np.flip(data, axis=0))
        
        # Check vertical symmetry
        vertical = np.array_equal(data, np.flip(data, axis=1))
        
        # Check 180-degree rotational symmetry
        rotational_180 = np.array_equal(data, np.rot90(data, k=2))
        
        return {
            "horizontal": horizontal,
            "vertical": vertical,
            "rotational_180": rotational_180,
        }
