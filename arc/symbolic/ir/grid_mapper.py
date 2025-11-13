"""Grid to Object Graph mapping functionality."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from scipy import ndimage

from arc.symbolic.dsl.types import BoundingBox, Grid, Region
from arc.symbolic.ir.object_graph import ObjectGraph, ObjectNode


class GridToObjectGraphMapper:
    """Maps between Grid and ObjectGraph representations.
    
    This class provides bidirectional conversion between grid-based and
    object-based representations of ARC tasks.
    """
    
    def __init__(self):
        """Initialize the mapper."""
        pass
    
    def map_grid_to_objects(
        self,
        grid: Grid,
        connectivity: int = 4,
        min_size: int = 1
    ) -> ObjectGraph:
        """Convert a grid to an object graph using connected component analysis.
        
        Args:
            grid: The input grid to convert
            connectivity: Connectivity for component analysis (4 or 8)
            min_size: Minimum size for an object to be included
            
        Returns:
            ObjectGraph representation of the grid
        """
        # Detect background color
        background_color = grid.detect_background_colour()
        
        # Create a mask for non-background pixels
        foreground_mask = grid.data != background_color
        
        # Define connectivity structure
        if connectivity == 4:
            structure = ndimage.generate_binary_structure(2, 1)
        elif connectivity == 8:
            structure = ndimage.generate_binary_structure(2, 2)
        else:
            raise ValueError(f"Connectivity must be 4 or 8, got {connectivity}")
        
        # Find connected components for each color
        nodes: List[ObjectNode] = []
        node_id = 0
        
        # Get unique colors (excluding background)
        unique_colors = np.unique(grid.data[foreground_mask])
        
        for color in unique_colors:
            # Create mask for this color
            color_mask = grid.data == color
            
            # Label connected components
            labeled, num_features = ndimage.label(color_mask, structure=structure)
            
            # Extract each component as an object
            for component_id in range(1, num_features + 1):
                component_mask = labeled == component_id
                
                # Check minimum size
                area = np.sum(component_mask)
                if area < min_size:
                    continue
                
                # Create region
                region = Region(component_mask)
                
                # Compute bounding box
                bbox = region.bounding_box()
                if bbox is None:
                    continue
                
                # Create object node
                node = ObjectNode(
                    id=node_id,
                    region=region,
                    color=int(color),
                    bbox=bbox,
                    properties={
                        "area": area,
                        "connectivity": connectivity,
                    }
                )
                nodes.append(node)
                node_id += 1
        
        # Compute spatial relationships (edges)
        edges = self._compute_spatial_relationships(nodes)
        
        # Create object graph
        return ObjectGraph(
            nodes=nodes,
            edges=edges,
            background_color=background_color,
            canvas_shape=grid.shape,
            metadata={
                "connectivity": connectivity,
                "min_size": min_size,
                "num_objects": len(nodes),
            }
        )
    
    def map_objects_to_grid(
        self,
        object_graph: ObjectGraph
    ) -> Grid:
        """Reconstruct a grid from an object graph.
        
        Args:
            object_graph: The object graph to convert
            
        Returns:
            Grid representation reconstructed from the object graph
        """
        # Initialize grid with background color
        height, width = object_graph.canvas_shape
        grid_data = np.full((height, width), object_graph.background_color, dtype=np.int16)
        
        # Paint each object onto the grid
        for node in object_graph.nodes:
            # Get the region mask
            mask = node.region.mask
            
            # Ensure mask shape matches grid shape
            if mask.shape != (height, width):
                raise ValueError(
                    f"Object region shape {mask.shape} does not match "
                    f"canvas shape {(height, width)}"
                )
            
            # Paint the object color where the mask is True
            grid_data[mask] = node.color
        
        return Grid(grid_data)
    
    def _compute_spatial_relationships(
        self,
        nodes: List[ObjectNode]
    ) -> List[Tuple[int, int, str]]:
        """Compute spatial relationships between objects.
        
        Args:
            nodes: List of object nodes
            
        Returns:
            List of edges (src_id, dst_id, relation_type)
        """
        edges: List[Tuple[int, int, str]] = []
        
        # For each pair of nodes, check for spatial relationships
        for i, node_a in enumerate(nodes):
            for node_b in nodes[i + 1:]:
                # Check if objects are adjacent
                if self._are_adjacent(node_a, node_b):
                    edges.append((node_a.id, node_b.id, "adjacent"))
                
                # Check if one contains the other
                containment = self._check_containment(node_a, node_b)
                if containment == "a_contains_b":
                    edges.append((node_a.id, node_b.id, "contains"))
                elif containment == "b_contains_a":
                    edges.append((node_b.id, node_a.id, "contains"))
                
                # Check for alignment
                alignment = self._check_alignment(node_a, node_b)
                if alignment:
                    edges.append((node_a.id, node_b.id, alignment))
        
        return edges
    
    def _are_adjacent(self, node_a: ObjectNode, node_b: ObjectNode) -> bool:
        """Check if two objects are spatially adjacent.
        
        Args:
            node_a: First object node
            node_b: Second object node
            
        Returns:
            True if objects are adjacent, False otherwise
        """
        # Dilate one region and check for overlap with the other
        dilated_a = ndimage.binary_dilation(node_a.region.mask)
        overlap = np.logical_and(dilated_a, node_b.region.mask)
        return np.any(overlap)
    
    def _check_containment(
        self,
        node_a: ObjectNode,
        node_b: ObjectNode
    ) -> Optional[str]:
        """Check if one object contains the other.
        
        Args:
            node_a: First object node
            node_b: Second object node
            
        Returns:
            "a_contains_b", "b_contains_a", or None
        """
        # Check if a's bbox contains b's bbox
        if (node_a.bbox.top <= node_b.bbox.top and
            node_a.bbox.left <= node_b.bbox.left and
            node_a.bbox.bottom >= node_b.bbox.bottom and
            node_a.bbox.right >= node_b.bbox.right):
            # Check if all of b's pixels are within a's region
            overlap = np.logical_and(node_a.region.mask, node_b.region.mask)
            if np.sum(overlap) == node_b.area:
                return "a_contains_b"
        
        # Check if b's bbox contains a's bbox
        if (node_b.bbox.top <= node_a.bbox.top and
            node_b.bbox.left <= node_a.bbox.left and
            node_b.bbox.bottom >= node_a.bbox.bottom and
            node_b.bbox.right >= node_a.bbox.right):
            # Check if all of a's pixels are within b's region
            overlap = np.logical_and(node_a.region.mask, node_b.region.mask)
            if np.sum(overlap) == node_a.area:
                return "b_contains_a"
        
        return None
    
    def _check_alignment(
        self,
        node_a: ObjectNode,
        node_b: ObjectNode
    ) -> Optional[str]:
        """Check if two objects are aligned horizontally or vertically.
        
        Args:
            node_a: First object node
            node_b: Second object node
            
        Returns:
            "aligned_horizontal", "aligned_vertical", or None
        """
        # Check horizontal alignment (same row range)
        if (abs(node_a.bbox.top - node_b.bbox.top) <= 1 or
            abs(node_a.bbox.bottom - node_b.bbox.bottom) <= 1):
            return "aligned_horizontal"
        
        # Check vertical alignment (same column range)
        if (abs(node_a.bbox.left - node_b.bbox.left) <= 1 or
            abs(node_a.bbox.right - node_b.bbox.right) <= 1):
            return "aligned_vertical"
        
        return None
