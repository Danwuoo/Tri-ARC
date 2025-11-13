"""Abstract interpretation for early pruning in program synthesis.

This module implements abstract interpretation, which executes programs
in an abstract domain to detect infeasible candidates early without
full concrete execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage

logger = logging.getLogger(__name__)


@dataclass
class AbstractGrid:
    """Abstract representation of a grid for abstract interpretation.
    
    Instead of tracking exact cell values, AbstractGrid tracks properties
    that can be used for early pruning:
    - color_set: Set of colors that may appear in the grid
    - component_count_range: Range of possible connected components
    - symmetry_flags: Symmetry properties (horizontal, vertical, rotational)
    - bbox: Bounding box of non-background regions
    - shape_range: Range of possible grid shapes
    
    Attributes:
        color_set: Set of colors that may appear
        component_count_range: (min, max) number of connected components
        symmetry_flags: Dictionary of symmetry properties
        bbox: Bounding box as (min_row, min_col, max_row, max_col)
        shape_range: ((min_height, min_width), (max_height, max_width))
    """
    
    color_set: Set[int] = field(default_factory=set)
    component_count_range: Tuple[int, int] = (0, float('inf'))
    symmetry_flags: Dict[str, bool] = field(default_factory=dict)
    bbox: Optional[Tuple[int, int, int, int]] = None
    shape_range: Tuple[Tuple[int, int], Tuple[int, int]] = ((0, 0), (float('inf'), float('inf')))
    
    def __post_init__(self):
        """Initialize default symmetry flags if not provided."""
        if not self.symmetry_flags:
            self.symmetry_flags = {
                "horizontal": False,
                "vertical": False,
                "rotational_90": False,
                "rotational_180": False,
            }
    
    @classmethod
    def from_concrete_grid(cls, grid: Any) -> AbstractGrid:
        """Create an abstract grid from a concrete grid.
        
        Args:
            grid: Concrete grid (numpy array or list of lists)
            
        Returns:
            AbstractGrid representing the concrete grid
        """
        import numpy as np
        
        if not isinstance(grid, np.ndarray):
            grid = np.array(grid)
        
        # Extract color set
        color_set = set(np.unique(grid).tolist())
        
        # Compute shape
        height, width = grid.shape
        shape_range = ((height, width), (height, width))
        
        # Compute bounding box of non-zero regions (assuming 0 is background)
        non_zero = np.argwhere(grid != 0)
        if len(non_zero) > 0:
            min_row, min_col = non_zero.min(axis=0)
            max_row, max_col = non_zero.max(axis=0)
            bbox = (int(min_row), int(min_col), int(max_row), int(max_col))
        else:
            bbox = None
        
        # Detect symmetries
        symmetry_flags = {
            "horizontal": cls._check_horizontal_symmetry(grid),
            "vertical": cls._check_vertical_symmetry(grid),
            "rotational_90": cls._check_rotational_90_symmetry(grid),
            "rotational_180": cls._check_rotational_180_symmetry(grid),
        }
        
        # Estimate component count (simplified)
        component_count = cls._estimate_component_count(grid)
        component_count_range = (component_count, component_count)
        
        return cls(
            color_set=color_set,
            component_count_range=component_count_range,
            symmetry_flags=symmetry_flags,
            bbox=bbox,
            shape_range=shape_range,
        )
    
    @staticmethod
    def _check_horizontal_symmetry(grid: Any) -> bool:
        """Check if grid has horizontal symmetry."""
        import numpy as np
        return np.array_equal(grid, np.flipud(grid))
    
    @staticmethod
    def _check_vertical_symmetry(grid: Any) -> bool:
        """Check if grid has vertical symmetry."""
        import numpy as np
        return np.array_equal(grid, np.fliplr(grid))
    
    @staticmethod
    def _check_rotational_90_symmetry(grid: Any) -> bool:
        """Check if grid has 90-degree rotational symmetry."""
        import numpy as np
        return np.array_equal(grid, np.rot90(grid, k=1))
    
    @staticmethod
    def _check_rotational_180_symmetry(grid: Any) -> bool:
        """Check if grid has 180-degree rotational symmetry."""
        import numpy as np
        return np.array_equal(grid, np.rot90(grid, k=2))
    
    @staticmethod
    def _estimate_component_count(grid: Any) -> int:
        """Estimate the number of connected components in the grid."""
        import numpy as np
        from scipy import ndimage
        
        # Label connected components (4-connectivity)
        labeled, num_components = ndimage.label(grid != 0)
        return int(num_components)
    
    def is_compatible_with(self, concrete_grid: Any) -> bool:
        """Check if a concrete grid is compatible with this abstract grid.
        
        Args:
            concrete_grid: Concrete grid to check
            
        Returns:
            True if concrete grid is compatible, False otherwise
        """
        import numpy as np
        
        if not isinstance(concrete_grid, np.ndarray):
            concrete_grid = np.array(concrete_grid)
        
        # Check color set
        concrete_colors = set(np.unique(concrete_grid).tolist())
        if not concrete_colors.issubset(self.color_set):
            return False
        
        # Check shape
        height, width = concrete_grid.shape
        min_h, min_w = self.shape_range[0]
        max_h, max_w = self.shape_range[1]
        if not (min_h <= height <= max_h and min_w <= width <= max_w):
            return False
        
        # Check component count
        concrete_components = self._estimate_component_count(concrete_grid)
        min_comp, max_comp = self.component_count_range
        if not (min_comp <= concrete_components <= max_comp):
            return False
        
        return True
    
    def union(self, other: AbstractGrid) -> AbstractGrid:
        """Compute the union (join) of two abstract grids.
        
        Args:
            other: Another abstract grid
            
        Returns:
            Abstract grid representing the union
        """
        # Union of color sets
        color_set = self.color_set.union(other.color_set)
        
        # Union of component count ranges
        min_comp = min(self.component_count_range[0], other.component_count_range[0])
        max_comp = max(self.component_count_range[1], other.component_count_range[1])
        component_count_range = (min_comp, max_comp)
        
        # Union of symmetry flags (conservative: both must have symmetry)
        symmetry_flags = {
            key: self.symmetry_flags.get(key, False) and other.symmetry_flags.get(key, False)
            for key in self.symmetry_flags
        }
        
        # Union of bounding boxes
        if self.bbox and other.bbox:
            bbox = (
                min(self.bbox[0], other.bbox[0]),
                min(self.bbox[1], other.bbox[1]),
                max(self.bbox[2], other.bbox[2]),
                max(self.bbox[3], other.bbox[3]),
            )
        else:
            bbox = self.bbox or other.bbox
        
        # Union of shape ranges
        min_h = min(self.shape_range[0][0], other.shape_range[0][0])
        min_w = min(self.shape_range[0][1], other.shape_range[0][1])
        max_h = max(self.shape_range[1][0], other.shape_range[1][0])
        max_w = max(self.shape_range[1][1], other.shape_range[1][1])
        shape_range = ((min_h, min_w), (max_h, max_w))
        
        return AbstractGrid(
            color_set=color_set,
            component_count_range=component_count_range,
            symmetry_flags=symmetry_flags,
            bbox=bbox,
            shape_range=shape_range,
        )


class AbstractInterpreter:
    """Abstract interpreter for program synthesis.
    
    This class executes programs in an abstract domain to detect
    infeasible candidates early without full concrete execution.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the abstract interpreter.
        
        Args:
            config: Configuration dictionary with optional parameters:
                - enable_color_tracking: Track color sets
                - enable_component_tracking: Track connected components
                - enable_symmetry_tracking: Track symmetries
        """
        self.config = config or {}
        self.enable_color_tracking = self.config.get("enable_color_tracking", True)
        self.enable_component_tracking = self.config.get("enable_component_tracking", True)
        self.enable_symmetry_tracking = self.config.get("enable_symmetry_tracking", True)
        
        logger.info("Initialized AbstractInterpreter")
    
    def abstract_execute(
        self,
        program: Program,
        abstract_input: AbstractGrid,
    ) -> AbstractGrid:
        """Execute a program in the abstract domain.
        
        Args:
            program: Program to execute
            abstract_input: Abstract input grid
            
        Returns:
            Abstract output grid
        """
        current = abstract_input
        
        for stage in program.stages:
            current = self._abstract_execute_stage(stage, current)
        
        return current
    
    def check_feasibility(
        self,
        abstract_output: AbstractGrid,
        concrete_output: Any,
    ) -> bool:
        """Check if an abstract output is compatible with a concrete output.
        
        This is used for early pruning: if the abstract output is not
        compatible with the expected concrete output, the program can
        be pruned without full execution.
        
        Args:
            abstract_output: Abstract output from program execution
            concrete_output: Expected concrete output
            
        Returns:
            True if abstract output is compatible, False otherwise
        """
        return abstract_output.is_compatible_with(concrete_output)
    
    def _abstract_execute_stage(
        self,
        stage: Stage,
        abstract_input: AbstractGrid,
    ) -> AbstractGrid:
        """Execute a single stage in the abstract domain.
        
        Args:
            stage: Stage to execute
            abstract_input: Abstract input grid
            
        Returns:
            Abstract output grid
        """
        operator = stage.operator
        
        # Dispatch to operator-specific abstract execution
        if operator in ("rotate_cw", "rotate_ccw", "rotate_180"):
            return self._abstract_rotate(abstract_input, operator)
        elif operator in ("reflect_horizontal", "reflect_vertical"):
            return self._abstract_reflect(abstract_input, operator)
        elif operator == "flood_fill":
            return self._abstract_flood_fill(abstract_input, stage.arguments)
        elif operator == "paint_region":
            return self._abstract_paint_region(abstract_input, stage.arguments)
        elif operator == "detect_objects":
            return self._abstract_detect_objects(abstract_input)
        else:
            # Unknown operator: return conservative over-approximation
            return self._abstract_unknown(abstract_input)
    
    def _abstract_rotate(
        self,
        abstract_input: AbstractGrid,
        operator: str,
    ) -> AbstractGrid:
        """Abstract execution of rotation operators.
        
        Args:
            abstract_input: Abstract input grid
            operator: Rotation operator
            
        Returns:
            Abstract output grid
        """
        # Rotation preserves colors and component count
        result = AbstractGrid(
            color_set=abstract_input.color_set.copy(),
            component_count_range=abstract_input.component_count_range,
            symmetry_flags=abstract_input.symmetry_flags.copy(),
            bbox=abstract_input.bbox,
            shape_range=abstract_input.shape_range,
        )
        
        # Update symmetry flags based on rotation
        if operator == "rotate_cw":
            # 90-degree clockwise rotation
            result.symmetry_flags["horizontal"] = abstract_input.symmetry_flags.get("vertical", False)
            result.symmetry_flags["vertical"] = abstract_input.symmetry_flags.get("horizontal", False)
        elif operator == "rotate_ccw":
            # 90-degree counter-clockwise rotation
            result.symmetry_flags["horizontal"] = abstract_input.symmetry_flags.get("vertical", False)
            result.symmetry_flags["vertical"] = abstract_input.symmetry_flags.get("horizontal", False)
        elif operator == "rotate_180":
            # 180-degree rotation preserves symmetries
            pass
        
        return result
    
    def _abstract_reflect(
        self,
        abstract_input: AbstractGrid,
        operator: str,
    ) -> AbstractGrid:
        """Abstract execution of reflection operators.
        
        Args:
            abstract_input: Abstract input grid
            operator: Reflection operator
            
        Returns:
            Abstract output grid
        """
        # Reflection preserves colors and component count
        result = AbstractGrid(
            color_set=abstract_input.color_set.copy(),
            component_count_range=abstract_input.component_count_range,
            symmetry_flags=abstract_input.symmetry_flags.copy(),
            bbox=abstract_input.bbox,
            shape_range=abstract_input.shape_range,
        )
        
        # Update symmetry flags
        if operator == "reflect_horizontal":
            result.symmetry_flags["horizontal"] = True
        elif operator == "reflect_vertical":
            result.symmetry_flags["vertical"] = True
        
        return result
    
    def _abstract_flood_fill(
        self,
        abstract_input: AbstractGrid,
        arguments: Tuple[Any, ...],
    ) -> AbstractGrid:
        """Abstract execution of flood_fill operator.
        
        Args:
            abstract_input: Abstract input grid
            arguments: Operator arguments
            
        Returns:
            Abstract output grid
        """
        # Flood fill may add a new color
        new_color_set = abstract_input.color_set.copy()
        if arguments and len(arguments) > 0:
            # Add the fill color
            new_color_set.add(arguments[0])
        
        # Component count may change (components may merge)
        min_comp = 1
        max_comp = abstract_input.component_count_range[1]
        
        return AbstractGrid(
            color_set=new_color_set,
            component_count_range=(min_comp, max_comp),
            symmetry_flags={},  # Symmetry may be broken
            bbox=abstract_input.bbox,
            shape_range=abstract_input.shape_range,
        )
    
    def _abstract_paint_region(
        self,
        abstract_input: AbstractGrid,
        arguments: Tuple[Any, ...],
    ) -> AbstractGrid:
        """Abstract execution of paint_region operator.
        
        Args:
            abstract_input: Abstract input grid
            arguments: Operator arguments
            
        Returns:
            Abstract output grid
        """
        # Paint region may add a new color
        new_color_set = abstract_input.color_set.copy()
        if arguments and len(arguments) > 0:
            new_color_set.add(arguments[0])
        
        return AbstractGrid(
            color_set=new_color_set,
            component_count_range=abstract_input.component_count_range,
            symmetry_flags={},  # Symmetry may be broken
            bbox=abstract_input.bbox,
            shape_range=abstract_input.shape_range,
        )
    
    def _abstract_detect_objects(
        self,
        abstract_input: AbstractGrid,
    ) -> AbstractGrid:
        """Abstract execution of detect_objects operator.
        
        Args:
            abstract_input: Abstract input grid
            
        Returns:
            Abstract output grid
        """
        # Detect objects preserves most properties
        return AbstractGrid(
            color_set=abstract_input.color_set.copy(),
            component_count_range=abstract_input.component_count_range,
            symmetry_flags=abstract_input.symmetry_flags.copy(),
            bbox=abstract_input.bbox,
            shape_range=abstract_input.shape_range,
        )
    
    def _abstract_unknown(
        self,
        abstract_input: AbstractGrid,
    ) -> AbstractGrid:
        """Abstract execution for unknown operators (conservative).
        
        Args:
            abstract_input: Abstract input grid
            
        Returns:
            Abstract output grid (over-approximation)
        """
        # Conservative over-approximation: allow all colors, any component count
        return AbstractGrid(
            color_set=set(range(10)),  # All ARC colors
            component_count_range=(0, float('inf')),
            symmetry_flags={},
            bbox=None,
            shape_range=((0, 0), (float('inf'), float('inf'))),
        )


__all__ = [
    "AbstractGrid",
    "AbstractInterpreter",
]
