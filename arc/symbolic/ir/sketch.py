"""Program sketch data structures for sketch-guided synthesis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

from arc.symbolic.dsl.types import Stage


@dataclass
class Hole:
    """Represents a hole (unknown value) in a program sketch.
    
    A hole is a placeholder that needs to be filled during synthesis.
    It has a type, a domain of possible values, and constraints.
    
    Attributes:
        id: Unique identifier for this hole
        type: The type of value expected (e.g., "int", "color", "operator")
        domain: Set of possible values for this hole
        constraints: List of constraints that must be satisfied
    """
    
    id: str
    type: str
    domain: Set[Any] = field(default_factory=set)
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize Hole to dictionary.
        
        Returns:
            Dictionary representation of the hole
        """
        return {
            "id": self.id,
            "type": self.type,
            "domain": list(self.domain),
            "constraints": self.constraints,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Hole:
        """Deserialize Hole from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed Hole
        """
        return cls(
            id=data["id"],
            type=data["type"],
            domain=set(data.get("domain", [])),
            constraints=data.get("constraints", []),
        )
    
    def add_constraint(self, constraint: Dict[str, Any]) -> None:
        """Add a constraint to this hole.
        
        Args:
            constraint: Constraint dictionary with type and parameters
        """
        self.constraints.append(constraint)
    
    def refine_domain(self, new_domain: Set[Any]) -> None:
        """Refine the domain by intersecting with a new domain.
        
        Args:
            new_domain: New domain to intersect with current domain
        """
        if self.domain:
            self.domain = self.domain.intersection(new_domain)
        else:
            self.domain = new_domain
    
    def is_satisfied(self, value: Any) -> bool:
        """Check if a value satisfies all constraints.
        
        Args:
            value: The value to check
            
        Returns:
            True if value satisfies all constraints, False otherwise
        """
        # Check if value is in domain
        if self.domain and value not in self.domain:
            return False
        
        # Check all constraints
        for constraint in self.constraints:
            constraint_type = constraint.get("type")
            
            if constraint_type == "not_equal":
                if value == constraint.get("value"):
                    return False
            elif constraint_type == "in_range":
                min_val = constraint.get("min")
                max_val = constraint.get("max")
                if not (min_val <= value <= max_val):
                    return False
            elif constraint_type == "custom":
                # Custom constraint with a predicate function
                predicate = constraint.get("predicate")
                if predicate and not predicate(value):
                    return False
        
        return True


@dataclass
class ProgramSketch:
    """Represents a partial program with holes to be filled.
    
    A program sketch is a template that guides synthesis by providing
    a partial structure with holes that need to be instantiated.
    
    Attributes:
        stages: List of stages (can be Stage or Hole objects)
        constraints: Global constraints on the sketch
        metadata: Additional metadata about the sketch
    """
    
    stages: List[Union[Stage, Hole]]
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize ProgramSketch to dictionary.
        
        Returns:
            Dictionary representation of the sketch
        """
        stages_data = []
        for stage in self.stages:
            if isinstance(stage, Hole):
                stages_data.append({
                    "type": "hole",
                    "data": stage.to_dict()
                })
            elif isinstance(stage, Stage):
                stages_data.append({
                    "type": "stage",
                    "data": {
                        "operator": stage.operator,
                        "arguments": [str(arg) for arg in stage.arguments]
                    }
                })
            else:
                raise ValueError(f"Unknown stage type: {type(stage)}")
        
        return {
            "stages": stages_data,
            "constraints": self.constraints,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProgramSketch:
        """Deserialize ProgramSketch from dictionary.
        
        Args:
            data: Dictionary representation
            
        Returns:
            Reconstructed ProgramSketch
        """
        stages = []
        for stage_data in data["stages"]:
            if stage_data["type"] == "hole":
                stages.append(Hole.from_dict(stage_data["data"]))
            elif stage_data["type"] == "stage":
                # Note: This is a simplified reconstruction
                # In practice, you'd need to properly parse arguments
                stage_info = stage_data["data"]
                stages.append(Stage(
                    operator=stage_info["operator"],
                    arguments=tuple(stage_info["arguments"])
                ))
        
        return cls(
            stages=stages,
            constraints=data.get("constraints", []),
            metadata=data.get("metadata", {}),
        )
    
    def to_json(self) -> str:
        """Serialize ProgramSketch to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> ProgramSketch:
        """Deserialize ProgramSketch from JSON string.
        
        Args:
            json_str: JSON string representation
            
        Returns:
            Reconstructed ProgramSketch
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def get_holes(self) -> List[Hole]:
        """Get all holes in this sketch.
        
        Returns:
            List of all Hole objects in the sketch
        """
        return [stage for stage in self.stages if isinstance(stage, Hole)]
    
    def get_hole_by_id(self, hole_id: str) -> Optional[Hole]:
        """Get a hole by its ID.
        
        Args:
            hole_id: The ID of the hole to retrieve
            
        Returns:
            The Hole if found, None otherwise
        """
        for stage in self.stages:
            if isinstance(stage, Hole) and stage.id == hole_id:
                return stage
        return None
    
    def is_complete(self) -> bool:
        """Check if the sketch has no holes (is a complete program).
        
        Returns:
            True if sketch has no holes, False otherwise
        """
        return len(self.get_holes()) == 0
    
    def validate(self) -> bool:
        """Validate the sketch structure and constraints.
        
        Returns:
            True if sketch is valid, False otherwise
        """
        # Check that all hole IDs are unique
        hole_ids = [hole.id for hole in self.get_holes()]
        if len(hole_ids) != len(set(hole_ids)):
            return False
        
        # Check that all holes have non-empty domains
        for hole in self.get_holes():
            if not hole.domain:
                # Empty domain is allowed, but should be filled during synthesis
                pass
        
        # Additional validation can be added here
        return True
    
    def add_constraint(self, constraint: Dict[str, Any]) -> None:
        """Add a global constraint to the sketch.
        
        Args:
            constraint: Constraint dictionary with type and parameters
        """
        self.constraints.append(constraint)
