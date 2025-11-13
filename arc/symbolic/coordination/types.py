"""Data structures for module coordination.

This module defines the core data structures used for communication
between the symbolic solver and other modules (TTT, LLM).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from arc.symbolic.dsl.types import Stage


@dataclass
class Invariant:
    """Represents an invariant constraint from TTT or other modules.
    
    Invariants are properties that should hold for valid programs.
    They can be used as hard or soft constraints during synthesis.
    
    Attributes:
        type: Type of invariant (e.g., "color_conservation", "object_count", "topology")
        constraint: The actual constraint specification
        confidence: Confidence score (0.0 to 1.0)
        source: Source module that generated this invariant (e.g., "ttt", "symbolic", "llm")
    """
    
    type: str
    constraint: Any
    confidence: float
    source: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize Invariant to dictionary.
        
        Returns:
            Dictionary representation of the invariant
        """
        return {
            "type": self.type,
            "constraint": self._serialize_constraint(self.constraint),
            "confidence": self.confidence,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Invariant:
        """Deserialize Invariant from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed Invariant
        """
        return cls(
            type=data["type"],
            constraint=data["constraint"],
            confidence=data["confidence"],
            source=data["source"],
        )
    
    def to_json(self) -> str:
        """Serialize Invariant to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> Invariant:
        """Deserialize Invariant from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            Reconstructed Invariant
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def validate(self) -> bool:
        """Validate the invariant structure.
        
        Returns:
            True if invariant is valid, False otherwise
        """
        # Check confidence is in valid range
        if not (0.0 <= self.confidence <= 1.0):
            return False
        
        # Check type is not empty
        if not self.type:
            return False
        
        # Check source is not empty
        if not self.source:
            return False
        
        return True
    
    def _serialize_constraint(self, constraint: Any) -> Any:
        """Serialize constraint to JSON-compatible format.
        
        Args:
            constraint: The constraint to serialize
            
        Returns:
            JSON-compatible representation
        """
        if isinstance(constraint, dict):
            return constraint
        elif isinstance(constraint, (list, tuple)):
            return list(constraint)
        elif isinstance(constraint, (str, int, float, bool, type(None))):
            return constraint
        else:
            # For complex objects, convert to string
            return str(constraint)


@dataclass
class Relation:
    """Represents a spatial or semantic relation between objects.
    
    Relations describe how objects in a grid are related to each other.
    They can be used to guide synthesis or as constraints.
    
    Attributes:
        relation_type: Type of relation (e.g., "spatial", "color", "size")
        objects: List of object IDs involved in this relation
        parameters: Additional parameters for the relation
        confidence: Confidence score (0.0 to 1.0)
    """
    
    relation_type: str
    objects: List[int]
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize Relation to dictionary.
        
        Returns:
            Dictionary representation of the relation
        """
        return {
            "relation_type": self.relation_type,
            "objects": self.objects,
            "parameters": self.parameters,
            "confidence": self.confidence,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Relation:
        """Deserialize Relation from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed Relation
        """
        return cls(
            relation_type=data["relation_type"],
            objects=data["objects"],
            parameters=data.get("parameters", {}),
            confidence=data.get("confidence", 1.0),
        )
    
    def to_json(self) -> str:
        """Serialize Relation to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> Relation:
        """Deserialize Relation from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            Reconstructed Relation
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def validate(self) -> bool:
        """Validate the relation structure.
        
        Returns:
            True if relation is valid, False otherwise
        """
        # Check confidence is in valid range
        if not (0.0 <= self.confidence <= 1.0):
            return False
        
        # Check relation_type is not empty
        if not self.relation_type:
            return False
        
        # Check objects list is not empty
        if not self.objects:
            return False
        
        return True


@dataclass
class DSLMacro:
    """Represents a high-level DSL macro from LLM module.
    
    DSL macros are reusable program fragments that can be expanded
    into concrete DSL stages during synthesis.
    
    Attributes:
        name: Name of the macro
        parameters: List of parameter names
        body: List of stages that make up the macro body
        documentation: Human-readable description of the macro
        confidence: Confidence score (0.0 to 1.0)
    """
    
    name: str
    parameters: List[str]
    body: List[Stage]
    documentation: str = ""
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize DSLMacro to dictionary.
        
        Returns:
            Dictionary representation of the macro
        """
        return {
            "name": self.name,
            "parameters": self.parameters,
            "body": [
                {
                    "operator": stage.operator,
                    "arguments": [str(arg) for arg in stage.arguments]
                }
                for stage in self.body
            ],
            "documentation": self.documentation,
            "confidence": self.confidence,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DSLMacro:
        """Deserialize DSLMacro from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed DSLMacro
        """
        body = []
        for stage_data in data["body"]:
            # Simplified reconstruction - in practice, arguments need proper parsing
            body.append(Stage(
                operator=stage_data["operator"],
                arguments=tuple(stage_data["arguments"])
            ))
        
        return cls(
            name=data["name"],
            parameters=data["parameters"],
            body=body,
            documentation=data.get("documentation", ""),
            confidence=data.get("confidence", 1.0),
        )
    
    def to_json(self) -> str:
        """Serialize DSLMacro to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> DSLMacro:
        """Deserialize DSLMacro from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            Reconstructed DSLMacro
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def validate(self) -> bool:
        """Validate the macro structure.
        
        Returns:
            True if macro is valid, False otherwise
        """
        # Check confidence is in valid range
        if not (0.0 <= self.confidence <= 1.0):
            return False
        
        # Check name is not empty
        if not self.name:
            return False
        
        # Check body is not empty
        if not self.body:
            return False
        
        # Check all parameters are strings
        if not all(isinstance(p, str) for p in self.parameters):
            return False
        
        return True
    
    def expand(self, argument_values: Dict[str, Any]) -> List[Stage]:
        """Expand the macro with concrete argument values.
        
        Args:
            argument_values: Dictionary mapping parameter names to values
            
        Returns:
            List of expanded stages with parameters substituted
        """
        # Check all required parameters are provided
        for param in self.parameters:
            if param not in argument_values:
                raise ValueError(f"Missing required parameter: {param}")
        
        # For now, return body as-is
        # In a full implementation, you would substitute parameters in the body
        return self.body.copy()
