"""Symmetry detection for grids and object graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid, Program
from arc.symbolic.ir.object_graph import ObjectGraph, ObjectNode


@dataclass(frozen=True)
class SymmetryGroup:
    """Represents a symmetry group with generators.
    
    Attributes:
        generators: List of transformation names that generate the group
        order: The order (size) of the group
        type: Type of symmetry group (e.g., "reflection", "rotation", "dihedral")
    """
    
    generators: Tuple[str, ...]
    order: int
    type: str
    
    def __repr__(self) -> str:
        return f"SymmetryGroup(type={self.type}, order={self.order}, generators={self.generators})"


@dataclass(frozen=True)
class Isomorphism:
    """Represents an isomorphism between two object graphs.
    
    Attributes:
        node_mapping: Maps node IDs from graph A to graph B
        edge_mapping: Maps edges from graph A to graph B
        confidence: Confidence score of the isomorphism (0.0 to 1.0)
    """
    
    node_mapping: Dict[int, int]
    edge_mapping: Dict[Tuple[int, int], Tuple[int, int]]
    confidence: float = 1.0
    
    def __repr__(self) -> str:
        return f"Isomorphism(nodes={len(self.node_mapping)}, edges={len(self.edge_mapping)}, confidence={self.confidence:.2f})"


class SymmetryDetector:
    """Detects symmetries in grids and object graphs."""
    
    def __init__(self):
        """Initialize the SymmetryDetector."""
        pass
    
    def detect_grid_symmetry(self, grid: Grid) -> SymmetryGroup:
        """Detect symmetries in a grid.
        
        Args:
            grid: Grid to analyze
            
        Returns:
            SymmetryGroup describing the detected symmetries
        """
        generators = []
        
        # Check horizontal reflection
        if self._has_horizontal_reflection(grid):
            generators.append("reflect_horizontal")
        
        # Check vertical reflection
        if self._has_vertical_reflection(grid):
            generators.append("reflect_vertical")
        
        # Check 90-degree rotation
        has_rot90 = self._has_rotation_90(grid)
        if has_rot90:
            generators.append("rotate_90")
        
        # Check 180-degree rotation
        if not has_rot90 and self._has_rotation_180(grid):
            generators.append("rotate_180")
        
        # Determine group type and order
        if not generators:
            return SymmetryGroup(generators=(), order=1, type="trivial")
        
        # Compute group order based on generators
        order = self._compute_group_order(generators)
        group_type = self._determine_group_type(generators)
        
        return SymmetryGroup(
            generators=tuple(generators),
            order=order,
            type=group_type,
        )
    
    def detect_object_graph_isomorphism(
        self,
        graph_a: ObjectGraph,
        graph_b: ObjectGraph
    ) -> Optional[Isomorphism]:
        """Detect isomorphism between two object graphs.
        
        Args:
            graph_a: First object graph
            graph_b: Second object graph
            
        Returns:
            Isomorphism if found, None otherwise
        """
        # Quick checks
        if graph_a.num_nodes != graph_b.num_nodes:
            return None
        if graph_a.num_edges != graph_b.num_edges:
            return None
        
        # Try to find a node mapping
        node_mapping = self._find_node_mapping(graph_a, graph_b)
        if node_mapping is None:
            return None
        
        # Verify edge mapping
        edge_mapping = self._compute_edge_mapping(graph_a, graph_b, node_mapping)
        if edge_mapping is None:
            return None
        
        # Compute confidence based on property matching
        confidence = self._compute_isomorphism_confidence(
            graph_a, graph_b, node_mapping
        )
        
        return Isomorphism(
            node_mapping=node_mapping,
            edge_mapping=edge_mapping,
            confidence=confidence,
        )
    
    def compute_quotient_representatives(
        self,
        programs: List[Program],
        symmetry_group: SymmetryGroup
    ) -> List[Program]:
        """Compute representative programs from each symmetry equivalence class.
        
        Args:
            programs: List of programs to analyze
            symmetry_group: Symmetry group to use for quotient
            
        Returns:
            List of representative programs (one per equivalence class)
        """
        if symmetry_group.order == 1:
            # No symmetry, all programs are representatives
            return programs
        
        # Group programs by canonical form
        canonical_map: Dict[str, Program] = {}
        
        for program in programs:
            # Compute canonical form (simplest representation)
            canonical_form = self._compute_canonical_form(program, symmetry_group)
            canonical_key = self._program_to_key(canonical_form)
            
            if canonical_key not in canonical_map:
                canonical_map[canonical_key] = canonical_form
        
        return list(canonical_map.values())
    
    def _has_horizontal_reflection(self, grid: Grid) -> bool:
        """Check if grid has horizontal reflection symmetry."""
        flipped = np.flipud(grid.data)
        return np.array_equal(grid.data, flipped)
    
    def _has_vertical_reflection(self, grid: Grid) -> bool:
        """Check if grid has vertical reflection symmetry."""
        flipped = np.fliplr(grid.data)
        return np.array_equal(grid.data, flipped)
    
    def _has_rotation_90(self, grid: Grid) -> bool:
        """Check if grid has 90-degree rotation symmetry."""
        if grid.shape[0] != grid.shape[1]:
            return False  # Must be square
        rotated = np.rot90(grid.data, k=1)
        return np.array_equal(grid.data, rotated)
    
    def _has_rotation_180(self, grid: Grid) -> bool:
        """Check if grid has 180-degree rotation symmetry."""
        rotated = np.rot90(grid.data, k=2)
        return np.array_equal(grid.data, rotated)
    
    def _compute_group_order(self, generators: List[str]) -> int:
        """Compute the order of the symmetry group from generators."""
        # Simplified computation based on common cases
        if "rotate_90" in generators:
            # Has 4-fold rotation
            if "reflect_horizontal" in generators or "reflect_vertical" in generators:
                return 8  # Dihedral group D4
            return 4  # Cyclic group C4
        elif "rotate_180" in generators:
            # Has 2-fold rotation
            if "reflect_horizontal" in generators and "reflect_vertical" in generators:
                return 4  # Klein four-group
            elif "reflect_horizontal" in generators or "reflect_vertical" in generators:
                return 4  # Dihedral group D2
            return 2  # Cyclic group C2
        elif "reflect_horizontal" in generators and "reflect_vertical" in generators:
            return 4  # Two reflections generate 180 rotation
        elif "reflect_horizontal" in generators or "reflect_vertical" in generators:
            return 2  # Single reflection
        return 1  # Trivial group
    
    def _determine_group_type(self, generators: List[str]) -> str:
        """Determine the type of symmetry group."""
        if "rotate_90" in generators:
            if "reflect_horizontal" in generators or "reflect_vertical" in generators:
                return "dihedral_4"
            return "cyclic_4"
        elif "rotate_180" in generators:
            if "reflect_horizontal" in generators or "reflect_vertical" in generators:
                return "dihedral_2"
            return "cyclic_2"
        elif "reflect_horizontal" in generators and "reflect_vertical" in generators:
            return "klein_four"
        elif "reflect_horizontal" in generators:
            return "reflection_horizontal"
        elif "reflect_vertical" in generators:
            return "reflection_vertical"
        return "trivial"
    
    def _find_node_mapping(
        self,
        graph_a: ObjectGraph,
        graph_b: ObjectGraph
    ) -> Optional[Dict[int, int]]:
        """Find a node mapping between two graphs using greedy matching.
        
        This is a simplified version. A full implementation would use
        graph isomorphism algorithms like VF2.
        """
        # Create candidate mappings based on node properties
        candidates: Dict[int, List[int]] = {}
        
        for node_a in graph_a.nodes:
            candidates[node_a.id] = []
            for node_b in graph_b.nodes:
                if self._nodes_compatible(node_a, node_b):
                    candidates[node_a.id].append(node_b.id)
        
        # Try to find a consistent mapping using backtracking
        mapping: Dict[int, int] = {}
        used_b_nodes = set()
        
        def backtrack(a_idx: int) -> bool:
            if a_idx >= len(graph_a.nodes):
                return True  # All nodes mapped
            
            node_a = graph_a.nodes[a_idx]
            for node_b_id in candidates[node_a.id]:
                if node_b_id in used_b_nodes:
                    continue
                
                # Try this mapping
                mapping[node_a.id] = node_b_id
                used_b_nodes.add(node_b_id)
                
                # Check if consistent with edges
                if self._mapping_consistent_with_edges(graph_a, graph_b, mapping):
                    if backtrack(a_idx + 1):
                        return True
                
                # Backtrack
                del mapping[node_a.id]
                used_b_nodes.remove(node_b_id)
            
            return False
        
        if backtrack(0):
            return mapping
        return None
    
    def _nodes_compatible(self, node_a: ObjectNode, node_b: ObjectNode) -> bool:
        """Check if two nodes are compatible for mapping."""
        # Check basic properties
        if node_a.color != node_b.color:
            return False
        if node_a.area != node_b.area:
            return False
        if node_a.width != node_b.width or node_a.height != node_b.height:
            return False
        return True
    
    def _mapping_consistent_with_edges(
        self,
        graph_a: ObjectGraph,
        graph_b: ObjectGraph,
        partial_mapping: Dict[int, int]
    ) -> bool:
        """Check if a partial mapping is consistent with graph edges."""
        for src_a, dst_a, rel_a in graph_a.edges:
            if src_a in partial_mapping and dst_a in partial_mapping:
                src_b = partial_mapping[src_a]
                dst_b = partial_mapping[dst_a]
                
                # Check if corresponding edge exists in graph_b
                edge_found = False
                for src_b2, dst_b2, rel_b in graph_b.edges:
                    if (src_b2 == src_b and dst_b2 == dst_b and rel_a == rel_b):
                        edge_found = True
                        break
                    if (src_b2 == dst_b and dst_b2 == src_b and rel_a == rel_b):
                        # Undirected edge
                        edge_found = True
                        break
                
                if not edge_found:
                    return False
        
        return True
    
    def _compute_edge_mapping(
        self,
        graph_a: ObjectGraph,
        graph_b: ObjectGraph,
        node_mapping: Dict[int, int]
    ) -> Optional[Dict[Tuple[int, int], Tuple[int, int]]]:
        """Compute edge mapping from node mapping."""
        edge_mapping = {}
        
        for src_a, dst_a, rel_a in graph_a.edges:
            src_b = node_mapping[src_a]
            dst_b = node_mapping[dst_a]
            
            # Find corresponding edge in graph_b
            found = False
            for src_b2, dst_b2, rel_b in graph_b.edges:
                if (src_b2 == src_b and dst_b2 == dst_b and rel_a == rel_b):
                    edge_mapping[(src_a, dst_a)] = (src_b2, dst_b2)
                    found = True
                    break
            
            if not found:
                return None
        
        return edge_mapping
    
    def _compute_isomorphism_confidence(
        self,
        graph_a: ObjectGraph,
        graph_b: ObjectGraph,
        node_mapping: Dict[int, int]
    ) -> float:
        """Compute confidence score for an isomorphism."""
        if not node_mapping:
            return 0.0
        
        # Start with perfect confidence
        confidence = 1.0
        
        # Check property matching for each node pair
        total_checks = 0
        matching_checks = 0
        
        for node_a_id, node_b_id in node_mapping.items():
            node_a = graph_a.get_node_by_id(node_a_id)
            node_b = graph_b.get_node_by_id(node_b_id)
            
            if node_a and node_b:
                # Check color
                total_checks += 1
                if node_a.color == node_b.color:
                    matching_checks += 1
                
                # Check area
                total_checks += 1
                if node_a.area == node_b.area:
                    matching_checks += 1
                
                # Check dimensions
                total_checks += 1
                if node_a.width == node_b.width and node_a.height == node_b.height:
                    matching_checks += 1
        
        if total_checks > 0:
            confidence = matching_checks / total_checks
        
        return confidence
    
    def _compute_canonical_form(
        self,
        program: Program,
        symmetry_group: SymmetryGroup
    ) -> Program:
        """Compute canonical form of a program under symmetry group.
        
        For now, just return the program as-is. A full implementation
        would apply symmetry transformations and choose the lexicographically
        smallest representation.
        """
        # Simplified: return the program unchanged
        # A full implementation would generate all symmetric variants
        # and choose the canonical one
        return program
    
    def _program_to_key(self, program: Program) -> str:
        """Convert program to a string key for deduplication."""
        # Create a string representation of the program
        stage_strs = []
        for stage in program.stages:
            args_str = ",".join(str(arg) for arg in stage.arguments)
            stage_strs.append(f"{stage.operator}({args_str})")
        return "|".join(stage_strs)
