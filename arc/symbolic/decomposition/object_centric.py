"""Object-centric decomposition for symbolic synthesis.

This module implements object-centric decomposition strategies that break down
complex grid transformations into local object transformations and composition rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from arc.symbolic.dsl.types import Grid, Program, Stage
from arc.symbolic.ir.object_graph import ObjectGraph, ObjectNode


@dataclass
class LocalTransformation:
    """Represents a local transformation applied to a single object.
    
    Attributes:
        input_object: The input object node
        output_object: The output object node
        transformation: The DSL program that transforms input to output
        confidence: Confidence score for this transformation (0.0 to 1.0)
        metadata: Additional metadata about the transformation
    """
    
    input_object: ObjectNode
    output_object: ObjectNode
    transformation: Program
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize LocalTransformation to dictionary.
        
        Returns:
            Dictionary representation of the local transformation
        """
        return {
            "input_object": self.input_object.to_dict(),
            "output_object": self.output_object.to_dict(),
            "transformation": {
                "stages": [
                    {"operator": stage.operator, "arguments": list(stage.arguments)}
                    for stage in self.transformation.stages
                ]
            },
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """Serialize LocalTransformation to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)


class ObjectCentricDecomposer:
    """Decomposes grid transformations into object-centric local transformations.
    
    This class implements object-centric decomposition strategies that:
    1. Match objects between input and output graphs
    2. Synthesize local transformations for individual objects
    3. Generate composition rules to combine local transformations
    
    Requirements: 9.1, 9.2
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the object-centric decomposer.
        
        Args:
            config: Configuration dictionary with decomposition parameters
        """
        self.config = config or {}
        self.matching_threshold = self.config.get("matching_threshold", 0.7)
        self.max_local_depth = self.config.get("max_local_depth", 5)
        self.synthesis_timeout = self.config.get("synthesis_timeout", 5.0)
        
    def decompose_task(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> List[LocalTransformation]:
        """Decompose a task into local object transformations.
        
        This method:
        1. Matches objects between input and output graphs
        2. For each matched pair, synthesizes a local transformation
        3. Returns a list of local transformations
        
        Args:
            input_graph: The input object graph
            output_graph: The output object graph
            
        Returns:
            List of local transformations for matched object pairs
            
        Requirements: 9.1
        """
        # Match objects between input and output
        matches = self._match_objects(input_graph, output_graph)
        
        # Synthesize local transformations for each match
        local_transformations = []
        for input_obj, output_obj, confidence in matches:
            transformation = self.synthesize_local_transformation(
                input_obj, output_obj
            )
            if transformation:
                local_transformations.append(
                    LocalTransformation(
                        input_object=input_obj,
                        output_object=output_obj,
                        transformation=transformation,
                        confidence=confidence,
                        metadata={
                            "match_confidence": confidence,
                            "input_id": input_obj.id,
                            "output_id": output_obj.id,
                        }
                    )
                )
        
        return local_transformations
    
    def synthesize_local_transformation(
        self,
        input_object: ObjectNode,
        output_object: ObjectNode
    ) -> Optional[Program]:
        """Synthesize a transformation for a single object.
        
        This method generates a DSL program that transforms the input object
        to the output object. It uses heuristics based on:
        - Color changes
        - Size changes
        - Position changes
        - Shape changes
        
        Args:
            input_object: The input object node
            output_object: The output object node
            
        Returns:
            A Program that transforms input to output, or None if synthesis fails
            
        Requirements: 9.1
        """
        stages = []
        
        # Detect color transformation
        if input_object.color != output_object.color:
            stages.append(Stage(
                operator="paint_region",
                arguments=(output_object.color,)
            ))
        
        # Detect size transformation
        if input_object.area != output_object.area:
            scale_factor = output_object.area / input_object.area
            if abs(scale_factor - 2.0) < 0.1:
                stages.append(Stage(operator="scale_up", arguments=(2,)))
            elif abs(scale_factor - 0.5) < 0.1:
                stages.append(Stage(operator="scale_down", arguments=(2,)))
        
        # Detect rotation
        if self._detect_rotation(input_object, output_object):
            rotation_angle = self._compute_rotation_angle(input_object, output_object)
            if rotation_angle:
                stages.append(Stage(
                    operator="rotate",
                    arguments=(rotation_angle,)
                ))
        
        # Detect reflection
        if self._detect_reflection(input_object, output_object):
            axis = self._compute_reflection_axis(input_object, output_object)
            if axis:
                stages.append(Stage(
                    operator="reflect",
                    arguments=(axis,)
                ))
        
        # If no transformations detected, return None
        if not stages:
            return None
        
        return Program(stages=tuple(stages))
    
    def synthesize_composition_rule(
        self,
        local_transformations: List[LocalTransformation]
    ) -> Program:
        """Synthesize a composition rule from local transformations.
        
        This method generates a DSL program that composes multiple local
        transformations into a single coherent transformation. It handles:
        - Sequential composition
        - Parallel composition
        - Spatial alignment
        
        Args:
            local_transformations: List of local transformations to compose
            
        Returns:
            A Program that composes all local transformations
            
        Requirements: 9.2
        """
        if not local_transformations:
            return Program(stages=tuple())
        
        # For now, implement simple sequential composition
        # More sophisticated composition strategies can be added later
        all_stages = []
        
        for lt in local_transformations:
            # Add object selection stage
            all_stages.append(Stage(
                operator="select_object",
                arguments=(lt.input_object.id,)
            ))
            
            # Add transformation stages
            all_stages.extend(lt.transformation.stages)
        
        return Program(stages=tuple(all_stages))
    
    def _match_objects(
        self,
        input_graph: ObjectGraph,
        output_graph: ObjectGraph
    ) -> List[Tuple[ObjectNode, ObjectNode, float]]:
        """Match objects between input and output graphs.
        
        Uses heuristics based on:
        - Spatial proximity
        - Color similarity
        - Size similarity
        - Shape similarity
        
        Args:
            input_graph: The input object graph
            output_graph: The output object graph
            
        Returns:
            List of (input_obj, output_obj, confidence) tuples
        """
        matches = []
        used_output_ids = set()
        
        for input_obj in input_graph.nodes:
            best_match = None
            best_score = 0.0
            
            for output_obj in output_graph.nodes:
                if output_obj.id in used_output_ids:
                    continue
                
                score = self._compute_match_score(input_obj, output_obj)
                if score > best_score and score >= self.matching_threshold:
                    best_score = score
                    best_match = output_obj
            
            if best_match:
                matches.append((input_obj, best_match, best_score))
                used_output_ids.add(best_match.id)
        
        return matches
    
    def _compute_match_score(
        self,
        obj1: ObjectNode,
        obj2: ObjectNode
    ) -> float:
        """Compute a matching score between two objects.
        
        Args:
            obj1: First object node
            obj2: Second object node
            
        Returns:
            Matching score between 0.0 and 1.0
        """
        score = 0.0
        
        # Color similarity (weight: 0.3)
        if obj1.color == obj2.color:
            score += 0.3
        
        # Size similarity (weight: 0.3)
        size_ratio = min(obj1.area, obj2.area) / max(obj1.area, obj2.area)
        score += 0.3 * size_ratio
        
        # Spatial proximity (weight: 0.4)
        # Compute center of mass for both objects
        center1 = self._compute_center(obj1)
        center2 = self._compute_center(obj2)
        distance = ((center1[0] - center2[0]) ** 2 + (center1[1] - center2[1]) ** 2) ** 0.5
        max_distance = (obj1.bbox.height ** 2 + obj1.bbox.width ** 2) ** 0.5
        proximity = max(0.0, 1.0 - distance / max(max_distance, 1.0))
        score += 0.4 * proximity
        
        return score
    
    def _compute_center(self, obj: ObjectNode) -> Tuple[float, float]:
        """Compute the center of mass of an object.
        
        Args:
            obj: Object node
            
        Returns:
            (row, col) coordinates of the center
        """
        indices = obj.region.to_indices()
        if not indices:
            return (0.0, 0.0)
        
        row_sum = sum(r for r, c in indices)
        col_sum = sum(c for r, c in indices)
        count = len(indices)
        
        return (row_sum / count, col_sum / count)
    
    def _detect_rotation(self, obj1: ObjectNode, obj2: ObjectNode) -> bool:
        """Detect if obj2 is a rotation of obj1.
        
        Args:
            obj1: First object node
            obj2: Second object node
            
        Returns:
            True if rotation is detected
        """
        # Simple heuristic: check if dimensions are swapped
        return (obj1.width == obj2.height and obj1.height == obj2.width)
    
    def _compute_rotation_angle(
        self,
        obj1: ObjectNode,
        obj2: ObjectNode
    ) -> Optional[int]:
        """Compute the rotation angle between two objects.
        
        Args:
            obj1: First object node
            obj2: Second object node
            
        Returns:
            Rotation angle in degrees (90, 180, 270) or None
        """
        if obj1.width == obj2.height and obj1.height == obj2.width:
            return 90
        return None
    
    def _detect_reflection(self, obj1: ObjectNode, obj2: ObjectNode) -> bool:
        """Detect if obj2 is a reflection of obj1.
        
        Args:
            obj1: First object node
            obj2: Second object node
            
        Returns:
            True if reflection is detected
        """
        # Simple heuristic: check if dimensions are the same
        return (obj1.width == obj2.width and obj1.height == obj2.height)
    
    def _compute_reflection_axis(
        self,
        obj1: ObjectNode,
        obj2: ObjectNode
    ) -> Optional[str]:
        """Compute the reflection axis between two objects.
        
        Args:
            obj1: First object node
            obj2: Second object node
            
        Returns:
            Reflection axis ("horizontal" or "vertical") or None
        """
        # For now, default to horizontal
        # More sophisticated detection can be added later
        return "horizontal"
