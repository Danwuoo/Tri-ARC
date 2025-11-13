"""Object graph data structures for IR layer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from arc.symbolic.dsl.types import BoundingBox, Region


@dataclass
class ObjectNode:
    """Represents a single object in the grid as a node in the object graph.
    
    Attributes:
        id: Unique identifier for this object node
        region: The spatial region occupied by this object
        color: The color value of this object
        bbox: Bounding box of the object
        properties: Additional properties (symmetry, connectivity, etc.)
    """
    
    id: int
    region: Region
    color: int
    bbox: BoundingBox
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize ObjectNode to dictionary.
        
        Returns:
            Dictionary representation of the object node
        """
        return {
            "id": self.id,
            "region_indices": self.region.to_indices(),
            "color": self.color,
            "bbox": {
                "top": self.bbox.top,
                "left": self.bbox.left,
                "bottom": self.bbox.bottom,
                "right": self.bbox.right,
            },
            "properties": self.properties,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], shape: Tuple[int, int]) -> ObjectNode:
        """Deserialize ObjectNode from dictionary.
        
        Args:
            data: Dictionary representation
            shape: Grid shape for reconstructing the region
            
        Returns:
            Reconstructed ObjectNode
        """
        region = Region.from_coordinates(shape, data["region_indices"])
        bbox_data = data["bbox"]
        bbox = BoundingBox(
            top=bbox_data["top"],
            left=bbox_data["left"],
            bottom=bbox_data["bottom"],
            right=bbox_data["right"],
        )
        return cls(
            id=data["id"],
            region=region,
            color=data["color"],
            bbox=bbox,
            properties=data.get("properties", {}),
        )
    
    @property
    def area(self) -> int:
        """Get the area of this object."""
        return self.region.area
    
    @property
    def width(self) -> int:
        """Get the width of this object."""
        return self.bbox.width
    
    @property
    def height(self) -> int:
        """Get the height of this object."""
        return self.bbox.height


@dataclass
class ObjectGraph:
    """Represents a grid as a graph of objects with spatial relationships.
    
    Attributes:
        nodes: List of object nodes in the graph
        edges: List of edges representing relationships between objects
               Each edge is (src_id, dst_id, relation_type)
        background_color: The background color of the grid
        canvas_shape: The shape (height, width) of the original grid
        metadata: Additional metadata about the graph
    """
    
    nodes: List[ObjectNode]
    edges: List[Tuple[int, int, str]] = field(default_factory=list)
    background_color: int = 0
    canvas_shape: Tuple[int, int] = (0, 0)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize ObjectGraph to dictionary.
        
        Returns:
            Dictionary representation of the object graph
        """
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [
                {"src": src, "dst": dst, "relation": rel}
                for src, dst, rel in self.edges
            ],
            "background_color": self.background_color,
            "canvas_shape": list(self.canvas_shape),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ObjectGraph:
        """Deserialize ObjectGraph from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed ObjectGraph
        """
        canvas_shape = tuple(data["canvas_shape"])
        nodes = [
            ObjectNode.from_dict(node_data, canvas_shape)
            for node_data in data["nodes"]
        ]
        edges = [
            (edge["src"], edge["dst"], edge["relation"])
            for edge in data["edges"]
        ]
        return cls(
            nodes=nodes,
            edges=edges,
            background_color=data["background_color"],
            canvas_shape=canvas_shape,
            metadata=data.get("metadata", {}),
        )
    
    def to_json(self) -> str:
        """Serialize ObjectGraph to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> ObjectGraph:
        """Deserialize ObjectGraph from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            Reconstructed ObjectGraph
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def get_node_by_id(self, node_id: int) -> Optional[ObjectNode]:
        """Get a node by its ID.
        
        Args:
            node_id: The ID of the node to retrieve
            
        Returns:
            The ObjectNode if found, None otherwise
        """
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_neighbors(self, node_id: int) -> List[Tuple[ObjectNode, str]]:
        """Get all neighbors of a node with their relationship types.
        
        Args:
            node_id: The ID of the node
            
        Returns:
            List of (neighbor_node, relation_type) tuples
        """
        neighbors = []
        for src, dst, relation in self.edges:
            if src == node_id:
                neighbor = self.get_node_by_id(dst)
                if neighbor:
                    neighbors.append((neighbor, relation))
            elif dst == node_id:
                neighbor = self.get_node_by_id(src)
                if neighbor:
                    neighbors.append((neighbor, relation))
        return neighbors
    
    @property
    def num_nodes(self) -> int:
        """Get the number of nodes in the graph."""
        return len(self.nodes)
    
    @property
    def num_edges(self) -> int:
        """Get the number of edges in the graph."""
        return len(self.edges)
