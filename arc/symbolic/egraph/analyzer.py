"""E-class analysis for extracting summary properties from equivalent programs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from arc.symbolic.dsl.types import Program, Stage


@dataclass
class BoundingBox:
    """Bounding box representation"""
    min_row: int
    max_row: int
    min_col: int
    max_col: int
    
    def area(self) -> int:
        """Compute bounding box area"""
        return (self.max_row - self.min_row + 1) * (self.max_col - self.min_col + 1)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BoundingBox):
            return NotImplemented
        return (
            self.min_row == other.min_row
            and self.max_row == other.max_row
            and self.min_col == other.min_col
            and self.max_col == other.max_col
        )
    
    def __hash__(self) -> int:
        return hash((self.min_row, self.max_row, self.min_col, self.max_col))


@dataclass
class ConnectivityInfo:
    """Connectivity information for grids/objects"""
    min_components: int
    max_components: int
    connectivity_type: int  # 4 or 8
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ConnectivityInfo):
            return NotImplemented
        return (
            self.min_components == other.min_components
            and self.max_components == other.max_components
            and self.connectivity_type == other.connectivity_type
        )
    
    def __hash__(self) -> int:
        return hash((self.min_components, self.max_components, self.connectivity_type))


@dataclass
class SymmetryFlags:
    """Symmetry flags for grids/objects"""
    horizontal: bool = False
    vertical: bool = False
    rotational_90: bool = False
    rotational_180: bool = False
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymmetryFlags):
            return NotImplemented
        return (
            self.horizontal == other.horizontal
            and self.vertical == other.vertical
            and self.rotational_90 == other.rotational_90
            and self.rotational_180 == other.rotational_180
        )
    
    def __hash__(self) -> int:
        return hash((self.horizontal, self.vertical, self.rotational_90, self.rotational_180))
    
    def any_symmetry(self) -> bool:
        """Check if any symmetry is present"""
        return self.horizontal or self.vertical or self.rotational_90 or self.rotational_180


@dataclass
class EClassSummary:
    """Summary properties for an equivalence class of programs"""
    eclass_id: int
    color_set: Set[int]
    connectivity: ConnectivityInfo
    symmetry: SymmetryFlags
    bbox_bounds: Optional[BoundingBox]
    object_count_range: Tuple[int, int]
    metadata: Dict[str, Any]
    
    def __init__(
        self,
        eclass_id: int,
        color_set: Optional[Set[int]] = None,
        connectivity: Optional[ConnectivityInfo] = None,
        symmetry: Optional[SymmetryFlags] = None,
        bbox_bounds: Optional[BoundingBox] = None,
        object_count_range: Optional[Tuple[int, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.eclass_id = eclass_id
        self.color_set = color_set or set()
        self.connectivity = connectivity or ConnectivityInfo(0, 0, 4)
        self.symmetry = symmetry or SymmetryFlags()
        self.bbox_bounds = bbox_bounds
        self.object_count_range = object_count_range or (0, 0)
        self.metadata = metadata or {}
    
    def is_compatible_with(self, other: EClassSummary) -> bool:
        """Check if two summaries are compatible (can be merged)"""
        # Color sets should overlap
        if self.color_set and other.color_set:
            if not self.color_set.intersection(other.color_set):
                return False
        
        # Connectivity ranges should overlap
        if self.connectivity.max_components < other.connectivity.min_components:
            return False
        if other.connectivity.max_components < self.connectivity.min_components:
            return False
        
        # Object count ranges should overlap
        if self.object_count_range[1] < other.object_count_range[0]:
            return False
        if other.object_count_range[1] < self.object_count_range[0]:
            return False
        
        return True
    
    def merge(self, other: EClassSummary) -> EClassSummary:
        """Merge two summaries into a more general one"""
        return EClassSummary(
            eclass_id=self.eclass_id,
            color_set=self.color_set.union(other.color_set),
            connectivity=ConnectivityInfo(
                min_components=min(self.connectivity.min_components, other.connectivity.min_components),
                max_components=max(self.connectivity.max_components, other.connectivity.max_components),
                connectivity_type=self.connectivity.connectivity_type,
            ),
            symmetry=SymmetryFlags(
                horizontal=self.symmetry.horizontal and other.symmetry.horizontal,
                vertical=self.symmetry.vertical and other.symmetry.vertical,
                rotational_90=self.symmetry.rotational_90 and other.symmetry.rotational_90,
                rotational_180=self.symmetry.rotational_180 and other.symmetry.rotational_180,
            ),
            bbox_bounds=self._merge_bbox(self.bbox_bounds, other.bbox_bounds),
            object_count_range=(
                min(self.object_count_range[0], other.object_count_range[0]),
                max(self.object_count_range[1], other.object_count_range[1]),
            ),
            metadata={**self.metadata, **other.metadata},
        )
    
    def _merge_bbox(
        self,
        bbox1: Optional[BoundingBox],
        bbox2: Optional[BoundingBox]
    ) -> Optional[BoundingBox]:
        """Merge two bounding boxes"""
        if bbox1 is None:
            return bbox2
        if bbox2 is None:
            return bbox1
        
        return BoundingBox(
            min_row=min(bbox1.min_row, bbox2.min_row),
            max_row=max(bbox1.max_row, bbox2.max_row),
            min_col=min(bbox1.min_col, bbox2.min_col),
            max_col=max(bbox1.max_col, bbox2.max_col),
        )
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EClassSummary):
            return NotImplemented
        return (
            self.eclass_id == other.eclass_id
            and self.color_set == other.color_set
            and self.connectivity == other.connectivity
            and self.symmetry == other.symmetry
            and self.bbox_bounds == other.bbox_bounds
            and self.object_count_range == other.object_count_range
        )
    
    def __hash__(self) -> int:
        return hash((
            self.eclass_id,
            frozenset(self.color_set),
            self.connectivity,
            self.symmetry,
            self.bbox_bounds,
            self.object_count_range,
        ))


class EClassAnalyzer:
    """Analyzer for extracting summary properties from e-classes"""
    
    def __init__(self):
        """Initialize the analyzer"""
        pass
    
    def analyze_eclass(
        self,
        programs: List[Program],
        eclass_id: int,
        grid_examples: Optional[List[Tuple[Any, Any]]] = None
    ) -> EClassSummary:
        """
        Analyze an equivalence class and extract summary properties.
        
        Args:
            programs: List of equivalent programs in the e-class
            eclass_id: Identifier for the e-class
            grid_examples: Optional list of (input_grid, output_grid) tuples for analysis
            
        Returns:
            EClassSummary with extracted properties
        """
        if not programs:
            return EClassSummary(eclass_id=eclass_id)
        
        # Extract color set from programs
        color_set = self.compute_color_set(programs)
        
        # Analyze connectivity (simplified without grid execution)
        connectivity = self._analyze_connectivity(programs)
        
        # Detect symmetry patterns
        symmetry = self.detect_symmetry(programs)
        
        # Estimate object count range
        object_count_range = self._estimate_object_count(programs)
        
        return EClassSummary(
            eclass_id=eclass_id,
            color_set=color_set,
            connectivity=connectivity,
            symmetry=symmetry,
            bbox_bounds=None,  # Would require grid execution
            object_count_range=object_count_range,
            metadata={"program_count": len(programs)},
        )
    
    def compute_color_set(self, programs: List[Program]) -> Set[int]:
        """
        Compute the set of colors involved in the programs.
        
        Extracts color arguments from stages that manipulate colors.
        """
        colors: Set[int] = set()
        
        for program in programs:
            for stage in program.stages:
                # Extract color arguments from common operators
                if stage.operator in {"paint_region", "fill_color", "replace_color", "flood_fill"}:
                    for arg in stage.arguments:
                        if isinstance(arg, int) and 0 <= arg <= 9:
                            colors.add(arg)
                
                # Handle region_where_colour
                if stage.operator == "region_where_colour" and stage.arguments:
                    color_arg = stage.arguments[0]
                    if isinstance(color_arg, int) and 0 <= color_arg <= 9:
                        colors.add(color_arg)
        
        return colors
    
    def compute_connectivity(self, programs: List[Program]) -> ConnectivityInfo:
        """
        Compute connectivity information from programs.
        
        Analyzes operators that affect connectivity.
        """
        return self._analyze_connectivity(programs)
    
    def detect_symmetry(self, programs: List[Program]) -> SymmetryFlags:
        """
        Detect symmetry patterns in programs.
        
        Looks for symmetry-related operators like reflect, rotate, transpose.
        """
        has_horizontal = False
        has_vertical = False
        has_rot_90 = False
        has_rot_180 = False
        
        for program in programs:
            for stage in program.stages:
                if stage.operator == "reflect":
                    if stage.arguments and stage.arguments[0] == "horizontal":
                        has_horizontal = True
                    elif stage.arguments and stage.arguments[0] == "vertical":
                        has_vertical = True
                
                elif stage.operator == "rotate":
                    if stage.arguments:
                        steps = stage.arguments[0]
                        if isinstance(steps, int):
                            if steps % 4 == 1 or steps % 4 == 3:
                                has_rot_90 = True
                            if steps % 4 == 2:
                                has_rot_180 = True
                
                elif stage.operator == "transpose":
                    # Transpose implies some form of symmetry
                    has_horizontal = True
                    has_vertical = True
        
        return SymmetryFlags(
            horizontal=has_horizontal,
            vertical=has_vertical,
            rotational_90=has_rot_90,
            rotational_180=has_rot_180,
        )
    
    def _analyze_connectivity(self, programs: List[Program]) -> ConnectivityInfo:
        """Analyze connectivity patterns in programs"""
        # Default connectivity analysis based on operators
        min_components = 1
        max_components = 100  # Conservative upper bound
        connectivity_type = 4  # Default to 4-connectivity
        
        for program in programs:
            for stage in program.stages:
                # Operators that might affect connectivity
                if stage.operator in {"detect_objects", "flood_fill", "connected_components"}:
                    # These operators work with connected components
                    if stage.arguments and len(stage.arguments) > 0:
                        conn_arg = stage.arguments[0]
                        if isinstance(conn_arg, int) and conn_arg in {4, 8}:
                            connectivity_type = conn_arg
        
        return ConnectivityInfo(
            min_components=min_components,
            max_components=max_components,
            connectivity_type=connectivity_type,
        )
    
    def _estimate_object_count(self, programs: List[Program]) -> Tuple[int, int]:
        """Estimate object count range from programs"""
        min_count = 0
        max_count = 100  # Conservative upper bound
        
        for program in programs:
            for stage in program.stages:
                # Operators that create or manipulate objects
                if stage.operator in {"detect_objects", "select_object"}:
                    # These suggest multiple objects
                    min_count = max(min_count, 1)
                    max_count = min(max_count, 50)
        
        return (min_count, max_count)


__all__ = [
    "BoundingBox",
    "ConnectivityInfo",
    "SymmetryFlags",
    "EClassSummary",
    "EClassAnalyzer",
]
